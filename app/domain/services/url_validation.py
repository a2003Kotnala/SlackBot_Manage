from __future__ import annotations

import ipaddress
from urllib.parse import urlparse, urlunparse


class UnsafeUrlError(ValueError):
    pass


def validate_https_url(url: str, allowed_hosts: tuple[str, ...]) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() != "https":
        raise UnsafeUrlError("Only https recording links are supported.")
    if not parsed.netloc:
        raise UnsafeUrlError("Recording link is missing a hostname.")
    if parsed.username or parsed.password:
        raise UnsafeUrlError(
            "Recording links with embedded credentials are not allowed."
        )

    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        raise UnsafeUrlError("Recording link is missing a valid hostname.")
    if _is_blocked_host(hostname):
        raise UnsafeUrlError("Recording link host is not allowed.")
    if not any(
        hostname == host or hostname.endswith(f".{host}") for host in allowed_hosts
    ):
        raise UnsafeUrlError("Recording provider is not supported.")

    normalized = parsed._replace(fragment="")
    return urlunparse(normalized)


def _is_blocked_host(hostname: str) -> bool:
    if hostname in {"localhost", "localhost.localdomain"}:
        return True

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False

    return any(
        [
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        ]
    )
