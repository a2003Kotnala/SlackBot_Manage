from app.slack.services.source_resolver import resolve_latest_huddle_notes_canvas
from app.domain.services.extraction_service import extract_structured_meeting_data
from app.domain.services.draft_service import create_draft

def register_handlers(bolt_app):
    @bolt_app.command("/zmanage")
    async def handle_zmanage(ack, say, command):
        await ack()
        channel_id = command["channel_id"]
        thread_ts = command.get("thread_ts")
        user_id = command["user_id"]

        source = await resolve_latest_huddle_notes_canvas(channel_id, thread_ts, user_id)
        if source:
            extraction = await extract_structured_meeting_data(source.raw_content_reference)
            draft = await create_draft(user_id, str(source.id), extraction)

            await say(f"Draft created! Canvas ID: {draft.slack_canvas_id}. Review and share when ready.")
        else:
            await say("No recent huddle notes canvas found. Try /zmanage text.")
