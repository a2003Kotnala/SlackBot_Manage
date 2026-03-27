from slack_sdk.errors import SlackApiError
from slack_sdk.web.slack_response import SlackResponse

from app.integrations.slack_client import SlackClient


class FakeSlackClient:
    def __init__(self) -> None:
        self.created = []
        self.edited = []
        self.info_requests = []
        self.updated_messages = []
        self.deleted_messages = []
        self.deleted_canvases = []
        self.standalone_created = []
        self.access_updates = []
        self.uploaded_files = []

    def conversations_canvases_create(self, **kwargs):
        self.created.append(kwargs)
        return {"canvas_id": "F123"}

    def canvases_create(self, **kwargs):
        self.standalone_created.append(kwargs)
        return {"canvas_id": "F789"}

    def conversations_info(self, **kwargs):
        self.info_requests.append(kwargs)
        return {"channel": {"properties": {"canvas": {"canvas_id": "F456"}}}}

    def canvases_edit(self, **kwargs):
        self.edited.append(kwargs)
        return {"ok": True}

    def canvases_access_set(self, **kwargs):
        self.access_updates.append(kwargs)
        return {"ok": True}

    def files_upload_v2(self, **kwargs):
        self.uploaded_files.append(kwargs)
        return {
            "file": {
                "id": "F999",
                "name": kwargs["filename"],
                "title": kwargs["title"],
            }
        }

    def chat_update(self, **kwargs):
        self.updated_messages.append(kwargs)
        return {"channel": kwargs["channel"], "ts": kwargs["ts"], "ok": True}

    def chat_delete(self, **kwargs):
        self.deleted_messages.append(kwargs)
        return {"ok": True}

    def canvases_delete(self, **kwargs):
        self.deleted_canvases.append(kwargs)
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

    assert result == {
        "id": "F123",
        "title": "Action Canvas Draft - 2026-03-19",
        "location": "conversation",
    }
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

    assert result == {
        "id": "F456",
        "title": "Action Canvas Draft - 2026-03-19",
        "location": "conversation",
    }
    assert fake.info_requests == [{"channel": "C123"}]
    assert fake.edited[0]["canvas_id"] == "F456"
    assert fake.edited[0]["changes"][0]["operation"] == "replace"


def test_upload_canvas_creates_standalone_canvas_for_dm():
    wrapper = SlackClient()
    fake = FakeSlackClient()
    wrapper.client = fake

    result = wrapper.upload_canvas(
        channel_id="D123",
        content="# Title\nBody",
        title="Launch Review | 23 Mar 04:40 PM",
        slack_user_id="U123",
    )

    assert result == {
        "id": "F789",
        "title": "Launch Review | 23 Mar 04:40 PM",
        "location": "standalone",
    }
    assert fake.standalone_created == [
        {
            "title": "Launch Review | 23 Mar 04:40 PM",
            "document_content": {"type": "markdown", "markdown": "# Title\nBody"},
        }
    ]
    assert fake.access_updates == [
        {
            "canvas_id": "F789",
            "access_level": "write",
            "user_ids": ["U123"],
        }
    ]


def test_upload_canvas_keeps_standalone_canvas_when_access_update_fails():
    wrapper = SlackClient()
    fake = FakeSlackClient()
    wrapper.client = fake

    def raise_access_error(**_kwargs):
        raise _slack_error("restricted_action")

    fake.canvases_access_set = raise_access_error

    result = wrapper.upload_canvas(
        channel_id="D123",
        content="# Title\nBody",
        title="Launch Review | 23 Mar 04:40 PM",
        slack_user_id="U123",
    )

    assert result == {
        "id": "F789",
        "title": "Launch Review | 23 Mar 04:40 PM",
        "location": "standalone",
    }


def test_update_message_uses_chat_update():
    wrapper = SlackClient()
    fake = FakeSlackClient()
    wrapper.client = fake

    result = wrapper.update_message(
        channel_id="D123",
        message_ts="1710000000.000200",
        text=":sparkles: Canvas ready.",
    )

    assert result == {
        "channel": "D123",
        "ts": "1710000000.000200",
        "text": ":sparkles: Canvas ready.",
    }
    assert fake.updated_messages == [
        {
            "channel": "D123",
            "ts": "1710000000.000200",
            "text": ":sparkles: Canvas ready.",
        }
    ]


def test_delete_message_uses_chat_delete():
    wrapper = SlackClient()
    fake = FakeSlackClient()
    wrapper.client = fake

    result = wrapper.delete_message(
        channel_id="D123",
        message_ts="1710000000.000250",
    )

    assert result == {"channel": "D123", "ts": "1710000000.000250"}
    assert fake.deleted_messages == [
        {"channel": "D123", "ts": "1710000000.000250"}
    ]


def test_delete_canvas_uses_canvases_delete():
    wrapper = SlackClient()
    fake = FakeSlackClient()
    wrapper.client = fake

    result = wrapper.delete_canvas("F123")

    assert result == {"id": "F123"}
    assert fake.deleted_canvases == [{"canvas_id": "F123"}]


def test_upload_text_file_uses_files_upload_v2():
    wrapper = SlackClient()
    fake = FakeSlackClient()
    wrapper.client = fake

    result = wrapper.upload_text_file(
        channel_id="D123",
        filename="followthru-transcript-20260323-184000.txt",
        content="Decision: Ship the pilot.",
        title="FollowThru Transcript | 23 Mar 06:40 PM",
    )

    assert result == {
        "id": "F999",
        "name": "followthru-transcript-20260323-184000.txt",
        "title": "FollowThru Transcript | 23 Mar 06:40 PM",
    }
    assert fake.uploaded_files == [
        {
            "channel": "D123",
            "filename": "followthru-transcript-20260323-184000.txt",
            "content": "Decision: Ship the pilot.",
            "title": "FollowThru Transcript | 23 Mar 06:40 PM",
        }
    ]
