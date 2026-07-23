from collections.abc import Sequence
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlmodel import Session, select

from app.core.config import settings
from app.models import Chunk
from app.services.embeddings import EmbeddingProvider
from tests.utils.user import authentication_token_from_email, create_random_user


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
        "app.services.sources.get_embedding_provider", lambda: FakeEmbeddingProvider()
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
