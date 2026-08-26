import socket
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from app.core import ssrf as ssrf_mod
from app.core.ssrf import (
    _pinned_request_args,
    pinned_request,
    pinned_stream,
    provider_request,
    provider_stream,
    resolve_public_ip,
    trusted_provider_request,
    trusted_provider_stream,
    validate_outbound_url,
)


def _assert_blocked(url: str) -> None:
    with pytest.raises(HTTPException) as exc:
        validate_outbound_url(url)
    assert exc.value.status_code == 422


def test_blocks_canonical_private_hosts() -> None:
    for url in (
        "http://127.0.0.1",
        "http://localhost",
        "http://[::1]",
        "http://169.254.169.254",
        "http://0.0.0.0",
        "http://metadata.google.internal",
        "http://10.0.0.5",
        "http://192.168.1.1",
    ):
        _assert_blocked(url)


def test_blocks_numeric_bypass_forms() -> None:
    # Each of these resolves to loopback or the cloud metadata address.
    for url in (
        "http://2130706433",
        "http://0xa9fea9fe",
        "http://017700000001",
        "http://127.1",
        "http://127.0.1",
        "http://0x7f.0.0.1",
        "http://localhost.localdomain",
    ):
        _assert_blocked(url)


def test_blocks_unresolvable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_host: str) -> list[tuple]:
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr("app.core.ssrf._resolve", fail)
    _assert_blocked("http://no-such-host.invalid")


def test_rejects_non_http_scheme() -> None:
    _assert_blocked("ftp://example.com")
    _assert_blocked("file:///etc/passwd")


def test_allows_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_resolve(_host: str) -> list[tuple]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
        ]

    monkeypatch.setattr("app.core.ssrf._resolve", fake_resolve)
    assert (
        validate_outbound_url("https://api.example.com/v1")
        == "https://api.example.com/v1"
    )


def test_blocks_ipv4_mapped_ipv6_private_forms() -> None:
    """IPv4-mapped IPv6 forms of private/CGNAT/loopback addresses must be
    blocked just like their plain IPv4 equivalents (a mapped-IPv6 address was
    previously classified as a plain IPv6Address, skipping the CGNAT check)."""
    from app.core.ssrf import validate_outbound_url

    for bad in (
        "http://[::ffff:100.64.0.1]:8080/v1",  # CGNAT / Tailscale
        "http://[::ffff:100.127.255.255]:80/",
        "http://[::ffff:127.0.0.1]:8000/",  # loopback
        "http://[::ffff:10.0.0.1]:8000/",  # RFC1918
        "http://[::ffff:169.254.169.254]:80/",  # link-local/metadata
    ):
        try:
            validate_outbound_url(bad)
        except Exception:
            continue
        raise AssertionError(f"{bad} was not blocked")

    # A genuinely public IPv4-mapped address still passes.
    assert validate_outbound_url("http://[::ffff:1.1.1.1]:8080/v1") == (
        "http://[::ffff:1.1.1.1]:8080/v1"
    )


# --- Resolution robustness ------------------------------------------------


def test_rejects_urls_with_control_characters() -> None:
    """Unparseable URLs map to the same 422 as other rejections."""
    _assert_blocked("http://a\nb.com")
    _assert_blocked("http://exa\tmple.com")


def test_blocks_local_suffix_without_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_host: str) -> list[tuple]:
        raise AssertionError(".local hosts must be rejected before DNS")

    monkeypatch.setattr("app.core.ssrf._resolve", fail)
    _assert_blocked("http://printer.local")
    _assert_blocked("http://")


def test_skips_unusable_dns_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-string or non-IP addresses are ignored while a usable public
    address still validates."""

    def dirty(_host: str) -> list[tuple]:
        return [
            (socket.AF_UNIX, socket.SOCK_STREAM, 0, "", (None,)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("teapot", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("9.9.9.9", 0)),
        ]

    monkeypatch.setattr("app.core.ssrf._resolve", dirty)
    assert (
        resolve_public_ip(httpx.URL("https://api.example.com")) == "9.9.9.9"
    )


def test_blocks_when_resolution_yields_no_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.ssrf._resolve", lambda _host: [])
    _assert_blocked("https://api.example.com")

    def garbage(_host: str) -> list[tuple]:
        return [(socket.AF_UNIX, socket.SOCK_STREAM, 0, "", (None,))]

    monkeypatch.setattr("app.core.ssrf._resolve", garbage)
    _assert_blocked("https://api.example.com")


# --- Request argument construction ----------------------------------------


def test_pinned_args_rewrite_host_and_inject_host_header() -> None:
    parsed = httpx.URL("https://api.example.com/v1")
    pinned, headers = _pinned_request_args(
        parsed, "203.0.113.10", {"Authorization": "Bearer sk"}
    )
    assert str(pinned) == "https://203.0.113.10/v1"
    # netloc arrives as bytes; must be decoded for the Host header.
    assert headers["Host"] == "api.example.com"
    assert headers["Authorization"] == "Bearer sk"


def test_pinned_args_bracket_ipv6_and_honour_caller_host() -> None:
    parsed = httpx.URL("https://[2001:db8::20]/v1")
    pinned, headers = _pinned_request_args(parsed, "2001:db8::20", {"Host": "orig"})
    assert str(pinned) == "https://[2001:db8::20]/v1"
    assert headers["Host"] == "orig"


# --- Transport helpers (offline, via fake httpx.Client) --------------------


class _FakeResponse:
    def __init__(self) -> None:
        self.read_calls = 0

    def read(self) -> None:
        self.read_calls += 1


def _fake_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace app-level httpx.Client; record ctor/stream args, yield marker."""
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        @contextmanager
        def stream(self, method: str, url: str, **kwargs: Any):
            captured["method"] = method
            captured["url"] = url
            captured["request"] = kwargs
            yield _FakeResponse()

    monkeypatch.setattr(ssrf_mod.httpx, "Client", FakeClient)
    return captured


