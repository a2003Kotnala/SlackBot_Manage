from typing import Optional
from app.integrations.slack_client import slack_client
from app.db.models.source import Source, SourceType
from app.db.session import SessionLocal
from app.domain.models.user import User
from datetime import datetime

async def resolve_latest_huddle_notes_canvas(channel_id: str, thread_ts: Optional[str], user_id: str) -> Optional[Source]:
    """
    Resolve the latest huddle notes canvas in the channel/thread.
    Returns a Source object if found, else None.
    """
    # Get recent files in the channel
    files = await slack_client.list_files(channel_id, ts_from=thread_ts)
    
    # Filter for canvases (assuming huddle notes are canvases)
    canvases = [f for f in files if f.get("filetype") == "canvas"]
    
    if not canvases:
        return None
    
    # Get the most recent canvas
    latest_canvas = max(canvases, key=lambda f: f["timestamp"])
    
    # Get canvas content
    canvas_content = await slack_client.get_file_content(latest_canvas["id"])
    
    # Create Source record
    db = SessionLocal()
    try:
        # Get or create user
        user = db.query(User).filter(User.slack_user_id == user_id).first()
        if not user:
            user = User(slack_user_id=user_id, name="", email="")
            db.add(user)
            db.commit()
            db.refresh(user)
        
        source = Source(
            source_type=SourceType.huddle_notes,
            slack_channel_id=channel_id,
            slack_thread_ts=thread_ts,
            slack_canvas_id=latest_canvas["id"],
            raw_content_reference=canvas_content.get("content", ""),
            created_by=user.id,
            created_at=datetime.utcnow()
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return source
    finally:
        db.close()