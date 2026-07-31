from collections.abc import Sequence
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import encrypt_secret
from app.models import Chunk, UserProviderSettings
from app.services.embeddings import EmbeddingProvider
from tests.utils.user import (
    authentication_token_from_email,
    create_random_user,
)


class FakeEmbeddingProvider(EmbeddingProvider):
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(index)] * settings.EMBEDDING_DIMENSIONS for index, _ in enumerate(texts)]


def create_notebook(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    response = client.post(
        f"{settings.API_V1_STR}/notebooks/",
        headers=headers,
        json={"title": "Source test"},
    )
    assert response.status_code == 200
    return cast(dict[str, object], response.json())


def test_upload_text_source_creates_chunks(
    client: TestClient,
    db: Session,
    monkeypatch: MonkeyPatch,
    normal_user_token_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(
        "app.services.sources.get_embedding_provider",
        lambda _config=None: FakeEmbeddingProvider(),
    )
    notebook = create_notebook(client, normal_user_token_headers)
    content = "NotebookLM retrieves relevant source text. " * 60

    response = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook['id']}/sources/",
        headers=normal_user_token_headers,
        files={"file": ("lecture.txt", content.encode(), "text/plain")},
    )

    assert response.status_code == 200
    source = response.json()
    assert source["display_name"] == "lecture.txt"
    assert source["status"] == "ready"
    assert source["char_count"] == len(content)
    assert list(tmp_path.rglob("*.txt"))
    chunks = db.exec(select(Chunk).where(Chunk.source_id == source["id"])).all()
    assert len(chunks) > 1
    assert all(chunk.content for chunk in chunks)
    assert all(chunk.embedding for chunk in chunks)


def test_reject_unsupported_source(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    notebook = create_notebook(client, normal_user_token_headers)
    response = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook['id']}/sources/",
        headers=normal_user_token_headers,
        files={
            "file": (
                "lecture.docx",
                b"not a supported file",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 415


def test_user_cannot_upload_to_another_notebook(
    client: TestClient,
    db: Session,
    normal_user_token_headers: dict[str, str],
) -> None:
    notebook = create_notebook(client, normal_user_token_headers)
    other_user = create_random_user(db)
    other_headers = authentication_token_from_email(
        client=client, email=other_user.email, db=db
    )

    response = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook['id']}/sources/",
        headers=other_headers,
        files={"file": ("lecture.txt", b"private notes", "text/plain")},
    )
    assert response.status_code == 404


def test_process_source_uses_user_embedding_key(
    client: TestClient,
    db: Session,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    user = create_random_user(db)
    headers = authentication_token_from_email(
        client=client, email=user.email, db=db
    )
    db.add(
        UserProviderSettings(
            user_id=user.id,
            embedding_base_url="https://embed.example.com",
            embedding_api_key=encrypt_secret("user-embed-key-999"),
            embedding_model="embed-model",
        )
    )
    db.commit()
    monkeypatch.setattr(settings, "UPLOADS_DIR", tmp_path)

    captured: dict[str, object] = {}

    def fake_provider(_config=None):
        captured["config"] = _config
        return FakeEmbeddingProvider()

    monkeypatch.setattr(
        "app.services.sources.get_embedding_provider", fake_provider
    )

    notebook = create_notebook(client, headers)
    content = "User-provided embedding key. " * 40
    response = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook['id']}/sources/",
        headers=headers,
        files={"file": ("lecture.txt", content.encode(), "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    config = captured["config"]
    assert config.api_key == "user-embed-key-999"
    assert config.base_url == "https://embed.example.com"
    assert config.model == "embed-model"
