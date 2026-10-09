from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.turnstile import _verify_response
from app.main import app


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TURNSTILE_SITE_KEY", "test-site")
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(settings, "TURNSTILE_HOSTNAMES", ["notellm.au1bhi.com"])


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/login/access-token", {"username": "nobody@example.com", "password": "bad"}),
        ("/users/signup", {"email": "new@example.com", "password": "password123"}),
        ("/password-recovery/nobody@example.com", None),
    ],
)
def test_protected_auth_endpoints_require_turnstile_header(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    _enable(monkeypatch)
    url = f"{settings.API_V1_STR}{path}"
    response = (
        client.post(url, data=payload)
        if path == "/login/access-token"
        else client.post(url, json=payload)
    )
    assert response.status_code == 400
    assert "人机验证失败" in response.json()["detail"]


def test_valid_turnstile_token_reaches_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    verify = Mock(return_value=True)
    monkeypatch.setattr("app.core.turnstile._verify_response", verify)
    response = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": "nobody@example.com", "password": "bad"},
        headers={"X-Turnstile-Token": "valid-token"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "邮箱或密码错误"
    verify.assert_called_once()


def test_turnstile_provider_failure_is_fail_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr("app.core.turnstile._verify_response", lambda *_: False)
    response = client.post(
        f"{settings.API_V1_STR}/password-recovery/nobody@example.com",
        headers={"X-Turnstile-Token": "rejected-token"},
    )
    assert response.status_code == 400
    assert "人机验证失败" in response.json()["detail"]


def test_turnstile_network_failure_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = Mock()
    inner.post.side_effect = httpx.ConnectError("network unavailable")
    context = Mock()
    context.__enter__ = Mock(return_value=inner)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("app.core.turnstile.httpx.Client", Mock(return_value=context))
    with pytest.raises(HTTPException) as captured:
        _verify_response("token", "203.0.113.10", "login")
    assert captured.value.status_code == 503


def test_overlong_token_is_rejected_without_provider_call(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    verify = Mock(return_value=True)
    monkeypatch.setattr("app.core.turnstile._verify_response", verify)
    response = client.post(
        f"{settings.API_V1_STR}/password-recovery/nobody@example.com",
        headers={"X-Turnstile-Token": "x" * 2049},
    )
    assert response.status_code == 400
    verify.assert_not_called()


def test_turnstile_keys_must_be_configured_together() -> None:
    common = {
        "PROJECT_NAME": "NoteLLM",
        "SECRET_KEY": "x" * 32,
        "POSTGRES_SERVER": "localhost",
        "POSTGRES_USER": "postgres",
        "FIRST_SUPERUSER": "admin@example.com",
        "FIRST_SUPERUSER_PASSWORD": "strong-password",
        "TURNSTILE_SITE_KEY": "site-only",
        "TURNSTILE_SECRET_KEY": None,
    }
    with pytest.raises(ValidationError, match="must be configured together"):
        Settings(_env_file=None, **common)  # type: ignore[call-arg]


def test_openapi_documents_turnstile_header_on_all_protected_routes() -> None:
    schema = app.openapi()
    for path in (
        "/api/v1/login/access-token",
        "/api/v1/users/signup",
        "/api/v1/password-recovery/{email}",
    ):
        parameters = schema["paths"][path]["post"]["parameters"]
        assert any(
            parameter["in"] == "header" and parameter["name"] == "X-Turnstile-Token"
            for parameter in parameters
        )


def test_verify_response_maps_http_error_to_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = Mock()
    inner.post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
        "boom", request=Mock(), response=Mock()
    )
    context = Mock()
    context.__enter__ = Mock(return_value=inner)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("app.core.turnstile.httpx.Client", Mock(return_value=context))
    with pytest.raises(HTTPException) as captured:
        _verify_response("token", "203.0.113.10", "login")
    assert captured.value.status_code == 503
    assert "暂时不可用" in captured.value.detail


def test_verify_response_accepts_only_success_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TURNSTILE_HOSTNAMES", ["notellm.au1bhi.com"])
    cases: list[tuple[object, bool]] = [
        ([], False),  # non-dict payload
        ({"success": False}, False),
        ({}, False),
        ({"success": True}, False),
        ({"success": True, "hostname": "notellm.au1bhi.com", "action": "login"}, True),
        (
            {"success": True, "hostname": "notellm.au1bhi.com", "action": "signup"},
            False,
        ),
        ({"success": True, "hostname": "attacker.example", "action": "login"}, False),
        ({"success": True, "hostname": "localhost", "action": "login"}, False),
        (
            {"success": "true", "hostname": "notellm.au1bhi.com", "action": "login"},
            False,
        ),
    ]

    for payload, expected in cases:
        inner = Mock()
        inner.post.return_value.raise_for_status = Mock()
        inner.post.return_value.json = Mock(return_value=payload)
        context = Mock()
        context.__enter__ = Mock(return_value=inner)
        context.__exit__ = Mock(return_value=False)
        monkeypatch.setattr(
            "app.core.turnstile.httpx.Client", Mock(return_value=context)
        )
        assert _verify_response("token", "203.0.113.10", "login") is expected


def test_verify_response_maps_malformed_json_to_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = Mock()
    inner.post.return_value.raise_for_status = Mock()
    inner.post.return_value.json.side_effect = ValueError("not json")
    context = Mock()
    context.__enter__ = Mock(return_value=inner)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("app.core.turnstile.httpx.Client", Mock(return_value=context))
    with pytest.raises(HTTPException) as captured:
        _verify_response("token", "203.0.113.10", "login")
    assert captured.value.status_code == 503


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_production_cannot_disable_rate_limits(environment: str) -> None:
    config = settings.model_dump()
    config.update(
        ENVIRONMENT=environment,
        FRONTEND_HOST="https://notellm.example.com",
        RATE_LIMIT_ENABLED=False,
    )
    with pytest.raises(ValidationError, match="RATE_LIMIT_ENABLED must be true"):
        Settings(_env_file=None, **config)


def test_required_turnstile_cannot_silently_disable() -> None:
    config = settings.model_dump()
    config.update(
        TURNSTILE_REQUIRED=True, TURNSTILE_SITE_KEY=None, TURNSTILE_SECRET_KEY=None
    )
    with pytest.raises(ValidationError, match="TURNSTILE_REQUIRED requires"):
        Settings(_env_file=None, **config)
    config.update(
        TURNSTILE_SITE_KEY="site",
        TURNSTILE_SECRET_KEY="secret",
        TURNSTILE_HOSTNAMES=["notellm.au1bhi.com"],
    )
    assert Settings(_env_file=None, **config).turnstile_enabled


@pytest.mark.parametrize(
    "hostname",
    [
        "localhost",
        "127.0.0.1",
        "10.0.0.1",
        "app.local",
        "app.localhost",
        "https://notellm.au1bhi.com",
        "notellm.au1bhi.com:443",
        "*.au1bhi.com",
    ],
)
def test_production_turnstile_rejects_unsafe_expected_hosts(hostname: str) -> None:
    config = settings.model_dump()
    config.update(
        ENVIRONMENT="production",
        FRONTEND_HOST="https://notellm.au1bhi.com",
        TURNSTILE_HOSTNAMES=[hostname],
    )
    with pytest.raises(ValidationError, match="TURNSTILE_HOSTNAMES"):
        Settings(_env_file=None, **config)


def test_turnstile_enabled_requires_hostname_allowlist() -> None:
    config = settings.model_dump()
    config.update(
        TURNSTILE_SITE_KEY="test-site",
        TURNSTILE_SECRET_KEY="test-secret",
        TURNSTILE_HOSTNAMES=[],
    )
    with pytest.raises(ValidationError, match="TURNSTILE_HOSTNAMES is required"):
        Settings(_env_file=None, **config)
    config.update(TURNSTILE_HOSTNAMES=" Notellm.Au1bhi.Com , ")
    assert Settings(_env_file=None, **config).TURNSTILE_HOSTNAMES == [
        "notellm.au1bhi.com"
    ]


def test_runtime_missing_hosts_fails_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr(settings, "TURNSTILE_HOSTNAMES", [])
    response = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": "nobody@example.com", "password": "bad"},
        headers={"X-Turnstile-Token": "token"},
    )
    assert response.status_code == 503


def _mock_siteverify(monkeypatch: pytest.MonkeyPatch, payloads: list[dict]) -> Mock:
    inner = Mock()
    responses = []
    for payload in payloads:
        response = Mock()
        response.json.return_value = payload
        responses.append(response)
    inner.post.side_effect = responses
    context = Mock()
    context.__enter__ = Mock(return_value=inner)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("app.core.turnstile.httpx.Client", Mock(return_value=context))
    return inner


@pytest.mark.parametrize(
    ("path", "action"),
    [
        ("/login/access-token", "login"),
        ("/users/signup", "signup"),
        ("/password-recovery/nobody@example.com", "password_recovery"),
    ],
)
def test_handlers_validate_siteverify_action_and_host(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, path: str, action: str
) -> None:
    _enable(monkeypatch)
    token_headers = {"X-Turnstile-Token": "test-token"}
    body = (
        {"username": "nobody@example.com", "password": "bad"}
        if action == "login"
        else {"email": "test@example.com", "password": "strong-password"}
    )
    for returned_action, hostname in [
        ("wrong_action", "notellm.au1bhi.com"),
        (action, "localhost"),
        (action, "notellm.au1bhi.com.attacker.example"),
        (action, "notellm.au1bhi.com"),
    ]:
        inner = _mock_siteverify(
            monkeypatch,
            [{"success": True, "action": returned_action, "hostname": hostname}],
        )
        response = client.post(
            f"{settings.API_V1_STR}{path}",
            headers=token_headers,
            **({"data": body} if action == "login" else {"json": body}),
        )
        if returned_action == action and hostname == "notellm.au1bhi.com":
            assert response.status_code == (400 if action == "login" else 200)
            if action == "login":
                assert response.json()["detail"] == "邮箱或密码错误"
        else:
            assert response.status_code == 400
            assert response.json()["detail"].startswith("人机验证失败")
        assert inner.post.call_args.args == (
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        )
        assert inner.post.call_args.kwargs["data"]["response"] == "test-token"
        assert inner.post.call_args.kwargs["follow_redirects"] is False


def test_login_success_then_siteverify_replay_rejection(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    inner = _mock_siteverify(
        monkeypatch,
        [
            {"success": True, "action": "login", "hostname": "notellm.au1bhi.com"},
            {"success": False, "error-codes": ["timeout-or-duplicate"]},
        ],
    )
    data = {
        "username": settings.FIRST_SUPERUSER,
        "password": settings.FIRST_SUPERUSER_PASSWORD,
    }
    headers = {"X-Turnstile-Token": "single-use-test-token"}
    first = client.post(
        f"{settings.API_V1_STR}/login/access-token", data=data, headers=headers
    )
    assert first.status_code == 200
    assert first.json()["access_token"]
    replay = client.post(
        f"{settings.API_V1_STR}/login/access-token", data=data, headers=headers
    )
    assert replay.status_code == 400
    assert replay.json()["detail"].startswith("人机验证失败")
    assert inner.post.call_count == 2
