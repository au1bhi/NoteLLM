import json
from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlmodel import Session

from app.core.config import settings
from app.models import (
    Chunk,
    Citation,
    Conversation,
    ConversationMessage,
    Notebook,
    Source,
    User,
)
from app.services.answers import AnswerCitation, GroundedAnswer
from tests.utils.user import authentication_token_from_email, create_random_user


def seeded(db: Session) -> tuple[User, Notebook, Conversation, Chunk, str]:
    owner = create_random_user(db)
    notebook = Notebook(owner_id=owner.id, title="Synthetic citation boundary")
    db.add(notebook)
    db.flush()
    source = Source(
        notebook_id=notebook.id,
        display_name="synthetic.txt",
        media_type="text/plain",
        file_size_bytes=1,
        storage_path="synthetic-no-file",
        status="ready",
    )
    db.add(source)
    db.flush()
    content = (
        "合成引用块开头。" * 85
        + "AFTER_500_AUTHORIZED_MARKER: the complete evidence is visible here."
    )
    chunk = Chunk(
        source_id=source.id,
        ordinal=0,
        content=content,
        char_start=0,
        char_end=len(content),
    )
    conversation = Conversation(notebook_id=notebook.id, title="Citation refresh")
    db.add_all([chunk, conversation])
    db.flush()
    message = ConversationMessage(
        conversation_id=conversation.id, role="assistant", content="Synthetic answer"
    )
    db.add(message)
    db.flush()
    db.add(
        Citation(
            message_id=message.id, chunk_id=chunk.id, ordinal=0, quote=content[:500]
        )
    )
    db.commit()
    return owner, notebook, conversation, chunk, content


def headers(client: TestClient, db: Session, owner: User) -> dict[str, str]:
    return authentication_token_from_email(client=client, email=owner.email, db=db)


def test_authorized_full_chunk_and_snapshot_survive_refresh(
    client: TestClient, db: Session
) -> None:
    owner, _, conversation, _, content = seeded(db)
    auth = headers(client, db, owner)
    path = f"{settings.API_V1_STR}/conversations/{conversation.id}"
    for _ in range(2):
        response = client.get(path, headers=auth)
        assert response.status_code == 200
        citation = response.json()["messages"][0]["citations"][0]
        assert citation["quote"] == content[:500]
        assert "AFTER_500_AUTHORIZED_MARKER" not in citation["quote"]
        assert citation.get("chunk_content") == content
        db.expire_all()


def test_full_chunk_is_current_content_not_permanent_archive(
    client: TestClient, db: Session
) -> None:
    owner, _, conversation, chunk, content = seeded(db)
    chunk.content = "Updated synthetic block, not the persisted quote."
    db.add(chunk)
    db.commit()
    response = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation.id}",
        headers=headers(client, db, owner),
    )
    assert response.status_code == 200
    citation = response.json()["messages"][0]["citations"][0]
    assert citation["quote"] == content[:500]
    assert citation.get("chunk_content") == chunk.content


def test_other_user_cannot_read_full_citation(client: TestClient, db: Session) -> None:
    _, _, conversation, _, _ = seeded(db)
    stranger = create_random_user(db)
    response = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation.id}",
        headers=headers(client, db, stranger),
    )
    assert response.status_code == 404
    assert "AFTER_500_AUTHORIZED_MARKER" not in response.text


def test_corrupt_cross_notebook_reference_is_not_exposed(
    client: TestClient, db: Session
) -> None:
    owner, _, conversation, _, _ = seeded(db)
    _, _, _, other_chunk, _ = seeded(db)
    message = ConversationMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="Forged cross-notebook reference",
    )
    db.add(message)
    db.flush()
    db.add(
        Citation(
            message_id=message.id,
            chunk_id=other_chunk.id,
            ordinal=0,
            quote="Cross-notebook snapshot must also be hidden",
        )
    )
    db.commit()
    response = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation.id}",
        headers=headers(client, db, owner),
    )
    assert response.status_code == 200
    forged = next(m for m in response.json()["messages"] if m["id"] == str(message.id))
    assert forged["citations"] == []
    assert "Cross-notebook snapshot must also be hidden" not in response.text


def test_sse_citation_exposes_same_optional_complete_block(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    owner, _, conversation, chunk, content = seeded(db)

    def fake_persist(**_: Any) -> GroundedAnswer:
        return GroundedAnswer(
            content="Synthetic stream",
            citations=[
                AnswerCitation(
                    chunk_id=chunk.id,
                    page_number=None,
                    quote=content[:500],
                    source_display_name="synthetic.txt",
                    chunk_content=content,
                )
            ],
        )

    monkeypatch.setattr("app.api.routes.conversations.persist_answer", fake_persist)
    response = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation.id}/messages/stream",
        headers=headers(client, db, owner),
        json={"content": "Explain the document."},
    )
    assert response.status_code == 200
    assert "event: error" not in response.text
    blocks = response.text.replace("\r\n", "\n").split("\n\n")
    event = next(b for b in blocks if "event: citations" in b)
    payload = json.loads(
        next(l[6:] for l in event.splitlines() if l.startswith("data: "))
    )
    citation = payload["citations"][0]
    assert citation["quote"] == content[:500]
    assert citation.get("chunk_content") == content


def test_real_stream_filters_foreign_notebook_content(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    from app.services.chat import ModelAnswer

    owner, _, conversation, own_chunk, _ = seeded(db)
    _, _, _, foreign_chunk, _ = seeded(db)
    vector = [0.0] * settings.EMBEDDING_DIMENSIONS
    vector[0] = 1.0
    own_chunk.embedding = vector
    foreign_chunk.embedding = vector
    foreign_chunk.content = "FOREIGN_NOTEBOOK_ONLY_PRIVATE_MARKER"
    db.add_all([own_chunk, foreign_chunk])
    db.commit()

    class ControlledEmbedding:
        def embed(self, texts: Any) -> list[list[float]]:
            return [vector for _ in texts]

    class ForeignCitationChat:
        total_tokens_used = 0

        def answer(self, **_: Any) -> ModelAnswer:
            return ModelAnswer(
                content="Unsupported foreign citation",
                citation_chunk_ids=[str(foreign_chunk.id)],
            )

        def complete_json(self, **_: Any) -> dict[str, Any]:
            return {"questions": []}

    monkeypatch.setattr(
        "app.services.conversations.get_chat_provider", lambda *_: ForeignCitationChat()
    )
    monkeypatch.setattr(
        "app.services.conversations.get_embedding_provider",
        lambda *_: ControlledEmbedding(),
    )
    response = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation.id}/messages/stream",
        headers=headers(client, db, owner),
        json={"content": "What does the document require?"},
    )
    assert response.status_code == 200
    assert "event: error" not in response.text
    assert "FOREIGN_NOTEBOOK_ONLY_PRIVATE_MARKER" not in response.text
    blocks = response.text.replace("\r\n", "\n").split("\n\n")
    event = next(b for b in blocks if "event: citations" in b)
    payload = json.loads(
        next(l[6:] for l in event.splitlines() if l.startswith("data: "))
    )
    assert payload["citations"] == []
