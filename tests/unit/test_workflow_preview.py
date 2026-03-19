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
    assert "Action Canvas" in payload["draft_canvas_markdown"]
    assert "## Action Tracker" in payload["draft_canvas_markdown"]
    assert "| ID | Action | Owner | Due | Status | Priority | Confidence | Notes |" in payload[
        "draft_canvas_markdown"
    ]
