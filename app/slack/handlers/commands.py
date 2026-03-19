from app.domain.services.draft_service import create_draft
from app.domain.services.extraction_service import extract_structured_meeting_data
from app.slack.services.source_resolver import (
    create_text_source,
    resolve_latest_huddle_notes_canvas,
)


def register_handlers(bolt_app) -> None:
    @bolt_app.command("/zmanage")
    def handle_zmanage(ack, say, command):
        ack()

        channel_id = command["channel_id"]
        thread_ts = command.get("thread_ts")
        user_id = command["user_id"]
        text = (command.get("text") or "").strip()

        if text:
            source = create_text_source(
                raw_content=text,
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
            )
        else:
            source = resolve_latest_huddle_notes_canvas(channel_id, thread_ts, user_id)

        if not source:
            say(
                "No recent huddle notes canvas found. "
                "Provide inline notes after /zmanage to process text directly."
            )
            return

        extraction = extract_structured_meeting_data(source.raw_content_reference)
        draft, _canvas_content = create_draft(source.created_by, source, extraction)

        if draft.slack_canvas_id:
            say(
                "Draft created successfully. "
                f"Title: {draft.title}. "
                f"Slack canvas ID: {draft.slack_canvas_id}."
            )
            return

        say(
            "Draft created locally. "
            f"Title: {draft.title}. "
            "Slack publication was skipped or unavailable."
        )
