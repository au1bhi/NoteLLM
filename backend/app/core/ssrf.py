import ipaddress
import socket
from socket import AddressFamily, SocketKind
from typing import Any

import httpx
from fastapi import HTTPException
from httpx import URL

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

_BLOCKED_DETAIL = "base_url 必须指向公网地址"


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
            # RFC 6598 carrier-grade NAT space (100.64.0.0/10, e.g. Tailscale).
            # `is_reserved` does not cover it on older Python versions.
            (
                isinstance(address, ipaddress.IPv4Address)
                and address >= ipaddress.IPv4Address("100.64.0.0")
                and address <= ipaddress.IPv4Address("100.127.255.255")
            ),
        )
    )


def _resolve(host: str) -> list[_AddrInfo]:
    """Resolve a hostname to its socket addresses (injectable in tests)."""
    return socket.getaddrinfo(host, None)


def _parse_base_url(base_url: str) -> URL:
    try:
        parsed = httpx.URL(base_url.strip())
    except httpx.InvalidURL as error:
        raise HTTPException(status_code=422, detail=_BLOCKED_DETAIL) from error
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise HTTPException(
            status_code=422, detail="base_url 必须是 http(s) URL"
        )
    return parsed


def resolve_public_ip(url: URL) -> str:
    """Return a validated public IP for the URL's host.

    Resolves the hostname *now* and rejects it if any address is private,
    loopback, link-local, reserved, CGNAT, multicast, or unspecified. The
    caller pins the connection to the returned IP, so a later re-resolution
    (DNS rebinding) cannot silently redirect the request to an internal
    service or cloud metadata endpoint.
    """
    host = url.host.lower().rstrip(".")
    if not host or host in _ALWAYS_BLOCKED or host.endswith(".local"):
        raise HTTPException(status_code=422, detail=_BLOCKED_DETAIL)
    try:
        addresses = _resolve(host)
    except socket.gaierror:
        raise HTTPException(status_code=422, detail=_BLOCKED_DETAIL) from None
    candidates: list[str] = []
    for *_, sockaddr in addresses:
        ip = sockaddr[0] if isinstance(sockaddr[0], str) else None
        if not ip:
            continue
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if _is_blocked_address(address):
            raise HTTPException(status_code=422, detail=_BLOCKED_DETAIL)
        if ip not in candidates:
            candidates.append(ip)
    if not candidates:
        raise HTTPException(status_code=422, detail=_BLOCKED_DETAIL)
    return candidates[0]


def validate_outbound_url(base_url: str) -> str:
    """Validate a user-supplied provider base URL and return it trimmed of a
    trailing slash. Blocks non-http(s) schemes and any host whose DNS resolves
    (including non-canonical decimal/hex/shorthand numeric forms) to a private,
    loopback, link-local, reserved, CGNAT, multicast, or unspecified address, so
    the server cannot be pointed at internal services or cloud metadata."""
    value = base_url.strip()
    resolve_public_ip(_parse_base_url(value))
    return value.rstrip("/")


def pinned_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Issue an outbound HTTP request that cannot be redirected to an internal
    service by DNS rebinding.

    Validates and resolves the host at request time, then connects to the
    validated public IP directly while preserving the original hostname in the
    ``Host`` header and (for HTTPS) as the TLS SNI / certificate-verification
    name. `trust_env` is forced off so proxy environment variables never apply.
    """
    parsed = _parse_base_url(url)
    ip = resolve_public_ip(parsed)
    display_host = f"[{ip}]" if ":" in ip else ip
    pinned = parsed.copy_with(host=display_host)
    netloc = parsed.netloc
    host_header = netloc.decode() if isinstance(netloc, bytes) else str(netloc)
    merged = dict(headers or {})
    merged.setdefault("Host", host_header)
    # trust_env is pinned off at the Client level so proxy environment
    # variables never route (or leak) the request.
    kwargs.pop("trust_env", None)
    with httpx.Client(trust_env=False) as client:
        return client.request(
            method,
            str(pinned),
            headers=merged,
            extensions={"sni_hostname": parsed.host},
            **kwargs,
        )
