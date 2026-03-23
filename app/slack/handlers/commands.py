from app.domain.schemas.followthru import FollowThruChatRequest
from app.domain.services.draft_service import create_draft
from app.domain.services.extraction_service import extract_structured_meeting_data
from app.domain.services.followthru_service import (
    LEGACY_SLACK_COMMAND,
    PRIMARY_SLACK_COMMAND,
    handle_followthru_chat,
)
from app.integrations.slack_client import slack_client
from app.slack.services.source_resolver import (
    resolve_latest_huddle_notes_canvas,
)

HELP_TEXT = (
    "*FollowThru command guide*\n"
    "In channels:\n"
    "- `/followthru` previews the latest huddle notes for this channel.\n"
    "- `/followthru publish` publishes the latest huddle notes to the channel canvas.\n"
    "In DMs:\n"
    "- Paste a transcript or upload a plain-text transcript file for a private preview.\n"
    "FollowThru keeps command output private to the person who runs it."
)

MISSING_SOURCE_MESSAGE = (
    "No recent huddle notes canvas found. "
    "Finish the huddle notes first, or DM FollowThru with pasted transcript text or a text file."
)

CHANNEL_TEXT_REDIRECT_MESSAGE = (
    "Channel commands only work from the latest huddle notes for that channel. "
    "To process custom transcript text or a file, DM FollowThru instead."
)

DM_HELP_TEXT = (
    "*FollowThru DM guide*\n"
    "- Paste transcript text directly in this DM for a private preview.\n"
    "- Upload a plain-text transcript file and FollowThru will read it privately.\n"
    "- To publish a finalized result to a channel canvas, go to that channel and run `/followthru publish`."
)


