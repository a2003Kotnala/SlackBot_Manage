from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings
from app.domain.providers.base import MeetingProviderAdapter, ProviderAuthContext
from app.domain.schemas.ingestion import (
    ProviderFetchResult,
    ProviderMetadata,
    ProviderReference,
    ProviderType,
    TranscriptDocument,
)
from app.domain.services.url_validation import UnsafeUrlError, validate_https_url

ZOOM_ALLOWED_HOSTS = ("zoom.us", "zoom.com", "zoomgov.com")
TRANSCRIPT_URL_PATTERN = re.compile(
    r"""(?P<url>https://[^"' ]+\.(?:txt|vtt|srt)(?:\?[^"' ]*)?)""",
    re.IGNORECASE,
)
MEDIA_URL_PATTERN = re.compile(
    r"""(?P<url>https://[^"' ]+\.(?:mp4|m4a|mp3|wav|webm)(?:\?[^"' ]*)?)""",
    re.IGNORECASE,
)
TITLE_PATTERN = re.compile(r"<title>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL)


class ZoomMeetingProvider(MeetingProviderAdapter):
    provider_name = ProviderType.zoom.value

    def can_handle(self, url: str) -> bool:
        try:
            validate_https_url(url, ZOOM_ALLOWED_HOSTS)
        except UnsafeUrlError:
            return False
        return True

    def normalize_reference(self, url: str) -> ProviderReference:
        normalized_url = validate_https_url(url, ZOOM_ALLOWED_HOSTS)
        return self.parse_reference(normalized_url)

    def parse_reference(self, url: str) -> ProviderReference:
        normalized_url = validate_https_url(url, ZOOM_ALLOWED_HOSTS)
        parsed = urlparse(normalized_url)
        path_bits = [bit for bit in parsed.path.split("/") if bit]
        external_id = path_bits[-1] if path_bits else None
        return ProviderReference(
            provider_type=ProviderType.zoom,
            original_url=url,
            normalized_url=normalized_url,
            external_id=external_id,
        )

    def is_accessible(
        self,
        reference: ProviderReference,
        auth_context: ProviderAuthContext,
    ) -> bool:
        response = self._request(reference.normalized_url)
        return response.status_code < 400

    def fetch_metadata(
        self,
        reference: ProviderReference,
        auth_context: ProviderAuthContext,
    ) -> ProviderFetchResult:
        response = self._request(reference.normalized_url)
        title = _extract_html_title(response.text)
        return ProviderFetchResult(
            metadata=ProviderMetadata(
                title=title,
                final_url=str(response.url),
                accessible=response.status_code < 400,
                metadata={"status_code": response.status_code},
            )
        )

    def fetch_transcript(
        self,
        reference: ProviderReference,
        auth_context: ProviderAuthContext,
    ) -> ProviderFetchResult:
        response = self._request(reference.normalized_url)
        transcript_url = self._select_candidate_url(
            response.text,
            response.url,
            TRANSCRIPT_URL_PATTERN,
        )
        transcript = None
        if transcript_url:
            transcript_response = self._request(transcript_url)
            transcript = TranscriptDocument(
                text=transcript_response.text.strip(),
                source_kind="provider-transcript",
                provenance=transcript_url,
            )

        return ProviderFetchResult(
            metadata=ProviderMetadata(
                title=_extract_html_title(response.text),
                final_url=str(response.url),
                accessible=response.status_code < 400,
                metadata={"status_code": response.status_code},
            ),
            transcript=transcript,
        )

    def fetch_media(
        self,
        reference: ProviderReference,
        auth_context: ProviderAuthContext,
    ) -> ProviderFetchResult:
        response = self._request(reference.normalized_url)
        media_url = self._select_candidate_url(
            response.text,
            response.url,
            MEDIA_URL_PATTERN,
        )
        filename = None
        mimetype = None
        if media_url:
            parsed = urlparse(media_url)
            filename = parsed.path.rsplit("/", 1)[-1] or "recording"
            mimetype = _guess_mimetype(filename)

        return ProviderFetchResult(
            metadata=ProviderMetadata(
                title=_extract_html_title(response.text),
                final_url=str(response.url),
                accessible=response.status_code < 400,
                metadata={"status_code": response.status_code},
            ),
            media_download_url=media_url,
            media_filename=filename,
            media_mimetype=mimetype,
        )

    def _request(self, url: str) -> httpx.Response:
        with httpx.Client(
            follow_redirects=True,
            timeout=settings.followthru_download_timeout_seconds,
        ) as client:
            response = client.get(
                url,
                headers={"User-Agent": "FollowThru/1.0"},
            )
        response.raise_for_status()
        validate_https_url(str(response.url), ZOOM_ALLOWED_HOSTS)
        return response

    def _select_candidate_url(
        self,
        page_text: str,
        page_url: httpx.URL,
        pattern: re.Pattern[str],
    ) -> str | None:
        for match in pattern.finditer(unescape(page_text)):
            candidate = match.group("url")
            try:
                return validate_https_url(candidate, ZOOM_ALLOWED_HOSTS)
            except UnsafeUrlError:
                continue

        for quoted_url in re.findall(r'"(\/[^"]+\.(?:txt|vtt|srt|mp4|m4a|mp3|wav|webm)[^"]*)"', page_text, re.IGNORECASE):
            candidate = urljoin(str(page_url), quoted_url)
            try:
                return validate_https_url(candidate, ZOOM_ALLOWED_HOSTS)
            except UnsafeUrlError:
                continue
        return None


def _extract_html_title(page_text: str) -> str | None:
    match = TITLE_PATTERN.search(page_text)
    if not match:
        return None
    return unescape(re.sub(r"\s+", " ", match.group("title"))).strip() or None


def _guess_mimetype(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".mp4"):
        return "video/mp4"
    if lowered.endswith(".webm"):
        return "video/webm"
    if lowered.endswith(".wav"):
        return "audio/wav"
    if lowered.endswith(".mp3"):
        return "audio/mpeg"
    return "audio/mp4"
