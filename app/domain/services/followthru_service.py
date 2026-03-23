from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.config import settings
from app.db.models.chat_message import ChatMessage, ChatRole
from app.db.models.chat_session import ChatSession
from app.db.models.source import SourceType
from app.db.models.user import User
from app.db.session import SessionLocal
from app.domain.schemas.extraction import ExtractionResult
from app.domain.schemas.followthru import (
    FollowThruCapabilitiesResponse,
    FollowThruChatRequest,
    FollowThruMode,
    FollowThruResponse,
    FollowThruVoiceCommandRequest,
)
from app.domain.services.canvas_composer import create_draft_canvas
from app.domain.services.draft_service import (
    build_canvas_title_for_channel,
    create_draft,
)
from app.domain.services.extraction_service import extract_structured_meeting_data
from app.integrations.openai_client import openai_client
from app.logger import logger
from app.slack.services.source_resolver import (
    create_source_record,
    resolve_latest_huddle_notes_canvas,
)

PRIMARY_SLACK_COMMAND = "/followthru"
LEGACY_SLACK_COMMAND = "/zmanage"
LATEST_CANVAS_HINTS = (
    "latest huddle",
    "latest huddle notes",
    "latest canvas",
    "latest notes",
    "current huddle",
)
MODE_PATTERNS: list[tuple[FollowThruMode, tuple[str, ...]]] = [
    (FollowThruMode.help, ("help", "what can you do", "capabilities", "how do i use")),
    (
        FollowThruMode.preview,
        ("preview", "show preview", "dry run", "generate preview"),
    ),
    (FollowThruMode.draft, ("draft", "save draft", "create draft")),
    (
        FollowThruMode.publish,
        ("publish", "ship it", "update canvas", "send to canvas", "push to canvas"),
    ),
]


@dataclass
class ParsedFollowThruRequest:
    mode: FollowThruMode
    notes: str
    use_latest_canvas: bool
    normalized_input: str


@dataclass
class FollowThruExecution:
    mode: FollowThruMode
    reply: str
    source_id: str | None = None
    draft_id: str | None = None
    draft_title: str | None = None
    slack_canvas_id: str | None = None
    draft_canvas_markdown: str | None = None
    extraction: ExtractionResult | None = None


@dataclass
class FollowThruClearResult:
    cleared_sessions: int = 0
    cleared_messages: int = 0


def handle_followthru_chat(payload: FollowThruChatRequest) -> FollowThruResponse:
    return _handle_followthru_input(
        raw_input=payload.message,
        user_id=payload.user_id,
        channel_id=payload.channel_id,
        thread_ts=payload.thread_ts,
        session_id=payload.session_id,
        source_type=SourceType.text,
        persist_preview_source=False,
    )


def clear_followthru_dm_session(channel_id: str | None) -> FollowThruClearResult:
    if not channel_id:
        return FollowThruClearResult()

    db = SessionLocal()
    try:
        session_ids = [
            session_id
            for (session_id,) in (
                db.query(ChatSession.id)
                .filter(ChatSession.slack_channel_id == channel_id)
                .all()
            )
        ]
        if not session_ids:
            return FollowThruClearResult()

        deleted_messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id.in_(session_ids))
            .delete(synchronize_session=False)
        )
        deleted_sessions = (
            db.query(ChatSession)
            .filter(ChatSession.id.in_(session_ids))
            .delete(synchronize_session=False)
        )

        db.commit()
        return FollowThruClearResult(
            cleared_sessions=deleted_sessions,
            cleared_messages=deleted_messages,
        )
    finally:
        db.close()


def handle_followthru_voice_command(
    payload: FollowThruVoiceCommandRequest,
) -> FollowThruResponse:
    return _handle_followthru_input(
        raw_input=payload.transcript,
        user_id=payload.user_id,
        channel_id=payload.channel_id,
        thread_ts=payload.thread_ts,
        session_id=payload.session_id,
        source_type=SourceType.voice,
        persist_preview_source=True,
    )