def register_handlers(bolt_app) -> None:
    def handle_followthru_command(ack, command, respond):
        ack()

        channel_id = command["channel_id"]
        thread_ts = command.get("thread_ts")
        user_id = command["user_id"]
        mode, text = _parse_command_text((command.get("text") or "").strip())

        if mode == "help":
            _respond_privately(respond, HELP_TEXT)
            return

        if text and mode not in {"publish", "preview"}:
            _respond_privately(respond, CHANNEL_TEXT_REDIRECT_MESSAGE)
            return

        if text:
            _respond_privately(respond, CHANNEL_TEXT_REDIRECT_MESSAGE)
            return

        source = resolve_latest_huddle_notes_canvas(channel_id, thread_ts, user_id)
        raw_content = source.raw_content_reference if source else ""
        if not raw_content:
            _respond_privately(respond, MISSING_SOURCE_MESSAGE)
            return

        extraction = extract_structured_meeting_data(raw_content)
        tracking_summary = _build_tracking_summary(extraction)

        if mode == "preview":
            _respond_privately(
                respond, _build_preview_message(extraction, tracking_summary)
            )
            return

        draft, _canvas_content = create_draft(
            source.created_by,
            source,
            extraction,
            publish_to_slack=True,
        )

        if draft.slack_canvas_id:
            _respond_privately(
                respond,
                "Channel canvas updated successfully. "
                f"Title: {draft.title}. "
                f"Slack canvas ID: {draft.slack_canvas_id}. "
                f"{tracking_summary}",
            )
            return

        _respond_privately(
            respond,
            "Draft created locally. "
            f"Title: {draft.title}. "
            f"{tracking_summary} "
            "Slack publication was skipped or unavailable.",
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

    @bolt_app.event("message")
    def handle_followthru_dm(event, say):
        if event.get("channel_type") != "im":
            return
        if event.get("bot_id") or event.get("subtype") == "message_changed":
            return

        dm_text = _build_dm_source_text(event)
        if not dm_text:
            say(text=DM_HELP_TEXT)
            return

        lowered = dm_text.lower()
        if lowered in {"help", "hi", "hello"}:
            say(text=DM_HELP_TEXT)
            return
        if lowered.startswith("publish"):
            say(
                text=(
                    "DMs are for private transcript review. "
                    "When you're ready to publish, go to the target channel and run `/followthru publish`."
                )
            )
            return

        extraction = extract_structured_meeting_data(dm_text)
        tracking_summary = _build_tracking_summary(extraction)
        say(text=_build_preview_message(extraction, tracking_summary))


def _parse_command_text(text: str) -> tuple[str, str]:
    if not text:
        return "preview", ""

    command, _, remainder = text.partition(" ")
    mode = command.lower()
    if mode in {"publish", "preview", "help"}:
        return mode, remainder.strip()
    return "preview", text


def _build_tracking_summary(extraction) -> str:
    return (
        f"{len(extraction.action_items)} action item(s), "
        f"{len(extraction.risks) + len(extraction.open_questions)} attention item(s)."
    )


def _resolve_source_label(source) -> str:
    source_type = getattr(source, "source_type", None)
    return getattr(source_type, "value", "slack-command")


def _build_preview_message(extraction, tracking_summary: str) -> str:
    title = extraction.meeting_title or "Untitled meeting"
    lines = [
        "*Preview ready.* No draft was created.",
        f"*Title:* {title}",
        f"*Summary:* {tracking_summary}",
    ]

    if extraction.status_summary:
        lines.append(f"*Status:* {extraction.status_summary}")
    if extraction.priority_focus:
        lines.append(f"*Priority focus:* {extraction.priority_focus}")

    lines.extend(["", "*What FollowThru captured*"])

    if extraction.decisions:
        lines.append("*Decisions*")
        lines.extend(f"- {item.content}" for item in extraction.decisions[:3])

    if extraction.action_items:
        lines.append("*Action items*")
        for item in extraction.action_items[:5]:
            detail_parts = []
            if item.owner:
                detail_parts.append(f"owner {item.owner}")
            if item.due_date:
                detail_parts.append(f"due {item.due_date.isoformat()}")
            suffix = f" ({', '.join(detail_parts)})" if detail_parts else ""
            lines.append(f"- {item.content}{suffix}")

    attention_items = [
        *(f"Risk: {item.content}" for item in extraction.risks[:3]),
        *(f"Question: {item.content}" for item in extraction.open_questions[:3]),
    ]
    if attention_items:
        lines.append("*Attention*")
        lines.extend(f"- {item}" for item in attention_items)

    if not extraction.decisions and not extraction.action_items and not attention_items:
        lines.append(
            "- No structured decisions, action items, or risks were detected yet."
        )

    lines.extend(
        [
            "",
            "Use `/followthru publish` in the channel when you're ready to update the channel canvas.",
        ]
    )
    return "\n".join(lines)


def _respond_privately(respond, text: str) -> None:
    respond(text=text, response_type="ephemeral")


def _strip_mention_tokens(text: str) -> str:
    return " ".join(
        token
        for token in text.split()
        if not (token.startswith("<@") and token.endswith(">"))
    ).strip()


def _build_dm_source_text(event) -> str:
    text_parts: list[str] = []
    message_text = (event.get("text") or "").strip()
    if message_text:
        text_parts.append(message_text)

    file_text_parts = []
    unsupported_files = []
    for file_info in event.get("files", []):
        file_text = _extract_supported_file_text(file_info)
        if file_text:
            file_text_parts.append(file_text)
        else:
            unsupported_files.append(file_info.get("name", "uploaded file"))

    if unsupported_files and not text_parts and not file_text_parts:
        return ""
    return "\n\n".join(part for part in [*text_parts, *file_text_parts] if part)


def _extract_supported_file_text(file_info) -> str | None:
    mimetype = (file_info.get("mimetype") or "").lower()
    filetype = (file_info.get("filetype") or "").lower()
    preview = (file_info.get("preview") or "").strip()
    if preview and filetype in {"text", "csv", "markdown"}:
        return preview

    if not (
        mimetype.startswith("text/") or filetype in {"text", "csv", "markdown", "md"}
    ):
        return None

    download_url = file_info.get("url_private_download") or file_info.get("url_private")
    if not download_url:
        return None

    try:
        return slack_client.download_text_file(download_url).strip()
    except Exception:
        return None
