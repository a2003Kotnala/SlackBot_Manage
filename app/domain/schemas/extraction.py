import enum
from datetime import date
from pydantic import BaseModel, Field


class Confidence(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"
    needs_review = "needs_review"


class InsightItem(BaseModel):
    content: str
    confidence: Confidence = Confidence.medium


class ActionItem(InsightItem):
    owner: str | None = None
    due_date: date | None = None
    confidence: Confidence = Confidence.needs_review


class ExtractionResult(BaseModel):
    meeting_title: str = "Execution Review"
    summary: str = ""
    what_happened: str = ""
    status_summary: str = ""
    priority_focus: str = ""
    next_review_date: date | None = None
    decisions: list[InsightItem] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    owners: list[str] = Field(default_factory=list)
    due_dates: list[date] = Field(default_factory=list)
    open_questions: list[InsightItem] = Field(default_factory=list)
    risks: list[InsightItem] = Field(default_factory=list)
    confidence_overall: Confidence = Confidence.needs_review
