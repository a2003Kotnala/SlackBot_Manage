from app.domain.schemas.followthru import (
    FollowThruChatRequest,
    FollowThruMode,
)
from app.domain.services.draft_service import create_draft
from app.domain.services.extraction_service import extract_structured_meeting_data
from app.domain.services.followthru_service import (
    LEGACY_SLACK_COMMAND,
    PRIMARY_SLACK_COMMAND,
    clear_followthru_dm_session,
    handle_followthru_chat,
)
from app.integrations.slack_client import slack_client
from app.logger import logger
from app.slack.services.source_resolver import (
    resolve_latest_huddle_notes_canvas,
)

HELP_TEXT = (
    "*FollowThru command guide*\n"
    "In channels:\n"
    "- `/followthru` previews the latest huddle notes for this channel.\n"
    "- `/followthru publish` publishes the latest huddle notes "
    "to the channel canvas.\n"
    "In DMs:\n"
    "- `/followthru clear` clears FollowThru chat state in this DM and removes "
    "recent bot chat messages.\n"
    "- Paste a transcript or upload a plain-text transcript file "
    "to create a private canvas workflow.\n"
    "FollowThru keeps command output private to the person who runs it."
)

MISSING_SOURCE_MESSAGE = (
    "No recent huddle notes canvas found. "
    "Finish the huddle notes first, or DM FollowThru with pasted transcript "
    "text or a text file."
)

CHANNEL_TEXT_REDIRECT_MESSAGE = (
    "Channel commands only work from the latest huddle notes for that channel. "
    "To process custom transcript text or a file, DM FollowThru instead."
)

DM_HELP_TEXT = (
    "*FollowThru DM guide*\n"
    "- Run `/followthru clear` for a fresh FollowThru reset in this DM.\n"
    "- Paste transcript text or upload a plain-text transcript file and "
    "FollowThru will create a standalone canvas in Slack when possible.\n"
    "- Start with `preview` if you only want a private preview.\n"
    "- Start with `draft` to save a local draft without publishing.\n"
    "- Start with `publish` to create a standalone canvas you can edit and share."
)
DM_CLEAR_CHANNEL_MESSAGE = (
    "`/followthru clear` only works in a DM with FollowThru."
)

DM_PREVIEW_FOOTER = (
    "Use `publish` in this DM to create a standalone Slack canvas, "
    "or `draft` to save a local draft without publishing."
)
DM_CANVAS_MARKDOWN_LIMIT = 3500
DM_PROCESSING_MESSAGE = (
    ":hourglass_flowing_sand: *Processing your transcript...*\n"
    "_Finding decisions, linking owners, and shaping your canvas._"
)
DM_FAILURE_MESSAGE = (
    ":warning: *I hit a snag while processing that transcript.*\n"
    "_Please try again in a moment._"
)


def register_handlers(bolt_app) -> None:
    def handle_followthru_command(ack, command, respond):
        ack()

        channel_id = command["channel_id"]
        thread_ts = command.get("thread_ts")
        user_id = command["user_id"]
        mode, text = _parse_command_text((command.get("text") or "").strip())
        is_dm = channel_id.startswith("D")

        if mode == "help":
            _respond_privately(respond, DM_HELP_TEXT if is_dm else HELP_TEXT)
            return

        if mode == "clear":
            if not is_dm:
                _respond_privately(respond, DM_CLEAR_CHANNEL_MESSAGE)
                return

            clear_result = clear_followthru_dm_session(channel_id)
            removed_bot_messages = _clear_dm_bot_messages(channel_id)
            _respond_privately(
                respond,
                _build_dm_clear_message(
                    clear_result,
                    removed_bot_messages,
                ),
            )
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

        status_message = say(text=DM_PROCESSING_MESSAGE)
        message_ref = _extract_message_ref(status_message, event["channel"])

        try:
            response = handle_followthru_chat(
                FollowThruChatRequest(
                    message=_normalize_dm_request(dm_text),
                    user_id=event["user"],
                    channel_id=event["channel"],
                    thread_ts=event.get("thread_ts") or event["ts"],
                )
            )
            final_text = _build_dm_followthru_message(response)
        except Exception:
            logger.exception("Failed to process FollowThru DM transcript")
            final_text = DM_FAILURE_MESSAGE

        if _update_dm_status_message(message_ref, final_text):
            return

        say(text=final_text)


def _parse_command_text(text: str) -> tuple[str, str]:
    if not text:
        return "preview", ""

    command, _, remainder = text.partition(" ")
    mode = command.lower()
    if mode in {"publish", "preview", "help", "clear"}:
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


