from datetime import datetime

from app.db.models.source import Source, SourceType
from app.db.models.user import User
from app.db.session import SessionLocal
from app.integrations.slack_client import slack_client


def resolve_latest_huddle_notes_canvas(
    channel_id: str, thread_ts: str | None, user_id: str
) -> Source | None:
    files = slack_client.list_files(channel_id, ts_from=thread_ts)
    canvases = [item for item in files if item.get("filetype") == "canvas"]
    if not canvases:
        return None

    latest_canvas = max(canvases, key=lambda item: item["timestamp"])
    canvas_content = slack_client.get_file_content(latest_canvas["id"])
    return create_source_record(
        source_type=SourceType.huddle_notes,
        raw_content=canvas_content.get("content", ""),
        user_id=user_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        slack_canvas_id=latest_canvas["id"],
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
