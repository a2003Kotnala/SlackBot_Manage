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


def extract_structured_meeting_data(raw_content: str) -> ExtractionResult:
    normalized = raw_content.strip()
    if not normalized:
        return ExtractionResult(
            summary="No meeting content was provided.",
            what_happened="No meeting content was provided.",
        )

    if openai_client.is_configured():
        try:
            return openai_client.extract_meeting_data(normalized)
        except Exception as exc:  # pragma: no cover - external integration
            logger.warning(
                "Configured LLM extraction failed; falling back to deterministic parsing: %s",
                exc,
            )

    return _extract_with_rules(normalized)


def _extract_with_rules(raw_content: str) -> ExtractionResult:
    lines = [_normalize_line(line) for line in raw_content.splitlines()]
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

    summary = (
        " ".join(narrative_lines[:2])
        or "Structured notes were extracted from the source."
    )
    what_happened = " ".join(narrative_lines[:5]) or summary
    owners = _unique(item.owner for item in action_items if item.owner)
    due_dates = _unique_dates(item.due_date for item in action_items if item.due_date)
    confidence = (
        Confidence.high
        if any([decisions, action_items, open_questions, risks])
        else Confidence.needs_review
    )

    return ExtractionResult(
        summary=summary,
        what_happened=what_happened,
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


def _normalize_line(line: str) -> str:
    return line.strip().lstrip("-").strip()


def _strip_prefix(line: str) -> str:
    return line.split(":", 1)[1].strip() if ":" in line else line.strip()


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
