import ipaddress
from urllib.parse import urlparse

from fastapi import HTTPException

_ALWAYS_BLOCKED = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "metadata.google.internal",
}


def _is_private_or_local(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    if lowered in _ALWAYS_BLOCKED or lowered.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        # A hostname we cannot resolve here; allow it (DNS-rebinding is out of
        # scope for this app) but still block literal IPs below.
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )


def validate_outbound_url(base_url: str) -> str:
    """Validate a user-supplied provider base URL and return it trimmed of a
    trailing slash. Blocks non-http(s) schemes and private/link-local hosts so
    the server cannot be pointed at internal services or cloud metadata."""
    value = base_url.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(
            status_code=422, detail="base_url must be an http(s) URL"
        )
    if _is_private_or_local(parsed.hostname):
        raise HTTPException(
            status_code=422,
            detail="base_url must point to a public endpoint",
        )
    return value.rstrip("/")