def _build_preview_message(
    extraction,
    tracking_summary: str,
    footer: str | None = None,
) -> str:
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
            footer
            or (
                "Use `/followthru publish` in the channel when you're ready "
                "to update the channel canvas."
            ),
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


def _normalize_dm_request(dm_text: str) -> str:
    normalized = dm_text.strip()
    lowered = normalized.lower()
    if any(
        lowered.startswith(prefix)
        for prefix in (
            "help",
            "what can you do",
            "capabilities",
            "how do i use",
            "preview",
            "show preview",
            "dry run",
            "generate preview",
            "draft",
            "save draft",
            "create draft",
            "publish",
            "ship it",
            "update canvas",
            "send to canvas",
            "push to canvas",
        )
    ):
        return normalized
    return f"publish {normalized}"


def _build_dm_followthru_message(response) -> str:
    if response.mode == FollowThruMode.help:
        return DM_HELP_TEXT

    if response.mode == FollowThruMode.preview and response.extraction:
        return _build_preview_message(
            response.extraction,
            _build_tracking_summary(response.extraction),
            footer=DM_PREVIEW_FOOTER,
        )

    lines = [_build_dm_completion_banner(response), "", response.reply]
    if response.draft_title and response.draft_title not in response.reply:
        lines.append(f"*Title:* {response.draft_title}")

    if not response.slack_canvas_id and response.draft_canvas_markdown:
        canvas_markdown = response.draft_canvas_markdown.strip()
        if len(canvas_markdown) > DM_CANVAS_MARKDOWN_LIMIT:
            canvas_markdown = (
                canvas_markdown[:DM_CANVAS_MARKDOWN_LIMIT].rstrip() + "\n..."
            )
            lines.append(
                "_Canvas markdown is truncated in chat, but the full draft "
                "is stored by FollowThru._"
            )

        lines.extend(["", "*Canvas draft*", f"```{canvas_markdown}```"])

    return "\n".join(lines)


def _build_dm_completion_banner(response) -> str:
    if response.slack_canvas_id:
        return (
            ":sparkles: *Canvas ready.*\n"
            "_Done creating it. Hope you enjoyed it. See you soon._"
        )
    if response.mode in {FollowThruMode.draft, FollowThruMode.publish}:
        return (
            ":spiral_note_pad: *Draft ready.*\n"
            "_Canvas is prepared. Hope you enjoyed it. See you soon._"
        )
    return ":white_check_mark: *Done.*"


def _extract_message_ref(
    message_response, fallback_channel: str | None = None
) -> dict[str, str] | None:
    if message_response is None:
        return None

    channel_id = _response_value(message_response, "channel") or fallback_channel
    message_ts = _response_value(message_response, "ts")
    if not channel_id or not message_ts:
        return None
    return {"channel": channel_id, "ts": message_ts}


def _response_value(message_response, key: str) -> str | None:
    if isinstance(message_response, dict):
        return message_response.get(key)

    getter = getattr(message_response, "get", None)
    if callable(getter):
        value = getter(key)
        if value is not None:
            return value

    try:
        return message_response[key]
    except Exception:
        return getattr(message_response, key, None)


def _update_dm_status_message(message_ref: dict[str, str] | None, text: str) -> bool:
    if not message_ref:
        return False

    try:
        slack_client.update_message(message_ref["channel"], message_ref["ts"], text)
        return True
    except Exception:
        logger.warning(
            "Failed to update DM status message; sending a new message instead"
        )
        return False


def _clear_dm_bot_messages(channel_id: str, history_limit: int = 100) -> int:
    try:
        messages = slack_client.get_channel_history(channel_id, limit=history_limit)
    except Exception:
        logger.warning("Failed to load DM history for clear command")
        return 0

    removed = 0
    for message in messages:
        if not _is_followthru_bot_message(message):
            continue
        try:
            slack_client.delete_message(channel_id, message["ts"])
            removed += 1
        except Exception:
            logger.warning("Failed to delete bot DM message during clear")
    return removed


def _is_followthru_bot_message(message: dict) -> bool:
    subtype = message.get("subtype")
    return bool(message.get("bot_id") or subtype == "bot_message")


def _build_dm_clear_message(
    clear_result,
    removed_bot_messages: int,
) -> str:
    cleared_total = sum(
        [
            clear_result.cleared_sessions,
            clear_result.cleared_messages,
            removed_bot_messages,
        ]
    )
    if not cleared_total:
        return (
            "Fresh start ready. There was no FollowThru chat state to clear, "
            "and your standalone canvases were left untouched."
        )

    return (
        "Fresh start ready. FollowThru chat state was cleared and recent bot "
        "chat messages were removed where Slack allowed it. Your standalone "
        "canvases were left untouched."
    )


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
