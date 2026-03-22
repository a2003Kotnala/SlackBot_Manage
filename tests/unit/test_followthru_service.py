from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import ChatMessage, ChatSession  # noqa: F401
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
