import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select
from starlette.requests import Request

from app.core import rate_limit as rate_limit_module
from app.core.config import settings
from app.core.db import engine
from app.core.rate_limit import (
    _consume,
    _rate_limit_identity,
    client_ip,
)
from app.models import RateLimitBucket


class _FrozenClock:
    current = datetime(2026, 8, 19, tzinfo=UTC)

    @classmethod
    def now(cls, tz: object = None) -> datetime:
        return cls.current


class _DatabaseFailure(Exception):
    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate


class _FailingSession:
    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate

    def __enter__(self) -> "_FailingSession":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, *_: object, **__: object) -> None:
        raise OperationalError(
            "rate-limit operation", {}, _DatabaseFailure(self.sqlstate)
        )


def _request(peer: str, headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [
                (name.lower().encode(), value.encode())
                for name, value in headers.items()
            ],
            "client": (peer, 12345),
            "server": ("testserver", 80),
        }
    )


def test_login_endpoint_rate_limited_after_many_attempts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FrozenClock.current = datetime(2026, 8, 19, tzinfo=UTC)
    monkeypatch.setattr(rate_limit_module, "datetime", _FrozenClock)
    url = f"{settings.API_V1_STR}/login/access-token"
    form = {"username": "nobody@example.com", "password": "wrong-password"}

    # First 20 attempts are allowed through to the (failing) credential check.
    for _ in range(20):
        response = client.post(url, data=form)
        assert response.status_code == 400

    # The 21st attempt within the same window is blocked by the limiter.
    response = client.post(
        url,
        data=form,
        headers={"Origin": settings.FRONTEND_HOST},
    )
    assert response.status_code == 429
    assert "请求过于频繁" in response.json()["detail"]
    assert 1 <= int(response.headers["Retry-After"]) <= 60
    assert response.headers["Access-Control-Expose-Headers"] == "Retry-After"

    _FrozenClock.current += timedelta(seconds=61)
    response = client.post(url, data=form)
    assert response.status_code == 400
    assert response.json()["detail"] == "邮箱或密码错误"


