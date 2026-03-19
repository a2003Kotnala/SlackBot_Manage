import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Uuid

from app.db.base import Base


class ShareType(enum.Enum):
    channel = "channel"
    user = "user"


class Share(Base):
    __tablename__ = "shares"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    draft_id = Column(Uuid, ForeignKey("drafts.id"))
    share_type = Column(Enum(ShareType))
    target_id = Column(String)
    shared_by = Column(Uuid, ForeignKey("users.id"))
    shared_at = Column(DateTime)
