from datetime import date

from app.domain.schemas.extraction import (
    ActionItem,
    Confidence,
    ExtractionResult,
    InsightItem,
)
from app.domain.services.canvas_composer import create_draft_canvas


def test_create_draft_canvas_renders_slack_native_tracking_layout():
    extraction = ExtractionResult(
        meeting_title="Launch Readiness Review",
        summary="Reviewed launch readiness.",
        what_happened="The team confirmed scope and assigned follow-ups.",
        status_summary="Execution in progress",
        priority_focus="Prepare beta checklist",
        next_review_date=date(2026, 3, 20),
        decisions=[
            InsightItem(content="Launch internal beta", confidence=Confidence.high)
        ],
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

    assert "# Launch Readiness Review" in canvas
    assert "## Meeting Summary" in canvas
    assert ":traffic_light: *Status:* Execution in progress" in canvas
    assert ":busts_in_silhouette: *Owners:* *maya*" in canvas
    assert "## Action Items" in canvas
    assert "| # | Task | Owner | Due | State | Pri |" in canvas
    assert "Prepare beta checklist" in canvas
    assert "## Open Risks & Questions" in canvas
    assert "## Key Decisions" in canvas
    assert "`----------` 0% (0/1 complete)" in canvas
    assert "**1**<br>To Do" in canvas
    assert "- :grey_question:" not in canvas
    assert "- :large_yellow_circle:" not in canvas


def test_create_draft_canvas_deduplicates_summary_content():
    extraction = ExtractionResult(
        meeting_title="Roadmap Sync - Product, Design, Engineering",
        summary="Roadmap Sync - Product, Design, Engineering Summary:",
        what_happened=(
            "Roadmap Sync - Product, Design, Engineering Summary: "
            "The team reviewed roadmap priorities and agreed to shift execution focus."
        ),
        confidence_overall=Confidence.high,
    )

    canvas = create_draft_canvas(extraction, "manual-demo")

    assert "## Meeting Summary" in canvas
    assert " Roadmap Sync - Product, Design, Engineering Summary:" not in canvas
    assert (
        "The team reviewed roadmap priorities and agreed to shift execution focus."
        in canvas
    )


def test_create_draft_canvas_truncates_long_status_and_summary():
    long_status = (
        "The backend is largely ready with transcript fallback and improved DM "
        "workflow implemented, but significant unknowns remain around live "
        "Slack transcript access, permissions, and publishing behavior."
    )
    long_summary = " ".join(
        f"Sentence {index} covers launch readiness, blockers, owners, and next steps."
        for index in range(1, 13)
    )
    extraction = ExtractionResult(
        meeting_title="FollowThru Launch Review",
        summary=long_summary,
        what_happened=long_summary,
        status_summary=long_status,
        priority_focus=(
            "Prove the live Slack flow works, clean up setup, and document the "
            "happy path for the team before rollout."
        ),
        confidence_overall=Confidence.high,
    )

    canvas = create_draft_canvas(extraction, "manual-demo")

    assert ":traffic_light: *Status:*" in canvas
    assert "publishing behavior." not in canvas
    assert "permissions..." in canvas
    assert "Sentence 12 covers launch readiness" not in canvas
    assert (
        "- Sentence 1 covers launch readiness, blockers, owners, and next steps."
        in canvas
    )


def test_create_draft_canvas_supports_compact_dm_header():
    extraction = ExtractionResult(
        meeting_title="FollowThru Launch Readiness Review",
        summary="Reviewed launch readiness for the DM flow.",
        confidence_overall=Confidence.high,
    )

    canvas = create_draft_canvas(
        extraction,
        "text",
        title_override="Launch Readiness Review | 23 Mar 02:49 PM",
        compact_header=True,
    )

    assert "# Launch Readiness Review | 23 Mar 02:49 PM" in canvas
    assert "_Text | High confidence_" in canvas
    assert "Action Canvas generated from" not in canvas
