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
        _verify_response("token", "203.0.113.10")
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
