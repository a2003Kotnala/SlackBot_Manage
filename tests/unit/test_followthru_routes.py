from fastapi.testclient import TestClient

from app.domain.schemas.extraction import ExtractionResult
from app.domain.schemas.followthru import FollowThruMode, FollowThruResponse
from app.main import app

client = TestClient(app)


def test_followthru_capabilities_endpoint_returns_launch_surface():
    response = client.get("/api/v1/followthru/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["bot_name"] == "FollowThru"
    assert payload["primary_slack_command"] == "/followthru"
    assert payload["supports_chat"] is True
    assert payload["supports_voice_transcript_commands"] is True


def test_followthru_chat_endpoint_returns_service_response(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.followthru.handle_followthru_chat",
        lambda payload: FollowThruResponse(
            bot_name="FollowThru",
            session_id="session-123",
            mode=FollowThruMode.chat,
            reply=f"Handled {payload.message}",
        ),
    )

    response = client.post(
        "/api/v1/followthru/chat",
        json={"message": "hello", "user_id": "api-user"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "session-123"
    assert payload["reply"] == "Handled hello"


def test_followthru_chat_endpoint_accepts_long_transcript_payload(monkeypatch):
    long_message = "publish " + ("A" * 9000)

    monkeypatch.setattr(
        "app.api.routes.followthru.handle_followthru_chat",
        lambda payload: FollowThruResponse(
            bot_name="FollowThru",
            session_id="session-long",
            mode=FollowThruMode.publish,
            reply=f"Handled {len(payload.message)} chars",
        ),
    )

    response = client.post(
        "/api/v1/followthru/chat",
        json={"message": long_message, "user_id": "api-user"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "session-long"
    assert payload["reply"] == f"Handled {len(long_message)} chars"


def test_followthru_voice_command_endpoint_returns_canvas_response(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.followthru.handle_followthru_voice_command",
        lambda payload: FollowThruResponse(
            bot_name="FollowThru",
            session_id="voice-session-123",
            mode=FollowThruMode.preview,
            reply="Preview ready",
            draft_canvas_markdown="# Voice Canvas",
            extraction=ExtractionResult(meeting_title="Voice Notes"),
            normalized_input=payload.transcript,
        ),
    )

    response = client.post(
        "/api/v1/followthru/voice-command",
        json={"transcript": "preview these notes", "user_id": "voice-user"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "preview"
    assert payload["draft_canvas_markdown"] == "# Voice Canvas"
    assert payload["normalized_input"] == "preview these notes"
