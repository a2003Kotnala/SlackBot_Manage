from __future__ import annotations

from app.domain.schemas.followthru import FollowThruMode
from app.domain.schemas.ingestion import SlackFileReference
from app.domain.services.ingestion_job_service import (
    create_or_get_slack_ingestion_job,
    prepare_job_for_enqueue,
    record_status_message,
    request_job_stop,
)
from app.slack.services.dm_response_builder import DM_ACCEPTED_MESSAGE, DM_HELP_TEXT
from app.workers.job_queue import job_queue


def handle_dm_ingestion_event(event, say) -> bool:
    message_text = (event.get("text") or "").strip()
    files = [
        SlackFileReference.model_validate(file_info)
        for file_info in (event.get("files") or [])
    ]

    if not message_text and not files:
        say(text=DM_HELP_TEXT)
        return True

    if message_text.lower() in {"help", "hi", "hello"}:
        say(text=DM_HELP_TEXT)
        return True

    if message_text.lower() == "stop" and not files:
        stop_result = request_job_stop(event["channel"])
        if stop_result.stopped:
            say(
                text=(
                    "Stop requested. FollowThru will halt the current meeting job "
                    "shortly."
                    if stop_result.active
                    else "FollowThru stopped the queued meeting job for this DM."
                )
            )
        else:
            say(text="There is no active FollowThru job to stop in this DM.")
        return True

    creation = create_or_get_slack_ingestion_job(
        workspace_external_id=event.get("team")
        or event.get("team_id")
        or "slack-default",
        workspace_name=event.get("team") or "Slack Workspace",
        slack_user_id=event["user"],
        channel_id=event["channel"],
        message_ts=event["ts"],
        thread_ts=event.get("thread_ts") or event["ts"],
        message_text=message_text,
        files=files,
    )

    if creation.classification.requested_mode == FollowThruMode.help:
        say(text=DM_HELP_TEXT)
        return True

    if creation.created:
        response = say(text=DM_ACCEPTED_MESSAGE)
        status_ts = _extract_message_ts(response)
        if status_ts:
            record_status_message(creation.job.id, status_ts)
        prepare_job_for_enqueue(creation.job.id)
        job_queue.enqueue(creation.job.id)
        return True

    return True


def _extract_message_ts(response) -> str | None:
    if response is None:
        return None
    if isinstance(response, dict):
        return response.get("ts")
    getter = getattr(response, "get", None)
    if callable(getter):
        return getter("ts")
    return getattr(response, "ts", None)