def build_followthru_capabilities() -> FollowThruCapabilitiesResponse:
    return FollowThruCapabilitiesResponse(
        bot_name=settings.app_name,
        primary_slack_command=PRIMARY_SLACK_COMMAND,
        legacy_slack_command=LEGACY_SLACK_COMMAND,
        supports_chat=True,
        supports_voice_transcript_commands=True,
        supports_slack_canvas_publish=True,
        supports_latest_huddle_resolution=True,
        supported_modes=[
            FollowThruMode.help,
            FollowThruMode.chat,
            FollowThruMode.preview,
            FollowThruMode.draft,
            FollowThruMode.publish,
        ],
        quickstart_examples=[
            (
                "/followthru preview Decision: Ship pilot. "
                "Action: Prepare demo @maya 2026-03-25"
            ),
            "FollowThru, use the latest huddle notes and draft the action canvas.",
            (
                "Voice command: publish these notes "
                "to the canvas after extracting actions."
            ),
        ],
    )


def _handle_followthru_input(
    raw_input: str,
    user_id: str,
    channel_id: str | None,
    thread_ts: str | None,
    session_id: str | None,
    source_type: SourceType,
    persist_preview_source: bool,
) -> FollowThruResponse:
    parsed = _parse_followthru_request(raw_input)
    db = SessionLocal()
    session = None
    try:
        session = _get_or_create_session(
            db=db,
            session_id=session_id,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )
        _store_message(db, session.id, ChatRole.user, parsed.normalized_input)

        execution = _execute_request(
            parsed=parsed,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            source_type=source_type,
            persist_preview_source=persist_preview_source,
            history=_load_recent_history(db, session.id),
        )

        _store_message(db, session.id, ChatRole.assistant, execution.reply)
        session.updated_at = _utcnow()
        if not session.title:
            session.title = _derive_session_title(parsed.normalized_input, execution)
        db.add(session)
        db.commit()

        return FollowThruResponse(
            bot_name=settings.app_name,
            session_id=str(session.id),
            mode=execution.mode,
            reply=execution.reply,
            source_id=execution.source_id,
            draft_id=execution.draft_id,
            draft_title=execution.draft_title,
            slack_canvas_id=execution.slack_canvas_id,
            draft_canvas_markdown=execution.draft_canvas_markdown,
            extraction=execution.extraction,
            normalized_input=parsed.normalized_input,
        )
    finally:
        db.close()


def _get_or_create_session(
    db,
    session_id: str | None,
    user_id: str,
    channel_id: str | None,
    thread_ts: str | None,
) -> ChatSession:
    session = None
    if session_id:
        try:
            session = (
                db.query(ChatSession).filter(ChatSession.id == UUID(session_id)).first()
            )
        except ValueError:
            session = None

    if session:
        return session

    now = _utcnow()
    user_uuid = _resolve_user_id(db, user_id, now)
    session = ChatSession(
        id=uuid4(),
        bot_name=settings.app_name,
        user_id=user_uuid,
        slack_channel_id=channel_id,
        slack_thread_ts=thread_ts,
        title=None,
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _resolve_user_id(db, external_user_id: str, now: datetime) -> UUID:
    existing = db.query(User).filter(User.slack_user_id == external_user_id).first()
    if existing:
        return existing.id

    user = User(
        slack_user_id=external_user_id,
        name="",
        email="",
        created_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user.id


def _store_message(db, session_id: UUID, role: ChatRole, content: str) -> None:
    db.add(
        ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            created_at=_utcnow(),
        )
    )
    db.commit()


def _load_recent_history(db, session_id: UUID) -> list[dict[str, str]]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(settings.followthru_chat_history_limit)
        .all()
    )
    return [
        {"role": row.role.value, "content": row.content}
        for row in reversed(rows)
        if row.role in {ChatRole.user, ChatRole.assistant}
    ]


def _execute_request(
    parsed: ParsedFollowThruRequest,
    user_id: str,
    channel_id: str | None,
    thread_ts: str | None,
    source_type: SourceType,
    persist_preview_source: bool,
    history: list[dict[str, str]],
) -> FollowThruExecution:
    if parsed.mode == FollowThruMode.help:
        return FollowThruExecution(
            mode=FollowThruMode.help,
            reply=_build_help_reply(),
        )

    if parsed.mode in {
        FollowThruMode.preview,
        FollowThruMode.draft,
        FollowThruMode.publish,
    }:
        return _execute_canvas_request(
            parsed=parsed,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            source_type=source_type,
            persist_preview_source=persist_preview_source,
        )

    reply = _build_chat_reply(history, parsed.normalized_input)
    return FollowThruExecution(mode=FollowThruMode.chat, reply=reply)


