from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

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
    "- `/followthru stop` cancels the latest in-flight meeting job for this DM.\n"
    "- Paste a transcript directly for shorter notes, or upload a transcript "
    "file for larger Zoom, Meet, or Slack huddles.\n"
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
    "- Paste transcript text for shorter notes.\n"
    "- For larger transcripts, upload a file and FollowThru will turn it into "
    "a standalone canvas when possible.\n"
    "- Supported uploads: `.txt`, `.md`, `.csv`, `.tsv`, `.srt`, `.vtt`, "
    "and `.docx`.\n"
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
DM_TRANSCRIPT_ARTIFACT_THRESHOLD = 8000
DM_SUPPORTED_TRANSCRIPT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".srt",
    ".vtt",
    ".log",
    ".docx",
}
DM_SUPPORTED_TEXT_FILETYPES = {
    "text",
    "txt",
    "csv",
    "markdown",
    "md",
    "tsv",
    "srt",
    "vtt",
    "log",
}
DM_SUPPORTED_DOCX_MIMETYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
DM_SUPPORTED_UPLOAD_LABEL = "`.txt`, `.md`, `.csv`, `.tsv`, `.srt`, `.vtt`, or `.docx`"


@dataclass
class DMSourcePayload:
    text: str = ""
    had_files: bool = False
    processed_files: list[str] = field(default_factory=list)
    unreadable_files: list[str] = field(default_factory=list)
    unsupported_files: list[str] = field(default_factory=list)
    artifact_content: str | None = None
    artifact_filename: str | None = None
    artifact_title: str | None = None


def register_handlers(bolt_app) -> None:
    def handle_followthru_command(ack, command, respond):
        ack()

        channel_id = command["channel_id"]
        thread_ts = command.get("thread_ts")
        user_id = command["user_id"]
        mode, text = _parse_command_text((command.get("text") or "").strip())
        is_dm = channel_id.startswith("D")

        if mode == "help":
            if is_dm:
                # Send a REAL message in DMs so it can be cleared later
                from app.integrations.slack_client import slack_client
                slack_client.client.chat_postMessage(channel=channel_id, text=DM_HELP_TEXT)
            else:
                # Keep channel help messages ephemeral so we don't spam the team
                _respond_privately(respond, HELP_TEXT)
            return

        if mode == "clear":
            if not is_dm:
                _respond_privately(respond, DM_CLEAR_CHANNEL_MESSAGE)
                return

            clear_followthru_dm_session(channel_id)
            removed_bot_messages =_clear_dm_bot_messages(channel_id)
            # _respond_privately(
            #     respond,
            #     _build_dm_clear_message(
            #         clear_result,
            #         removed_bot_messages,
            #     ),
            # )
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
        if event.get("bot_id") or event.get("subtype") in {"message_changed", "message_deleted"}:
            return

        dm_payload = _build_dm_source_payload(event)
        if not dm_payload.text:
            say(text=_build_dm_file_support_message(dm_payload))
            return

        lowered = dm_payload.text.lower()
        if lowered in {"help", "hi", "hello"}:
            slack_client.client.chat_postMessage(channel=event["channel"], text=DM_HELP_TEXT)
            return

        status_message = say(text=DM_PROCESSING_MESSAGE)
        message_ref = _extract_message_ref(status_message, event["channel"])
        transcript_artifact = _upload_dm_transcript_artifact(
            event["channel"],
            dm_payload,
        )

        try:
            response = handle_followthru_chat(
                FollowThruChatRequest(
                    message=_normalize_dm_request(dm_payload.text),
                    user_id=event["user"],
                    channel_id=event["channel"],
                    thread_ts=event.get("thread_ts") or event["ts"],
                )
            )
            final_text = _build_dm_followthru_message(
                response,
                dm_payload=dm_payload,
                transcript_artifact=transcript_artifact,
            )
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
    if mode in {"publish", "preview", "help", "clear", "stop"}:
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


