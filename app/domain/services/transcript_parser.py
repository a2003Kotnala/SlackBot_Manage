from __future__ import annotations

import csv
import re
from io import BytesIO, StringIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from app.domain.schemas.ingestion import TranscriptDocument

TRANSCRIPT_FILE_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".srt",
    ".vtt",
    ".log",
    ".docx",
}
MEDIA_FILE_EXTENSIONS = {
    ".aac",
    ".m4a",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".wav",
    ".webm",
}
DOCX_MIMETYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
TIMESTAMP_LINE_PATTERN = re.compile(
    r"^\s*(\d{2}:)?\d{2}:\d{2}[,.]\d{3}\s*-->\s*(\d{2}:)?\d{2}:\d{2}[,.]\d{3}"
)
VTT_TIMESTAMP_PATTERN = re.compile(
    r"^\s*(\d{2}:)?\d{2}:\d{2}\.\d{3}\s*-->\s*(\d{2}:)?\d{2}:\d{2}\.\d{3}"
)


def is_supported_transcript_file(file_info: dict) -> bool:
    mimetype = (file_info.get("mimetype") or "").lower()
    filetype = (file_info.get("filetype") or "").lower()
    extension = file_extension(file_info)
    return (
        extension in TRANSCRIPT_FILE_EXTENSIONS
        or mimetype.startswith("text/")
        or mimetype == DOCX_MIMETYPE
        or filetype
        in {
            "text",
            "txt",
            "csv",
            "markdown",
            "md",
            "tsv",
            "srt",
            "vtt",
            "log",
            "docx",
        }
    )


def is_supported_media_file(file_info: dict) -> bool:
    mimetype = (file_info.get("mimetype") or "").lower()
    extension = file_extension(file_info)
    return extension in MEDIA_FILE_EXTENSIONS or mimetype.startswith(
        ("audio/", "video/")
    )


def file_extension(file_info: dict) -> str:
    return Path(file_info.get("name") or "").suffix.lower()


def parse_transcript_bytes(
    filename: str,
    content: bytes,
    mimetype: str | None = None,
) -> TranscriptDocument:
    extension = Path(filename).suffix.lower()
    lowered_mimetype = (mimetype or "").lower()

    if extension == ".docx" or lowered_mimetype == DOCX_MIMETYPE:
        text = _extract_docx_text(content)
    else:
        text = content.decode("utf-8", errors="ignore")

    parsed_text = parse_transcript_text(filename, text)
    return TranscriptDocument(
        text=parsed_text,
        source_kind="file",
        provenance=filename,
    )


def parse_transcript_text(filename: str, content: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension in {".txt", ".md", ".markdown", ".log"}:
        return content.strip()
    if extension == ".csv":
        return _parse_delimited_text(content, ",")
    if extension == ".tsv":
        return _parse_delimited_text(content, "\t")
    if extension == ".srt":
        return _parse_srt(content)
    if extension == ".vtt":
        return _parse_vtt(content)
    if extension == ".docx":
        return content.strip()
    return content.strip()


def _parse_delimited_text(content: str, delimiter: str) -> str:
    stream = StringIO(content)
    reader = csv.reader(stream, delimiter=delimiter)
    rows: list[str] = []
    for row in reader:
        cleaned = " ".join(cell.strip() for cell in row if cell and cell.strip())
        if cleaned:
            rows.append(cleaned)
    return "\n".join(rows).strip()


def _parse_srt(content: str) -> str:
    lines: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.isdigit() or TIMESTAMP_LINE_PATTERN.match(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _parse_vtt(content: str) -> str:
    lines: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line == "WEBVTT" or line.startswith("NOTE "):
            continue
        if VTT_TIMESTAMP_PATTERN.match(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _extract_docx_text(file_bytes: bytes) -> str:
    try:
        with ZipFile(BytesIO(file_bytes)) as archive:
            document_xml = archive.read("word/document.xml")
    except (BadZipFile, KeyError):
        return ""

    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError:
        return ""

    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        parts: list[str] = []
        for node in paragraph.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "t" and node.text:
                parts.append(node.text)
            elif tag == "tab":
                parts.append("\t")
            elif tag in {"br", "cr"}:
                parts.append("\n")
        paragraph_text = "".join(parts).strip()
        if paragraph_text:
            paragraphs.append(paragraph_text)
    return "\n".join(paragraphs).strip()
