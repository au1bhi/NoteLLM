import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


def test_watermark_endpoint_returns_configured_text(
    client: TestClient,
) -> None:
    response = client.get(f"{settings.API_V1_STR}/meta/watermark")
    assert response.status_code == 200
    assert response.json() == {
        "enabled": settings.WATERMARK_ENABLED,
        "text": settings.WATERMARK_TEXT,
    }


def test_watermark_default_text_is_required_domain() -> None:
    # The anti-screenshot branding default is pinned to the deployment domain.
    assert settings.WATERMARK_TEXT == "notellm.au1bhi.com"


def test_watermark_default_enabled() -> None:
    # The watermark is on unless the operator turns it off.
    assert settings.WATERMARK_ENABLED is True


def test_watermark_disabled_flag(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "WATERMARK_ENABLED", False)
    response = client.get(f"{settings.API_V1_STR}/meta/watermark")
    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "text": settings.WATERMARK_TEXT,
    }


def test_watermark_is_public_no_auth(client: TestClient) -> None:
    # Must render on login/signup before any auth; no 401/403 allowed.
    response = client.get(f"{settings.API_V1_STR}/meta/watermark")
    assert response.status_code == 200
    assert "WWW-Authenticate" not in response.headers
