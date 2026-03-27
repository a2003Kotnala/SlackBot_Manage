from fastapi import APIRouter

from app.domain.schemas.workflow import (
    WorkflowPreviewRequest,
    WorkflowPreviewResponse,
    WorkflowProcessTextRequest,
    WorkflowProcessTextResponse,
)
from app.domain.services.canvas_composer import create_draft_canvas
from app.domain.services.draft_service import create_draft
from app.domain.services.extraction_service import extract_structured_meeting_data
from app.slack.services.source_resolver import create_text_source

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


@router.post("/preview", response_model=WorkflowPreviewResponse)
def preview_workflow(payload: WorkflowPreviewRequest) -> WorkflowPreviewResponse:
    extraction = extract_structured_meeting_data(payload.text)
    canvas = create_draft_canvas(extraction, payload.source_label)
    return WorkflowPreviewResponse(
        extraction=extraction,
        draft_canvas_markdown=canvas,
    )


@router.post("/process-text", response_model=WorkflowProcessTextResponse)
def process_text_workflow(
    payload: WorkflowProcessTextRequest,
) -> WorkflowProcessTextResponse:
    source = create_text_source(
        raw_content=payload.text,
        user_id=payload.user_id,
        channel_id=payload.channel_id,
        thread_ts=payload.thread_ts,
    )
    extraction = extract_structured_meeting_data(source.raw_content_reference)
    draft, canvas = create_draft(
        owner_user_id=source.created_by,
        source=source,
        extraction=extraction,
        publish_to_slack=payload.publish_to_slack,
    )
    return WorkflowProcessTextResponse(
        source_id=str(source.id),
        draft_id=str(draft.id),
        draft_title=draft.title,
        slack_canvas_id=draft.slack_canvas_id,
        extraction=extraction,
        draft_canvas_markdown=canvas,
    )