def test_pinned_stream_pins_ip_sends_original_sni_and_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def public(_host: str) -> list[tuple]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("9.9.9.9", 0))]

    monkeypatch.setattr("app.core.ssrf._resolve", public)
    captured = _fake_client(monkeypatch)
    with pinned_stream(
        "POST",
        "https://api.example.com/v1/chat",
        headers={"X-Trace": "t"},
        json={},
        timeout=30.0,
        trust_env=True,  # caller-supplied env trust must be dropped
    ) as response:
        assert isinstance(response, _FakeResponse)
    assert captured["client"] == {"trust_env": False}
    assert captured["method"] == "POST"
    assert captured["url"] == "https://9.9.9.9/v1/chat"
    assert captured["request"]["extensions"] == {"sni_hostname": "api.example.com"}
    assert captured["request"]["headers"]["Host"] == "api.example.com"
    assert captured["request"]["headers"]["X-Trace"] == "t"
    assert "trust_env" not in captured["request"]


def test_trusted_stream_rides_proxy_without_local_pinning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _fake_client(monkeypatch)
    with trusted_provider_stream(
        "GET",
        "https://models.example/v1/models",
        proxy_url="http://192.0.2.1:7890",
        headers=None,
    ) as response:
        assert isinstance(response, _FakeResponse)
    assert captured["client"] == {"proxy": "http://192.0.2.1:7890", "trust_env": False}
    # Original hostname stays in the URL — the operator proxy resolves it.
    assert captured["url"] == "https://models.example/v1/models"


def test_blocking_requests_read_the_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner: dict[str, Any] = {}

    @contextmanager
    def fake_stream(method: str, url: str, **_kwargs: Any):
        inner["called_with"] = (method, url)
        yield _FakeResponse()

    monkeypatch.setattr(ssrf_mod, "pinned_stream", fake_stream)
    response = pinned_request("GET", "https://api.example.com", timeout=5)
    assert isinstance(response, _FakeResponse)
    assert response.read_calls == 1
    assert inner["called_with"][0] == "GET"

    @contextmanager
    def fake_trusted_stream(
        _method: str, _url: str, *, proxy_url: str, **_kwargs: Any
    ):
        inner["trusted_proxy"] = proxy_url
        yield _FakeResponse()

    monkeypatch.setattr(ssrf_mod, "trusted_provider_stream", fake_trusted_stream)
    response = trusted_provider_request(
        "GET", "https://models.example", proxy_url="http://192.0.2.1:7890"
    )
    assert response.read_calls == 1
    assert inner["trusted_proxy"] == "http://192.0.2.1:7890"


# --- Dispatchers ------------------------------------------------------------


def test_provider_dispatch_selects_transport_by_proxy(monkeypatch) -> None:
    calls: list[str] = []

    def pick(label: str, result: str):
        def _pick(*_a: object, **_k: object) -> str:
            calls.append(label)
            return result

        return _pick

    monkeypatch.setattr(
        ssrf_mod,
        "trusted_provider_stream",
        pick("trusted-stream", "ctx-trusted"),
    )
    monkeypatch.setattr(
        ssrf_mod, "pinned_stream", pick("pinned-stream", "ctx-pinned")
    )
    assert (
        provider_stream(
            "GET", "u", proxy_url="http://p", headers={"h": "1"}
        )
        == "ctx-trusted"
    )
    assert provider_stream("GET", "u", proxy_url=None) == "ctx-pinned"
    assert provider_stream("GET", "u", proxy_url="") == "ctx-pinned"

    monkeypatch.setattr(
        ssrf_mod,
        "trusted_provider_request",
        pick("trusted-request", "resp-trusted"),
    )
    monkeypatch.setattr(
        ssrf_mod, "pinned_request", pick("pinned-request", "resp-pinned")
    )
    assert provider_request("GET", "u", proxy_url="http://p") == "resp-trusted"
    assert provider_request("GET", "u", proxy_url=None) == "resp-pinned"
    assert calls == [
        "trusted-stream",
        "pinned-stream",
        "pinned-stream",
        "trusted-request",
        "pinned-request",
    ]
