from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.config import settings
from app.domain.schemas.ingestion import TranscriptDocument, TranscriptSegment


class TranscriptionError(RuntimeError):
    pass


def transcribe_audio_file(audio_path: Path) -> TranscriptDocument:
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


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
