from app.domain.schemas.extraction import ExtractionResult
from app.domain.services.extraction_service import extract_structured_meeting_data


def test_rule_based_extraction_parses_actions_decisions_and_risks():
    notes = """
    Weekly engineering sync for the FollowThru rollout.
    Decision: Keep Slack as the system of engagement and Postgres as the system of
    record.
    Action: Prepare boss-ready demo narrative @anita 2026-03-21
    Risk: Production Slack app approval is still pending.
    Question: Should we enable the workflow preview endpoint for business users?
    """

    result = extract_structured_meeting_data(notes)

    assert result.meeting_title.startswith("Weekly engineering sync")
    assert result.summary.startswith("Weekly engineering sync")
    assert result.status_summary == "At risk"
    assert result.priority_focus.startswith("Production Slack")
    assert result.next_review_date.isoformat() == "2026-03-21"
    assert result.decisions[0].content.startswith("Keep Slack")
    assert result.action_items[0].owner == "anita"
    assert result.action_items[0].due_date.isoformat() == "2026-03-21"
    assert result.risks[0].content.startswith("Production Slack")
    assert result.open_questions[0].content.startswith("Should we enable")


def test_rule_based_extraction_splits_inline_labeled_segments():
    notes = (
        "Decision: Ship the pilot. Action: Prepare demo @maya 2026-03-21 "
        "Risk: QA sign-off is pending."
    )

    result = extract_structured_meeting_data(notes)

    assert result.decisions[0].content.startswith("Ship the pilot")
    assert result.action_items[0].content.startswith("Prepare demo")
    assert result.action_items[0].owner == "maya"
    assert result.action_items[0].due_date.isoformat() == "2026-03-21"
    assert result.risks[0].content.startswith("QA sign-off")


def test_long_transcript_is_compacted_before_llm_extraction(monkeypatch):
    filler = "\n".join(
        f"Ankit: yeah, sounds good, let's come back to this in a second {index}"
        for index in range(350)
    )
    notes = (
        f"{filler}\n"
        "Decision: Ship the pilot this week.\n"
        "Action: Prepare the customer demo @maya 2026-03-27\n"
        "Risk: QA sign-off is still pending.\n"
        "Question: Should DM publish remain enabled by default?\n"
    )
    captured = {}

    monkeypatch.setattr(
        "app.domain.services.extraction_service.openai_client.is_configured",
        lambda: True,
    )

    def fake_extract_meeting_data(raw_content: str) -> ExtractionResult:
        captured["raw_content"] = raw_content
        return ExtractionResult(meeting_title="Compacted Transcript")

    monkeypatch.setattr(
        "app.domain.services.extraction_service.openai_client.extract_meeting_data",
        fake_extract_meeting_data,
    )

    result = extract_structured_meeting_data(notes)

    assert result.meeting_title == "Compacted Transcript"
    assert len(captured["raw_content"]) < len(notes)
    assert "Decision: Ship the pilot this week." in captured["raw_content"]
    assert (
        "Action: Prepare the customer demo @maya 2026-03-27"
        in captured["raw_content"]
    )
    assert "Risk: QA sign-off is still pending." in captured["raw_content"]
    assert (
        "Question: Should DM publish remain enabled by default?"
        in captured["raw_content"]
    )


def test_long_transcript_rule_parser_keeps_high_signal_segments():
    filler = "\n".join(
        f"Mike: okay, yeah, sounds good, we can revisit that later {index}"
        for index in range(350)
    )
    notes = (
        f"{filler}\n"
        "Decision: Keep channel publish as the default release path.\n"
        "Action: Validate transcript fallback with a real Slack huddle "
        "@mike 2026-03-24\n"
        "Risk: Slack transcript metadata may differ in production.\n"
        "Question: Should we force preview for very short transcripts?\n"
    )

    result = extract_structured_meeting_data(notes)

    assert result.decisions[0].content.startswith(
        "Keep channel publish as the default release path"
    )
    assert result.action_items[0].owner == "mike"
    assert result.action_items[0].due_date.isoformat() == "2026-03-24"
    assert result.risks[0].content.startswith(
        "Slack transcript metadata may differ in production"
    )
    assert result.open_questions[0].content.startswith(
        "Should we force preview for very short transcripts"
    )
