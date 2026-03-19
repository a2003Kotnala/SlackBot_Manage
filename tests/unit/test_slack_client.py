from slack_sdk.errors import SlackApiError
from slack_sdk.web.slack_response import SlackResponse

from app.integrations.slack_client import SlackClient


class FakeSlackClient:
    def __init__(self) -> None:
        self.created = []
        self.edited = []
        self.info_requests = []

    def conversations_canvases_create(self, **kwargs):
        self.created.append(kwargs)
        return {"canvas_id": "F123"}

    def conversations_info(self, **kwargs):
        self.info_requests.append(kwargs)
        return {"channel": {"properties": {"canvas": {"canvas_id": "F456"}}}}

    def canvases_edit(self, **kwargs):
        self.edited.append(kwargs)
        return {"ok": True}


def _slack_error(error: str) -> SlackApiError:
    return SlackApiError(
        message=error,
        response=SlackResponse(
            client=None,  # type: ignore[arg-type]
            http_verb="POST",
            api_url="https://slack.com/api/test",
            req_args={},
            data={"ok": False, "error": error},
            headers={},
            status_code=200,
        ),
    )


def test_upload_canvas_uses_conversations_canvases_create():
    wrapper = SlackClient()
    fake = FakeSlackClient()
    wrapper.client = fake

    result = wrapper.upload_canvas(
        channel_id="C123",
        content="# Title\nBody",
        title="Action Canvas Draft - 2026-03-19",
    )

    assert result == {"id": "F123", "title": "Action Canvas Draft - 2026-03-19"}
    assert fake.created[0]["channel_id"] == "C123"
    assert fake.created[0]["document_content"] == {
        "type": "markdown",
        "markdown": "# Title\nBody",
    }


def test_upload_canvas_updates_existing_channel_canvas():
    wrapper = SlackClient()
    fake = FakeSlackClient()
    wrapper.client = fake

    def raise_existing(**kwargs):
        raise _slack_error("channel_canvas_already_exists")

    fake.conversations_canvases_create = raise_existing

    result = wrapper.upload_canvas(
        channel_id="C123",
        content="# Updated",
        title="Action Canvas Draft - 2026-03-19",
    )

    assert result == {"id": "F456", "title": "Action Canvas Draft - 2026-03-19"}
    assert fake.info_requests == [{"channel": "C123"}]
    assert fake.edited[0]["canvas_id"] == "F456"
    assert fake.edited[0]["changes"][0]["operation"] == "replace"
