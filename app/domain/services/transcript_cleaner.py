from __future__ import annotations

import re

from app.domain.schemas.ingestion import TranscriptDocument

SPEAKER_OR_SECTION_PATTERN = re.compile(
    r"^([A-Z][A-Za-z0-9 ._-]{0,40}:|\[[^\]]+\]|Action:|Decision:|Risk:|Question:)"
)
PURE_TIMESTAMP_PATTERN = re.compile(
    r"^\s*(\d{2}:)?\d{2}:\d{2}([,.]\d{3})?\s*$"
)


def clean_transcript(document: TranscriptDocument) -> TranscriptDocument:
    text = document.text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]

    merged_lines: list[str] = []
    buffer = ""
    seen: set[str] = set()

    for raw_line in lines:
        line = _normalize_whitespace(raw_line)
        if not line or PURE_TIMESTAMP_PATTERN.match(line):
            continue

        dedupe_key = line.casefold()
        if dedupe_key in seen:
            continue

        if not buffer:
            buffer = line
            seen.add(dedupe_key)
            continue

        if _should_merge_lines(buffer, line):
            buffer = f"{buffer} {line}"
            seen.add(dedupe_key)
            continue

        merged_lines.append(buffer)
        buffer = line
        seen.add(dedupe_key)

    if buffer:
        merged_lines.append(buffer)

    cleaned_text = "\n".join(merged_lines).strip()
    return TranscriptDocument(
        text=cleaned_text,
        source_kind=document.source_kind,
        provenance=document.provenance,
        segments=document.segments,
        metadata=document.metadata,
    )


def _should_merge_lines(previous: str, current: str) -> bool:
    if SPEAKER_OR_SECTION_PATTERN.match(current):
        return False
    if previous.endswith((".", "!", "?", ":", ";")):
        return False
    if previous.count(" ") < 2:
        return False
    return True


def _normalize_whitespace(value: str) -> str:
    value = value.replace("\u200b", " ")
    return re.sub(r"\s+", " ", value).strip()
