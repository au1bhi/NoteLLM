import uuid
from collections.abc import Sequence
from typing import cast

from pytest import MonkeyPatch
from sqlmodel import Session

from app.models import Chunk
from app.services.answers import INSUFFICIENT_EVIDENCE_ANSWER, answer_question
from app.services.chat import ModelAnswer
from app.services.retrieval import RetrievedChunk


class FakeEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


class FakeChatProvider:
    def __init__(self, answer: ModelAnswer) -> None:
        self.answer_result = answer

    def answer(self, *, prompt: str) -> ModelAnswer:
        return self.answer_result


def test_answer_discards_citations_not_in_retrieved_set(
    monkeypatch: MonkeyPatch,
) -> None:
    chunk = Chunk(source_id=uuid.uuid4(), ordinal=0, content="Verified evidence", char_start=0, char_end=17)
    retrieved = [RetrievedChunk(chunk=chunk, score=0.9, source_display_name="notes.txt")]
    monkeypatch.setattr("app.services.answers.retrieve_chunks", lambda **_: retrieved)

    answer = answer_question(
        session=cast(Session, None),
        notebook_id=uuid.uuid4(),
        query="What is verified?",
        embedding_provider=FakeEmbeddingProvider(),
        chat_provider=FakeChatProvider(
            ModelAnswer(content="A made-up answer", citation_chunk_ids=[str(uuid.uuid4())])
        ),
    )

    assert answer.content == INSUFFICIENT_EVIDENCE_ANSWER
    assert answer.citations == []


def test_answer_persists_only_retrieved_citation(monkeypatch: MonkeyPatch) -> None:
    chunk = Chunk(source_id=uuid.uuid4(), ordinal=0, content="Verified evidence", char_start=0, char_end=17)
    retrieved = [RetrievedChunk(chunk=chunk, score=0.9, source_display_name="notes.txt")]
    monkeypatch.setattr("app.services.answers.retrieve_chunks", lambda **_: retrieved)

    answer = answer_question(
        session=cast(Session, None),
        notebook_id=uuid.uuid4(),
        query="What is verified?",
        embedding_provider=FakeEmbeddingProvider(),
        chat_provider=FakeChatProvider(
            ModelAnswer(
                content="Verified evidence answers the question.",
                citation_chunk_ids=[str(chunk.id), str(chunk.id)],
            )
        ),
    )

    assert answer.content == "Verified evidence answers the question."
    assert [citation.chunk.id for citation in answer.citations] == [chunk.id]
