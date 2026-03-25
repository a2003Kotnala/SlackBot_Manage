from types import SimpleNamespace
from uuid import uuid4

from app.domain.schemas.extraction import (
    ActionItem,
    Confidence,
    ExtractionResult,
    InsightItem,
)
from app.domain.services.followthru_service import FollowThruClearResult
from app.slack.handlers.commands import register_handlers


class FakeBoltApp:
    def __init__(self) -> None:
        self.command_handlers = {}
        self.event_handlers = {}

    def command(self, name: str):
        def decorator(func):
            self.command_handlers[name] = func
            return func

        return decorator

    def event(self, name: str):
        def decorator(func):
            self.event_handlers[name] = func
            return func

        return decorator


def test_followthru_command_reports_canvas_update(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    source = SimpleNamespace(
        created_by=uuid4(),
        raw_content_reference=(
            "Decision: Ship the pilot.\n" "Action: Prepare demo @maya 2026-03-20"
        ),
    )
    extraction = ExtractionResult(
        meeting_title="Pilot Review",
        summary="Pilot was approved.",
        status_summary="Execution in progress",
        priority_focus="Prepare demo",
        decisions=[InsightItem(content="Ship the pilot.", confidence=Confidence.high)],
        action_items=[
            ActionItem(
                content="Prepare demo",
                owner="maya",
                confidence=Confidence.high,
            )
        ],
        risks=[
            InsightItem(
                content="Need final approver confirmation.",
                confidence=Confidence.medium,
            )
        ],
        confidence_overall=Confidence.high,
    )
    draft = SimpleNamespace(
        title="Action Canvas Draft - 2026-03-19", slack_canvas_id="F123"
    )

    monkeypatch.setattr(
        "app.slack.handlers.commands.resolve_latest_huddle_notes_canvas",
        lambda *_args, **_kwargs: source,
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.extract_structured_meeting_data",
        lambda _: extraction,
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.create_draft",
        lambda *_args, **_kwargs: (draft, "# canvas"),
    )

    responses: list[dict] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        command={"channel_id": "C123", "user_id": "U123", "text": "publish"},
        respond=lambda **kwargs: responses.append(kwargs),
    )

    assert responses[0]["response_type"] == "ephemeral"
    assert "Channel canvas updated successfully." in responses[0]["text"]
    assert "1 action item(s), 1 attention item(s)." in responses[0]["text"]


def test_followthru_command_reports_missing_source(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    monkeypatch.setattr(
        "app.slack.handlers.commands.resolve_latest_huddle_notes_canvas",
        lambda *_args, **_kwargs: None,
    )

    responses: list[dict] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        command={"channel_id": "C123", "user_id": "U123", "text": ""},
        respond=lambda **kwargs: responses.append(kwargs),
    )

    assert responses == [
        {
            "text": (
                "No recent huddle notes canvas found. "
                "Finish the huddle notes first, or DM FollowThru with pasted "
                "transcript text or a text file."
            ),
            "response_type": "ephemeral",
        }
    ]


def test_followthru_preview_command_returns_canvas_preview(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    extraction = ExtractionResult(
        meeting_title="Pilot Review",
        summary="Pilot was approved.",
        status_summary="Execution in progress",
        priority_focus="Prepare demo",
        decisions=[InsightItem(content="Ship the pilot.", confidence=Confidence.high)],
        action_items=[
            ActionItem(
                content="Prepare demo",
                owner="maya",
                confidence=Confidence.high,
            )
        ],
        risks=[
            InsightItem(
                content="Need final approver confirmation.",
                confidence=Confidence.medium,
            )
        ],
        confidence_overall=Confidence.high,
    )

    monkeypatch.setattr(
        "app.slack.handlers.commands.resolve_latest_huddle_notes_canvas",
        lambda *_args, **_kwargs: SimpleNamespace(
            raw_content_reference=(
                "Decision: Ship the pilot.\n" "Action: Prepare demo @maya 2026-03-20"
            ),
            source_type=SimpleNamespace(value="huddle_notes"),
        ),
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.extract_structured_meeting_data",
        lambda _: extraction,
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.create_draft",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("preview must not create a draft")
        ),
    )

    responses: list[dict] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        command={"channel_id": "C123", "user_id": "U123", "text": ""},
        respond=lambda **kwargs: responses.append(kwargs),
    )

    assert responses[0]["response_type"] == "ephemeral"
    assert "*Preview ready.* No draft was created." in responses[0]["text"]
    assert "*Title:* Pilot Review" in responses[0]["text"]
    assert "*Action items*" in responses[0]["text"]
    assert "Prepare demo (owner maya)" in responses[0]["text"]
    assert "*Attention*" in responses[0]["text"]


def test_followthru_command_redirects_inline_channel_text_to_dm():
    app = FakeBoltApp()
    register_handlers(app)

    responses: list[dict] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        command={
            "channel_id": "C123",
            "user_id": "U123",
            "text": "Decision: Ship the pilot. Action: Prepare demo @maya",
        },
        respond=lambda **kwargs: responses.append(kwargs),
    )

    assert responses == [
        {
            "text": (
                "Channel commands only work from the latest huddle notes "
                "for that channel. "
                "To process custom transcript text or a file, DM FollowThru instead."
            ),
            "response_type": "ephemeral",
        }
    ]


