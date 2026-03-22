from app.domain.schemas.followthru import FollowThruChatRequest
from app.domain.services.canvas_composer import create_draft_canvas
from app.domain.services.draft_service import create_draft
from app.domain.services.extraction_service import extract_structured_meeting_data
from app.domain.services.followthru_service import (
    LEGACY_SLACK_COMMAND,
    PRIMARY_SLACK_COMMAND,
    handle_followthru_chat,
)
from app.slack.services.source_resolver import (
    create_text_source,
    resolve_latest_huddle_notes_canvas,
)

HELP_TEXT = (
    "Usage:\n"
    "/followthru <notes> - create or update the channel canvas draft\n"
    "/followthru publish <notes> - explicit publish mode\n"
    "/followthru draft <notes> - save a local draft without Slack publication\n"
    "/followthru preview <notes> - preview the generated action canvas without saving\n"
    "/followthru help - show this help message\n"
    "Legacy alias: /zmanage"
)

MISSING_SOURCE_MESSAGE = (
    "No recent huddle notes canvas found. "
    "Provide inline notes after /followthru to process text directly."
)


def register_handlers(bolt_app) -> None:
    def handle_followthru_command(ack, say, command):
        ack()

        channel_id = command["channel_id"]
        thread_ts = command.get("thread_ts")
        user_id = command["user_id"]
        mode, text = _parse_command_text((command.get("text") or "").strip())

        if mode == "help":
            say(HELP_TEXT)
            return

        source = None
        preview_source_label = "slack-command"
        raw_content = text

        if text and mode != "preview":
            source = create_text_source(
                raw_content=text,
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
            )
            raw_content = source.raw_content_reference
            preview_source_label = _resolve_source_label(source)
        elif not text:
            source = resolve_latest_huddle_notes_canvas(channel_id, thread_ts, user_id)
            if source:
                raw_content = source.raw_content_reference
                preview_source_label = _resolve_source_label(source)

        if not raw_content:
            say(MISSING_SOURCE_MESSAGE)
            return

        extraction = extract_structured_meeting_data(raw_content)
        tracking_summary = _build_tracking_summary(extraction)

        if mode == "preview":
            canvas_content = create_draft_canvas(extraction, preview_source_label)
            say(
                _build_preview_message(
                    extraction.meeting_title, tracking_summary, canvas_content
                )
            )
            return

        if source is None:
            say(MISSING_SOURCE_MESSAGE)
            return

        publish_to_slack = mode != "draft"
        draft, _canvas_content = create_draft(
            source.created_by,
            source,
            extraction,
            publish_to_slack=publish_to_slack,
        )

        if draft.slack_canvas_id:
            say(
                "Channel canvas updated successfully. "
                f"Title: {draft.title}. "
                f"Slack canvas ID: {draft.slack_canvas_id}. "
                f"{tracking_summary}"
            )
            return

        if not publish_to_slack:
            say(
                "Draft created locally without Slack publication. "
                f"Title: {draft.title}. "
                f"{tracking_summary}"
            )
            return

        say(
            "Draft created locally. "
            f"Title: {draft.title}. "
            f"{tracking_summary} "
            "Slack publication was skipped or unavailable."
        )

    for command_name in (PRIMARY_SLACK_COMMAND, LEGACY_SLACK_COMMAND):
        bolt_app.command(command_name)(handle_followthru_command)

    @bolt_app.event("app_mention")
    def handle_followthru_mention(event, say):
        message = _strip_mention_tokens(event.get("text", ""))
        response = handle_followthru_chat(
            FollowThruChatRequest(
                message=message or "help",
                user_id=event["user"],
                channel_id=event["channel"],
                thread_ts=event.get("thread_ts") or event["ts"],
            )
        )
        say(text=response.reply, thread_ts=event.get("thread_ts") or event["ts"])


def _parse_command_text(text: str) -> tuple[str, str]:
    if not text:
        return "publish", ""

    command, _, remainder = text.partition(" ")
    mode = command.lower()
    if mode in {"publish", "draft", "preview", "help"}:
        return mode, remainder.strip()
    return "publish", text


def _build_tracking_summary(extraction) -> str:
    return (
        f"{len(extraction.action_items)} action item(s), "
        f"{len(extraction.risks) + len(extraction.open_questions)} attention item(s)."
    )


def _resolve_source_label(source) -> str:
    source_type = getattr(source, "source_type", None)
    return getattr(source_type, "value", "slack-command")


def _build_preview_message(
    meeting_title: str, tracking_summary: str, canvas_content: str
) -> str:
    preview = _truncate_for_slack(canvas_content.strip(), limit=2500)
    title = meeting_title or "Untitled meeting"
    return (
        "Preview generated. No draft was created.\n"
        f"Title: {title}.\n"
        f"{tracking_summary}\n"
        f"```{preview}```"
    )


def _truncate_for_slack(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 15].rstrip() + "\n...[truncated]"


def _strip_mention_tokens(text: str) -> str:
    return " ".join(
        token
        for token in text.split()
        if not (token.startswith("<@") and token.endswith(">"))
    ).strip()
