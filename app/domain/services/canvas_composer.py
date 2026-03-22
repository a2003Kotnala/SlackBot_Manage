import re
from datetime import date, datetime

from app.domain.schemas.extraction import ActionItem, ExtractionResult, InsightItem


def create_draft_canvas(
    extraction: ExtractionResult, source_label: str = "huddle_notes"
) -> str:
    title = (
        extraction.meeting_title or f"Meeting - {datetime.now().strftime('%Y-%m-%d')}"
    )
    sections = [
        build_meta_section(extraction, source_label, title),
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
    formatted = due_date.strftime("%d %b %Y")
    if delta < 0:
        return f":rotating_light: *{formatted}* _(overdue)_"
    if delta <= 3:
        return f":warning: *{formatted}* _(in {delta}d)_"
    return formatted


def progress_bar(done: int, total: int, width: int = 10) -> str:
    if total == 0:
        return "`----------` 0% (0/0 complete)"
    filled = round((done / total) * width)
    bar = "#" * filled + "-" * (width - filled)
    pct = round((done / total) * 100)
    return f"`{bar}` {pct}% ({done}/{total} complete)"


def build_meta_section(
    extraction: ExtractionResult, source_label: str, title: str
) -> str:
    owners = ", ".join(bold(owner) for owner in extraction.owners) or italic(
        "Unassigned"
    )
    next_review = (
        extraction.next_review_date.strftime("%d %b %Y")
        if extraction.next_review_date
        else italic("Not scheduled")
    )
    return "\n".join(
        [
            header(title),
            italic(
                "Action Canvas generated from "
                f"{source_label} | AI confidence: "
                f"{_confidence_label(extraction.confidence_overall.value)}"
            ),
            "",
            (
                f":calendar: {bold('Date:')} {datetime.now().strftime('%d %b %Y')}   "
                f":traffic_light: {bold('Status:')} "
                f"{extraction.status_summary or 'Needs review'}   "
                f":spiral_calendar_pad: {bold('Next review:')} {next_review}"
            ),
            "",
            (
                f":dart: {bold('Priority focus:')} "
                f"{extraction.priority_focus or 'Confirm next steps and owners.'}"
            ),
            "",
            f":busts_in_silhouette: {bold('Owners:')} {owners}",
        ]
    )


def build_summary_section(extraction: ExtractionResult) -> str:
    summary_text = _compose_summary_text(extraction)
    lines = [
        header("Meeting Summary", 2),
        "",
        summary_text or "No summary available.",
    ]
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
        "| S.No | Task | Owner | Due | Status | Priority |",
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

    for risk in extraction.risks:
        lines.append(f"{_risk_badge(risk)} {risk.content}")
    for question in extraction.open_questions:
        lines.append(f":grey_question: {bold('Open question')} - {question.content}")
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
        ["", "", "", ""],
        [
            [
                _metric_card("To Do", todo),
                _metric_card("Needs review", needs_review),
                _metric_card("High priority", high_priority),
                _metric_card("Attention", attention),
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
    return ":eyes: Needs Review"


def _status_badge(item: ActionItem) -> str:
    mapping = {
        "To Do": ":white_circle: To Do",
        "In Progress": ":large_blue_circle: In Progress",
        "Needs Review": ":eyes: Needs Review",
        "Blocked": ":no_entry: Blocked",
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
        "Medium": ":large_yellow_circle: Medium",
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
        return ":red_circle: *High risk* -"
    if item.confidence.value == "medium":
        return ":large_yellow_circle: *Medium risk* -"
    return ":large_green_circle: *Low risk* -"


def _metric_card(label: str, value: int) -> str:
    return f"**{value}**<br>{label}"


def _confidence_label(value: str) -> str:
    mapping = {
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "needs_review": "Needs review",
    }
    return mapping[value]


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