def _build_dm_source_payload(event) -> DMSourcePayload:
    payload = DMSourcePayload(had_files=bool(event.get("files")))
    text_parts: list[str] = []
    message_text = (event.get("text") or "").strip()
    if message_text:
        text_parts.append(message_text)

    for file_info in event.get("files", []):
        file_text, status = _extract_supported_file_text(file_info)
        file_name = file_info.get("name", "uploaded file")
        if file_text:
            text_parts.append(file_text)
            payload.processed_files.append(file_name)
            continue
        if status == "unreadable":
            payload.unreadable_files.append(file_name)
        else:
            payload.unsupported_files.append(file_name)

    payload.text = "\n\n".join(part for part in text_parts if part)

    if message_text and len(message_text) >= DM_TRANSCRIPT_ARTIFACT_THRESHOLD:
        payload.artifact_content = _strip_dm_mode_prefix(message_text)
        event_dt = _event_datetime(event.get("ts"))
        payload.artifact_filename = (
            f"followthru-transcript-{event_dt:%Y%m%d-%H%M%S}.txt"
        )
        payload.artifact_title = f"FollowThru Transcript | {event_dt:%d %b %I:%M %p}"

    return payload


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


def _build_dm_followthru_message(
    response,
    dm_payload: DMSourcePayload | None = None,
    transcript_artifact: dict | None = None,
) -> str:
    if response.mode == FollowThruMode.help:
        return DM_HELP_TEXT

    if response.mode == FollowThruMode.preview and response.extraction:
        preview_message = _build_preview_message(
            response.extraction,
            _build_tracking_summary(response.extraction),
            footer=DM_PREVIEW_FOOTER,
        )
        notices = _build_dm_result_notices(dm_payload, transcript_artifact)
        if not notices:
            return preview_message
        return "\n".join([preview_message, "", *notices])

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

    notices = _build_dm_result_notices(dm_payload, transcript_artifact)
    if notices:
        lines.extend(["", *notices])

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
    from app.config import settings
    return bool(message.get("bot_id") or subtype == "bot_message" or "bot_profile" in message)

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


def _build_dm_file_support_message(dm_payload: DMSourcePayload) -> str:
    if dm_payload.unreadable_files:
        file_names = ", ".join(f"`{name}`" for name in dm_payload.unreadable_files[:3])
        return (
            ":paperclip: *I found a transcript file but could not read it yet.*\n"
            f"_Try re-exporting {file_names} as plain text, or upload one of "
            f"{DM_SUPPORTED_UPLOAD_LABEL}._"
        )

    if dm_payload.unsupported_files:
        file_names = ", ".join(
            f"`{name}`" for name in dm_payload.unsupported_files[:3]
        )
        return (
            ":paperclip: *That upload format is not supported yet.*\n"
            f"_I can currently process transcript files in "
            f"{DM_SUPPORTED_UPLOAD_LABEL}. Please re-upload {file_names} "
            "in one of those formats, or paste a shorter excerpt here._"
        )

    return DM_HELP_TEXT


def _build_dm_result_notices(
    dm_payload: DMSourcePayload | None,
    transcript_artifact: dict | None,
) -> list[str]:
    notices: list[str] = []
    if transcript_artifact:
        artifact_name = transcript_artifact.get("name") or "uploaded transcript"
        notices.append(
            "_Saved a transcript file copy as "
            f"`{artifact_name}` so you can reuse it from Slack Files._"
        )

    if dm_payload and dm_payload.processed_files:
        names = ", ".join(f"`{name}`" for name in dm_payload.processed_files[:3])
        notices.append(f"_Processed uploaded transcript file(s): {names}._")

    skipped_files = []
    if dm_payload:
        skipped_files.extend(dm_payload.unreadable_files)
        skipped_files.extend(dm_payload.unsupported_files)
    if skipped_files:
        names = ", ".join(f"`{name}`" for name in skipped_files[:3])
        notices.append(
            "_Skipped file(s) I could not use: "
            f"{names}. Best results come from {DM_SUPPORTED_UPLOAD_LABEL}._"
        )

    return notices


def _upload_dm_transcript_artifact(
    channel_id: str,
    dm_payload: DMSourcePayload,
) -> dict | None:
    if not dm_payload.artifact_content or not dm_payload.artifact_filename:
        return None

    try:
        return slack_client.upload_text_file(
            channel_id=channel_id,
            filename=dm_payload.artifact_filename,
            content=dm_payload.artifact_content,
            title=dm_payload.artifact_title,
        )
    except Exception as exc:
        logger.warning("Failed to upload DM transcript artifact: %s", exc)
        return None


