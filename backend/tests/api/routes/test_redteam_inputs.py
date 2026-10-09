import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.models import Source, UserProviderSettings
from tests.utils.user import authentication_token_from_email, create_random_user


@pytest.mark.parametrize(
    "query", ["skip=-1", "limit=-1", "limit=0", "limit=101", "skip=9223372036854775808"]
)
def test_pagination_rejects_invalid_bounds(
    client: TestClient, superuser_token_headers: dict[str, str], query: str
) -> None:
    headers = superuser_token_headers
    notebook = client.post(
        f"{settings.API_V1_STR}/notebooks/", headers=headers, json={"title": "分页测试"}
    ).json()
    for path in [
        "/users/",
        "/notebooks/",
        "/study-plans",
        f"/notebooks/{notebook['id']}/sources",
        f"/notebooks/{notebook['id']}/conversations",
    ]:
        response = client.get(f"{settings.API_V1_STR}{path}?{query}", headers=headers)
        assert response.status_code == 422, (path, response.text)
    response = client.get(
        f"{settings.API_V1_STR}/notebooks/?skip=0&limit=1", headers=headers
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) <= 1


@pytest.mark.parametrize("filename", [b"bad\x00.txt", b"bad\x01.txt", b"bad\x7f.txt"])
def test_upload_rejects_control_characters_before_persistence(
    client: TestClient,
    db: Session,
    normal_user_token_headers: dict[str, str],
    filename: bytes,
) -> None:
    headers = normal_user_token_headers
    notebook = client.post(
        f"{settings.API_V1_STR}/notebooks/",
        headers=headers,
        json={"title": "文件名测试"},
    ).json()
    # Raw multipart preserves the actual bytes rather than client-side escaping.
    body = (
        b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="'
        + filename
        + b'"\r\nContent-Type: text/plain\r\n\r\nhello\r\n--boundary--\r\n'
    )
    response = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook['id']}/sources",
        headers={**headers, "Content-Type": "multipart/form-data; boundary=boundary"},
        content=body,
    )
    assert response.status_code == 400, response.text
    assert "控制字符" in response.json()["detail"]
    assert not db.exec(select(Source).where(Source.notebook_id == notebook["id"])).all()


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1",
        "https://169.254.169.254",
        "http://public.example",
        "https://public.example:8080",
        "https://user:password@public.example",
        "https://public.example/?url=internal",
    ],
)
@pytest.mark.parametrize("field", ["chat_base_url", "embedding_base_url"])
def test_invalid_provider_url_is_not_saved(
    client: TestClient, db: Session, url: str, field: str
) -> None:
    user = create_random_user(db)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    response = client.put(
        f"{settings.API_V1_STR}/users/me/provider-settings",
        headers=headers,
        json={field: url},
    )
    assert response.status_code == 422, response.text
    assert (
        db.exec(
            select(UserProviderSettings).where(UserProviderSettings.user_id == user.id)
        ).first()
        is None
    )
