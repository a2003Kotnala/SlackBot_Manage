import re
from datetime import date, datetime

from app.domain.schemas.extraction import ActionItem, ExtractionResult, InsightItem

STATUS_MAX_WORDS = 24
PRIORITY_MAX_WORDS = 18
SUMMARY_MAX_WORDS = 95
SUMMARY_BULLET_TARGET_WORDS = 32


def create_draft_canvas(
    extraction: ExtractionResult,
    source_label: str = "huddle_notes",
    title_override: str | None = None,
    compact_header: bool = False,
) -> str:
    title = title_override or (
        extraction.meeting_title or f"Meeting - {datetime.now().strftime('%Y-%m-%d')}"
    )
    sections = [
        build_meta_section(extraction, source_label, title, compact_header),
        build_summary_section(extraction),
        build_decisions_section(extraction.decisions),
        build_action_items_section(extraction.action_items),
        build_risks_section(extraction.risks),
        build_questions_section(extraction.open_questions),
        build_footer(source_label),
    ]
    return f"\n\n{divider()}\n\n".join(
        section for section in sections if section.strip()
    ) + "\n"


def divider() -> str:
    return "---"


def bold(text: str) -> str:
    return f"*{text}*"


def italic(text: str) -> str:
    return f"_{text}_"


def header(text: str, level: int = 1) -> str:
    return f"{'#' * level} {text}"


def fmt_due(due_date: date | None) -> str:
    if due_date is None:
        return italic("TBD")
    return due_date.strftime("%d %b")


def build_meta_section(
    extraction: ExtractionResult,
    source_label: str,
    title: str,
    compact_header: bool = False,
) -> str:
    owners = ", ".join(extraction.owners)
    status_text = _compact_status_text(extraction.status_summary or "Needs review")
    next_review = (
        extraction.next_review_date.strftime("%d %b %Y")
        if extraction.next_review_date
        else italic("Not scheduled")
    )
    lines = [
        header(title),
        f":calendar: {bold('Date:')} {datetime.now().strftime('%d %b %Y')}",
        (
            f":traffic_light: {bold('Status:')} {status_text}   "
            f":spiral_calendar_pad: {bold('Next review:')} {next_review}"
        ),
    ]

    if extraction.priority_focus:
        lines.extend(
            [
                "",
                f":dart: {bold('Priority focus:')}",
                "",
                *_priority_focus_lines(extraction.priority_focus),
            ]
        )

    if owners:
        lines.extend(
            [
                "",
                f":busts_in_silhouette: {bold('Owners:')} {owners}",
            ]
        )
    return "\n".join(lines)


def build_summary_section(extraction: ExtractionResult) -> str:
    summary_text = _truncate_summary_text(_compose_summary_text(extraction))
    if not summary_text:
        return ""

    lines = [
        header("Meeting Summary", 2),
        "",
    ]
    lines.extend(f"- {item}" for item in _summary_bullets(summary_text))
    return "\n".join(lines)


def build_decisions_section(decisions: list[InsightItem]) -> str:
    if not decisions:
        return ""

    lines = [header("Key Decisions", 2), ""]
    for index, item in enumerate(decisions, start=1):
        lines.append(f"{index}. {item.content}")
    return "\n".join(lines)


