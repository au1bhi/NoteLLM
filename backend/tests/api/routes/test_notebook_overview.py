from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlmodel import Session

from app.core.config import settings
from app.models import Chunk, Source
from tests.utils.notebook import create_random_notebook
from tests.utils.user import authentication_token_from_email, create_random_user


class FakeOverviewProvider:
    def __init__(self, summary: str = "About the material.", topics: list[str] | None = None) -> None:
        self.summary = summary
        self.topics = topics if topics is not None else ["topic one"]
        self.calls = 0

    def complete_json(self, *, prompt: str) -> dict:
        self.calls += 1
        return {"summary": self.summary, "topics": self.topics}


def _add_ready_source(db: Session, notebook_id, content: str = "pgvector adds vector search to PostgreSQL.") -> Source:
    source = Source(
        notebook_id=notebook_id,
        display_name="notes.txt",
        media_type="text/plain",
        file_size_bytes=10,
        status="ready",
        storage_path="x.txt",
        char_count=len(content),
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    db.add(
        Chunk(
            source_id=source.id,
            ordinal=0,
            content=content,
            char_start=0,
            char_end=len(content),
            embedding=[0.0] * settings.EMBEDDING_DIMENSIONS,
        )
    )
    db.commit()
    return source


def test_overview_generates_lazily_and_caches(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    _add_ready_source(db, notebook.id)
    provider = FakeOverviewProvider(
        summary="About pgvector.", topics=["vector search", "PostgreSQL"]
    )
    monkeypatch.setattr(
        "app.api.routes.notebooks.get_chat_provider", lambda _config=None: provider
    )

    response = client.get(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/overview", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "About pgvector."
    assert body["topics"] == ["vector search", "PostgreSQL"]
    assert body["updated_at"] is not None
    assert provider.calls == 1

    # Second read should hit the cache, not regenerate.
    client.get(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/overview", headers=headers
    )
    assert provider.calls == 1


def test_regenerate_overview(client: TestClient, db: Session, monkeypatch: MonkeyPatch) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    _add_ready_source(db, notebook.id)
    provider = FakeOverviewProvider(summary="First version")
    monkeypatch.setattr(
        "app.api.routes.notebooks.get_chat_provider", lambda _config=None: provider
    )
    client.get(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/overview", headers=headers
    )
    provider.summary = "Second version"

    response = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/overview/regenerate",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["summary"] == "Second version"


def test_overview_empty_without_ready_sources(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    provider = FakeOverviewProvider()
    monkeypatch.setattr(
        "app.api.routes.notebooks.get_chat_provider", lambda _config=None: provider
    )
    response = client.get(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/overview", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["summary"] == ""
    assert response.json()["topics"] == []
    assert provider.calls == 0
