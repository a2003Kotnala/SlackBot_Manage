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
    notes = "Decision: Ship the pilot. Action: Prepare demo @maya 2026-03-21 Risk: QA sign-off is pending."

    result = extract_structured_meeting_data(notes)

    assert result.decisions[0].content.startswith("Ship the pilot")
    assert result.action_items[0].content.startswith("Prepare demo")
    assert result.action_items[0].owner == "maya"
    assert result.action_items[0].due_date.isoformat() == "2026-03-21"
    assert result.risks[0].content.startswith("QA sign-off")
