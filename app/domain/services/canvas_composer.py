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
        divider(),
        build_summary_section(extraction),
        divider(),
        build_decisions_section(extraction.decisions),
        divider(),
        build_action_items_section(extraction.action_items),
        divider(),
        build_attention_section(extraction),
        divider(),
        build_footer(extraction, source_label),
    ]
    return "\n\n".join(section for section in sections if section.strip()) + "\n"


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

    delta = (due_date - date.today()).days
    formatted = due_date.strftime("%d %b")
    if delta < 0:
        return f":rotating_light: {formatted}"
    if delta <= 3:
        return f":warning: {formatted}"
    return formatted


def progress_bar(done: int, total: int, width: int = 10) -> str:
    if total == 0:
        return "`----------` 0% (0/0 complete)"
    filled = round((done / total) * width)
    bar = "#" * filled + "-" * (width - filled)
    pct = round((done / total) * 100)
    return f"`{bar}` {pct}% ({done}/{total} complete)"


def build_meta_section(
    extraction: ExtractionResult,
    source_label: str,
    title: str,
    compact_header: bool = False,
) -> str:
    owners = ", ".join(bold(owner) for owner in extraction.owners) or italic(
        "Unassigned"
    )
    status_text = _compact_status_text(extraction.status_summary or "Needs review")
    next_review = (
        extraction.next_review_date.strftime("%d %b %Y")
        if extraction.next_review_date
        else italic("Not scheduled")
    )
    return "\n".join(
        [
            header(title),
            _build_header_subtitle(
                source_label,
                extraction.confidence_overall.value,
                compact_header,
            ),
            "",
            f":calendar: {bold('Date:')} {datetime.now().strftime('%d %b %Y')}",
            f":traffic_light: {bold('Status:')} {status_text}",
            f":spiral_calendar_pad: {bold('Next review:')} {next_review}",
            "",
            f":dart: {bold('Priority focus:')}",
            *_priority_focus_lines(extraction.priority_focus),
            "",
            f":busts_in_silhouette: {bold('Owners:')} {owners}",
        ]
    )


def build_summary_section(extraction: ExtractionResult) -> str:
    summary_text = _truncate_summary_text(_compose_summary_text(extraction))
    lines = [
        header("Meeting Summary", 2),
        "",
    ]
    if not summary_text:
        lines.append("No summary available.")
        return "\n".join(lines)

    lines.extend(f"- {item}" for item in _summary_bullets(summary_text))
    return "\n".join(lines)


def build_decisions_section(decisions: list[InsightItem]) -> str:
    lines = [header("Key Decisions", 2), ""]
    if not decisions:
        lines.append("- None captured.")
        return "\n".join(lines)

    for index, item in enumerate(decisions, start=1):
        lines.append(f"{index}. {item.content}")
    return "\n".join(lines)


def build_action_items_section(items: list[ActionItem]) -> str:
    total = len(items)
    done = 0
    lines = [
        header("Action Items", 2),
        "",
        progress_bar(done, total),
        "",
        "| S.No | Task | Owner | Due | State | Priority |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not items:
        lines.append("|  | None captured |  |  |  |  |")
        return "\n".join(lines)

    for index, item in enumerate(items, start=1):
        row = [
            str(index),
            _escape_cell(item.content),
            _escape_cell(_owner_label(item)),
            _escape_cell(fmt_due(item.due_date)),
            _escape_cell(_status_badge(item)),
            _escape_cell(_priority_badge(item)),
        ]
        lines.append("| " + " | ".join(row) + " |")

    if any(item.owner is None for item in items):
        review_note = (
            "Items marked Needs Review need an owner before they can be closed."
        )
        lines.extend(
            [
                "",
                f"> :eyes: {italic(review_note)}",
            ]
        )
    return "\n".join(lines)


def build_attention_section(extraction: ExtractionResult) -> str:
    attention_count = len(extraction.risks) + len(extraction.open_questions)
    lines = [header("Open Risks & Questions", 2), ""]
    if attention_count == 0:
        lines.append("- None captured.")
        return "\n".join(lines)

    if extraction.risks:
        lines.append(f"{bold('Risks')}")
        for index, risk in enumerate(extraction.risks, start=1):
            lines.append(f"{index}. {_risk_badge(risk)} {risk.content}")

    if extraction.open_questions:
        if extraction.risks:
            lines.append("")
        lines.append(f"{bold('Questions')}")
        for index, question in enumerate(extraction.open_questions, start=1):
            lines.append(
                f"{index}. :grey_question: {bold('Open question')} - {question.content}"
            )
    return "\n".join(lines)


def build_footer(extraction: ExtractionResult, source_label: str) -> str:
    todo = len(extraction.action_items)
    needs_review = sum(
        1 for item in extraction.action_items if _status_plain(item) == "Needs Review"
    )
    high_priority = sum(
        1 for item in extraction.action_items if _priority_plain(item) == "High"
    )
    attention = len(extraction.risks) + len(extraction.open_questions)
    generated_at = datetime.now().strftime("%d %b %Y, %H:%M")
    summary_table = _render_table(
        ["To Do", "Needs Review", "High Priority", "Attention"],
        [
            [
                str(todo),
                str(needs_review),
                str(high_priority),
                str(attention),
            ]
        ],
    )
    footer_line = (
        f":robot_face: {bold('Generated')} {generated_at}   "
        f":pushpin: {bold('Source')} {source_label}"
    )
    return "\n".join([summary_table, "", footer_line])


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    divider_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    body_lines = [
        "| " + " | ".join(_escape_cell(cell) for cell in row) + " |" for row in rows
    ]
    return "\n".join([header_line, divider_line, *body_lines])


def _escape_cell(value: str) -> str:
    return value.replace("\n", "<br>").replace("|", "\\|")


def _owner_label(item: ActionItem) -> str:
    if item.owner:
        return item.owner
    return ":eyes: Review"


def _status_badge(item: ActionItem) -> str:
    mapping = {
        "To Do": ":white_circle: To do",
        "In Progress": ":large_blue_circle: Doing",
        "Needs Review": ":eyes: Review",
        "Blocked": ":no_entry: Block",
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


def _priority_badge(item: ActionItem) -> str:
    mapping = {
        "High": ":red_circle: High",
        "Medium": ":large_yellow_circle: Med",
        "Low": ":large_green_circle: Low",
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


def _risk_badge(item: InsightItem) -> str:
    if item.confidence.value == "high":
        return ":red_circle: *High*"
    if item.confidence.value == "medium":
        return ":large_yellow_circle: *Medium*"
    return ":large_green_circle: *Low*"


def _confidence_label(value: str) -> str:
    mapping = {
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "needs_review": "Needs review",
    }
    return mapping[value]


def _build_header_subtitle(
    source_label: str, confidence_value: str, compact_header: bool
) -> str:
    confidence = _confidence_label(confidence_value)
    if compact_header:
        source_name = source_label.replace("_", " ").title()
        return italic(f"{source_name} | {confidence} confidence")
    return italic(
        "Action Canvas generated from "
        f"{source_label} | AI confidence: {confidence}"
    )


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
