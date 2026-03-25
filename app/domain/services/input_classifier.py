from __future__ import annotations

import re

from app.domain.providers.registry import resolve_provider_adapter
from app.domain.schemas.followthru import FollowThruMode
from app.domain.schemas.ingestion import (
    IngestionSourceType,
    InputClassification,
    ProviderType,
    SlackFileReference,
)
from app.domain.services.followthru_request import (
    detect_requested_mode,
    strip_mode_prefix,
)
from app.domain.services.transcript_parser import (
    is_supported_media_file,
    is_supported_transcript_file,
)

URL_PATTERN = re.compile(r"https://[^\s<>]+", re.IGNORECASE)


def classify_slack_input(
    message_text: str,
    files: list[SlackFileReference] | None = None,
) -> InputClassification:
    files = files or []
    requested_mode = detect_requested_mode(message_text)
    stripped_text = strip_mode_prefix(message_text)
    urls = URL_PATTERN.findall(stripped_text)

    if urls:
        adapter = resolve_provider_adapter(urls[0])
        if adapter:
            return InputClassification(
                requested_mode=requested_mode,
                source_type=IngestionSourceType.recording_link,
                provider_type=ProviderType.zoom,
                recording_url=urls[0],
                message_text=message_text.strip(),
                slack_files=files,
            )
        if not stripped_text.replace(urls[0], "").strip() and not files:
            return InputClassification(
                requested_mode=requested_mode,
                source_type=IngestionSourceType.unsupported,
                provider_type=ProviderType.none,
                message_text=message_text.strip(),
                rejection_reason="That recording provider is not supported yet.",
            )

    transcript_files = [
        file_ref
        for file_ref in files
        if is_supported_transcript_file(file_ref.model_dump())
    ]
    media_files = [
        file_ref for file_ref in files if is_supported_media_file(file_ref.model_dump())
    ]

    if transcript_files:
        return InputClassification(
            requested_mode=requested_mode,
            source_type=IngestionSourceType.transcript_file,
            provider_type=ProviderType.none,
            message_text=message_text.strip(),
            slack_files=transcript_files,
        )

    if media_files:
        return InputClassification(
            requested_mode=requested_mode,
            source_type=IngestionSourceType.media_file,
            provider_type=ProviderType.none,
            message_text=message_text.strip(),
            slack_files=media_files,
            media_filename=media_files[0].name,
        )

    if stripped_text and requested_mode != FollowThruMode.help:
        return InputClassification(
            requested_mode=requested_mode,
            source_type=IngestionSourceType.transcript_text,
            provider_type=ProviderType.none,
            transcript_text=stripped_text,
            message_text=message_text.strip(),
            slack_files=files,
        )

    if files:
        return InputClassification(
            requested_mode=requested_mode,
            source_type=IngestionSourceType.unsupported,
            provider_type=ProviderType.none,
            message_text=message_text.strip(),
            slack_files=files,
            rejection_reason=(
                "That upload could not be processed. Supported transcript files are "
                ".txt, .md, .csv, .tsv, .srt, .vtt, .log, and .docx."
            ),
        )

    return InputClassification(
        requested_mode=requested_mode,
        source_type=IngestionSourceType.unsupported,
        provider_type=ProviderType.none,
        message_text=message_text.strip(),
        rejection_reason=(
            "Send transcript text, upload a transcript file, "
            "or paste a Zoom recording link."
        ),
    )