def test_login_missing_rate_limit_schema_fails_closed_before_authentication(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authenticate = Mock(return_value=None)
    monkeypatch.setattr("app.api.routes.login.crud.authenticate", authenticate)
    monkeypatch.setattr(
        rate_limit_module,
        "Session",
        lambda _: _FailingSession("42P01"),
    )

    response = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": "nobody@example.com", "password": "wrong-password"},
        headers={"Origin": settings.FRONTEND_HOST},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "请求保护服务尚未初始化，请联系管理员"
    assert response.headers["Retry-After"] == "30"
    assert response.headers["Access-Control-Expose-Headers"] == "Retry-After"
    authenticate.assert_not_called()


def test_login_recovers_on_next_request_after_rate_limit_database_recovers(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authenticate = Mock(return_value=None)
    real_session = Session
    monkeypatch.setattr("app.api.routes.login.crud.authenticate", authenticate)
    monkeypatch.setattr(
        rate_limit_module,
        "Session",
        lambda _: _FailingSession("08006"),
    )

    url = f"{settings.API_V1_STR}/login/access-token"
    form = {"username": "nobody@example.com", "password": "wrong-password"}
    unavailable = client.post(
        url,
        data=form,
        headers={"Origin": settings.FRONTEND_HOST},
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "请求保护服务暂时不可用，请稍后重试"
    assert unavailable.headers["Retry-After"] == "5"
    assert unavailable.headers["Access-Control-Expose-Headers"] == "Retry-After"
    authenticate.assert_not_called()

    monkeypatch.setattr(rate_limit_module, "Session", real_session)
    recovered = client.post(url, data=form)
    assert recovered.status_code == 400
    assert recovered.json()["detail"] == "邮箱或密码错误"
    authenticate.assert_called_once()


def test_spoofed_x_forwarded_for_shares_one_rate_limit_bucket(
    client: TestClient,
) -> None:
    """A client-supplied leftmost XFF hop must not mint a fresh bucket.

    Traefik/uvicorn expose the original-client slot as the leftmost hop, which
    any caller can set. The limiter keys on the rightmost hop — the address
    the nearest reverse proxy observed — so rotating X-Forwarded-For cannot
    bypass the login throttle.
    """
    url = f"{settings.API_V1_STR}/login/access-token"
    form = {"username": "nobody@example.com", "password": "wrong-password"}

    for index in range(20):
        response = client.post(
            url,
            data=form,
            headers={"X-Forwarded-For": f"203.0.113.{index}, 127.0.0.1"},
        )
        assert response.status_code == 400, response.text

    response = client.post(
        url,
        data=form,
        headers={"X-Forwarded-For": "198.51.100.1, 127.0.0.1"},
    )
    assert response.status_code == 429


def test_direct_client_cannot_spoof_forwarding_headers() -> None:
    request = _request(
        "198.51.100.20",
        {
            "X-Forwarded-For": "203.0.113.50",
            "CF-Connecting-IP": "203.0.113.51",
        },
    )
    assert client_ip(request) == "198.51.100.20"


def test_trusted_proxy_chain_discards_spoofed_leftmost_hop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", ["10.0.0.0/8", "192.0.2.0/24"])
    request = _request(
        "10.0.0.2",
        {"X-Forwarded-For": "203.0.113.99, 198.51.100.8, 192.0.2.5"},
    )
    assert client_ip(request) == "198.51.100.8"


def test_cloudflare_header_is_ignored_behind_trusted_public_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", ["10.0.0.0/8", "192.0.2.0/24"])
    request = _request(
        "10.0.0.2",
        {
            "CF-Connecting-IP": "203.0.113.25",
            "X-Forwarded-For": "203.0.113.99, 198.51.100.8, 192.0.2.5",
        },
    )
    assert client_ip(request) == "198.51.100.8"


def test_tunnel_converted_xff_is_resolved_behind_trusted_ingress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", ["172.16.0.0/12"])
    request = _request(
        "172.18.0.4",
        {
            "X-Forwarded-For": "203.0.113.25",
            "CF-Connecting-IP": "198.51.100.99",
        },
    )
    assert client_ip(request) == "203.0.113.25"


def test_ipv6_rate_limit_identity_groups_by_64_without_truncating_client_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", ["10.0.0.0/8"])
    first = "2001:db8:1:2::1234"
    second = "2001:db8:1:2:ffff::5678"
    different = "2001:db8:1:3::1234"

    request = _request("10.0.0.2", {"X-Forwarded-For": first})
    assert client_ip(request) == first
    assert _rate_limit_identity(first) == "2001:db8:1:2::/64"
    assert _rate_limit_identity(first) == _rate_limit_identity(second)
    assert _rate_limit_identity(first) != _rate_limit_identity(different)


def test_new_bucket_capacity_fails_closed_but_existing_bucket_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX_ACTIVE_BUCKETS", 2)

    assert _consume("capacity", "first", 60)[0] == 1
    assert _consume("capacity", "second", 60)[0] == 1
    with pytest.raises(HTTPException) as exc_info:
        _consume("capacity", "third", 60)
    assert exc_info.value.status_code == 503
    assert "容量已满" in str(exc_info.value.detail)
    assert exc_info.value.headers == {"Retry-After": "60"}
    assert _consume("capacity", "first", 60)[0] == 2


def test_new_bucket_capacity_is_atomic_across_concurrent_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX_ACTIVE_BUCKETS", 1)
    barrier = threading.Barrier(2)

    def consume(value: str) -> int:
        barrier.wait()
        try:
            return _consume("concurrent-capacity", value, 60)[0]
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(consume, ["first", "second"]))

    assert sorted(results) == [1, 503]
    with Session(engine) as session:
        count = session.exec(select(func.count()).select_from(RateLimitBucket)).one()
    assert count == 1


def test_same_bucket_count_is_atomic_across_concurrent_workers() -> None:
    worker_count = 8
    barrier = threading.Barrier(worker_count)

    def consume(_: int) -> int:
        barrier.wait()
        return _consume("concurrent-same-bucket", "shared-client", 60)[0]

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(consume, range(worker_count)))

    assert sorted(results) == list(range(1, worker_count + 1))
