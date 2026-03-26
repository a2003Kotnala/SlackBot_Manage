from pathlib import Path

import pytest

from app.domain.services.media_processing_service import (
    MediaProcessingError,
    MediaProcessingStoppedError,
    normalize_media_to_audio,
)


class _FakeProcess:
    def __init__(self, poll_values, *, returncode=0):
        self._poll_values = list(poll_values)
        self.returncode = returncode
        self.killed = False
        self.communicated = False

    def poll(self):
        if self.killed:
            return -9
        if self._poll_values:
            value = self._poll_values.pop(0)
            if value is not None:
                self.returncode = value
            return value
        return self.returncode

    def communicate(self):
        self.communicated = True
        return ("", "fake stderr")

    def kill(self):
        self.killed = True


def test_normalize_media_to_audio_stops_immediately_when_requested(monkeypatch):
    input_path = Path("meeting.mp4")
    output_path = Path("meeting.wav")
    fake_process = _FakeProcess([None, None, 0])
    monkeypatch.setattr(
        "app.domain.services.media_processing_service.probe_media_duration_seconds",
        lambda _path: 5.0,
    )
    monkeypatch.setattr(
        "app.domain.services.media_processing_service.subprocess.Popen",
        lambda *args, **kwargs: fake_process,
    )
    monkeypatch.setattr(
        "app.domain.services.media_processing_service.time.sleep",
        lambda _seconds: None,
    )

    with pytest.raises(MediaProcessingStoppedError, match="Stopped by user."):
        normalize_media_to_audio(
            input_path,
            output_path,
            stop_requested=lambda: True,
        )

    assert fake_process.killed is True


def test_normalize_media_to_audio_times_out_for_stuck_ffmpeg(monkeypatch):
    input_path = Path("meeting.mp4")
    output_path = Path("meeting.wav")
    fake_process = _FakeProcess([None, None, None])
    monotonic_values = iter([0.0, 0.0, 200.0])
    monkeypatch.setattr(
        "app.domain.services.media_processing_service.probe_media_duration_seconds",
        lambda _path: None,
    )
    monkeypatch.setattr(
        "app.domain.services.media_processing_service.subprocess.Popen",
        lambda *args, **kwargs: fake_process,
    )
    monkeypatch.setattr(
        "app.domain.services.media_processing_service.time.sleep",
        lambda _seconds: None,
    )
    monkeypatch.setattr(
        "app.domain.services.media_processing_service.time.monotonic",
        lambda: next(monotonic_values),
    )

    with pytest.raises(MediaProcessingError, match="Media normalization timed out"):
        normalize_media_to_audio(input_path, output_path)

    assert fake_process.killed is True
