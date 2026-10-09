import ipaddress
import socket
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from socket import AddressFamily, SocketKind
from typing import Any

import httpx
from fastapi import HTTPException
from httpx import URL

from app.core.config import settings

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
    # IPv4-mapped IPv6 (::ffff:a.b.c.d) must be classified as its embedded IPv4,
    # otherwise the CGNAT (100.64.0.0/10) check — which is IPv4Address-only —
    # and other IPv4-range rules are silently skipped. Verified bypass:
    # 'http://[::ffff:100.64.0.1]' passed validation while 'http://100.64.0.1'
    # was correctly blocked.
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
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
        raise HTTPException(status_code=422, detail="base_url 必须是 http(s) URL")
    if parsed.userinfo or parsed.query or parsed.fragment:
        raise HTTPException(
            status_code=422, detail="base_url 不能包含用户名、密码、查询参数或片段"
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
    parsed = _parse_base_url(base_url)
    if parsed.scheme != "https" or parsed.port not in {None, 443}:
        raise HTTPException(
            status_code=422, detail="自定义 base_url 必须使用 HTTPS 443 端口"
        )
    allowed = settings.BYOK_ALLOWED_HOSTS
    if isinstance(allowed, str):
        allowed = [host.strip() for host in allowed.split(",") if host.strip()]
    if allowed and parsed.host.lower().rstrip(".") not in {
        host.lower().rstrip(".") for host in allowed
    }:
        raise HTTPException(
            status_code=422, detail="该模型服务域名不在管理员允许列表中"
        )
    resolve_public_ip(parsed)
    return str(parsed).rstrip("/")


def _pinned_request_args(
    parsed: URL, ip: str, headers: dict[str, str] | None
) -> tuple[URL, dict[str, str]]:
    display_host = f"[{ip}]" if ":" in ip else ip
    pinned = parsed.copy_with(host=display_host)
    netloc = parsed.netloc
    host_header = netloc.decode() if isinstance(netloc, bytes) else str(netloc)
    merged = dict(headers or {})
    merged.setdefault("Host", host_header)
    return pinned, merged


@contextmanager
def pinned_stream(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> Iterator[httpx.Response]:
    """Open an outbound HTTP request whose body can be consumed incrementally.

    Same validation and IP-pinning guarantees as :func:`pinned_request`; the
    caller consumes the response inside the context so streaming SSE bodies
    work without buffering.
    """
    parsed = _parse_base_url(url)
    ip = resolve_public_ip(parsed)
    pinned, merged = _pinned_request_args(parsed, ip, headers)
    kwargs.pop("trust_env", None)
    kwargs["follow_redirects"] = False
    with httpx.Client(trust_env=False) as client:
        with client.stream(
            method,
            str(pinned),
            headers=merged,
            extensions={"sni_hostname": parsed.host},
            **kwargs,
        ) as response:
            yield response


@contextmanager
def trusted_provider_stream(
    method: str,
    url: str,
    *,
    proxy_url: str,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> Iterator[httpx.Response]:
    """Streaming counterpart of :func:`trusted_provider_request` (operator
    proxy; no local pinning — see that function for the rationale)."""
    parsed = _parse_base_url(url)
    kwargs.pop("trust_env", None)
    kwargs["follow_redirects"] = False
    with httpx.Client(proxy=proxy_url, trust_env=False) as client:
        with client.stream(method, str(parsed), headers=headers, **kwargs) as response:
            yield response


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
    with pinned_stream(method, url, headers=headers, **kwargs) as response:
        response.read()
        return response


def trusted_provider_request(
    method: str,
    url: str,
    *,
    proxy_url: str,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Call an operator-configured provider through an operator proxy.

    This deliberately does not resolve/pin ``url`` locally: Fake-IP proxy
    modes return reserved addresses such as ``198.18.0.0/15`` to the client,
    while the proxy resolves the real public destination itself. It is only
    used for server environment configuration, never for a user's BYOK URL,
    which continues to use :func:`pinned_request`.
    """
    with trusted_provider_stream(
        method, url, proxy_url=proxy_url, headers=headers, **kwargs
    ) as response:
        response.read()
        return response


def provider_stream(
    method: str,
    url: str,
    *,
    proxy_url: str | None,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> AbstractContextManager[httpx.Response]:
    """Pick the right streaming transport for a provider config.

    Operator proxies get :func:`trusted_provider_stream`; everything else is
    DNS-validated and IP-pinned via :func:`pinned_stream`. Single dispatch
    point so call sites never re-implement the choice.
    """
    if proxy_url:
        return trusted_provider_stream(
            method, url, proxy_url=proxy_url, headers=headers, **kwargs
        )
    return pinned_stream(method, url, headers=headers, **kwargs)


def provider_request(
    method: str,
    url: str,
    *,
    proxy_url: str | None,
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Blocking counterpart of :func:`provider_stream`."""
    if proxy_url:
        return trusted_provider_request(
            method, url, proxy_url=proxy_url, headers=headers, **kwargs
        )
    return pinned_request(method, url, headers=headers, **kwargs)