def test_followthru_help_command_returns_usage():
    app = FakeBoltApp()
    register_handlers(app)

    responses: list[dict] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        command={"channel_id": "C123", "user_id": "U123", "text": "help"},
        respond=lambda **kwargs: responses.append(kwargs),
    )

    assert responses == [
        {
            "text": (
                "*FollowThru command guide*\n"
                "In channels:\n"
                "- `/followthru` previews the latest huddle notes for this channel.\n"
                "- `/followthru publish` publishes the latest huddle notes "
                "to the channel canvas.\n"
                "In DMs:\n"
                "- `/followthru clear` clears FollowThru chat state in this DM "
                "and removes recent bot chat messages.\n"
                "- Paste a transcript directly for shorter notes, or upload a "
                "transcript file for larger Zoom, Meet, or Slack huddles.\n"
                "- Paste a supported Zoom recording link to fetch a transcript "
                "or transcribe media.\n"
                "FollowThru keeps command output private to the person who runs it."
            ),
            "response_type": "ephemeral",
        }
    ]


def test_zmanage_alias_still_points_to_followthru_handler():
    app = FakeBoltApp()
    register_handlers(app)

    assert "/followthru" in app.command_handlers
    assert "/zmanage" in app.command_handlers


def test_followthru_clear_in_dm_resets_memory_and_deletes_bot_messages(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    monkeypatch.setattr(
        "app.slack.handlers.commands.clear_followthru_dm_session",
        lambda _channel_id: FollowThruClearResult(
            cleared_sessions=2,
            cleared_messages=5,
        ),
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.slack_client.get_channel_history",
        lambda _channel_id, limit=100: [
            {"ts": "1710000000.000101", "bot_id": "B111"},
            {"ts": "1710000000.000102", "subtype": "bot_message"},
            {"ts": "1710000000.000103", "user": "U123"},
        ],
    )

    deleted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.slack.handlers.commands.slack_client.delete_message",
        lambda channel_id, message_ts: deleted.append((channel_id, message_ts)),
    )

    responses: list[dict] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        command={"channel_id": "D123", "user_id": "U123", "text": "clear"},
        respond=lambda **kwargs: responses.append(kwargs),
    )

    assert deleted == [
        ("D123", "1710000000.000101"),
        ("D123", "1710000000.000102"),
    ]
    assert responses == [
        {
            "text": (
                "Fresh start ready. FollowThru chat state was cleared and "
                "recent bot chat messages were removed where Slack allowed it. "
                "Your standalone canvases were left untouched."
            ),
            "response_type": "ephemeral",
        }
    ]


def test_followthru_clear_in_channel_redirects_to_dm():
    app = FakeBoltApp()
    register_handlers(app)

    responses: list[dict] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        command={"channel_id": "C123", "user_id": "U123", "text": "clear"},
        respond=lambda **kwargs: responses.append(kwargs),
    )

    assert responses == [
        {
            "text": "`/followthru clear` only works in a DM with FollowThru.",
            "response_type": "ephemeral",
        }
    ]


def test_followthru_app_mention_uses_chat_service(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    monkeypatch.setattr(
        "app.slack.handlers.commands.handle_followthru_chat",
        lambda payload: SimpleNamespace(reply=f"Handled: {payload.message}"),
    )

    messages: list[tuple[str, str]] = []
    app.event_handlers["app_mention"](
        event={
            "user": "U123",
            "channel": "C123",
            "ts": "1710000000.000100",
            "text": "<@U999> preview these notes",
        },
        say=lambda text, thread_ts: messages.append((text, thread_ts)),
    )

    assert messages == [("Handled: preview these notes", "1710000000.000100")]


def test_followthru_dm_message_delegates_to_ingestion_service(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    captured: list[dict] = []
    monkeypatch.setattr(
        "app.slack.handlers.commands.handle_dm_ingestion_event",
        lambda event, say: captured.append(event) or True,
    )

    app.event_handlers["message"](
        event={
            "channel_type": "im",
            "user": "U123",
            "channel": "D123",
            "ts": "1710000000.000200",
            "text": "Decision: Ship the pilot. Action: Prepare demo @maya",
        },
        say=lambda text: {"channel": "D123", "ts": "1710000000.000200"},
    )

    assert captured == [
        {
            "channel_type": "im",
            "user": "U123",
            "channel": "D123",
            "ts": "1710000000.000200",
            "text": "Decision: Ship the pilot. Action: Prepare demo @maya",
        }
    ]


def test_followthru_dm_file_message_delegates_to_ingestion_service(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    captured: list[dict] = []
    monkeypatch.setattr(
        "app.slack.handlers.commands.handle_dm_ingestion_event",
        lambda event, say: captured.append(event) or True,
    )

    app.event_handlers["message"](
        event={
            "channel_type": "im",
            "user": "U123",
            "channel": "D123",
            "ts": "1710000000.000300",
            "text": "",
            "files": [
                {
                    "name": "transcript.txt",
                    "mimetype": "text/plain",
                    "filetype": "text",
                    "url_private_download": "https://example.com/transcript.txt",
                }
            ],
        },
        say=lambda text: {"channel": "D123", "ts": "1710000000.000300"},
    )

    assert captured[0]["files"][0]["name"] == "transcript.txt"


def test_followthru_dm_ignores_non_dm_messages(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    called = {"value": False}
    monkeypatch.setattr(
        "app.slack.handlers.commands.handle_dm_ingestion_event",
        lambda event, say: called.__setitem__("value", True),
    )

    app.event_handlers["message"](
        event={
            "channel_type": "channel",
            "user": "U123",
            "channel": "C123",
            "ts": "1710000000.000200",
            "text": "Decision: Ship the pilot.",
        },
        say=lambda text: None,
    )

    assert called["value"] is False
