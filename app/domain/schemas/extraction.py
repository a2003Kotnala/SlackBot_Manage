import enum
from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator


class Confidence(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"
    needs_review = "needs_review"


class InsightItem(BaseModel):
    content: str
    confidence: Confidence = Confidence.medium

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return " ".join((value or "").split()).strip()


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

    @field_validator(
        "meeting_title",
        "summary",
        "what_happened",
        "status_summary",
        "priority_focus",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return " ".join((value or "").split()).strip()

    @model_validator(mode="after")
    def deduplicate_and_derive_fields(self):
        self.decisions = _dedupe_items(self.decisions)
        self.action_items = _dedupe_action_items(self.action_items)
        self.open_questions = _dedupe_items(self.open_questions)
        self.risks = _dedupe_items(self.risks)

        if not self.owners:
            self.owners = list(
                dict.fromkeys(item.owner for item in self.action_items if item.owner)
            )
        if not self.due_dates:
            self.due_dates = list(
                dict.fromkeys(
                    item.due_date for item in self.action_items if item.due_date
                )
            )
        return self


def _dedupe_items(items: list[InsightItem]) -> list[InsightItem]:
    deduped: list[InsightItem] = []
    seen: set[str] = set()
    for item in items:
        key = item.content.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _dedupe_action_items(items: list[ActionItem]) -> list[ActionItem]:
    deduped: list[ActionItem] = []
    seen: set[tuple[str, str | None, date | None]] = set()
    for item in items:
        key = (item.content.casefold(), item.owner, item.due_date)
        if not item.content or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
