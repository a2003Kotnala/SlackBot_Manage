from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import settings
from app.domain.services.transcription_service import (
    TranscriptionError,
    transcribe_audio_file,
)


class _FakeSegment:
    def __init__(self, text: str, start: float, end: float) -> None:
        self.text = text
        self.start = start
        self.end = end


class _FakeWhisperModel:
    def transcribe(self, _audio_path: str, **_kwargs):
        segments = [
            _FakeSegment("Namaste team", 0.0, 1.1),
            _FakeSegment("let us ship this today", 1.1, 3.2),
        ]
        info = SimpleNamespace(language="hi", language_probability=0.82)
        return segments, info


def test_local_whisper_transcription_collects_segments(monkeypatch):
    audio_path = Path("meeting.wav")
    monkeypatch.setattr(settings, "transcription_provider", "local-whisper")
    monkeypatch.setattr(settings, "transcription_language_hint", None)
    monkeypatch.setattr(settings, "transcription_initial_prompt", None)
    monkeypatch.setattr(
        "app.domain.services.transcription_service._get_local_whisper_model",
        lambda: _FakeWhisperModel(),
    )

    document = transcribe_audio_file(audio_path)

    assert "Namaste team" in document.text
    assert "let us ship this today" in document.text
    assert document.metadata["provider"] == "local-whisper"
    assert document.segments[0].started_at == 0.0


def test_local_whisper_transcription_respects_stop_request(monkeypatch):
    audio_path = Path("meeting.wav")
    monkeypatch.setattr(settings, "transcription_provider", "local-whisper")
    monkeypatch.setattr(settings, "transcription_language_hint", None)
    monkeypatch.setattr(settings, "transcription_initial_prompt", None)
    monkeypatch.setattr(
        "app.domain.services.transcription_service._get_local_whisper_model",
        lambda: _FakeWhisperModel(),
    )

    with pytest.raises(TranscriptionError, match="Stopped by user."):
        transcribe_audio_file(audio_path, stop_requested=lambda: True)
