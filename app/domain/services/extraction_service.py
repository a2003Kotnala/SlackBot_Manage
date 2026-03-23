import re
from collections.abc import Iterable
from datetime import date

from app.domain.schemas.extraction import (
    ActionItem,
    Confidence,
    ExtractionResult,
    InsightItem,
)
from app.integrations.openai_client import openai_client
from app.logger import logger

ACTION_PREFIXES = ("action:", "todo:", "owner:", "[ ]", "- [ ]")
DECISION_PREFIXES = ("decision:", "decided:", "approved:")
RISK_PREFIXES = ("risk:", "blocker:", "issue:")
QUESTION_PREFIXES = ("question:", "q:")
DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
OWNER_PATTERN = re.compile(r"@([A-Za-z0-9._-]+)")
SPEAKER_PREFIX_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9 ._-]{0,30}:\s*")
INLINE_LABEL_PATTERN = re.compile(
    r"(?i)(action:|todo:|owner:|decision:|decided:|approved:|risk:|blocker:|issue:|question:|q:)"
)
EXTRACTION_TARGET_CHARS = 9000
EXTRACTION_CONTEXT_SEGMENTS = 8
EXTRACTION_MAX_SEGMENTS = 120
LOW_SIGNAL_PHRASES = {
    "okay",
    "ok",
    "cool",
    "sounds good",
    "got it",
    "thank you",
    "thanks",
    "yep",
    "yeah",
    "right",
    "sure",
}
HIGH_SIGNAL_KEYWORDS = (
    "launch",
    "publish",
    "ship",
    "owner",
    "due",
    "deadline",
    "blocker",
    "risk",
    "question",
    "decision",
    "action",
    "slack",
    "transcript",
    "canvas",
    "database",
    "postgres",
    "api",
)


def extract_structured_meeting_data(raw_content: str) -> ExtractionResult:
    normalized = raw_content.strip()
    if not normalized:
        return ExtractionResult(
            meeting_title="Execution Review",
            summary="No meeting content was provided.",
            what_happened="No meeting content was provided.",
            status_summary="Needs input",
            priority_focus="Capture meeting notes to generate a tracking draft.",
        )

    prepared_content = _prepare_content_for_extraction(normalized)
    if prepared_content != normalized:
        logger.info(
            "Compacted meeting content from %s to %s chars before extraction",
            len(normalized),
            len(prepared_content),
        )

    if openai_client.is_configured():
        try:
            return openai_client.extract_meeting_data(prepared_content)
        except Exception as exc:  # pragma: no cover - external integration
            logger.warning(
                (
                    "Configured LLM extraction failed; "
                    "falling back to deterministic parsing: %s"
                ),
                exc,
            )

    return _extract_with_rules(prepared_content)


def _extract_with_rules(raw_content: str) -> ExtractionResult:
    lines = [_normalize_line(line) for line in _split_into_segments(raw_content)]
    lines = [line for line in lines if line]

    decisions: list[InsightItem] = []
    action_items: list[ActionItem] = []
    open_questions: list[InsightItem] = []
    risks: list[InsightItem] = []
    narrative_lines: list[str] = []

    for line in lines:
        lowered = line.lower()
        if lowered.startswith(ACTION_PREFIXES):
            action_items.append(_build_action_item(line))
        elif lowered.startswith(DECISION_PREFIXES) or " decided " in f" {lowered} ":
            decisions.append(
                InsightItem(content=_strip_prefix(line), confidence=Confidence.high)
            )
        elif lowered.startswith(RISK_PREFIXES):
            risks.append(
                InsightItem(content=_strip_prefix(line), confidence=Confidence.medium)
            )
        elif lowered.startswith(QUESTION_PREFIXES) or line.endswith("?"):
            open_questions.append(
                InsightItem(
                    content=_strip_prefix(line),
                    confidence=Confidence.needs_review,
                )
            )
        else:
            narrative_lines.append(line)

    meeting_title = _derive_meeting_title(lines, narrative_lines)
    summary = (
        " ".join(narrative_lines[:2])
        or "Structured notes were extracted from the source."
    )
    what_happened = " ".join(narrative_lines[:5]) or summary
    owners = _unique(item.owner for item in action_items if item.owner)
    due_dates = _unique_dates(item.due_date for item in action_items if item.due_date)
    next_review_date = min(due_dates) if due_dates else None
    confidence = (
        Confidence.high
        if any([decisions, action_items, open_questions, risks])
        else Confidence.needs_review
    )

    return ExtractionResult(
        meeting_title=meeting_title,
        summary=summary,
        what_happened=what_happened,
        status_summary=_derive_status_summary(action_items, open_questions, risks),
        priority_focus=_derive_priority_focus(
            action_items, risks, open_questions, decisions
        ),
        next_review_date=next_review_date,
        decisions=decisions,
        action_items=action_items,
        owners=owners,
        due_dates=due_dates,
        open_questions=open_questions,
        risks=risks,
        confidence_overall=confidence,
    )


def _build_action_item(line: str) -> ActionItem:
    owner_match = OWNER_PATTERN.search(line)
    due_match = DATE_PATTERN.search(line)
    owner = owner_match.group(1) if owner_match else None
    due_date = date.fromisoformat(due_match.group(1)) if due_match else None

    content = _strip_prefix(line)
    if owner_match:
        content = content.replace(f"@{owner}", "").strip(" -")
    if due_match:
        content = content.replace(due_match.group(1), "").strip(" -")

    confidence = Confidence.medium if owner or due_date else Confidence.needs_review
    return ActionItem(
        content=content or _strip_prefix(line),
        owner=owner,
        due_date=due_date,
        confidence=confidence,
    )