def _execute_canvas_request(
    parsed: ParsedFollowThruRequest,
    user_id: str,
    channel_id: str | None,
    thread_ts: str | None,
    source_type: SourceType,
    persist_preview_source: bool,
) -> FollowThruExecution:
    source = None
    source_label = source_type.value
    raw_content = parsed.notes

    if parsed.use_latest_canvas or not raw_content:
        if channel_id:
            source = resolve_latest_huddle_notes_canvas(channel_id, thread_ts, user_id)
            if source:
                raw_content = source.raw_content_reference or ""
                source_label = getattr(
                    getattr(source, "source_type", None), "value", source_label
                )
        if not raw_content:
            return FollowThruExecution(
                mode=parsed.mode,
                reply=(
                    "I could not find huddle notes to work from. "
                    "Send inline notes or mention that I should use "
                    "the latest huddle notes in a Slack channel."
                ),
            )

    should_persist_source = parsed.mode in {
        FollowThruMode.draft,
        FollowThruMode.publish,
    }
    should_persist_source = should_persist_source or persist_preview_source

    if raw_content and source is None and should_persist_source:
        source = create_source_record(
            source_type=source_type,
            raw_content=raw_content,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            slack_canvas_id=None,
        )
        source_label = source.source_type.value

    extraction = extract_structured_meeting_data(raw_content)
    tracking_summary = _build_tracking_summary(extraction)

    if parsed.mode == FollowThruMode.preview:
        compact_header = bool(channel_id and channel_id.startswith("D"))
        canvas = create_draft_canvas(
            extraction,
            source_label,
            title_override=build_canvas_title_for_channel(
                extraction.meeting_title,
                channel_id,
                datetime.now(),
            ),
            compact_header=compact_header,
        )
        return FollowThruExecution(
            mode=FollowThruMode.preview,
            reply=(
                f"Preview ready for {extraction.meeting_title}. "
                f"{tracking_summary} "
                "Use publish when you are ready to update the Slack canvas."
            ),
            source_id=str(source.id) if source else None,
            draft_canvas_markdown=canvas,
            extraction=extraction,
        )

    if source is None:
        source = create_source_record(
            source_type=source_type,
            raw_content=raw_content,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            slack_canvas_id=None,
        )

    draft, canvas = create_draft(
        owner_user_id=source.created_by,
        source=source,
        extraction=extraction,
        publish_to_slack=parsed.mode == FollowThruMode.publish,
    )

    if draft.slack_canvas_id:
        if channel_id and channel_id.startswith("D"):
            reply = (
                f"Published standalone canvas {draft.title}. "
                f"{tracking_summary} "
                "It should appear in Slack Files/Canvases so you can edit it "
                f"and share it to channels. Slack canvas ID: {draft.slack_canvas_id}."
            )
        else:
            reply = (
                f"Published {draft.title}. "
                f"{tracking_summary} Slack canvas ID: {draft.slack_canvas_id}."
            )
    elif parsed.mode == FollowThruMode.draft:
        reply = f"Saved local draft {draft.title}. {tracking_summary}"
    else:
        reply = (
            f"Saved local draft {draft.title}. "
            f"{tracking_summary} "
            "Slack publication was unavailable, so the canvas was not updated."
        )

    return FollowThruExecution(
        mode=parsed.mode,
        reply=reply,
        source_id=str(source.id),
        draft_id=str(draft.id),
        draft_title=draft.title,
        slack_canvas_id=draft.slack_canvas_id,
        draft_canvas_markdown=canvas,
        extraction=extraction,
    )


