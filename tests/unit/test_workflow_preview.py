from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_workflow_preview_returns_canvas_and_extraction():
    response = client.post(
        "/api/v1/workflows/preview",
        json={
            "text": (
                "Decision: Ship the pilot this week.\n"
                "Action: Prepare demo @maya 2026-03-20"
            ),
            "source_label": "manual-demo",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["extraction"]["decisions"][0]["content"] == "Ship the pilot this week."
    )
    assert payload["extraction"]["action_items"][0]["owner"] == "maya"
    assert "## Meeting Summary" in payload["draft_canvas_markdown"]
    assert "## Action Items" in payload["draft_canvas_markdown"]
    assert (
        "| S.No | Task | Owner | Due | Status | Priority |"
        in payload["draft_canvas_markdown"]
    )
    assert "## Open Risks & Questions" in payload["draft_canvas_markdown"]