def build_action_items_section(items: list[ActionItem]) -> str:
    if not items:
        return ""

    lines = [
        header("Action Items", 2),
        "",
        "| S.No | Task | Owner | Due | Status | Priority |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for index, item in enumerate(items, start=1):
        row = [
            str(index),
            _escape_cell(item.content),
            _escape_cell(_owner_label(item)),
            _escape_cell(fmt_due(item.due_date)),
            _escape_cell(_status_label(item)),
            _escape_cell(_priority_label(item)),
        ]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_risks_section(risks: list[InsightItem]) -> str:
    if not risks:
        return ""

    lines = [header("Open Risks", 2), ""]
    for index, risk in enumerate(risks, start=1):
        lines.append(f"{index}. {risk.content}")
    return "\n".join(lines)


def build_questions_section(open_questions: list[InsightItem]) -> str:
    if not open_questions:
        return ""

    lines = [header("Open Questions", 2), ""]
    for index, question in enumerate(open_questions, start=1):
        lines.append(f"{index}. {question.content}")
    return "\n".join(lines)


def build_footer(source_label: str) -> str:
    generated_at = datetime.now().strftime("%d %b %Y, %H:%M")
    return (
        f"{bold('Generated:')} {generated_at}   "
        f"{bold('Source:')} {source_label.replace('_', ' ').title()}"
    )


def _escape_cell(value: str) -> str:
    return value.replace("\n", "<br>").replace("|", "\\|")


def _owner_label(item: ActionItem) -> str:
    if item.owner:
        return item.owner
    return "Needs review"


def _status_label(item: ActionItem) -> str:
    mapping = {
        "To Do": "To do",
        "In Progress": "In progress",
        "Needs Review": "Needs review",
        "Blocked": "Blocked",
    }
    return mapping[_status_plain(item)]


def _status_plain(item: ActionItem) -> str:
    if (
        item.owner is None
        or item.due_date is None
        or item.confidence.value == "needs_review"
    ):
        return "Needs Review"
    if item.due_date < date.today():
        return "Blocked"
    if item.due_date <= date.today():
        return "In Progress"
    return "To Do"


def _priority_label(item: ActionItem) -> str:
    mapping = {
        "High": "High",
        "Medium": "Medium",
        "Low": "Low",
    }
    return mapping[_priority_plain(item)]


def _priority_plain(item: ActionItem) -> str:
    if not item.due_date:
        return "Medium"
    days_until_due = (item.due_date - date.today()).days
    if days_until_due <= 3:
        return "High"
    if days_until_due <= 7:
        return "Medium"
    return "Low"


def _priority_focus_lines(text: str) -> list[str]:
    compact_text = _compact_priority_focus(text)
    if not compact_text:
        return ["1. Confirm next steps and owners."]

    normalized = re.sub(r"\s+", " ", compact_text).strip()
    numbered_chunks = re.split(r"\s*\d+\.\s*", normalized)
    if len(numbered_chunks) > 2:
        items = [chunk.strip() for chunk in numbered_chunks if chunk.strip()]
        return [f"{index}. {item}" for index, item in enumerate(items, start=1)]

    sentences = [
        segment.strip(" -")
        for segment in re.split(r"(?<=[.!?])\s+|\s*;\s*", normalized)
        if segment.strip(" -")
    ]
    if len(sentences) == 1 and ", and " in normalized:
        sentences = [part.strip() for part in normalized.split(", ") if part.strip()]

    return [
        f"{index}. {sentence.rstrip('.')}"
        for index, sentence in enumerate(sentences[:3], start=1)
    ] or ["1. Confirm next steps and owners."]


def _compose_summary_text(extraction: ExtractionResult) -> str:
    summary = _clean_summary_text(extraction.summary, extraction.meeting_title)
    details = _clean_summary_text(extraction.what_happened, extraction.meeting_title)

    if details and summary and details.startswith(summary):
        return details
    if summary and details and summary.startswith(details):
        return summary
    if details and details != summary:
        return " ".join(part for part in [summary, details] if part).strip()
    return summary or details


def _clean_summary_text(text: str, meeting_title: str) -> str:
    if not text:
        return ""

    cleaned = " ".join(text.split())
    patterns = [
        rf"^{re.escape(meeting_title)}\s*[-:|]?\s*summary\s*:\s*",
        rf"^{re.escape(meeting_title)}\s*[-:|]?\s*",
        r"^summary\s*:\s*",
        r"^what happened\s*:\s*",
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\bsummary\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(
        r"\bwhat happened\s*:\s*", "", cleaned, flags=re.IGNORECASE
    ).strip()
    return cleaned


def _truncate_summary_text(text: str) -> str:
    return _truncate_words(text, SUMMARY_MAX_WORDS)


def _summary_bullets(text: str) -> list[str]:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]
    if not sentences:
        return [text]

    bullets: list[str] = []
    current_parts: list[str] = []
    current_words = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())
        if (
            current_parts
            and current_words + sentence_words > SUMMARY_BULLET_TARGET_WORDS
        ):
            bullets.append(" ".join(current_parts).strip())
            current_parts = [sentence]
            current_words = sentence_words
            continue

        current_parts.append(sentence)
        current_words += sentence_words

    if current_parts:
        bullets.append(" ".join(current_parts).strip())

    return bullets or [text]


def _compact_status_text(text: str) -> str:
    return _truncate_words(text, STATUS_MAX_WORDS)


def _compact_priority_focus(text: str) -> str:
    default = "Confirm next steps and owners."
    return _truncate_words(text or default, PRIORITY_MAX_WORDS)


def _truncate_words(text: str, max_words: int) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""

    words = cleaned.split()
    if len(words) <= max_words:
        return cleaned

    truncated_words = words[:max_words]
    while truncated_words and truncated_words[-1].lower().rstrip(",;:-") in {
        "and",
        "or",
        "with",
        "to",
        "for",
        "of",
    }:
        truncated_words.pop()

    truncated = " ".join(truncated_words).rstrip(",;:-")
    if truncated.endswith((".", "!", "?")):
        return truncated
    return f"{truncated}..."
