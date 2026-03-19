import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Uuid

from app.db.base import Base


class SourceType(enum.Enum):
    huddle_notes = "huddle_notes"
    text = "text"
    csv = "csv"
    voice = "voice"
    thread = "thread"


class Source(Base):
    __tablename__ = "sources"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    source_type = Column(Enum(SourceType))
    slack_channel_id = Column(String)
    slack_thread_ts = Column(String)
    slack_canvas_id = Column(String)
    raw_content_reference = Column(String)
    created_by = Column(Uuid, ForeignKey("users.id"))
    created_at = Column(DateTime)
