from datetime import date

from app.domain.schemas.extraction import (
    ActionItem,
    Confidence,
    ExtractionResult,
    InsightItem,
)
from app.domain.services.canvas_composer import create_draft_canvas


def test_create_draft_canvas_renders_tracking_tables_and_checklist():
    extraction = ExtractionResult(
        meeting_title="Launch Readiness Review",
        summary="Reviewed launch readiness.",
        what_happened="The team confirmed scope and assigned follow-ups.",
        status_summary="Execution in progress",
        priority_focus="Prepare beta checklist",
        next_review_date=date(2026, 3, 20),
        decisions=[InsightItem(content="Launch internal beta", confidence=Confidence.high)],
        action_items=[
            ActionItem(
                content="Prepare beta checklist",
                owner="maya",
                due_date=date(2026, 3, 20),
                confidence=Confidence.high,
            )
        ],
        owners=["maya"],
        due_dates=[date(2026, 3, 20)],
        open_questions=[
            InsightItem(
                content="Who signs off on release messaging?",
                confidence=Confidence.needs_review,
            )
        ],
        risks=[
            InsightItem(
                content="QA bandwidth is still limited.",
                confidence=Confidence.medium,
            )
        ],
        confidence_overall=Confidence.high,
    )

    canvas = create_draft_canvas(extraction, "manual-demo")

    assert "## Tracking Snapshot" in canvas
    assert "| Metric | Value |" in canvas
    assert "## Action Tracker" in canvas
    assert "| ID | Action | Owner | Due | Status | Priority | Notes |" in canvas
    assert "Prepare beta checklist" in canvas
    assert "## Attention Log" in canvas
    assert "## Decision Register" in canvas
    assert "## Next Review Checklist" in canvas
    assert "- [ ] Confirm 1 action item(s) have clear owners and dates." in canvas
