from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

from app.domain.schemas.extraction import (
    ActionItem,
    Confidence,
    ExtractionResult,
    InsightItem,
)
from app.domain.schemas.followthru import FollowThruMode
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
                "Decision: Ship the pilot.\n"
                "Action: Prepare demo @maya 2026-03-20"
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
                "- `/followthru stop` cancels the latest in-flight meeting job "
                "for this DM.\n"
                "- Paste a transcript directly for shorter notes, or upload a "
                "transcript file for larger Zoom, Meet, or Slack huddles.\n"
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


def test_followthru_stop_in_dm_requests_active_job_stop(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    monkeypatch.setattr(
        "app.slack.handlers.commands.request_job_stop",
        lambda _channel_id: SimpleNamespace(stopped=True, active=True),
    )

    responses: list[dict] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        command={"channel_id": "D123", "user_id": "U123", "text": "stop"},
        respond=lambda **kwargs: responses.append(kwargs),
    )

    assert responses == [
        {
            "text": (
                "Stop requested. FollowThru will halt the current meeting job "
                "shortly."
            ),
            "response_type": "ephemeral",
        }
    ]


def test_followthru_stop_in_dm_reports_when_no_job_exists(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    monkeypatch.setattr(
        "app.slack.handlers.commands.request_job_stop",
        lambda _channel_id: SimpleNamespace(stopped=False, active=False),
    )

    responses: list[dict] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        command={"channel_id": "D123", "user_id": "U123", "text": "stop"},
        respond=lambda **kwargs: responses.append(kwargs),
    )

    assert responses == [
        {
            "text": "There is no active FollowThru job to stop in this DM.",
            "response_type": "ephemeral",
        }
    ]