def _parse_followthru_request(raw_input: str) -> ParsedFollowThruRequest:
    normalized = _normalize_input(raw_input)
    lowered = normalized.lower()
    use_latest_canvas = any(phrase in lowered for phrase in LATEST_CANVAS_HINTS)

    mode = FollowThruMode.chat
    for candidate_mode, patterns in MODE_PATTERNS:
        if any(lowered.startswith(pattern) for pattern in patterns):
            mode = candidate_mode
            break

    if mode == FollowThruMode.chat and "canvas" in lowered:
        if "publish" in lowered or "update" in lowered:
            mode = FollowThruMode.publish
        elif "draft" in lowered or "save" in lowered:
            mode = FollowThruMode.draft
        elif any(
            keyword in lowered for keyword in ("preview", "show", "generate", "create")
        ):
            mode = FollowThruMode.preview

    notes = _strip_command_prefix(normalized, mode)
    if (
        mode in {FollowThruMode.preview, FollowThruMode.draft, FollowThruMode.publish}
        and not notes
    ):
        use_latest_canvas = True

    if not normalized:
        mode = FollowThruMode.help

    return ParsedFollowThruRequest(
        mode=mode,
        notes=notes,
        use_latest_canvas=use_latest_canvas,
        normalized_input=normalized,
    )


def _normalize_input(raw_input: str) -> str:
    stripped = raw_input.strip()
    stripped = re.sub(
        r"^\s*(followthru|follow through)\s*[:,]?\s*", "", stripped, flags=re.IGNORECASE
    )
    return " ".join(stripped.split())


def _strip_command_prefix(text: str, mode: FollowThruMode) -> str:
    lowered = text.lower()
    prefixes: tuple[str, ...] = ()
    if mode == FollowThruMode.preview:
        prefixes = ("preview", "show preview", "dry run", "generate preview")
    elif mode == FollowThruMode.draft:
        prefixes = ("draft", "save draft", "create draft")
    elif mode == FollowThruMode.publish:
        prefixes = (
            "publish",
            "ship it",
            "update canvas",
            "send to canvas",
            "push to canvas",
        )
    elif mode == FollowThruMode.help:
        return ""
    else:
        return text

    for prefix in prefixes:
        if lowered.startswith(prefix):
            remainder = text[len(prefix) :].strip(" :,-")
            remainder = re.sub(
                (
                    r"^(using|from|with)\s+(the\s+)?"
                    r"(latest\s+huddle\s+notes|latest\s+canvas|latest\s+notes)\b[:, -]*"
                ),
                "",
                remainder,
                flags=re.IGNORECASE,
            )
            remainder = re.sub(
                r"^(using|from|with)\s+(these|this)\s+notes\b[:, -]*",
                "",
                remainder,
                flags=re.IGNORECASE,
            )
            return remainder.strip()
    return text


def _build_tracking_summary(extraction) -> str:
    return (
        f"{len(extraction.action_items)} action item(s), "
        f"{len(extraction.risks) + len(extraction.open_questions)} attention item(s)."
    )


def _build_help_reply() -> str:
    return (
        "FollowThru can chat, preview a canvas, save a local draft, "
        "or publish to Slack. "
        "Try '/followthru preview <notes>' in Slack, "
        "'FollowThru, draft these notes: ...' in chat, "
        "or send a voice transcript such as "
        "'publish these notes to the canvas'."
    )


def _build_chat_reply(history: list[dict[str, str]], normalized_input: str) -> str:
    if openai_client.is_configured():
        try:
            return openai_client.generate_followthru_reply(
                messages=history,
                user_input=normalized_input,
            )
        except Exception as exc:  # pragma: no cover - external integration
            logger.warning(
                "FollowThru chat completion failed; using deterministic fallback: %s",
                exc,
            )

    lowered = normalized_input.lower()
    if any(
        keyword in lowered for keyword in ("what can you do", "help", "capabilities")
    ):
        return _build_help_reply()
    return (
        "FollowThru is ready. Ask me to preview, draft, "
        "or publish an action canvas from notes, "
        "or tell me to use the latest huddle notes in Slack."
    )


def _derive_session_title(message: str, execution: FollowThruExecution) -> str:
    if execution.extraction:
        return execution.extraction.meeting_title[:120]
    return message[:120] or "FollowThru Session"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
