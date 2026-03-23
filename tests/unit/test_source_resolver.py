from app.slack.services.source_resolver import resolve_latest_huddle_notes_canvas


def test_resolve_latest_huddle_notes_prefers_substantial_canvas(monkeypatch):
    monkeypatch.setattr(
        "app.slack.services.source_resolver.slack_client.list_files",
        lambda *_args, **_kwargs: [
            {
                "id": "F-CANVAS",
                "filetype": "canvas",
                "timestamp": 1710001000,
                "title": "Huddle notes: Daily sync",
            }
        ],
    )
    monkeypatch.setattr(
        "app.slack.services.source_resolver.slack_client.get_file_content",
        lambda file_id: {
            "id": file_id,
            "content": (
                "Decision: Ship the pilot today.\n"
                "Action: Prepare demo for Maya.\n"
                "Risk: Awaiting final budget approval."
            ),
        },
    )
    monkeypatch.setattr(
        "app.slack.services.source_resolver.create_source_record",
        lambda **kwargs: kwargs,
    )

    result = resolve_latest_huddle_notes_canvas("C123", None, "U123")

    assert result["raw_content"].startswith("Decision: Ship the pilot today.")
    assert result["slack_canvas_id"] == "F-CANVAS"


def test_resolve_latest_huddle_notes_falls_back_to_matching_transcript(monkeypatch):
    files = [
        {
            "id": "F-CANVAS",
            "filetype": "canvas",
            "timestamp": 1710001000,
            "title": "Huddle notes: Daily sync",
        },
        {
            "id": "F-OLD",
            "filetype": "text",
            "timestamp": 1710000100,
            "title": "Huddle transcript",
            "mimetype": "text/plain",
        },
        {
            "id": "F-BEST",
            "filetype": "text",
            "timestamp": 1710001002,
            "title": "Huddle transcript",
            "mimetype": "text/plain",
        },
    ]
    downloaded_urls: list[str] = []

    monkeypatch.setattr(
        "app.slack.services.source_resolver.slack_client.list_files",
        lambda *_args, **_kwargs: files,
    )

    def fake_get_file_content(file_id: str):
        if file_id == "F-CANVAS":
            return {
                "id": "F-CANVAS",
                "content": (
                    "Slack AI took notes for this huddle from 12:54 PM - 12:55 PM.\n"
                    "Attendees\n"
                    "@maya and @ankit\n"
                    "Summary\n"
                    "Not enough to summarize.\n"
                    "Huddle transcript"
                ),
            }

        return {
            "id": file_id,
            "title": "Huddle transcript",
            "filetype": "text",
            "mimetype": "text/plain",
            "url_private_download": f"https://example.com/{file_id}.txt",
        }

    monkeypatch.setattr(
        "app.slack.services.source_resolver.slack_client.get_file_content",
        fake_get_file_content,
    )
    monkeypatch.setattr(
        "app.slack.services.source_resolver.slack_client.download_text_file",
        lambda url: downloaded_urls.append(url)
        or "Decision: Ship the pilot.\nAction: Prepare demo @maya 2026-03-25",
    )
    monkeypatch.setattr(
        "app.slack.services.source_resolver.create_source_record",
        lambda **kwargs: kwargs,
    )

    result = resolve_latest_huddle_notes_canvas("C123", None, "U123")

    assert result["raw_content"].startswith("Decision: Ship the pilot.")
    assert result["slack_canvas_id"] == "F-CANVAS"
    assert downloaded_urls == ["https://example.com/F-BEST.txt"]


def test_resolve_latest_huddle_notes_uses_transcript_when_canvas_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.slack.services.source_resolver.slack_client.list_files",
        lambda *_args, **_kwargs: [
            {
                "id": "F-TRANSCRIPT",
                "filetype": "text",
                "timestamp": 1710001005,
                "title": "Huddle transcript",
                "mimetype": "text/plain",
            }
        ],
    )
    monkeypatch.setattr(
        "app.slack.services.source_resolver.slack_client.get_file_content",
        lambda file_id: {
            "id": file_id,
            "title": "Huddle transcript",
            "filetype": "text",
            "mimetype": "text/plain",
            "preview": "Decision: Capture blockers.\nAction: Share notes.",
        },
    )
    monkeypatch.setattr(
        "app.slack.services.source_resolver.create_source_record",
        lambda **kwargs: kwargs,
    )

    result = resolve_latest_huddle_notes_canvas("C123", None, "U123")

    assert result["raw_content"].startswith("Decision: Capture blockers.")
    assert result["slack_canvas_id"] is None
