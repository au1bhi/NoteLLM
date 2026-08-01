import ipaddress
import socket
from socket import AddressFamily, SocketKind
from urllib.parse import urlparse

from fastapi import HTTPException

type _AddrInfo = tuple[
    AddressFamily,
    SocketKind,
    int,
    str,
    tuple[str, int] | tuple[str, int, int, int] | tuple[int, bytes],
]

_ALWAYS_BLOCKED = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "metadata.google.internal",
}


def _is_blocked_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_reserved,
            address.is_multicast,
            address.is_unspecified,
        )
    )


def _resolve(host: str) -> list[_AddrInfo]:
    """Resolve a hostname to its socket addresses (injectable in tests)."""
    return socket.getaddrinfo(host, None)


def _is_private_or_local(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    if not lowered:
        return True
    if lowered in _ALWAYS_BLOCKED or lowered.endswith(".local"):
        return True
    try:
        addresses = _resolve(lowered)
    except socket.gaierror:
        # Unresolvable hostname — reject rather than allow a later DNS
        # resolution (or rebinding) to a private or metadata address.
        return True
    return any(
        isinstance(sockaddr[0], str)
        and _is_blocked_address(ipaddress.ip_address(sockaddr[0]))
        for *_, sockaddr in addresses
    )


def validate_outbound_url(base_url: str) -> str:
    """Validate a user-supplied provider base URL and return it trimmed of a
    trailing slash. Blocks non-http(s) schemes and any host whose DNS resolves
    (including non-canonical decimal/hex/shorthand numeric forms) to a private,
    loopback, link-local, reserved, multicast, or unspecified address, so the
    server cannot be pointed at internal services or cloud metadata."""
    value = base_url.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail="base_url 必须是 http(s) URL")
    if _is_private_or_local(parsed.hostname):
        raise HTTPException(
            status_code=422,
            detail="base_url 必须指向公网地址",
        )
    return value.rstrip("/")
