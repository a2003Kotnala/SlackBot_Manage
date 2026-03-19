import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Uuid

from app.db.base import Base


class DraftStatus(enum.Enum):
    draft = "draft"
    shared = "shared"
    archived = "archived"


class Draft(Base):
    __tablename__ = "drafts"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id = Column(Uuid, ForeignKey("users.id"))
    source_id = Column(Uuid, ForeignKey("sources.id"))
    slack_canvas_id = Column(String)
    title = Column(String)
    status = Column(Enum(DraftStatus))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
