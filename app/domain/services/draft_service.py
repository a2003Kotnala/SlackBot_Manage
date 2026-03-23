import re
from datetime import datetime
from uuid import UUID

from app.config import settings
from app.db.models.draft import Draft, DraftStatus
from app.db.models.extracted_item import Confidence, ExtractedItem, ItemType
from app.db.models.source import Source
from app.db.models.user import User
from app.db.session import SessionLocal
from app.domain.schemas.extraction import ExtractionResult
from app.domain.services.canvas_composer import create_draft_canvas
from app.integrations.slack_client import slack_client
from app.logger import logger


def create_draft(
    owner_user_id: str | UUID | None,
    source: Source,
    extraction: ExtractionResult,
    publish_to_slack: bool = True,
) -> tuple[Draft, str]:
    now = datetime.utcnow()
    display_now = datetime.now()
    resolved_owner_user_id = _resolve_owner_user_id(owner_user_id, source)
    owner_slack_user_id = _resolve_owner_slack_user_id(resolved_owner_user_id)
    compact_header = _uses_compact_canvas_title(source.slack_channel_id)
    canvas_title = build_canvas_title_for_channel(
        extraction.meeting_title,
        source.slack_channel_id,
        display_now,
    )
    canvas_content = create_draft_canvas(
        extraction,
        source.source_type.value,
        title_override=canvas_title,
        compact_header=compact_header,
    )
    file = None

    should_publish = (
        publish_to_slack
        and settings.slack_publish_drafts
        and slack_client.is_configured()
        and bool(source.slack_channel_id)
    )
    if should_publish:
        try:
            file = slack_client.upload_canvas(
                channel_id=source.slack_channel_id,
                content=canvas_content,
                title=canvas_title,
                slack_user_id=owner_slack_user_id,
            )
        except Exception as exc:  # pragma: no cover - external integration
            logger.warning(
                "Slack canvas upload failed; continuing with local draft only: %s",
                exc,
            )

    db = SessionLocal()
    try:
        draft = Draft(
            owner_user_id=resolved_owner_user_id,
            source_id=source.id,
            slack_canvas_id=file["id"] if file else None,
            title=file["title"] if file else canvas_title,
            status=DraftStatus.draft,
            created_at=now,
            updated_at=now,
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)

        db.add(
            ExtractedItem(
                draft_id=draft.id,
                item_type=ItemType.summary,
                content=extraction.summary,
                confidence=_map_confidence(extraction.confidence_overall),
                assignee=None,
                due_date=None,
                created_at=now,
            )
        )

        for item in extraction.decisions:
            db.add(
                ExtractedItem(
                    draft_id=draft.id,
                    item_type=ItemType.decision,
                    content=item.content,
                    confidence=_map_confidence(item.confidence),
                    assignee=None,
                    due_date=None,
                    created_at=now,
                )
            )

        for item in extraction.action_items:
            db.add(
                ExtractedItem(
                    draft_id=draft.id,
                    item_type=ItemType.action_item,
                    content=item.content,
                    confidence=_map_confidence(item.confidence),
                    assignee=item.owner,
                    due_date=item.due_date,
                    created_at=now,
                )
            )

        for item in extraction.open_questions:
            db.add(
                ExtractedItem(
                    draft_id=draft.id,
                    item_type=ItemType.question,
                    content=item.content,
                    confidence=_map_confidence(item.confidence),
                    assignee=None,
                    due_date=None,
                    created_at=now,
                )
            )

        for item in extraction.risks:
            db.add(
                ExtractedItem(
                    draft_id=draft.id,
                    item_type=ItemType.blocker,
                    content=item.content,
                    confidence=_map_confidence(item.confidence),
                    assignee=None,
                    due_date=None,
                    created_at=now,
                )
            )

        db.commit()
        db.refresh(draft)
        return draft, canvas_content
    finally:
        db.close()


def _map_confidence(value):
    return Confidence[value.value]


def _resolve_owner_user_id(
    owner_user_id: str | UUID | None, source: Source
) -> UUID | None:
    if isinstance(owner_user_id, UUID):
        return owner_user_id
    if isinstance(owner_user_id, str):
        try:
            return UUID(owner_user_id)
        except ValueError:
            pass
    return source.created_by


def _resolve_owner_slack_user_id(owner_user_id: UUID | None) -> str | None:
    if owner_user_id is None:
        return None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == owner_user_id).first()
        return user.slack_user_id if user else None
    finally:
        db.close()


def build_canvas_title_for_channel(
    meeting_title: str,
    channel_id: str | None,
    now: datetime | None = None,
) -> str:
    current_time = now or datetime.now()
    raw_title = (meeting_title or "").strip()
    if _uses_compact_canvas_title(channel_id):
        descriptor = _build_compact_descriptor(raw_title)
        return f"{descriptor} | {current_time.strftime('%d %b %I:%M %p')}"
    normalized = _normalize_meeting_title(raw_title, current_time)
    return f"Action Canvas - {normalized[:80]}"


def _normalize_meeting_title(meeting_title: str, now: datetime) -> str:
    normalized = (meeting_title or "").strip()
    if not normalized:
        normalized = f"Meeting - {now.strftime('%Y-%m-%d')}"
    return normalized


def _build_compact_descriptor(meeting_title: str) -> str:
    if not meeting_title:
        return "Meeting Notes"

    tokens = re.findall(r"[A-Za-z0-9']+", meeting_title)
    if not tokens:
        return "Meeting Notes"

    stop_words = {
        "a",
        "an",
        "and",
        "for",
        "in",
        "of",
        "on",
        "the",
        "to",
        "with",
    }
    meaningful_tokens = [token for token in tokens if token.lower() not in stop_words]
    descriptor_tokens = (meaningful_tokens or tokens)[:3]
    return " ".join(descriptor_tokens)[:40] or "Meeting Notes"


def _uses_compact_canvas_title(channel_id: str | None) -> bool:
    return bool(channel_id and channel_id.startswith("D"))
