from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Timer
from uuid import UUID, uuid4

import httpx

from app.config import settings
from app.db.models.audit_log import AuditLog
from app.db.models.canvas_version import CanvasVersion
from app.db.models.extraction_result_record import ExtractionResultRecord
from app.db.models.ingestion_job import IngestionJob
from app.db.models.normalized_artifact import NormalizedArtifact
from app.db.models.provider_access_record import ProviderAccessRecord
from app.db.models.retry_record import RetryRecord
from app.db.models.source_artifact import SourceArtifact
from app.db.models.transcript_artifact import TranscriptArtifact
from app.db.models.user import User
from app.db.models.workspace import Workspace
from app.db.session import SessionLocal
from app.domain.providers.base import ProviderAuthContext
from app.domain.providers.registry import resolve_provider_adapter
from app.domain.schemas.followthru import FollowThruChatRequest
from app.domain.schemas.ingestion import (
    ArtifactKind,
    IngestionJobStatus,
    IngestionSourceType,
    InputClassification,
    SlackFileReference,
    TranscriptDocument,
)
from app.domain.services.followthru_service import handle_followthru_chat
from app.domain.services.input_classifier import classify_slack_input
from app.domain.services.job_state_machine import validate_job_transition
from app.domain.services.media_processing_service import (
    MediaProcessingError,
    normalize_media_to_audio,
)
from app.domain.services.transcript_cleaner import clean_transcript
from app.domain.services.transcript_parser import (
    is_supported_media_file,
    parse_transcript_bytes,
    parse_transcript_text,
)
from app.domain.services.transcription_service import (
    TranscriptionError,
    transcribe_audio_file,
)
from app.integrations.slack_client import slack_client
from app.logger import logger
from app.slack.services.dm_response_builder import (
    build_completion_message,
    build_failure_message,
    build_stopped_message,
)

SUPPORTED_FILE_ARTIFACT_TYPE = "slack_file"
MESSAGE_ARTIFACT_TYPE = ArtifactKind.slack_message.value
RECORDING_LINK_ARTIFACT_TYPE = ArtifactKind.recording_link.value
STOP_REQUESTED_REASON = "Stopped by user."
TERMINAL_JOB_STATUSES = {
    IngestionJobStatus.completed,
    IngestionJobStatus.failed,
    IngestionJobStatus.unsupported_source,
}
STOPPABLE_ACTIVE_JOB_STATUSES = {
    IngestionJobStatus.fetching_source,
    IngestionJobStatus.fetched,
    IngestionJobStatus.normalizing_media,
    IngestionJobStatus.transcribing,
    IngestionJobStatus.cleaning_transcript,
    IngestionJobStatus.extracting_intelligence,
    IngestionJobStatus.rendering_canvas,
}
STOPPABLE_PENDING_JOB_STATUSES = {
    IngestionJobStatus.received,
    IngestionJobStatus.classified,
    IngestionJobStatus.validated,
    IngestionJobStatus.queued,
    IngestionJobStatus.retrying,
    IngestionJobStatus.needs_permission,
}


class UnsupportedSourceError(RuntimeError):
    pass


class RetryableJobError(RuntimeError):
    pass


class JobStoppedError(RuntimeError):
    pass


@dataclass
class JobCreationResult:
    job: IngestionJob
    classification: InputClassification
    created: bool


@dataclass
class ResolvedTranscript:
    document: TranscriptDocument
    processed_files: list[str]
    skipped_files: list[str]


@dataclass
class JobStopResult:
    stopped: bool
    job_id: str | None = None
    active: bool = False
    status: IngestionJobStatus | None = None


