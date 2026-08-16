from fastapi.testclient import TestClient

from app.core.config import settings


def test_login_endpoint_rate_limited_after_many_attempts(
    client: TestClient,
) -> None:
    url = f"{settings.API_V1_STR}/login/access-token"
    form = {"username": "nobody@example.com", "password": "wrong-password"}

    # First 20 attempts are allowed through to the (failing) credential check.
    for _ in range(20):
        response = client.post(url, data=form)
        assert response.status_code == 400

    # The 21st attempt within the same window is blocked by the limiter.
    response = client.post(url, data=form)
    assert response.status_code == 429
    assert "请求过于频繁" in response.json()["detail"]
    assert response.headers["Retry-After"] == "60"


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
