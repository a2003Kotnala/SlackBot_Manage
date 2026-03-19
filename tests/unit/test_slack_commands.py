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

    def command(self, name: str):
        def decorator(func):
            self.command_handlers[name] = func
            return func

        return decorator


def test_zmanage_command_reports_canvas_update(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    source = SimpleNamespace(
        created_by=uuid4(),
        raw_content_reference="Decision: Ship the pilot.\nAction: Prepare demo @maya 2026-03-20",
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
        risks=[InsightItem(content="Need final approver confirmation.", confidence=Confidence.medium)],
        confidence_overall=Confidence.high,
    )
    draft = SimpleNamespace(title="Action Canvas Draft - 2026-03-19", slack_canvas_id="F123")

    monkeypatch.setattr("app.slack.handlers.commands.create_text_source", lambda **_: source)
    monkeypatch.setattr(
        "app.slack.handlers.commands.extract_structured_meeting_data",
        lambda _: extraction,
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.create_draft",
        lambda *_args, **_kwargs: (draft, "# canvas"),
    )

    messages: list[str] = []
    app.command_handlers["/zmanage"](
        ack=lambda: None,
        say=messages.append,
        command={"channel_id": "C123", "user_id": "U123", "text": "ship it"},
    )

    assert "Channel canvas updated successfully." in messages[0]
    assert "1 action item(s), 1 attention item(s)." in messages[0]


def test_zmanage_command_reports_missing_source(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    monkeypatch.setattr(
        "app.slack.handlers.commands.resolve_latest_huddle_notes_canvas",
        lambda *_args, **_kwargs: None,
    )

    messages: list[str] = []
    app.command_handlers["/zmanage"](
        ack=lambda: None,
        say=messages.append,
        command={"channel_id": "C123", "user_id": "U123", "text": ""},
    )

    assert messages == [
        "No recent huddle notes canvas found. Provide inline notes after /zmanage to process text directly."
    ]
