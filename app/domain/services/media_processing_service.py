from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from app.config import settings


class MediaProcessingError(RuntimeError):
    pass


class MediaProcessingStoppedError(RuntimeError):
    pass


def normalize_media_to_audio(
    input_path: Path,
    output_path: Path,
    *,
    stop_requested: Callable[[], bool] | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration_seconds = probe_media_duration_seconds(input_path)
    if duration_seconds is not None and duration_seconds <= 0:
        raise MediaProcessingError(
            "The uploaded media does not contain playable audio."
        )

    timeout_seconds = _resolve_media_processing_timeout(duration_seconds)
    command = [
        settings.ffmpeg_binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-fflags",
        "+discardcorrupt",
        "-err_detect",
        "ignore_err",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_path),
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
    )
    started = time.monotonic()
    try:
        while process.poll() is None:
            if stop_requested and stop_requested():
                process.kill()
                process.communicate()
                raise MediaProcessingStoppedError("Stopped by user.")
            if time.monotonic() - started > timeout_seconds:
                process.kill()
                _stdout, stderr = process.communicate()
                detail = stderr.strip() or "ffmpeg timed out"
                raise MediaProcessingError(
                    "Media normalization timed out after "
                    f"{int(timeout_seconds)} seconds. {detail}"
                )
            time.sleep(0.25)

        stdout, stderr = process.communicate()
    except Exception:
        if process.poll() is None:
            process.kill()
            process.communicate()
        raise

    if process.returncode != 0:
        detail = (stderr or stdout or "").strip() or "ffmpeg failed"
        raise MediaProcessingError(detail)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise MediaProcessingError(
            "ffmpeg finished without producing normalized audio output."
        )
    return output_path


def probe_media_duration_seconds(input_path: Path) -> float | None:
    command = [
        settings.ffprobe_binary,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(input_path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        payload = json.loads(completed.stdout)
        duration = payload.get("format", {}).get("duration")
        return float(duration) if duration is not None else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _resolve_media_processing_timeout(duration_seconds: float | None) -> float:
    base_timeout = settings.followthru_media_processing_timeout_seconds
    if duration_seconds is None:
        return base_timeout
    return max(base_timeout, (duration_seconds * 3.0) + 30.0)