def create_or_get_slack_ingestion_job(
    *,
    workspace_external_id: str,
    workspace_name: str,
    slack_user_id: str,
    channel_id: str,
    message_ts: str,
    thread_ts: str | None,
    message_text: str,
    files: list[SlackFileReference],
) -> JobCreationResult:
    classification = classify_slack_input(message_text, files)
    idempotency_key = _build_idempotency_key(
        workspace_external_id=workspace_external_id,
        channel_id=channel_id,
        message_ts=message_ts,
        message_text=message_text,
        files=files,
    )

    db = SessionLocal()
    try:
        existing = (
            db.query(IngestionJob)
            .filter(IngestionJob.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return JobCreationResult(
                job=existing,
                classification=classification,
                created=False,
            )

        now = _utcnow()
        workspace = _get_or_create_workspace(
            db, workspace_external_id, workspace_name, now
        )
        user = _get_or_create_user(db, slack_user_id, now)
        first_file = files[0] if files else None
        source_reference = (
            classification.recording_url
            or (first_file.id if first_file else None)
            or _truncate(message_text, 240)
        )

        job = IngestionJob(
            id=uuid4(),
            workspace_id=workspace.id,
            user_id=user.id if user else None,
            source_type=classification.source_type,
            provider_type=classification.provider_type,
            requested_mode=classification.requested_mode,
            source_url=classification.recording_url,
            source_reference=source_reference,
            slack_channel_id=channel_id,
            slack_thread_ts=thread_ts,
            slack_message_ts=message_ts,
            slack_status_ts=None,
            status=IngestionJobStatus.received,
            progress_state="received",
            current_step="received",
            retries=0,
            failure_reason=None,
            idempotency_key=idempotency_key,
            created_at=now,
            started_at=None,
            completed_at=None,
            updated_at=now,
        )
        db.add(job)
        db.flush()

        _upsert_source_artifact(
            db,
            job.id,
            artifact_type=MESSAGE_ARTIFACT_TYPE,
            external_id=None,
            filename="slack-message.txt",
            mime_type="text/plain",
            source_url=None,
            text_content=message_text.strip() or None,
            byte_size=len(message_text.encode("utf-8")) if message_text else None,
            metadata={"requested_mode": classification.requested_mode.value},
            created_at=now,
        )

        if classification.recording_url:
            _upsert_source_artifact(
                db,
                job.id,
                artifact_type=RECORDING_LINK_ARTIFACT_TYPE,
                external_id=None,
                filename="recording-link.url",
                mime_type="text/uri-list",
                source_url=classification.recording_url,
                text_content=classification.recording_url,
                byte_size=len(classification.recording_url.encode("utf-8")),
                metadata={"provider_type": classification.provider_type.value},
                created_at=now,
            )

        for file_ref in files:
            _upsert_source_artifact(
                db,
                job.id,
                artifact_type=SUPPORTED_FILE_ARTIFACT_TYPE,
                external_id=file_ref.id,
                filename=file_ref.name,
                mime_type=file_ref.mimetype,
                source_url=file_ref.url_private_download or file_ref.url_private,
                text_content=None,
                byte_size=file_ref.size,
                metadata=file_ref.model_dump(),
                created_at=now,
            )

        _write_audit(
            db,
            job.id,
            "job_created",
            "Created ingestion job from Slack DM payload.",
            {
                "source_type": classification.source_type.value,
                "provider_type": classification.provider_type.value,
                "requested_mode": classification.requested_mode.value,
            },
            now,
        )
        db.commit()
        db.refresh(job)
        return JobCreationResult(job=job, classification=classification, created=True)
    finally:
        db.close()


def record_status_message(job_id: str | UUID, message_ts: str) -> None:
    db = SessionLocal()
    try:
        job = _get_job(db, job_id)
        if not job:
            return
        job.slack_status_ts = message_ts
        job.updated_at = _utcnow()
        db.add(job)
        db.commit()
    finally:
        db.close()


def request_job_stop(channel_id: str) -> JobStopResult:
    db = SessionLocal()
    try:
        job = (
            db.query(IngestionJob)
            .filter(IngestionJob.slack_channel_id == channel_id)
            .order_by(IngestionJob.created_at.desc())
            .first()
        )
        if not job or job.status in TERMINAL_JOB_STATUSES:
            return JobStopResult(stopped=False)

        _request_stop(job.id)

        if job.status in STOPPABLE_PENDING_JOB_STATUSES:
            _transition_job(
                db,
                job,
                IngestionJobStatus.failed,
                step="stopped",
                progress="stopped",
                notify=False,
            )
            job.failure_reason = STOP_REQUESTED_REASON
            job.completed_at = _utcnow()
            db.add(job)
            _write_audit(
                db,
                job.id,
                "job_stopped",
                STOP_REQUESTED_REASON,
                {"status": job.status.value},
                _utcnow(),
            )
            db.commit()
            _notify_job_stopped(job)
            _clear_stop_request(job.id)
            return JobStopResult(
                stopped=True,
                job_id=str(job.id),
                active=False,
                status=job.status,
            )

        job.failure_reason = STOP_REQUESTED_REASON
        job.updated_at = _utcnow()
        db.add(job)
        _write_audit(
            db,
            job.id,
            "job_stop_requested",
            STOP_REQUESTED_REASON,
            {"status": job.status.value},
            job.updated_at,
        )
        db.commit()
        return JobStopResult(
            stopped=True,
            job_id=str(job.id),
            active=job.status in STOPPABLE_ACTIVE_JOB_STATUSES,
            status=job.status,
        )
    finally:
        db.close()


def prepare_job_for_enqueue(job_id: str | UUID) -> None:
    db = SessionLocal()
    try:
        job = _get_job(db, job_id)
        if not job or job.status in TERMINAL_JOB_STATUSES:
            return

        if job.status == IngestionJobStatus.received:
            _transition_job(
                db,
                job,
                IngestionJobStatus.classified,
                step="classified",
                progress="classified",
                notify=False,
            )
        if job.status == IngestionJobStatus.classified:
            _transition_job(
                db,
                job,
                IngestionJobStatus.validated,
                step="validated",
                progress="validated",
                notify=False,
            )
        if job.status == IngestionJobStatus.validated:
            _transition_job(
                db,
                job,
                IngestionJobStatus.queued,
                step="queued",
                progress="queued",
                notify=True,
                message="Queued your meeting source for processing.",
            )
        db.commit()
    finally:
        db.close()


def process_ingestion_job(job_id: str | UUID) -> None:
    db = SessionLocal()
    try:
        job = _get_job(db, job_id)
        if not job:
            return
        if job.status in TERMINAL_JOB_STATUSES:
            return

        _raise_if_stop_requested(db, job)

        if job.started_at is None:
            job.started_at = _utcnow()
            db.add(job)
            db.commit()

        resolved = _resolve_transcript_for_job(db, job)
        _raise_if_stop_requested(db, job)
        cleaned_document = _clean_and_store_transcript(db, job, resolved.document)
        _raise_if_stop_requested(db, job)
        response = _extract_and_render(db, job, cleaned_document)

        _transition_job(
            db,
            job,
            IngestionJobStatus.completed,
            step="completed",
            progress="completed",
            notify=False,
        )
        job.completed_at = _utcnow()
        db.add(job)
        db.commit()
        _clear_stop_request(job.id)

        _notify_job_completion(
            job,
            response=response,
            processed_files=resolved.processed_files,
            skipped_files=resolved.skipped_files,
        )
    except JobStoppedError as exc:
        _handle_stopped_job(job_id, str(exc))
    except UnsupportedSourceError as exc:
        _handle_terminal_job_failure(
            job_id, IngestionJobStatus.unsupported_source, str(exc)
        )
    except (httpx.TimeoutException, RetryableJobError) as exc:
        _handle_retryable_failure(job_id, exc)
    except (httpx.HTTPStatusError, MediaProcessingError, TranscriptionError) as exc:
        _handle_terminal_job_failure(job_id, IngestionJobStatus.failed, str(exc))
    except Exception as exc:
        logger.exception("Unhandled ingestion job failure for %s", job_id)
        _handle_terminal_job_failure(job_id, IngestionJobStatus.failed, str(exc))
    finally:
        db.close()


def _resolve_transcript_for_job(db, job: IngestionJob) -> ResolvedTranscript:
    _raise_if_stop_requested(db, job)

    if job.source_type == IngestionSourceType.transcript_text:
        _transition_job(
            db,
            job,
            IngestionJobStatus.cleaning_transcript,
            step="cleaning_transcript",
            progress="cleaning_transcript",
            notify=True,
            message="Cleaning transcript text and preserving the strongest evidence.",
        )
        message_artifact = _get_source_artifact(db, job.id, MESSAGE_ARTIFACT_TYPE)
        return ResolvedTranscript(
            document=TranscriptDocument(
                text=(message_artifact.text_content or "").strip(),
                source_kind="inline-text",
                provenance="slack-dm",
            ),
            processed_files=[],
            skipped_files=[],
        )

    if job.source_type == IngestionSourceType.transcript_file:
        return _resolve_transcript_from_files(db, job)

    if job.source_type == IngestionSourceType.media_file:
        return _resolve_transcript_from_media_file(db, job)

    if job.source_type == IngestionSourceType.recording_link:
        return _resolve_transcript_from_recording_link(db, job)

    raise UnsupportedSourceError("That source type is not supported yet.")


def _resolve_transcript_from_files(db, job: IngestionJob) -> ResolvedTranscript:
    _raise_if_stop_requested(db, job)
    _transition_job(
        db,
        job,
        IngestionJobStatus.fetching_source,
        step="fetching_source",
        progress="fetching_source",
        notify=True,
        message="Downloading the uploaded transcript file.",
    )
    artifacts = _get_file_artifacts(db, job.id)
    documents: list[str] = []
    processed_files: list[str] = []

    for artifact in artifacts:
        _raise_if_stop_requested(db, job)
        file_url = artifact.source_url
        filename = artifact.filename or "transcript.txt"
        metadata = artifact.metadata_json or {}
        if not file_url:
            preview = metadata.get("preview")
            if preview:
                documents.append(parse_transcript_text(filename, preview))
                processed_files.append(filename)
                continue
            continue

        if (
            artifact.byte_size
            and artifact.byte_size > settings.followthru_max_download_bytes
        ):
            raise UnsupportedSourceError(f"{filename} is too large to process safely.")

        if filename.lower().endswith(
            (".txt", ".md", ".markdown", ".csv", ".tsv", ".srt", ".vtt", ".log")
        ):
            raw_text = slack_client.download_text_file(file_url)
            documents.append(parse_transcript_text(filename, raw_text))
        else:
            raw_bytes = slack_client.download_file_bytes(file_url)
            documents.append(
                parse_transcript_bytes(
                    filename=filename,
                    content=raw_bytes,
                    mimetype=artifact.mime_type,
                ).text
            )
        processed_files.append(filename)

    _raise_if_stop_requested(db, job)
    if not documents:
        raise UnsupportedSourceError(
            "I could not read any supported transcript text from those files."
        )

    _transition_job(
        db,
        job,
        IngestionJobStatus.fetched,
        step="fetched",
        progress="fetched",
        notify=True,
        message="Transcript file downloaded and parsed.",
    )
    return ResolvedTranscript(
        document=TranscriptDocument(
            text="\n\n".join(part for part in documents if part.strip()),
            source_kind="transcript-file",
            provenance=", ".join(processed_files),
        ),
        processed_files=processed_files,
        skipped_files=[],
    )


def _resolve_transcript_from_media_file(db, job: IngestionJob) -> ResolvedTranscript:
    _raise_if_stop_requested(db, job)
    _transition_job(
        db,
        job,
        IngestionJobStatus.fetching_source,
        step="fetching_source",
        progress="fetching_source",
        notify=True,
        message="Downloading the uploaded meeting media.",
    )
    artifacts = _get_file_artifacts(db, job.id)
    artifact = next(
        (
            item
            for item in artifacts
            if is_supported_media_file(item.metadata_json or {})
        ),
        None,
    )
    if artifact is None or not artifact.source_url:
        raise UnsupportedSourceError(
            "I could not find a supported media file to transcribe."
        )

    if (
        artifact.byte_size
        and artifact.byte_size > settings.followthru_max_download_bytes
    ):
        raise UnsupportedSourceError(
            f"{artifact.filename or 'Media file'} is too large to process safely."
        )

    _raise_if_stop_requested(db, job)
    media_bytes = slack_client.download_file_bytes(artifact.source_url)
    transcript = _transcribe_media_bytes(
        db=db,
        job=job,
        media_bytes=media_bytes,
        filename=artifact.filename or "recording",
        mime_type=artifact.mime_type,
    )
    return ResolvedTranscript(
        document=transcript,
        processed_files=[artifact.filename or "recording"],
        skipped_files=[
            item.filename or "uploaded file"
            for item in artifacts
            if item.id != artifact.id
        ],
    )


def _resolve_transcript_from_recording_link(
    db, job: IngestionJob
) -> ResolvedTranscript:
    _raise_if_stop_requested(db, job)
    if not job.source_url:
        raise UnsupportedSourceError("Recording link is missing.")

    adapter = resolve_provider_adapter(job.source_url)
    if adapter is None:
        raise UnsupportedSourceError("That recording provider is not supported yet.")

    _transition_job(
        db,
        job,
        IngestionJobStatus.fetching_source,
        step="fetching_source",
        progress="fetching_source",
        notify=True,
        message="Validating the recording link and fetching available artifacts.",
    )
    reference = adapter.normalize_reference(job.source_url)
    auth_context = ProviderAuthContext(
        slack_user_id=_resolve_slack_user_id(db, job.user_id),
        workspace_id=str(job.workspace_id),
    )

    transcript_result = adapter.fetch_transcript(reference, auth_context)
    _upsert_provider_access_record(
        db=db,
        job_id=job.id,
        provider_type=reference.provider_type.value,
        normalized_url=reference.normalized_url,
        external_reference=reference.external_id,
        access_status=(
            "accessible" if transcript_result.metadata.accessible else "inaccessible"
        ),
        metadata=transcript_result.metadata.model_dump(mode="json"),
        created_at=_utcnow(),
    )
    if transcript_result.transcript and transcript_result.transcript.text.strip():
        _transition_job(
            db,
            job,
            IngestionJobStatus.fetched,
            step="fetched",
            progress="fetched",
            notify=True,
            message="Provider transcript fetched successfully.",
        )
        return ResolvedTranscript(
            document=transcript_result.transcript,
            processed_files=[],
            skipped_files=[],
        )

    media_result = adapter.fetch_media(reference, auth_context)
    if not media_result.media_download_url:
        raise UnsupportedSourceError(
            "I could not fetch a transcript or downloadable media "
            "from that recording link."
        )

    _raise_if_stop_requested(db, job)
    media_bytes = _download_remote_bytes(
        media_result.media_download_url,
        stop_requested=lambda: _is_stop_requested(db, job),
    )
    transcript = _transcribe_media_bytes(
        db=db,
        job=job,
        media_bytes=media_bytes,
        filename=media_result.media_filename or "recording.mp4",
        mime_type=media_result.media_mimetype,
    )
    return ResolvedTranscript(
        document=transcript,
        processed_files=[],
        skipped_files=[],
    )


def _transcribe_media_bytes(
    *,
    db,
    job: IngestionJob,
    media_bytes: bytes,
    filename: str,
    mime_type: str | None,
) -> TranscriptDocument:
    _raise_if_stop_requested(db, job)
    _transition_job(
        db,
        job,
        IngestionJobStatus.fetched,
        step="fetched",
        progress="fetched",
        notify=True,
        message="Meeting media fetched successfully.",
    )
    with tempfile.TemporaryDirectory(prefix="followthru-media-") as temp_dir:
        temp_root = Path(temp_dir)
        media_path = temp_root / filename
        media_path.write_bytes(media_bytes)

        _transition_job(
            db,
            job,
            IngestionJobStatus.normalizing_media,
            step="normalizing_media",
            progress="normalizing_media",
            notify=True,
            message="Normalizing media to a transcription-friendly audio format.",
        )
        audio_path = temp_root / "normalized-audio.wav"
        if (mime_type or "").startswith(
            "audio/"
        ) and media_path.suffix.lower() == ".wav":
            audio_path.write_bytes(media_bytes)
        else:
            normalize_media_to_audio(media_path, audio_path)

        _raise_if_stop_requested(db, job)
        _upsert_normalized_artifact(
            db,
            job.id,
            ArtifactKind.normalized_audio.value,
            str(audio_path),
            metadata={"filename": audio_path.name},
            created_at=_utcnow(),
        )

        _transition_job(
            db,
            job,
            IngestionJobStatus.transcribing,
            step="transcribing",
            progress="transcribing",
            notify=True,
            message="Transcribing the meeting audio.",
        )
        return transcribe_audio_file(
            audio_path,
            stop_requested=lambda: _is_stop_requested(db, job),
        )


def _clean_and_store_transcript(
    db,
    job: IngestionJob,
    document: TranscriptDocument,
) -> TranscriptDocument:
    _raise_if_stop_requested(db, job)
    if job.status != IngestionJobStatus.cleaning_transcript:
        _transition_job(
            db,
            job,
            IngestionJobStatus.cleaning_transcript,
            step="cleaning_transcript",
            progress="cleaning_transcript",
            notify=True,
            message="Cleaning transcript text and preserving the strongest evidence.",
        )
    cleaned = clean_transcript(document)
    now = _utcnow()
    _upsert_transcript_artifact(
        db,
        job.id,
        source_artifact_id=None,
        source_kind=cleaned.source_kind,
        provenance=cleaned.provenance,
        transcript_text=cleaned.text,
        metadata=cleaned.metadata,
        created_at=now,
    )
    _upsert_normalized_artifact(
        db,
        job.id,
        ArtifactKind.cleaned_transcript.value,
        storage_path=None,
        text_content=cleaned.text,
        metadata={"provenance": cleaned.provenance},
        created_at=now,
    )
    db.commit()
    return cleaned


def _extract_and_render(db, job: IngestionJob, document: TranscriptDocument):
    _raise_if_stop_requested(db, job)
    _transition_job(
        db,
        job,
        IngestionJobStatus.extracting_intelligence,
        step="extracting_intelligence",
        progress="extracting_intelligence",
        notify=True,
        message="Extracting summary, decisions, risks, and action items.",
    )
    slack_user_id = _resolve_slack_user_id(db, job.user_id) or "slack-user"
    requested_text = f"{job.requested_mode.value} {document.text}".strip()
    response = handle_followthru_chat(
        FollowThruChatRequest(
            message=requested_text,
            user_id=slack_user_id,
            channel_id=job.slack_channel_id,
            thread_ts=job.slack_thread_ts,
        )
    )

    _transition_job(
        db,
        job,
        IngestionJobStatus.rendering_canvas,
        step="rendering_canvas",
        progress="rendering_canvas",
        notify=True,
        message="Rendering the Slack canvas draft.",
    )

    now = _utcnow()
    if response.extraction:
        _upsert_extraction_result(
            db=db,
            job_id=job.id,
            draft_id=response.draft_id,
            confidence=response.extraction.confidence_overall.value,
            summary=response.extraction.summary,
            structured_payload=response.extraction.model_dump(mode="json"),
            created_at=now,
        )

    if response.draft_canvas_markdown:
        _upsert_canvas_version(
            db=db,
            job_id=job.id,
            draft_id=response.draft_id,
            title=response.draft_title or response.extraction.meeting_title,
            body_markdown=response.draft_canvas_markdown,
            slack_canvas_id=response.slack_canvas_id,
            created_at=now,
        )
    db.commit()
    return response


def _notify_job_completion(
    job: IngestionJob,
    response,
    processed_files: list[str],
    skipped_files: list[str],
) -> None:
    if not job.slack_channel_id or not job.slack_status_ts:
        return
    text = build_completion_message(
        response,
        processed_files=processed_files,
        skipped_files=skipped_files,
    )
    slack_client.update_message(job.slack_channel_id, job.slack_status_ts, text)


def _handle_terminal_job_failure(
    job_id: str | UUID,
    final_status: IngestionJobStatus,
    reason: str,
) -> None:
    db = SessionLocal()
    try:
        job = _get_job(db, job_id)
        if not job or job.status in TERMINAL_JOB_STATUSES:
            return

        _transition_job(
            db,
            job,
            final_status,
            step=final_status.value,
            progress=final_status.value,
            notify=False,
        )
        job.failure_reason = reason
        job.completed_at = _utcnow()
        db.add(job)
        _write_audit(
            db,
            job.id,
            "job_failed",
            reason,
            {"status": final_status.value},
            _utcnow(),
        )
        db.commit()

        if job.slack_channel_id and job.slack_status_ts:
            slack_client.update_message(
                job.slack_channel_id,
                job.slack_status_ts,
                build_failure_message(reason),
            )
    finally:
        _clear_stop_request(job_id)
        db.close()


def _handle_stopped_job(job_id: str | UUID, reason: str) -> None:
    db = SessionLocal()
    try:
        job = _get_job(db, job_id)
        if not job or job.status in TERMINAL_JOB_STATUSES:
            return

        _transition_job(
            db,
            job,
            IngestionJobStatus.failed,
            step="stopped",
            progress="stopped",
            notify=False,
        )
        job.failure_reason = reason
        job.completed_at = _utcnow()
        db.add(job)
        _write_audit(
            db,
            job.id,
            "job_stopped",
            reason,
            {"status": job.status.value},
            _utcnow(),
        )
        db.commit()
        _notify_job_stopped(job)
    finally:
        _clear_stop_request(job_id)
        db.close()


def _handle_retryable_failure(job_id: str | UUID, exc: Exception) -> None:
    db = SessionLocal()
    try:
        job = _get_job(db, job_id)
        if not job:
            return
        if job.retries >= settings.followthru_max_job_retries:
            _handle_terminal_job_failure(job_id, IngestionJobStatus.failed, str(exc))
            return

        attempt = job.retries + 1
        now = _utcnow()
        next_retry_at = now + timedelta(seconds=min(2**attempt, 30))
        _transition_job(
            db,
            job,
            IngestionJobStatus.retrying,
            step="retrying",
            progress="retrying",
            notify=True,
            message=f"Temporary issue detected. Retrying attempt {attempt} shortly.",
        )
        job.retries = attempt
        job.failure_reason = str(exc)
        db.add(job)
        db.add(
            RetryRecord(
                job_id=job.id,
                attempt_number=attempt,
                error_type=type(exc).__name__,
                failure_reason=str(exc),
                next_retry_at=next_retry_at,
                created_at=now,
            )
        )
        db.commit()
    finally:
        db.close()

    if settings.followthru_job_execution_mode == "inline":
        _requeue_retry_job(job_id)
        return

    delay_seconds = min(2 ** _safe_attempt_number(job_id), 30)
    Timer(delay_seconds, lambda: _requeue_retry_job(job_id)).start()


def _requeue_retry_job(job_id: str | UUID) -> None:
    db = SessionLocal()
    try:
        job = _get_job(db, job_id)
        if not job or job.status != IngestionJobStatus.retrying:
            return
        _transition_job(
            db,
            job,
            IngestionJobStatus.queued,
            step="queued",
            progress="queued",
            notify=False,
        )
        db.commit()
    finally:
        db.close()

    from app.workers.job_queue import job_queue

    job_queue.enqueue(job_id)


def _safe_attempt_number(job_id: str | UUID) -> int:
    db = SessionLocal()
    try:
        job = _get_job(db, job_id)
        return job.retries if job else 1
    finally:
        db.close()


def _transition_job(
    db,
    job: IngestionJob,
    new_status: IngestionJobStatus,
    *,
    step: str,
    progress: str,
    notify: bool,
    message: str | None = None,
) -> None:
    validate_job_transition(job.status, new_status)
    job.status = new_status
    job.current_step = step
    job.progress_state = progress
    job.updated_at = _utcnow()
    db.add(job)
    _write_audit(
        db,
        job.id,
        "status_transition",
        message or f"Transitioned to {new_status.value}.",
        {"status": new_status.value, "step": step, "progress": progress},
        job.updated_at,
    )
    db.flush()
    if notify and job.slack_channel_id and job.slack_status_ts and message:
        slack_client.update_message(
            job.slack_channel_id,
            job.slack_status_ts,
            f"*Processing your meeting notes...*\n_{message}_",
        )


def _is_stop_requested(db, job: IngestionJob) -> bool:
    db.refresh(job)
    if job.failure_reason == STOP_REQUESTED_REASON:
        return True

    from app.workers.job_queue import job_queue

    return job_queue.is_stop_requested(job.id)


def _raise_if_stop_requested(db, job: IngestionJob) -> None:
    if _is_stop_requested(db, job):
        raise JobStoppedError(STOP_REQUESTED_REASON)


def _request_stop(job_id: str | UUID) -> None:
    from app.workers.job_queue import job_queue

    job_queue.request_stop(job_id)


def _clear_stop_request(job_id: str | UUID) -> None:
    from app.workers.job_queue import job_queue

    job_queue.clear_stop(job_id)


def _notify_job_stopped(job: IngestionJob) -> None:
    if not job.slack_channel_id or not job.slack_status_ts:
        return
    slack_client.update_message(
        job.slack_channel_id,
        job.slack_status_ts,
        build_stopped_message(),
    )


def _get_or_create_workspace(
    db,
    slack_team_id: str,
    workspace_name: str,
    now: datetime,
) -> Workspace:
    workspace = (
        db.query(Workspace).filter(Workspace.slack_team_id == slack_team_id).first()
    )
    if workspace:
        return workspace
    workspace = Workspace(
        id=uuid4(),
        slack_team_id=slack_team_id,
        name=workspace_name,
        created_at=now,
    )
    db.add(workspace)
    db.flush()
    return workspace


def _get_or_create_user(db, slack_user_id: str, now: datetime) -> User | None:
    if not slack_user_id:
        return None
    user = db.query(User).filter(User.slack_user_id == slack_user_id).first()
    if user:
        return user
    user = User(
        id=uuid4(),
        slack_user_id=slack_user_id,
        name="",
        email="",
        created_at=now,
    )
    db.add(user)
    db.flush()
    return user


def _build_idempotency_key(
    *,
    workspace_external_id: str,
    channel_id: str,
    message_ts: str,
    message_text: str,
    files: list[SlackFileReference],
) -> str:
    fingerprint = "|".join(
        [
            workspace_external_id,
            channel_id,
            message_ts,
            message_text.strip(),
            ",".join(file_ref.id or file_ref.name for file_ref in files),
        ]
    )
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def _write_audit(
    db,
    job_id,
    event_type: str,
    message: str,
    payload: dict,
    created_at: datetime,
) -> None:
    db.add(
        AuditLog(
            id=uuid4(),
            job_id=job_id,
            event_type=event_type,
            message=message,
            payload_json=payload,
            created_at=created_at,
        )
    )


def _upsert_source_artifact(
    db,
    job_id,
    *,
    artifact_type: str,
    external_id: str | None,
    filename: str | None,
    mime_type: str | None,
    source_url: str | None,
    text_content: str | None,
    byte_size: int | None,
    metadata: dict,
    created_at: datetime,
) -> SourceArtifact:
    artifact = (
        db.query(SourceArtifact)
        .filter(
            SourceArtifact.job_id == job_id,
            SourceArtifact.artifact_type == artifact_type,
            SourceArtifact.external_id == external_id,
            SourceArtifact.filename == filename,
        )
        .first()
    )
    if artifact:
        return artifact
    artifact = SourceArtifact(
        id=uuid4(),
        job_id=job_id,
        artifact_type=artifact_type,
        external_id=external_id,
        filename=filename,
        mime_type=mime_type,
        source_url=source_url,
        storage_path=None,
        text_content=text_content,
        byte_size=byte_size,
        metadata_json=metadata,
        created_at=created_at,
    )
    db.add(artifact)
    return artifact


def _upsert_normalized_artifact(
    db,
    job_id,
    artifact_type: str,
    storage_path: str | None,
    *,
    text_content: str | None = None,
    metadata: dict,
    created_at: datetime,
) -> NormalizedArtifact:
    artifact = (
        db.query(NormalizedArtifact)
        .filter(
            NormalizedArtifact.job_id == job_id,
            NormalizedArtifact.artifact_type == artifact_type,
        )
        .first()
    )
    if artifact:
        artifact.storage_path = storage_path
        artifact.text_content = text_content
        artifact.metadata_json = metadata
        return artifact
    artifact = NormalizedArtifact(
        id=uuid4(),
        job_id=job_id,
        artifact_type=artifact_type,
        storage_path=storage_path,
        text_content=text_content,
        metadata_json=metadata,
        created_at=created_at,
    )
    db.add(artifact)
    return artifact


def _upsert_transcript_artifact(
    db,
    job_id,
    *,
    source_artifact_id,
    source_kind: str,
    provenance: str,
    transcript_text: str,
    metadata: dict,
    created_at: datetime,
) -> TranscriptArtifact:
    artifact = (
        db.query(TranscriptArtifact)
        .filter(
            TranscriptArtifact.job_id == job_id,
            TranscriptArtifact.provenance == provenance,
        )
        .first()
    )
    if artifact:
        artifact.transcript_text = transcript_text
        artifact.metadata_json = metadata
        return artifact
    artifact = TranscriptArtifact(
        id=uuid4(),
        job_id=job_id,
        source_artifact_id=source_artifact_id,
        source_kind=source_kind,
        provenance=provenance,
        transcript_text=transcript_text,
        metadata_json=metadata,
        created_at=created_at,
    )
    db.add(artifact)
    return artifact


def _upsert_extraction_result(
    db,
    *,
    job_id,
    draft_id: str | None,
    confidence: str,
    summary: str,
    structured_payload: dict,
    created_at: datetime,
) -> ExtractionResultRecord:
    artifact = (
        db.query(ExtractionResultRecord)
        .filter(ExtractionResultRecord.job_id == job_id)
        .first()
    )
    if artifact:
        artifact.draft_id = _as_uuid(draft_id)
        artifact.confidence = confidence
        artifact.summary = summary
        artifact.structured_payload = structured_payload
        return artifact
    artifact = ExtractionResultRecord(
        id=uuid4(),
        job_id=job_id,
        draft_id=_as_uuid(draft_id),
        confidence=confidence,
        summary=summary,
        structured_payload=structured_payload,
        created_at=created_at,
    )
    db.add(artifact)
    return artifact


def _upsert_canvas_version(
    db,
    *,
    job_id,
    draft_id: str | None,
    title: str,
    body_markdown: str,
    slack_canvas_id: str | None,
    created_at: datetime,
) -> CanvasVersion:
    artifact = db.query(CanvasVersion).filter(CanvasVersion.job_id == job_id).first()
    if artifact:
        artifact.title = title
        artifact.body_markdown = body_markdown
        artifact.slack_canvas_id = slack_canvas_id
        return artifact
    artifact = CanvasVersion(
        id=uuid4(),
        job_id=job_id,
        draft_id=_as_uuid(draft_id),
        version_number=1,
        title=title,
        body_markdown=body_markdown,
        slack_canvas_id=slack_canvas_id,
        created_at=created_at,
    )
    db.add(artifact)
    return artifact


def _upsert_provider_access_record(
    db,
    *,
    job_id,
    provider_type: str,
    normalized_url: str,
    external_reference: str | None,
    access_status: str,
    metadata: dict,
    created_at: datetime,
) -> ProviderAccessRecord:
    record = (
        db.query(ProviderAccessRecord)
        .filter(
            ProviderAccessRecord.job_id == job_id,
            ProviderAccessRecord.normalized_url == normalized_url,
        )
        .first()
    )
    if record:
        record.external_reference = external_reference
        record.access_status = access_status
        record.metadata_json = metadata
        record.updated_at = created_at
        return record
    record = ProviderAccessRecord(
        id=uuid4(),
        job_id=job_id,
        provider_type=provider_type,
        normalized_url=normalized_url,
        external_reference=external_reference,
        access_status=access_status,
        metadata_json=metadata,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(record)
    return record


def _get_job(db, job_id: str | UUID) -> IngestionJob | None:
    try:
        parsed_id = job_id if isinstance(job_id, UUID) else UUID(str(job_id))
    except ValueError:
        return None
    return db.query(IngestionJob).filter(IngestionJob.id == parsed_id).first()


def _get_source_artifact(db, job_id, artifact_type: str) -> SourceArtifact:
    return (
        db.query(SourceArtifact)
        .filter(
            SourceArtifact.job_id == job_id,
            SourceArtifact.artifact_type == artifact_type,
        )
        .first()
    )


def _get_file_artifacts(db, job_id) -> list[SourceArtifact]:
    return (
        db.query(SourceArtifact)
        .filter(
            SourceArtifact.job_id == job_id,
            SourceArtifact.artifact_type == SUPPORTED_FILE_ARTIFACT_TYPE,
        )
        .all()
    )


def _resolve_slack_user_id(db, user_id) -> str | None:
    if user_id is None:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    return user.slack_user_id if user else None


def _download_remote_bytes(
    url: str,
    *,
    stop_requested=None,
) -> bytes:
    with httpx.Client(
        follow_redirects=True,
        timeout=settings.followthru_download_timeout_seconds,
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            _validate_download_size(response.headers.get("Content-Length"))
            payload = bytearray()
            for chunk in response.iter_bytes():
                if stop_requested and stop_requested():
                    raise JobStoppedError(STOP_REQUESTED_REASON)
                payload.extend(chunk)
                if len(payload) > settings.followthru_max_download_bytes:
                    raise UnsupportedSourceError(
                        "Downloaded media exceeds the size limit."
                    )
    return bytes(payload)


def _validate_download_size(content_length: str | None) -> None:
    if content_length is None:
        return
    try:
        if int(content_length) > settings.followthru_max_download_bytes:
            raise UnsupportedSourceError("Downloaded media exceeds the size limit.")
    except ValueError:
        return


def _as_uuid(value: str | None):
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _truncate(value: str, limit: int) -> str:
    collapsed = " ".join(value.split())
    return collapsed[:limit]


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
