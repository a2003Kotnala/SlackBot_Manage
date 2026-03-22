from types import SimpleNamespace
from uuid import uuid4

from app.domain.schemas.extraction import (
    ActionItem,
    Confidence,
    ExtractionResult,
    InsightItem,
)
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
        "app.slack.handlers.commands.create_text_source", lambda **_: source
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.extract_structured_meeting_data",
        lambda _: extraction,
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.create_draft",
        lambda *_args, **_kwargs: (draft, "# canvas"),
    )

    messages: list[str] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        say=messages.append,
        command={"channel_id": "C123", "user_id": "U123", "text": "ship it"},
    )

    assert "Channel canvas updated successfully." in messages[0]
    assert "1 action item(s), 1 attention item(s)." in messages[0]


def test_followthru_command_reports_missing_source(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    monkeypatch.setattr(
        "app.slack.handlers.commands.resolve_latest_huddle_notes_canvas",
        lambda *_args, **_kwargs: None,
    )

    messages: list[str] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        say=messages.append,
        command={"channel_id": "C123", "user_id": "U123", "text": ""},
    )

    assert messages == [
        (
            "No recent huddle notes canvas found. "
            "Provide inline notes after /followthru to process text directly."
        )
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
        "app.slack.handlers.commands.extract_structured_meeting_data",
        lambda _: extraction,
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.create_draft",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("preview must not create a draft")
        ),
    )

    messages: list[str] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        say=messages.append,
        command={"channel_id": "C123", "user_id": "U123", "text": "preview ship it"},
    )

    assert "Preview generated. No draft was created." in messages[0]
    assert "Title: Pilot Review." in messages[0]
    assert "## Meeting Summary" in messages[0]


def test_followthru_draft_command_skips_slack_publication(monkeypatch):
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
        action_items=[
            ActionItem(
                content="Prepare demo",
                owner="maya",
                confidence=Confidence.high,
            )
        ],
        confidence_overall=Confidence.high,
    )
    draft = SimpleNamespace(
        title="Action Canvas Draft - 2026-03-19", slack_canvas_id=None
    )
    publish_flags: list[bool] = []

    monkeypatch.setattr(
        "app.slack.handlers.commands.create_text_source", lambda **_: source
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.extract_structured_meeting_data",
        lambda _: extraction,
    )

    def fake_create_draft(*_args, **kwargs):
        publish_flags.append(kwargs["publish_to_slack"])
        return draft, "# canvas"

    monkeypatch.setattr("app.slack.handlers.commands.create_draft", fake_create_draft)

    messages: list[str] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        say=messages.append,
        command={"channel_id": "C123", "user_id": "U123", "text": "draft ship it"},
    )

    assert publish_flags == [False]
    assert messages == [
        (
            "Draft created locally without Slack publication. "
            "Title: Action Canvas Draft - 2026-03-19. "
            "1 action item(s), 0 attention item(s)."
        )
    ]


def test_followthru_help_command_returns_usage():
    app = FakeBoltApp()
    register_handlers(app)

    messages: list[str] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        say=messages.append,
        command={"channel_id": "C123", "user_id": "U123", "text": "help"},
    )

    assert messages == [
        (
            "Usage:\n"
            "/followthru <notes> - create or update the channel canvas draft\n"
            "/followthru publish <notes> - explicit publish mode\n"
            "/followthru draft <notes> - save a local draft without Slack publication\n"
            "/followthru preview <notes> - preview the generated action canvas "
            "without saving\n"
            "/followthru help - show this help message\n"
            "Legacy alias: /zmanage"
        )
    ]


def test_zmanage_alias_still_points_to_followthru_handler():
    app = FakeBoltApp()
    register_handlers(app)

    assert "/followthru" in app.command_handlers
    assert "/zmanage" in app.command_handlers


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
