from pydantic import BaseModel
from typing import List, Optional
from datetime import date
import enum

class Confidence(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"
    needs_review = "needs_review"

class ActionItem(BaseModel):
    content: str
    owner: Optional[str] = None
    due_date: Optional[date] = None

class ExtractionResult(BaseModel):
    summary: str
    what_happened: str
    decisions: List[str]
    action_items: List[ActionItem]
    owners: List[str]
    due_dates: List[date]
    open_questions: List[str]
    risks: List[str]
    confidence_overall: Confidence