from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import httpx

from app.config import settings
from app.domain.schemas.ingestion import TranscriptDocument, TranscriptSegment


class TranscriptionError(RuntimeError):
    pass


def transcribe_audio_file(
    audio_path: Path,
    *,
    stop_requested: Callable[[], bool] | None = None,
) -> TranscriptDocument:
    provider = settings.resolved_transcription_provider
    if provider in {"local-whisper", "faster-whisper", "whisper"}:
        return _transcribe_with_local_whisper(
            audio_path,
            stop_requested=stop_requested,
        )
    return _transcribe_with_openai_compatible(audio_path)


def _transcribe_with_openai_compatible(audio_path: Path) -> TranscriptDocument:
    api_key = settings.resolved_transcription_api_key
    if not api_key:
        raise TranscriptionError("No transcription API key is configured.")

    with audio_path.open("rb") as handle:
        files = {"file": (audio_path.name, handle, "audio/wav")}
        data = {
            "model": settings.resolved_transcription_model,
            "response_format": "verbose_json",
        }
        with httpx.Client(timeout=settings.followthru_download_timeout_seconds) as client:
            response = client.post(
                f"{settings.resolved_transcription_base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files=files,
            )

    if response.status_code >= 400:
        raise TranscriptionError(response.text)

    payload = response.json()
    segments = [
        TranscriptSegment(
            text=segment.get("text", "").strip(),
            speaker=segment.get("speaker"),
            started_at=_safe_float(segment.get("start")),
            ended_at=_safe_float(segment.get("end")),
        )
        for segment in payload.get("segments", [])
        if segment.get("text")
    ]

    transcript_text = payload.get("text")
    if not transcript_text and segments:
        transcript_text = "\n".join(segment.text for segment in segments)
    if not transcript_text:
        transcript_text = json.dumps(payload)

    return TranscriptDocument(
        text=transcript_text.strip(),
        source_kind="transcription",
        provenance=audio_path.name,
        segments=segments,
        metadata={"model": settings.resolved_transcription_model},
    )


def _transcribe_with_local_whisper(
    audio_path: Path,
    *,
    stop_requested: Callable[[], bool] | None = None,
) -> TranscriptDocument:
    model = _get_local_whisper_model()
    transcribe_kwargs = {
        "task": "transcribe",
        "beam_size": settings.transcription_beam_size,
        "vad_filter": settings.transcription_vad_filter,
        "condition_on_previous_text": (
            settings.transcription_condition_on_previous_text
        ),
    }
    if settings.transcription_initial_prompt:
        transcribe_kwargs["initial_prompt"] = settings.transcription_initial_prompt
    if settings.transcription_language_hint:
        transcribe_kwargs["language"] = settings.transcription_language_hint

    segments_iterable, info = model.transcribe(str(audio_path), **transcribe_kwargs)
    segments: list[TranscriptSegment] = []
    text_parts: list[str] = []
    for segment in segments_iterable:
        if stop_requested and stop_requested():
            raise TranscriptionError("Stopped by user.")

        text = (segment.text or "").strip()
        if not text:
            continue
        text_parts.append(text)
        segments.append(
            TranscriptSegment(
                text=text,
                started_at=_safe_float(getattr(segment, "start", None)),
                ended_at=_safe_float(getattr(segment, "end", None)),
            )
        )

    transcript_text = "\n".join(text_parts).strip()
    if not transcript_text:
        raise TranscriptionError(
            "The local Whisper model returned an empty transcript."
        )

    return TranscriptDocument(
        text=transcript_text,
        source_kind="transcription",
        provenance=audio_path.name,
        segments=segments,
        metadata={
            "model": settings.resolved_local_transcription_model,
            "provider": settings.resolved_transcription_provider,
            "language": getattr(info, "language", None),
            "language_probability": _safe_float(
                getattr(info, "language_probability", None)
            ),
        },
    )


@lru_cache(maxsize=1)
def _get_local_whisper_model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "Local Whisper transcription requires `faster-whisper`. "
            "Install it with `pip install faster-whisper`."
        ) from exc

    model_kwargs = {"device": settings.transcription_device}
    if settings.transcription_compute_type:
        model_kwargs["compute_type"] = settings.transcription_compute_type

    try:
        return WhisperModel(
            settings.resolved_local_transcription_model,
            **model_kwargs,
        )
    except Exception as exc:
        raise TranscriptionError(
            "Failed to initialize the local Whisper transcription model. "
            f"Model={settings.resolved_local_transcription_model!r} "
            f"device={settings.transcription_device!r} "
            f"compute_type={settings.transcription_compute_type!r}"
        ) from exc


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
