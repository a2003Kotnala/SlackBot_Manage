from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import CanvasVersion, ExtractionResultRecord, IngestionJob
from app.domain.schemas.extraction import ActionItem, Confidence, ExtractionResult
from app.domain.schemas.followthru import FollowThruMode, FollowThruResponse
from app.domain.schemas.ingestion import IngestionJobStatus
from app.domain.services.ingestion_job_service import (
    create_or_get_slack_ingestion_job,
    prepare_job_for_enqueue,
    process_ingestion_job,
    request_job_stop,
)


def _build_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_create_or_get_slack_ingestion_job_is_idempotent(monkeypatch):
    session_factory = _build_session_factory()
    monkeypatch.setattr(
        "app.domain.services.ingestion_job_service.SessionLocal",
        session_factory,
    )

    created = create_or_get_slack_ingestion_job(
        workspace_external_id="T123",
        workspace_name="Test Workspace",
        slack_user_id="U123",
        channel_id="D123",
        message_ts="1710000000.000200",
        thread_ts="1710000000.000200",
        message_text="Decision: Ship the pilot.",
        files=[],
    )
    duplicate = create_or_get_slack_ingestion_job(
        workspace_external_id="T123",
        workspace_name="Test Workspace",
        slack_user_id="U123",
        channel_id="D123",
        message_ts="1710000000.000200",
        thread_ts="1710000000.000200",
        message_text="Decision: Ship the pilot.",
        files=[],
    )

    assert created.created is True
    assert duplicate.created is False
    assert duplicate.job.id == created.job.id


def test_prepare_and_process_transcript_text_job(monkeypatch):
    session_factory = _build_session_factory()
    monkeypatch.setattr(
        "app.domain.services.ingestion_job_service.SessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        "app.domain.services.ingestion_job_service.handle_followthru_chat",
        lambda payload: FollowThruResponse(
            bot_name="FollowThru",
            session_id="session-123",
            mode=FollowThruMode.publish,
            reply=f"Handled {len(payload.message)} chars",
            draft_id="draft-123",
            draft_title="Pilot Review",
            slack_canvas_id="F123",
            draft_canvas_markdown=(
                "# Pilot Review\n\n## Action Items\n\n| # | Task | Owner | Due |"
            ),
            extraction=ExtractionResult(
                meeting_title="Pilot Review",
                summary="Pilot approved for rollout.",
                status_summary="Execution in progress",
                priority_focus="Prepare the demo",
                action_items=[
                    ActionItem(
                        content="Prepare the demo",
                        owner="maya",
                        confidence=Confidence.high,
                    )
                ],
                confidence_overall=Confidence.high,
            ),
            normalized_input=payload.message,
        ),
    )

    creation = create_or_get_slack_ingestion_job(
        workspace_external_id="T123",
        workspace_name="Test Workspace",
        slack_user_id="U123",
        channel_id="D123",
        message_ts="1710000000.000210",
        thread_ts="1710000000.000210",
        message_text="Decision: Ship the pilot.\nAction: Prepare the demo @maya",
        files=[],
    )

    prepare_job_for_enqueue(creation.job.id)
    process_ingestion_job(creation.job.id)

    db = session_factory()
    try:
        job = db.query(IngestionJob).filter(IngestionJob.id == creation.job.id).first()
        assert job.status == IngestionJobStatus.completed
        assert db.query(ExtractionResultRecord).count() == 1
        assert db.query(CanvasVersion).count() == 1
    finally:
        db.close()


def test_request_job_stop_marks_queued_job_failed(monkeypatch):
    session_factory = _build_session_factory()
    monkeypatch.setattr(
        "app.domain.services.ingestion_job_service.SessionLocal",
        session_factory,
    )
    requested_stops: list[str] = []
    monkeypatch.setattr(
        "app.domain.services.ingestion_job_service._request_stop",
        lambda job_id: requested_stops.append(str(job_id)),
    )
    monkeypatch.setattr(
        "app.domain.services.ingestion_job_service._clear_stop_request",
        lambda _job_id: None,
    )
    monkeypatch.setattr(
        "app.domain.services.ingestion_job_service._notify_job_stopped",
        lambda _job: None,
    )

    creation = create_or_get_slack_ingestion_job(
        workspace_external_id="T123",
        workspace_name="Test Workspace",
        slack_user_id="U123",
        channel_id="D123",
        message_ts="1710000000.000220",
        thread_ts="1710000000.000220",
        message_text="Decision: Queue this.",
        files=[],
    )
    prepare_job_for_enqueue(creation.job.id)

    result = request_job_stop("D123")

    db = session_factory()
    try:
        job = db.query(IngestionJob).filter(IngestionJob.id == creation.job.id).first()
        assert result.stopped is True
        assert result.active is False
        assert job.status == IngestionJobStatus.failed
        assert job.failure_reason == "Stopped by user."
        assert requested_stops == [str(creation.job.id)]
    finally:
        db.close()


def test_request_job_stop_marks_running_job_for_cooperative_stop(monkeypatch):
    session_factory = _build_session_factory()
    monkeypatch.setattr(
        "app.domain.services.ingestion_job_service.SessionLocal",
        session_factory,
    )
    requested_stops: list[str] = []
    monkeypatch.setattr(
        "app.domain.services.ingestion_job_service._request_stop",
        lambda job_id: requested_stops.append(str(job_id)),
    )

    creation = create_or_get_slack_ingestion_job(
        workspace_external_id="T123",
        workspace_name="Test Workspace",
        slack_user_id="U123",
        channel_id="D123",
        message_ts="1710000000.000230",
        thread_ts="1710000000.000230",
        message_text="Decision: Keep listening.",
        files=[],
    )

    db = session_factory()
    try:
        job = db.query(IngestionJob).filter(IngestionJob.id == creation.job.id).first()
        job.status = IngestionJobStatus.transcribing
        job.current_step = "transcribing"
        job.progress_state = "transcribing"
        db.add(job)
        db.commit()
    finally:
        db.close()

    result = request_job_stop("D123")

    db = session_factory()
    try:
        job = db.query(IngestionJob).filter(IngestionJob.id == creation.job.id).first()
        assert result.stopped is True
        assert result.active is True
        assert job.status == IngestionJobStatus.transcribing
        assert job.failure_reason == "Stopped by user."
        assert requested_stops == [str(creation.job.id)]
    finally:
        db.close()
