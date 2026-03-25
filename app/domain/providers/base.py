from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.schemas.ingestion import (
    ProviderFetchResult,
    ProviderReference,
)


@dataclass(frozen=True)
class ProviderAuthContext:
    slack_user_id: str | None = None
    workspace_id: str | None = None


class MeetingProviderAdapter(Protocol):
    provider_name: str

    def can_handle(self, url: str) -> bool:
        ...

    def normalize_reference(self, url: str) -> ProviderReference:
        ...

    def parse_reference(self, url: str) -> ProviderReference:
        ...

    def is_accessible(
        self,
        reference: ProviderReference,
        auth_context: ProviderAuthContext,
    ) -> bool:
        ...

    def fetch_metadata(
        self,
        reference: ProviderReference,
        auth_context: ProviderAuthContext,
    ) -> ProviderFetchResult:
        ...

    def fetch_transcript(
        self,
        reference: ProviderReference,
        auth_context: ProviderAuthContext,
    ) -> ProviderFetchResult:
        ...

    def fetch_media(
        self,
        reference: ProviderReference,
        auth_context: ProviderAuthContext,
    ) -> ProviderFetchResult:
        ...