def test_followthru_stop_in_channel_redirects_to_dm():
    app = FakeBoltApp()
    register_handlers(app)

    responses: list[dict] = []
    app.command_handlers["/followthru"](
        ack=lambda: None,
        command={"channel_id": "C123", "user_id": "U123", "text": "stop"},
        respond=lambda **kwargs: responses.append(kwargs),
    )

    assert responses == [
        {
            "text": "`/followthru stop` only works in a DM with FollowThru.",
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


def test_followthru_dm_message_defaults_to_publish_workflow(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    captured_messages: list[str] = []
    updated_messages: list[tuple[str, str, str]] = []

    monkeypatch.setattr(
        "app.slack.handlers.commands.handle_followthru_chat",
        lambda payload: captured_messages.append(payload.message)
        or SimpleNamespace(
            mode=FollowThruMode.publish,
            reply=(
                "Published Pilot Review. 1 action item(s), 0 attention item(s). "
                "Slack canvas ID: F123."
            ),
            slack_canvas_id="F123",
            draft_canvas_markdown="# Pilot Review",
            draft_title="Pilot Review",
            extraction=None,
        ),
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.slack_client.update_message",
        lambda channel_id, message_ts, text: updated_messages.append(
            (channel_id, message_ts, text)
        ),
    )

    messages: list[str] = []
    app.event_handlers["message"](
        event={
            "channel_type": "im",
            "user": "U123",
            "channel": "D123",
            "ts": "1710000000.000200",
            "text": "Decision: Ship the pilot. Action: Prepare demo @maya",
        },
        say=lambda text: messages.append(text)
        or {"channel": "D123", "ts": "1710000000.000200"},
    )

    assert captured_messages == [
        "publish Decision: Ship the pilot. Action: Prepare demo @maya"
    ]
    assert "Processing your transcript" in messages[0]
    assert updated_messages[0][0:2] == ("D123", "1710000000.000200")
    assert "Canvas ready." in updated_messages[0][2]
    assert "Slack canvas ID: F123." in updated_messages[0][2]


def test_followthru_dm_preview_command_returns_preview(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    extraction = ExtractionResult(
        meeting_title="Pilot Review",
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
        confidence_overall=Confidence.high,
    )

    monkeypatch.setattr(
        "app.slack.handlers.commands.handle_followthru_chat",
        lambda _payload: SimpleNamespace(
            mode=FollowThruMode.preview,
            reply="Preview ready",
            extraction=extraction,
            slack_canvas_id=None,
            draft_canvas_markdown="# Preview Canvas",
            draft_title=None,
        ),
    )
    updated_messages: list[str] = []
    monkeypatch.setattr(
        "app.slack.handlers.commands.slack_client.update_message",
        lambda _channel_id, _message_ts, text: updated_messages.append(text),
    )

    messages: list[str] = []
    app.event_handlers["message"](
        event={
            "channel_type": "im",
            "user": "U123",
            "channel": "D123",
            "ts": "1710000000.000250",
            "text": "preview Decision: Ship the pilot. Action: Prepare demo @maya",
        },
        say=lambda text: messages.append(text)
        or {"channel": "D123", "ts": "1710000000.000250"},
    )

    assert "Processing your transcript" in messages[0]
    assert "*Preview ready.* No draft was created." in updated_messages[0]
    assert "Use `publish` in this DM to create a standalone Slack canvas" in (
        updated_messages[0]
    )


def test_followthru_dm_file_downloads_supported_text_and_shows_local_canvas(
    monkeypatch,
):
    app = FakeBoltApp()
    register_handlers(app)
    updated_messages: list[str] = []

    monkeypatch.setattr(
        "app.slack.handlers.commands.slack_client.download_text_file",
        lambda _url: "Decision: Ship the pilot.",
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.handle_followthru_chat",
        lambda payload: SimpleNamespace(
            mode=FollowThruMode.draft,
            reply=(
                "Saved local draft Pilot Review. 1 action item(s), "
                "0 attention item(s)."
            ),
            extraction=None,
            slack_canvas_id=None,
            draft_canvas_markdown="# Pilot Review\n## Action Items\n- Prepare demo",
            draft_title="Pilot Review",
            normalized_input=payload.message,
        ),
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.slack_client.update_message",
        lambda _channel_id, _message_ts, text: updated_messages.append(text),
    )

    messages: list[str] = []
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
        say=lambda text: messages.append(text)
        or {"channel": "D123", "ts": "1710000000.000300"},
    )

    assert "Processing your transcript" in messages[0]
    assert "Draft ready." in updated_messages[0]
    assert "Saved local draft Pilot Review" in updated_messages[0]
    assert "*Canvas draft*" in updated_messages[0]
    assert "## Action Items" in updated_messages[0]
    assert "Processed uploaded transcript file(s): `transcript.txt`." in (
        updated_messages[0]
    )


def test_followthru_dm_docx_file_is_parsed_and_processed(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)
    updated_messages: list[str] = []
    captured_messages: list[str] = []

    def build_docx_bytes() -> bytes:
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr(
                "word/document.xml",
                (
                    "<w:document xmlns:w="
                    '"http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    "<w:body>"
                    "<w:p><w:r><w:t>Decision: Ship the pilot.</w:t></w:r></w:p>"
                    "<w:p><w:r><w:t>Action: Prepare demo.</w:t></w:r></w:p>"
                    "</w:body></w:document>"
                ),
            )
        return buffer.getvalue()

    monkeypatch.setattr(
        "app.slack.handlers.commands.slack_client.download_file_bytes",
        lambda _url: build_docx_bytes(),
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.handle_followthru_chat",
        lambda payload: captured_messages.append(payload.message)
        or SimpleNamespace(
            mode=FollowThruMode.publish,
            reply="Published Pilot Review. 1 action item(s), 0 attention item(s).",
            extraction=None,
            slack_canvas_id="F123",
            draft_canvas_markdown="# Pilot Review",
            draft_title="Pilot Review",
        ),
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.slack_client.update_message",
        lambda _channel_id, _message_ts, text: updated_messages.append(text),
    )

    messages: list[str] = []
    app.event_handlers["message"](
        event={
            "channel_type": "im",
            "user": "U123",
            "channel": "D123",
            "ts": "1710000000.000310",
            "text": "",
            "files": [
                {
                    "name": "zoom-transcript.docx",
                    "mimetype": (
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                    "filetype": "docx",
                    "url_private_download": "https://example.com/transcript.docx",
                }
            ],
        },
        say=lambda text: messages.append(text)
        or {"channel": "D123", "ts": "1710000000.000310"},
    )

    assert "Processing your transcript" in messages[0]
    assert captured_messages == [
        "publish Decision: Ship the pilot.\nAction: Prepare demo."
    ]
    assert "Processed uploaded transcript file(s): `zoom-transcript.docx`." in (
        updated_messages[0]
    )


def test_followthru_dm_unsupported_file_returns_clear_guidance(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)

    messages: list[str] = []
    app.event_handlers["message"](
        event={
            "channel_type": "im",
            "user": "U123",
            "channel": "D123",
            "ts": "1710000000.000320",
            "text": "",
            "files": [
                {
                    "name": "meeting-recording.pdf",
                    "mimetype": "application/pdf",
                    "filetype": "pdf",
                }
            ],
        },
        say=lambda text: messages.append(text),
    )

    assert "That upload format is not supported yet." in messages[0]
    assert "meeting-recording.pdf" in messages[0]
    assert "`.txt`, `.md`, `.csv`, `.tsv`, `.srt`, `.vtt`, or `.docx`" in (
        messages[0]
    )


def test_followthru_dm_long_text_uploads_transcript_artifact(monkeypatch):
    app = FakeBoltApp()
    register_handlers(app)
    updated_messages: list[str] = []
    uploaded_files: list[tuple[str, str, str, str | None]] = []

    long_text = "Decision: Ship the pilot.\n" * 500

    monkeypatch.setattr(
        "app.slack.handlers.commands.slack_client.upload_text_file",
        lambda channel_id, filename, content, title=None: uploaded_files.append(
            (channel_id, filename, content, title)
        )
        or {"id": "F888", "name": filename, "title": title},
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.handle_followthru_chat",
        lambda payload: SimpleNamespace(
            mode=FollowThruMode.publish,
            reply="Published Pilot Review. 1 action item(s), 0 attention item(s).",
            extraction=None,
            slack_canvas_id="F123",
            draft_canvas_markdown="# Pilot Review",
            draft_title="Pilot Review",
        ),
    )
    monkeypatch.setattr(
        "app.slack.handlers.commands.slack_client.update_message",
        lambda _channel_id, _message_ts, text: updated_messages.append(text),
    )

    messages: list[str] = []
    app.event_handlers["message"](
        event={
            "channel_type": "im",
            "user": "U123",
            "channel": "D123",
            "ts": "1710000000.000330",
            "text": long_text,
        },
        say=lambda text: messages.append(text)
        or {"channel": "D123", "ts": "1710000000.000330"},
    )

    assert "Processing your transcript" in messages[0]
    assert uploaded_files
    assert uploaded_files[0][0] == "D123"
    assert uploaded_files[0][1].startswith("followthru-transcript-")
    assert uploaded_files[0][2].startswith("Decision: Ship the pilot.")
    assert "Saved a transcript file copy as" in updated_messages[0]
