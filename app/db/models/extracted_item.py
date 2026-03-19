import enum
import uuid

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, String, Uuid

from app.db.base import Base


class ItemType(enum.Enum):
    summary = "summary"
    decision = "decision"
    action_item = "action_item"
    owner = "owner"
    due_date = "due_date"
    question = "question"
    blocker = "blocker"


class Confidence(enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"
    needs_review = "needs_review"


class ExtractedItem(Base):
    __tablename__ = "extracted_items"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    draft_id = Column(Uuid, ForeignKey("drafts.id"))
    item_type = Column(Enum(ItemType))
    content = Column(String)
    confidence = Column(Enum(Confidence))
    assignee = Column(String)
    due_date = Column(Date)
    created_at = Column(DateTime)
