from types import SimpleNamespace

from app.domain.providers.zoom import ZoomMeetingProvider
from app.domain.schemas.ingestion import ProviderType


def test_zoom_provider_normalizes_and_parses_reference():
    provider = ZoomMeetingProvider()

    reference = provider.normalize_reference(
        "https://acme.zoom.us/rec/share/demo?pwd=123#fragment"
    )

    assert reference.provider_type == ProviderType.zoom
    assert reference.normalized_url == "https://acme.zoom.us/rec/share/demo?pwd=123"
    assert reference.external_id == "demo"


def test_zoom_provider_blocks_unsupported_hosts():
    provider = ZoomMeetingProvider()

    assert provider.can_handle("https://acme.zoom.us/rec/share/demo") is True
    assert provider.can_handle("https://example.com/rec/share/demo") is False


def test_zoom_provider_fetch_transcript_uses_safe_candidate(monkeypatch):
    provider = ZoomMeetingProvider()
    reference = provider.normalize_reference("https://acme.zoom.us/rec/share/demo")

    responses = {
        reference.normalized_url: SimpleNamespace(
            status_code=200,
            text=(
                "<html><title>Demo Call</title>"
                ' <a href="https://acme.zoom.us/recording/demo.vtt">Transcript</a>'
                "</html>"
            ),
            url=reference.normalized_url,
        ),
        "https://acme.zoom.us/recording/demo.vtt": SimpleNamespace(
            status_code=200,
            text="Speaker 1: Decision: Ship the pilot.",
            url="https://acme.zoom.us/recording/demo.vtt",
        ),
    }

    monkeypatch.setattr(
        provider,
        "_request",
        lambda url: responses[url],
    )

    result = provider.fetch_transcript(reference, auth_context=SimpleNamespace())

    assert result.metadata.title == "Demo Call"
    assert result.transcript is not None
    assert "Ship the pilot" in result.transcript.text
