from __future__ import annotations

from app.domain.providers.base import MeetingProviderAdapter
from app.domain.providers.zoom import ZoomMeetingProvider

PROVIDER_ADAPTERS: tuple[MeetingProviderAdapter, ...] = (ZoomMeetingProvider(),)


def resolve_provider_adapter(url: str) -> MeetingProviderAdapter | None:
    for adapter in PROVIDER_ADAPTERS:
        if adapter.can_handle(url):
            return adapter
    return None
