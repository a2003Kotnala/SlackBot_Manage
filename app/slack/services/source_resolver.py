from __future__ import annotations

import re
from datetime import datetime

from app.db.models.source import Source, SourceType
from app.db.models.user import User
from app.db.session import SessionLocal
from app.integrations.slack_client import slack_client

TRANSCRIPT_NAME_MARKERS = (
    "huddle transcript",
    "transcript",
)
TEXT_FILE_TYPES = {"text", "csv", "markdown", "md", "txt"}
THIN_CANVAS_MARKERS = (
    "slack ai took notes for this huddle",
    "attendees",
    "summary",
    "view huddle in channel",
)


def resolve_latest_huddle_notes_canvas(
    channel_id: str, thread_ts: str | None, user_id: str
) -> Source | None:
    files = slack_client.list_files(channel_id, ts_from=thread_ts)
    canvases = [item for item in files if item.get("filetype") == "canvas"]
    latest_canvas = max(canvases, key=_file_timestamp) if canvases else None
    canvas_content = _load_canvas_content(latest_canvas) if latest_canvas else ""
    transcript_text = None
    if not canvas_content or _is_thin_canvas_content(canvas_content):
        transcript_text = _resolve_transcript_text(
            files=files,
            latest_canvas=latest_canvas,
            canvas_content=canvas_content,
            fallback_ts=thread_ts,
        )
    raw_content = _select_best_source_text(canvas_content, transcript_text)
    if not raw_content:
        return None

    return create_source_record(
        source_type=SourceType.huddle_notes,
        raw_content=raw_content,
        user_id=user_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        slack_canvas_id=latest_canvas["id"] if latest_canvas else None,
    )


def create_text_source(
    raw_content: str,
    user_id: str,
    channel_id: str | None = None,
    thread_ts: str | None = None,
) -> Source:
    return create_source_record(
        source_type=SourceType.text,
        raw_content=raw_content,
        user_id=user_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        slack_canvas_id=None,
    )


