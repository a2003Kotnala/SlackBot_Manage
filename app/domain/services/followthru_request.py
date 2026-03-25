from app.domain.schemas.followthru import FollowThruMode

MODE_PREFIXES: dict[FollowThruMode, tuple[str, ...]] = {
    FollowThruMode.preview: (
        "preview",
        "show preview",
        "dry run",
        "generate preview",
    ),
    FollowThruMode.draft: ("draft", "save draft", "create draft"),
    FollowThruMode.publish: (
        "publish",
        "ship it",
        "update canvas",
        "send to canvas",
        "push to canvas",
    ),
}


def detect_requested_mode(text: str) -> FollowThruMode:
    lowered = text.strip().lower()
    if not lowered:
        return FollowThruMode.publish

    if lowered.startswith(
        (
            "help",
            "what can you do",
            "capabilities",
            "how do i use",
        )
    ):
        return FollowThruMode.help

    for mode, prefixes in MODE_PREFIXES.items():
        if any(lowered.startswith(prefix) for prefix in prefixes):
            return mode
    return FollowThruMode.publish


def strip_mode_prefix(text: str) -> str:
    normalized = text.strip()
    lowered = normalized.lower()
    for prefixes in MODE_PREFIXES.values():
        for prefix in prefixes:
            if lowered.startswith(prefix):
                remainder = normalized[len(prefix) :].strip(" :,-\n")
                return remainder or normalized
    return normalized


def normalize_dm_request(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        return normalized

    mode = detect_requested_mode(normalized)
    if mode == FollowThruMode.help:
        return "help"
    if mode in {FollowThruMode.preview, FollowThruMode.draft, FollowThruMode.publish}:
        return normalized
    return f"publish {normalized}"
