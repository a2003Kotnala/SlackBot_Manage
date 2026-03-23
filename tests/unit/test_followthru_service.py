from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import ChatMessage, ChatSession, Draft, ExtractedItem, Source, User
from app.db.models.draft import DraftStatus
from app.db.models.extracted_item import Confidence as ModelConfidence
from app.db.models.extracted_item import ItemType
from app.db.models.source import SourceType
from app.domain.schemas.extraction import (
    ActionItem,
    Confidence,
    ExtractionResult,
    InsightItem,
)
from app.domain.schemas.followthru import (
    FollowThruChatRequest,
    FollowThruMode,
    FollowThruVoiceCommandRequest,
)
from app.domain.services.followthru_service import (
    clear_followthru_dm_session,
    handle_followthru_chat,
    handle_followthru_voice_command,
)


def _build_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_followthru_chat_help_persists_session(monkeypatch):
    session_factory = _build_session_factory()
    monkeypatch.setattr(
        "app.domain.services.followthru_service.SessionLocal", session_factory
    )

    response = handle_followthru_chat(
        FollowThruChatRequest(message="help", user_id="demo-user")
    )

    assert response.mode == FollowThruMode.help
    assert "FollowThru can chat" in response.reply

    db = session_factory()
    try:
        assert db.query(ChatSession).count() == 1
        assert db.query(ChatMessage).count() == 2
    finally:
        db.close()


def test_followthru_chat_preview_returns_canvas(monkeypatch):
    session_factory = _build_session_factory()
    monkeypatch.setattr(
        "app.domain.services.followthru_service.SessionLocal", session_factory
    )

    extraction = ExtractionResult(
        meeting_title="Pilot Review",
        summary="Pilot was approved.",
        status_summary="Execution in progress",
        priority_focus="Prepare demo",
        decisions=[InsightItem(content="Ship the pilot.", confidence=Confidence.high)],
        action_items=[
            ActionItem(
                content="Prepare demo",
                owner="maya",
                confidence=Confidence.high,
            )
        ],
        confidence_overall=Confidence.high,
    )
    monkeypatch.setattr(
        "app.domain.services.followthru_service.extract_structured_meeting_data",
        lambda _: extraction,
    )

    response = handle_followthru_chat(
        FollowThruChatRequest(
            message=(
                "preview Decision: Ship the pilot. "
                "Action: Prepare demo @maya 2026-03-25"
            ),
            user_id="demo-user",
        )
    )

    assert response.mode == FollowThruMode.preview
    assert response.draft_canvas_markdown is not None
    assert "## Action Items" in response.draft_canvas_markdown
    assert response.extraction.meeting_title == "Pilot Review"


def test_followthru_voice_preview_persists_voice_source(monkeypatch):
    session_factory = _build_session_factory()
    monkeypatch.setattr(
        "app.domain.services.followthru_service.SessionLocal", session_factory
    )

    source = SimpleNamespace(
        id=uuid4(),
        source_type=SourceType.voice,
        raw_content_reference="Decision: Ship the pilot.",
    )
    extraction = ExtractionResult(
        meeting_title="Voice Notes",
        summary="Prepared the voice-driven preview.",
        status_summary="Execution in progress",
        priority_focus="Prepare demo",
        action_items=[
            ActionItem(
                content="Prepare demo",
                owner="maya",
                confidence=Confidence.high,
            )
        ],
        confidence_overall=Confidence.high,
    )

    monkeypatch.setattr(
        "app.domain.services.followthru_service.create_source_record",
        lambda **_: source,
    )
    monkeypatch.setattr(
        "app.domain.services.followthru_service.extract_structured_meeting_data",
        lambda _: extraction,
    )

    response = handle_followthru_voice_command(
        FollowThruVoiceCommandRequest(
            transcript=(
                "preview these notes: Decision: Ship the pilot. "
                "Action: Prepare demo @maya 2026-03-25"
            ),
            user_id="voice-user",
        )
    )

    assert response.mode == FollowThruMode.preview
    assert response.source_id == str(source.id)
    assert response.normalized_input.startswith("preview these notes")


def test_clear_followthru_dm_session_removes_persisted_history(monkeypatch):
    session_factory = _build_session_factory()
    monkeypatch.setattr(
        "app.domain.services.followthru_service.SessionLocal", session_factory
    )

    response = handle_followthru_chat(
        FollowThruChatRequest(
            message="help",
            user_id="demo-user",
            channel_id="D123",
        )
    )

    assert response.session_id is not None

    db = session_factory()
    try:
        user = db.query(User).first()
        source = Source(
            source_type=SourceType.text,
            slack_channel_id="D123",
            slack_thread_ts=None,
            slack_canvas_id=None,
            raw_content_reference="Decision: Ship the pilot.",
            created_by=user.id,
            created_at=datetime.utcnow(),
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        draft = Draft(
            owner_user_id=user.id,
            source_id=source.id,
            slack_canvas_id="F123",
            title="Pilot Review | 23 Mar 02:49 PM",
            status=DraftStatus.draft,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)

        db.add(
            ExtractedItem(
                draft_id=draft.id,
                item_type=ItemType.summary,
                content="Pilot approved.",
                confidence=ModelConfidence.high,
                assignee=None,
                due_date=None,
                created_at=datetime.utcnow(),
            )
        )
        db.commit()
    finally:
        db.close()

    clear_result = clear_followthru_dm_session("D123")

    assert clear_result.cleared_sessions == 1
    assert clear_result.cleared_messages == 2

    db = session_factory()
    try:
        assert db.query(ChatSession).count() == 0
        assert db.query(ChatMessage).count() == 0
        assert db.query(Source).count() == 1
        assert db.query(Draft).count() == 1
        assert db.query(ExtractedItem).count() == 1
    finally:
        db.close()
