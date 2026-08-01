import socket

import pytest
from fastapi import HTTPException

from app.core.ssrf import validate_outbound_url


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