def _prepare_content_for_extraction(raw_content: str) -> str:
    if len(raw_content) <= EXTRACTION_TARGET_CHARS:
        return raw_content

    segments = _split_for_compression(raw_content)
    if not segments:
        return raw_content[:EXTRACTION_TARGET_CHARS]

    selected_indices = _select_context_segment_indices(segments)
    ranked_segments = sorted(
        (
            (_score_segment(segment), index)
            for index, segment in enumerate(segments)
            if index not in selected_indices
        ),
        reverse=True,
    )

    for score, index in ranked_segments:
        if score <= 0 or len(selected_indices) >= EXTRACTION_MAX_SEGMENTS:
            break
        selected_indices.add(index)

    compacted = _join_selected_segments(segments, selected_indices)
    return compacted or raw_content[:EXTRACTION_TARGET_CHARS]


def _split_into_segments(raw_content: str) -> list[str]:
    segments: list[str] = []
    for raw_line in raw_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        matches = list(INLINE_LABEL_PATTERN.finditer(line))
        if len(matches) <= 1:
            segments.append(line)
            continue

        if matches[0].start() > 0:
            leading = line[: matches[0].start()].strip(" -.;")
            if leading:
                segments.append(leading)

        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
            segment = line[match.start() : end].strip(" -;")
            if segment:
                segments.append(segment)

    return segments


def _split_for_compression(raw_content: str) -> list[str]:
    segments: list[str] = []
    for raw_line in raw_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for segment in _split_into_segments(line):
            normalized_segment = _normalize_line(segment)
            if normalized_segment:
                segments.append(normalized_segment)
    return segments


def _normalize_line(line: str) -> str:
    return line.strip().lstrip("-").strip()


def _strip_prefix(line: str) -> str:
    return line.split(":", 1)[1].strip() if ":" in line else line.strip()


def _select_context_segment_indices(segments: list[str]) -> set[int]:
    selected: set[int] = set()
    for index, segment in enumerate(segments):
        if _is_low_signal_segment(segment):
            continue
        selected.add(index)
        if len(selected) >= EXTRACTION_CONTEXT_SEGMENTS:
            break
    return selected


def _score_segment(segment: str) -> int:
    lowered = segment.lower()
    content = _strip_speaker_prefix(lowered)

    score = 0
    if lowered.startswith(ACTION_PREFIXES + DECISION_PREFIXES + RISK_PREFIXES):
        score += 100
    if lowered.startswith(QUESTION_PREFIXES) or segment.endswith("?"):
        score += 90
    if OWNER_PATTERN.search(segment):
        score += 25
    if DATE_PATTERN.search(segment):
        score += 20
    if any(keyword in content for keyword in HIGH_SIGNAL_KEYWORDS):
        score += 15
    if len(content.split()) >= 8:
        score += 10
    if len(content) >= 40:
        score += 5
    if _is_low_signal_segment(segment):
        score -= 60
    return score


def _is_low_signal_segment(segment: str) -> bool:
    content = _strip_speaker_prefix(segment.lower()).strip(" .,!?:;")
    if not content:
        return True
    if content in LOW_SIGNAL_PHRASES:
        return True
    return len(content.split()) <= 2 and not any(char.isdigit() for char in content)


def _strip_speaker_prefix(value: str) -> str:
    return SPEAKER_PREFIX_PATTERN.sub("", value).strip()


def _join_selected_segments(segments: list[str], selected_indices: set[int]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    total_chars = 0

    for index, segment in enumerate(segments):
        if index not in selected_indices:
            continue

        dedupe_key = " ".join(segment.lower().split())
        if dedupe_key in seen:
            continue

        projected = total_chars + len(segment) + (1 if lines else 0)
        if projected > EXTRACTION_TARGET_CHARS:
            break

        lines.append(segment)
        seen.add(dedupe_key)
        total_chars = projected

    return "\n".join(lines)


def _unique(values: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _unique_dates(values: Iterable[date]) -> list[date]:
    seen: list[date] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _derive_meeting_title(lines: list[str], narrative_lines: list[str]) -> str:
    candidates = narrative_lines or lines
    if not candidates:
        return "Execution Review"

    candidate = candidates[0].strip(" -")
    if ":" in candidate and len(candidate.split(":", 1)[0].split()) <= 3:
        candidate = candidate.split(":", 1)[1].strip()
    return candidate[:80] or "Execution Review"


def _derive_status_summary(
    action_items: list[ActionItem],
    open_questions: list[InsightItem],
    risks: list[InsightItem],
) -> str:
    if risks:
        return "At risk"
    if open_questions:
        return "Needs follow-up"
    if action_items:
        return "Execution in progress"
    return "Needs review"


def _derive_priority_focus(
    action_items: list[ActionItem],
    risks: list[InsightItem],
    open_questions: list[InsightItem],
    decisions: list[InsightItem],
) -> str:
    if risks:
        return risks[0].content
    if open_questions:
        return open_questions[0].content
    if action_items:
        return action_items[0].content
    if decisions:
        return decisions[0].content
    return "Confirm next steps and owners."
