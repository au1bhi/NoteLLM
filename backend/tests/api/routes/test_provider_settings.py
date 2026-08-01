import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models import UserProviderSettings, UserUsage
from app.services.provider_settings import (
    effective_chat_config,
    load_user_provider_settings,
)
from tests.utils.user import authentication_token_from_email, create_random_user


def _auth(client: TestClient, db: Session):
    user = create_random_user(db)
    headers = authentication_token_from_email(
        client=client, email=user.email, db=db
    )
    return user, headers


def _url() -> str:
    return f"{settings.API_V1_STR}/users/me/provider-settings"


def test_encrypt_secret_round_trip() -> None:
    value = "sk-super-secret-key"
    encrypted = encrypt_secret(value)
    assert encrypted != value
    assert decrypt_secret(encrypted) == value


def test_get_provider_settings_defaults_empty(client: TestClient, db: Session) -> None:
    _, headers = _auth(client, db)
    response = client.get(_url(), headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "chat_base_url": None,
        "chat_api_key": "",
        "chat_model": None,
        "embedding_base_url": None,
        "embedding_api_key": "",
        "embedding_model": None,
    }


def test_upsert_stores_encrypted_and_returns_masked(
    client: TestClient, db: Session
) -> None:
    user, headers = _auth(client, db)
    payload = {
        "chat_base_url": "https://llm.example.com",
        "chat_api_key": "sk-my-real-key-123456",
        "chat_model": "my-model",
        "embedding_api_key": "embed-123",
    }
    response = client.put(_url(), headers=headers, json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["chat_base_url"] == "https://llm.example.com"
    assert body["chat_model"] == "my-model"
    assert body["chat_api_key"] == "sk-m***3456"
    assert body["embedding_api_key"] == "embe***-123"
    assert "sk-my-real-key-123456" not in str(body)

    row = db.exec(
        select(UserProviderSettings).where(
            UserProviderSettings.user_id == user.id
        )
    ).one()
    assert row.chat_api_key != "sk-my-real-key-123456"
    assert decrypt_secret(row.chat_api_key) == "sk-my-real-key-123456"


def test_empty_api_key_keeps_stored_key(client: TestClient, db: Session) -> None:
    user, headers = _auth(client, db)
    db.add(
        UserProviderSettings(
            user_id=user.id, chat_api_key=encrypt_secret("keep-me-123")
        )
    )
    db.commit()

    response = client.put(_url(), headers=headers, json={"chat_api_key": ""})
    assert response.status_code == 200
    assert response.json()["chat_api_key"] == "keep***-123"

    row = db.exec(
        select(UserProviderSettings).where(
            UserProviderSettings.user_id == user.id
        )
    ).one()
    assert decrypt_secret(row.chat_api_key) == "keep-me-123"


def test_clear_provider_settings(client: TestClient, db: Session) -> None:
    user, headers = _auth(client, db)
    db.add(UserProviderSettings(user_id=user.id, chat_api_key=encrypt_secret("x")))
    db.commit()

    response = client.delete(_url(), headers=headers)
    assert response.status_code == 200
    row = db.exec(
        select(UserProviderSettings).where(
            UserProviderSettings.user_id == user.id
        )
    ).first()
    assert row is None


def test_provider_settings_are_user_isolated(
    client: TestClient, db: Session
) -> None:
    _, headers_a = _auth(client, db)
    _, headers_b = _auth(client, db)
    client.put(
        _url(), headers=headers_a, json={"chat_api_key": "aaa-bbb-ccc-111"}
    )

    response = client.get(_url(), headers=headers_b)
    assert response.status_code == 200
    assert response.json()["chat_api_key"] == ""


def test_custom_base_url_without_key_does_not_leak_server_key(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "LLM_API_KEY", "server-secret-key")
    monkeypatch.setattr(
        settings, "LLM_BASE_URL", "https://api.example.com/v1"
    )
    _, headers = _auth(client, db)
    client.put(
        _url(), headers=headers, json={"chat_base_url": "https://evil.example.com"}
    )
    user_settings = load_user_provider_settings(
        db, _current_user_id(client, headers)
    )
    config = effective_chat_config(user_settings)
    assert config.base_url == "https://evil.example.com"
    assert config.api_key == ""


def test_server_key_used_when_endpoint_is_server_default(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "LLM_API_KEY", "server-secret-key")
    monkeypatch.setattr(
        settings, "LLM_BASE_URL", "https://api.example.com/v1"
    )
    _, headers = _auth(client, db)
    user_settings = load_user_provider_settings(
        db, _current_user_id(client, headers)
    )
    config = effective_chat_config(user_settings)
    assert config.api_key == "server-secret-key"


def _current_user_id(client: TestClient, headers: dict[str, str]) -> str:
    return client.get(
        f"{settings.API_V1_STR}/users/me", headers=headers
    ).json()["id"]


def test_user_usage_returns_accumulated_totals(client: TestClient, db: Session) -> None:
    user, headers = _auth(client, db)
    db.add(
        UserUsage(user_id=user.id, chat_tokens=1234, embedding_chars=5678)
    )
    db.commit()

    response = client.get(
        f"{settings.API_V1_STR}/users/me/usage", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["chat_tokens"] == 1234
    assert body["embedding_chars"] == 5678


def test_user_usage_defaults_to_zero(client: TestClient, db: Session) -> None:
    _, headers = _auth(client, db)
    response = client.get(
        f"{settings.API_V1_STR}/users/me/usage", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["chat_tokens"] == 0
    assert response.json()["embedding_chars"] == 0


def test_fetch_models_rejects_private_url(client: TestClient, db: Session) -> None:
    _, headers = _auth(client, db)
    response = client.post(
        _url() + "/models",
        headers=headers,
        json={"base_url": "http://127.0.0.1:8000/v1", "api_key": "x"},
    )
    assert response.status_code == 422


def test_fetch_models_rejects_missing_scheme(client: TestClient, db: Session) -> None:
    _, headers = _auth(client, db)
    response = client.post(
        _url() + "/models",
        headers=headers,
        json={"base_url": "api.example.com/v1", "api_key": "x"},
    )
    assert response.status_code == 422


def test_fetch_models_requires_auth(client: TestClient) -> None:
    response = client.post(
        _url() + "/models",
        json={"base_url": "https://api.example.com/v1", "api_key": "x"},
    )
    assert response.status_code == 401


def test_fetch_models_custom_base_url_requires_key(client: TestClient, db: Session) -> None:
    _, headers = _auth(client, db)
    response = client.post(
        _url() + "/models",
        headers=headers,
        json={"base_url": "https://evil.example.com/v1", "api_key": ""},
    )
    assert response.status_code == 422


def test_fetch_models_server_key_not_sent_to_custom_endpoint(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "LLM_API_KEY", "server-secret-key")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://api.example.com/v1")
    _, headers = _auth(client, db)
    response = client.post(
        _url() + "/models",
        headers=headers,
        json={"base_url": "https://evil.example.com/v1", "api_key": ""},
    )
    assert response.status_code == 422
