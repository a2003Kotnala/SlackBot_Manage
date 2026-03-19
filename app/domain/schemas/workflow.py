from pydantic import BaseModel, Field

from app.domain.schemas.extraction import ExtractionResult


class WorkflowPreviewRequest(BaseModel):
    text: str = Field(min_length=1, description="Raw meeting notes or huddle summary.")
    source_label: str = "manual"


class WorkflowPreviewResponse(BaseModel):
    extraction: ExtractionResult
    draft_canvas_markdown: str


class WorkflowProcessTextRequest(BaseModel):
    text: str = Field(min_length=1, description="Raw meeting notes or huddle summary.")
    user_id: str = "api-user"
    channel_id: str | None = None
    thread_ts: str | None = None
    publish_to_slack: bool = False


class WorkflowProcessTextResponse(BaseModel):
    source_id: str
    draft_id: str
    draft_title: str
    slack_canvas_id: str | None = None
    extraction: ExtractionResult
    draft_canvas_markdown: str
