from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_service_metadata():
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "FollowThru"
    assert payload["database_target"] in {"postgresql", "sqlite"}
    assert payload["bot"]["primary_slack_command"] == "/followthru"
    assert "integrations" in payload
