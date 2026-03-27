from __future__ import annotations

from app.domain.schemas.ingestion import IngestionJobStatus

ALLOWED_JOB_TRANSITIONS: dict[IngestionJobStatus, set[IngestionJobStatus]] = {
    IngestionJobStatus.received: {
        IngestionJobStatus.classified,
        IngestionJobStatus.failed,
        IngestionJobStatus.unsupported_source,
    },
    IngestionJobStatus.classified: {
        IngestionJobStatus.validated,
        IngestionJobStatus.failed,
        IngestionJobStatus.unsupported_source,
        IngestionJobStatus.needs_permission,
    },
    IngestionJobStatus.validated: {
        IngestionJobStatus.queued,
        IngestionJobStatus.failed,
    },
    IngestionJobStatus.queued: {
        IngestionJobStatus.fetching_source,
        IngestionJobStatus.cleaning_transcript,
        IngestionJobStatus.failed,
        IngestionJobStatus.unsupported_source,
    },
    IngestionJobStatus.fetching_source: {
        IngestionJobStatus.fetched,
        IngestionJobStatus.failed,
        IngestionJobStatus.retrying,
        IngestionJobStatus.needs_permission,
    },
    IngestionJobStatus.fetched: {
        IngestionJobStatus.normalizing_media,
        IngestionJobStatus.transcribing,
        IngestionJobStatus.cleaning_transcript,
        IngestionJobStatus.failed,
    },
    IngestionJobStatus.normalizing_media: {
        IngestionJobStatus.transcribing,
        IngestionJobStatus.failed,
        IngestionJobStatus.retrying,
    },
    IngestionJobStatus.transcribing: {
        IngestionJobStatus.cleaning_transcript,
        IngestionJobStatus.failed,
        IngestionJobStatus.retrying,
    },
    IngestionJobStatus.cleaning_transcript: {
        IngestionJobStatus.extracting_intelligence,
        IngestionJobStatus.failed,
    },
    IngestionJobStatus.extracting_intelligence: {
        IngestionJobStatus.rendering_canvas,
        IngestionJobStatus.failed,
    },
    IngestionJobStatus.rendering_canvas: {
        IngestionJobStatus.completed,
        IngestionJobStatus.failed,
    },
    IngestionJobStatus.retrying: {
        IngestionJobStatus.queued,
        IngestionJobStatus.fetching_source,
        IngestionJobStatus.transcribing,
        IngestionJobStatus.failed,
    },
    IngestionJobStatus.needs_permission: {
        IngestionJobStatus.failed,
        IngestionJobStatus.queued,
    },
    IngestionJobStatus.unsupported_source: set(),
    IngestionJobStatus.completed: set(),
    IngestionJobStatus.failed: set(),
}


def validate_job_transition(
    current_status: IngestionJobStatus,
    new_status: IngestionJobStatus,
) -> None:
    if current_status == new_status:
        return
    if new_status not in ALLOWED_JOB_TRANSITIONS[current_status]:
        raise ValueError(f"Invalid job transition: {current_status} -> {new_status}")