def _extract_supported_file_text(file_info) -> tuple[str | None, str]:
    hydrated_file = _hydrate_dm_file_info(file_info)
    if not _is_supported_transcript_file(hydrated_file):
        return None, "unsupported"

    preview = (hydrated_file.get("preview") or "").strip()
    if preview and _is_text_transcript_file(hydrated_file):
        return preview, "ok"

    download_url = hydrated_file.get("url_private_download") or hydrated_file.get(
        "url_private"
    )
    if not download_url:
        return None, "unreadable"

    try:
        if _is_docx_transcript_file(hydrated_file):
            extracted_text = _extract_docx_text(
                slack_client.download_file_bytes(download_url)
            )
        else:
            extracted_text = slack_client.download_text_file(download_url)
    except Exception:
        return None, "unreadable"

    cleaned_text = extracted_text.strip()
    if not cleaned_text:
        return None, "unreadable"
    return cleaned_text, "ok"


def _hydrate_dm_file_info(file_info: dict) -> dict:
    if file_info.get("preview") or file_info.get("url_private_download"):
        return file_info

    file_id = file_info.get("id")
    if not file_id:
        return file_info

    try:
        details = slack_client.get_file_content(file_id)
    except Exception:
        return file_info
    return {**details, **file_info}


def _is_supported_transcript_file(file_info: dict) -> bool:
    mimetype = (file_info.get("mimetype") or "").lower()
    filetype = (file_info.get("filetype") or "").lower()
    extension = _file_extension(file_info)
    return (
        extension in DM_SUPPORTED_TRANSCRIPT_EXTENSIONS
        or mimetype.startswith("text/")
        or filetype in DM_SUPPORTED_TEXT_FILETYPES
        or mimetype in DM_SUPPORTED_DOCX_MIMETYPES
        or filetype == "docx"
    )


def _is_text_transcript_file(file_info: dict) -> bool:
    mimetype = (file_info.get("mimetype") or "").lower()
    filetype = (file_info.get("filetype") or "").lower()
    extension = _file_extension(file_info)
    return (
        mimetype.startswith("text/")
        or filetype in DM_SUPPORTED_TEXT_FILETYPES
        or extension in DM_SUPPORTED_TRANSCRIPT_EXTENSIONS - {".docx"}
    )


def _is_docx_transcript_file(file_info: dict) -> bool:
    mimetype = (file_info.get("mimetype") or "").lower()
    filetype = (file_info.get("filetype") or "").lower()
    extension = _file_extension(file_info)
    return (
        extension == ".docx"
        or filetype == "docx"
        or mimetype in DM_SUPPORTED_DOCX_MIMETYPES
    )


def _file_extension(file_info: dict) -> str:
    return Path(file_info.get("name") or "").suffix.lower()


def _extract_docx_text(file_bytes: bytes) -> str:
    try:
        with ZipFile(BytesIO(file_bytes)) as archive:
            document_xml = archive.read("word/document.xml")
    except (BadZipFile, KeyError):
        return ""

    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError:
        return ""

    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        parts: list[str] = []
        for node in paragraph.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "t" and node.text:
                parts.append(node.text)
            elif tag == "tab":
                parts.append("\t")
            elif tag in {"br", "cr"}:
                parts.append("\n")
        paragraph_text = "".join(parts).strip()
        if paragraph_text:
            paragraphs.append(paragraph_text)

    return "\n".join(paragraphs).strip()


def _strip_dm_mode_prefix(message_text: str) -> str:
    normalized = message_text.strip()
    lowered = normalized.lower()
    prefixes = (
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
    for prefix in prefixes:
        if lowered.startswith(prefix):
            remainder = normalized[len(prefix) :].strip(" :,-\n")
            return remainder or normalized
    return normalized


def _event_datetime(event_ts: str | None) -> datetime:
    if not event_ts:
        return datetime.now()
    try:
        return datetime.fromtimestamp(float(event_ts))
    except (TypeError, ValueError):
        return datetime.now()
