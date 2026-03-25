from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import settings


class MediaProcessingError(RuntimeError):
    pass


def normalize_media_to_audio(input_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        settings.ffmpeg_binary,
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise MediaProcessingError(completed.stderr.strip() or "ffmpeg failed")
    return output_path