def create_source_record(
    source_type: SourceType,
    raw_content: str,
    user_id: str,
    channel_id: str | None,
    thread_ts: str | None,
    slack_canvas_id: str | None,
) -> Source:
    db = SessionLocal()
    now = datetime.utcnow()
    try:
        user = db.query(User).filter(User.slack_user_id == user_id).first()
        if not user:
            user = User(
                slack_user_id=user_id,
                name="",
                email="",
                created_at=now,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        source = Source(
            source_type=source_type,
            slack_channel_id=channel_id,
            slack_thread_ts=thread_ts,
            slack_canvas_id=slack_canvas_id,
            raw_content_reference=raw_content,
            created_by=user.id,
            created_at=now,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return source
    finally:
        db.close()


def _load_canvas_content(canvas_file: dict | None) -> str:
    if not canvas_file:
        return ""
    details = slack_client.get_file_content(canvas_file["id"])
    return _coerce_text(details.get("content"))


def _resolve_transcript_text(
    files: list[dict],
    latest_canvas: dict | None,
    canvas_content: str,
    fallback_ts: str | None,
) -> str | None:
    transcript = _select_best_transcript_candidate(
        files=files,
        latest_canvas=latest_canvas,
        canvas_content=canvas_content,
        fallback_ts=fallback_ts,
    )
    if not transcript:
        return None

    full_details = slack_client.get_file_content(transcript["id"])
    merged_details = {**transcript, **full_details}
    preview = _extract_inline_file_text(merged_details)
    if preview:
        return preview

    download_url = (
        merged_details.get("url_private_download") or merged_details.get("url_private")
    )
    if not download_url:
        return None

    downloaded = slack_client.download_text_file(download_url).strip()
    return downloaded or None


def _select_best_source_text(
    canvas_content: str,
    transcript_text: str | None,
) -> str:
    if transcript_text and _is_thin_canvas_content(canvas_content):
        return transcript_text
    return canvas_content or transcript_text or ""


def _select_best_transcript_candidate(
    files: list[dict],
    latest_canvas: dict | None,
    canvas_content: str,
    fallback_ts: str | None,
) -> dict | None:
    reference_ts = _reference_timestamp(latest_canvas, fallback_ts)
    transcript_hints = _extract_transcript_hints(latest_canvas, canvas_content)
    candidates = [
        file_info
        for file_info in files
        if _is_transcript_candidate(file_info, latest_canvas, transcript_hints)
    ]
    if not candidates:
        return None

    return max(
        candidates,
        key=lambda file_info: _score_transcript_candidate(
            file_info, transcript_hints, reference_ts
        ),
    )


def _extract_transcript_hints(
    latest_canvas: dict | None,
    canvas_content: str,
) -> set[str]:
    hints: set[str] = set()
    for value in (
        (latest_canvas or {}).get("title"),
        (latest_canvas or {}).get("name"),
        canvas_content,
    ):
        if not isinstance(value, str):
            continue
        normalized_value = _normalize_name(value)
        if any(marker in normalized_value for marker in TRANSCRIPT_NAME_MARKERS):
            hints.add(normalized_value)
        for match in re.finditer(
            r"([a-z0-9][a-z0-9 ._-]{0,120}(?:transcript)[a-z0-9 ._-]{0,40})",
            normalized_value,
        ):
            hints.add(match.group(1).strip())
    return hints


def _is_transcript_candidate(
    file_info: dict,
    latest_canvas: dict | None,
    transcript_hints: set[str],
) -> bool:
    if file_info.get("filetype") == "canvas":
        return False
    if latest_canvas and file_info.get("id") == latest_canvas.get("id"):
        return False

    normalized_name = _normalized_file_name(file_info)
    if not normalized_name:
        return False

    if any(
        hint == normalized_name
        or hint in normalized_name
        or normalized_name in hint
        for hint in transcript_hints
    ):
        return True

    return any(marker in normalized_name for marker in TRANSCRIPT_NAME_MARKERS)


def _score_transcript_candidate(
    file_info: dict,
    transcript_hints: set[str],
    reference_ts: float | None,
) -> float:
    score = 0.0
    normalized_name = _normalized_file_name(file_info)
    if any(hint == normalized_name for hint in transcript_hints):
        score += 100
    elif any(
        hint in normalized_name or normalized_name in hint for hint in transcript_hints
    ):
        score += 60

    if "huddle transcript" in normalized_name:
        score += 30
    elif "transcript" in normalized_name:
        score += 20

    if _is_likely_text_file(file_info):
        score += 10

    file_ts = _file_timestamp(file_info)
    if reference_ts is not None and file_ts is not None:
        score += max(0, 25 - min(abs(reference_ts - file_ts), 25))
    elif file_ts is not None:
        score += file_ts / 1_000_000_000

    return score


def _extract_inline_file_text(file_info: dict) -> str | None:
    preview = _coerce_text(file_info.get("preview"))
    if preview and _is_likely_text_file(file_info):
        return preview
    return _coerce_text(file_info.get("content")) or None


def _is_likely_text_file(file_info: dict) -> bool:
    mimetype = _coerce_text(file_info.get("mimetype")).lower()
    filetype = _coerce_text(file_info.get("filetype")).lower()
    return (
        mimetype.startswith("text/")
        or filetype in TEXT_FILE_TYPES
        or bool(file_info.get("preview"))
    )


def _is_thin_canvas_content(content: str) -> bool:
    normalized = " ".join(content.lower().split())
    if not normalized:
        return True

    if "huddle transcript" in normalized and len(normalized) < 600:
        return True

    if all(marker in normalized for marker in THIN_CANVAS_MARKERS):
        return len(normalized) < 800

    return len(normalized) < 160


def _reference_timestamp(
    latest_canvas: dict | None,
    fallback_ts: str | None,
) -> float | None:
    file_ts = _file_timestamp(latest_canvas or {})
    if file_ts is not None:
        return file_ts
    if fallback_ts is None:
        return None
    try:
        return float(fallback_ts)
    except (TypeError, ValueError):
        return None


def _file_timestamp(file_info: dict) -> float:
    for key in ("timestamp", "created"):
        value = file_info.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _normalized_file_name(file_info: dict) -> str:
    return _normalize_name(file_info.get("title") or file_info.get("name") or "")


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _coerce_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""
