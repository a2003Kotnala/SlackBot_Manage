from __future__ import annotations

from app.domain.schemas.followthru import FollowThruMode

DM_HELP_TEXT = (
    "*FollowThru DM guide*\n"
    "- Run `stop` or `/followthru stop` to cancel the latest meeting job in this DM.\n"
    "- Paste transcript text for shorter meeting notes.\n"
    "- Upload transcript files in `.txt`, `.md`, `.csv`, `.tsv`, `.srt`, `.vtt`, `.log`, or `.docx`.\n"
    "- Paste a supported Zoom recording link and FollowThru will fetch the transcript or transcribe the media.\n"
    "- Start with `preview` for a private preview, `draft` for a saved draft, or `publish` to create a standalone Slack canvas."
)
DM_ACCEPTED_MESSAGE = (
    "*Processing your meeting notes...*\n"
    "_I accepted the job and will post progress here._"
)
DM_PREVIEW_FOOTER = (
    "Use `publish` in this DM to create a standalone Slack canvas, "
    "or `draft` to save a local draft without publishing."
)
DM_CANVAS_MARKDOWN_LIMIT = 3500


def build_preview_message(extraction, footer: str | None = None) -> str:
    title = extraction.meeting_title or "Untitled meeting"
    lines = ["*Preview ready.* No draft was created.", f"*Title:* {title}"]

    if extraction.summary:
        lines.append(f"*Summary:* {extraction.summary}")
    if extraction.status_summary:
        lines.append(f"*Current status:* {extraction.status_summary}")
    if extraction.priority_focus:
        lines.append(f"*Priority focus:* {extraction.priority_focus}")

    if extraction.decisions:
        lines.extend(["", "*Key decisions*"])
        lines.extend(f"{index}. {item.content}" for index, item in enumerate(extraction.decisions[:5], start=1))

    if extraction.action_items:
        lines.extend(["", "*Action items*"])
        for item in extraction.action_items[:5]:
            detail_parts = []
            if item.owner:
                detail_parts.append(f"owner {item.owner}")
            if item.due_date:
                detail_parts.append(f"due {item.due_date.isoformat()}")
            suffix = f" ({', '.join(detail_parts)})" if detail_parts else ""
            lines.append(f"- {item.content}{suffix}")

    if extraction.risks:
        lines.extend(["", "*Risks*"])
        lines.extend(f"{index}. {item.content}" for index, item in enumerate(extraction.risks[:5], start=1))

    if extraction.open_questions:
        lines.extend(["", "*Open questions*"])
        lines.extend(
            f"{index}. {item.content}"
            for index, item in enumerate(extraction.open_questions[:5], start=1)
        )

    lines.extend(["", footer or DM_PREVIEW_FOOTER])
    return "\n".join(lines)


def build_completion_message(
    response,
    processed_files: list[str] | None = None,
    skipped_files: list[str] | None = None,
    transcript_artifact_name: str | None = None,
) -> str:
    if response.mode == FollowThruMode.help:
        return DM_HELP_TEXT

    if response.mode == FollowThruMode.preview and response.extraction:
        message = build_preview_message(response.extraction)
    else:
        header = "*Canvas ready.*" if response.slack_canvas_id else "*Draft ready.*"
        lines = [header, "", response.reply]

        if not response.slack_canvas_id and response.draft_canvas_markdown:
            canvas_markdown = response.draft_canvas_markdown.strip()
            if len(canvas_markdown) > DM_CANVAS_MARKDOWN_LIMIT:
                canvas_markdown = (
                    canvas_markdown[:DM_CANVAS_MARKDOWN_LIMIT].rstrip() + "\n..."
                )
            lines.extend(["", "*Canvas draft*", f"```{canvas_markdown}```"])
        message = "\n".join(lines)

    notices: list[str] = []
    if transcript_artifact_name:
        notices.append(
            "_Saved a transcript file copy as "
            f"`{transcript_artifact_name}` so you can reuse it from Slack Files._"
        )
    if processed_files:
        names = ", ".join(f"`{name}`" for name in processed_files[:3])
        notices.append(f"_Processed uploaded file(s): {names}._")
    if skipped_files:
        names = ", ".join(f"`{name}`" for name in skipped_files[:3])
        notices.append(f"_Skipped file(s) I could not use: {names}._")

    if notices:
        message = "\n".join([message, "", *notices])
    return message


def build_failure_message(reason: str | None = None) -> str:
    if reason:
        return (
            "*I could not complete that job.*\n"
            f"_{reason}_"
        )
    return (
        "*I hit a snag while processing that source.*\n"
        "_Please try again in a moment._"
    )


def build_stopped_message() -> str:
    return "*Stopped.*\n" "_This job was cancelled by the user._"
