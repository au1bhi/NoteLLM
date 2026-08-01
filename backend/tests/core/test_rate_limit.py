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
