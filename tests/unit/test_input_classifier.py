from app.domain.schemas.followthru import FollowThruMode
from app.domain.schemas.ingestion import (
    IngestionSourceType,
    ProviderType,
    SlackFileReference,
)
from app.domain.services.input_classifier import classify_slack_input


def test_classify_transcript_text_defaults_to_publish():
    result = classify_slack_input(
        "Decision: Ship the pilot. Action: Prepare demo @maya"
    )

    assert result.requested_mode == FollowThruMode.publish
    assert result.source_type == IngestionSourceType.transcript_text
    assert result.provider_type == ProviderType.none
    assert result.transcript_text.startswith("Decision: Ship the pilot")


def test_classify_transcript_file_prefers_supported_upload():
    result = classify_slack_input(
        "",
        files=[
            SlackFileReference(
                name="transcript.vtt",
                mimetype="text/vtt",
                filetype="vtt",
                url_private_download="https://files.slack.com/transcript.vtt",
            )
        ],
    )

    assert result.source_type == IngestionSourceType.transcript_file
    assert result.slack_files[0].name == "transcript.vtt"


def test_classify_zoom_link_detects_provider():
    result = classify_slack_input("preview https://acme.zoom.us/rec/share/demo")

    assert result.requested_mode == FollowThruMode.preview
    assert result.source_type == IngestionSourceType.recording_link
    assert result.provider_type == ProviderType.zoom
    assert result.recording_url == "https://acme.zoom.us/rec/share/demo"


def test_classify_unsupported_link_fails_safely():
    result = classify_slack_input("https://example.com/recording/demo")

    assert result.source_type == IngestionSourceType.unsupported
    assert "not supported yet" in result.rejection_reason
