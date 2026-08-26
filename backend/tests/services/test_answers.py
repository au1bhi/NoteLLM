import uuid
from collections.abc import Sequence
from typing import cast

import pytest
from pytest import MonkeyPatch
from sqlmodel import Session

from app.models import Chunk
from app.services.answers import INSUFFICIENT_EVIDENCE_ANSWER, answer_question
from app.services.chat import ChatError, ModelAnswer
from app.services.embeddings import EmbeddingError
from app.services.retrieval import RetrievedChunk


class FakeEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


class FakeChatProvider:
    def __init__(
        self, answer: ModelAnswer, suggestions: list[str] | None = None
    ) -> None:
        self.answer_result = answer
        self.suggestions = suggestions if suggestions is not None else []
        self.total_tokens_used = 0

    def answer(
        self,
        *,
        prompt: str,
        system: str | None = None,
        on_delta: object = None,
    ) -> ModelAnswer:
        return self.answer_result

    def complete_json(self, *, prompt: str, system: str | None = None) -> dict:
        # The suggestions request is the one whose system rules mention
        # "questions"; the answer request's rules do not.
        if "questions" in (system or ""):
            return {"questions": self.suggestions}
        return {
            "answer": self.answer_result.content,
            "citations": self.answer_result.citation_chunk_ids,
        }


def test_answer_discards_citations_not_in_retrieved_set(
    monkeypatch: MonkeyPatch,
) -> None:
    chunk = Chunk(
        source_id=uuid.uuid4(),
        ordinal=0,
        content="Verified evidence",
        char_start=0,
        char_end=17,
    )
    retrieved = [
        RetrievedChunk(chunk=chunk, score=0.9, source_display_name="notes.txt")
    ]
    monkeypatch.setattr("app.services.answers.retrieve_chunks", lambda **_: retrieved)

    answer = answer_question(
        session=cast(Session, None),
        notebook_id=uuid.uuid4(),
        query="What is verified?",
        embedding_provider=FakeEmbeddingProvider(),
        chat_provider=FakeChatProvider(
            ModelAnswer(
                content="A made-up answer", citation_chunk_ids=[str(uuid.uuid4())]
            )
        ),
    )

    assert answer.content == INSUFFICIENT_EVIDENCE_ANSWER
    assert answer.citations == []


def test_answer_persists_only_retrieved_citation(monkeypatch: MonkeyPatch) -> None:
    chunk = Chunk(
        source_id=uuid.uuid4(),
        ordinal=0,
        content="Verified evidence",
        char_start=0,
        char_end=17,
    )
    retrieved = [
        RetrievedChunk(chunk=chunk, score=0.9, source_display_name="notes.txt")
    ]
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
    assert [citation.chunk_id for citation in answer.citations] == [chunk.id]


def test_knowledge_mode_skips_retrieval_and_returns_answer(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_if_called(**_: object) -> list[RetrievedChunk]:
        raise AssertionError("retrieve_chunks should not run in knowledge mode")

    monkeypatch.setattr("app.services.answers.retrieve_chunks", fail_if_called)

    answer = answer_question(
        session=cast(Session, None),
        notebook_id=uuid.uuid4(),
        query="What is machine learning?",
        embedding_provider=FakeEmbeddingProvider(),
        chat_provider=FakeChatProvider(
            ModelAnswer(
                content="Machine learning is a subset of AI.",
                citation_chunk_ids=[],
            )
        ),
        mode="knowledge",
    )

    assert answer.content == "Machine learning is a subset of AI."
    assert answer.citations == []


def test_hybrid_mode_answers_from_knowledge_without_evidence(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.answers.retrieve_chunks", lambda **_: [])

    answer = answer_question(
        session=cast(Session, None),
        notebook_id=uuid.uuid4(),
        query="What is the capital of France?",
        embedding_provider=FakeEmbeddingProvider(),
        chat_provider=FakeChatProvider(
            ModelAnswer(
                content="The capital of France is Paris.",
                citation_chunk_ids=[],
            )
        ),
        mode="hybrid",
    )

    assert answer.content == "The capital of France is Paris."
    assert answer.citations == []


def test_hybrid_mode_keeps_answer_when_model_cites_nothing(
    monkeypatch: MonkeyPatch,
) -> None:
    chunk = Chunk(
        source_id=uuid.uuid4(),
        ordinal=0,
        content="Paris is the capital and largest city of France.",
        char_start=0,
        char_end=52,
    )
    retrieved = [
        RetrievedChunk(chunk=chunk, score=0.8, source_display_name="notes.txt")
    ]
    monkeypatch.setattr("app.services.answers.retrieve_chunks", lambda **_: retrieved)

    answer = answer_question(
        session=cast(Session, None),
        notebook_id=uuid.uuid4(),
        query="Where is the Eiffel Tower?",
        embedding_provider=FakeEmbeddingProvider(),
        chat_provider=FakeChatProvider(
            ModelAnswer(
                content="The Eiffel Tower is in Paris, France.",
                citation_chunk_ids=[],
            )
        ),
        mode="hybrid",
    )

    assert answer.content == "The Eiffel Tower is in Paris, France."
    assert answer.citations == []


def test_answer_includes_suggestions(monkeypatch: MonkeyPatch) -> None:
    chunk = Chunk(
        source_id=uuid.uuid4(),
        ordinal=0,
        content="Verified evidence",
        char_start=0,
        char_end=17,
    )
    retrieved = [
        RetrievedChunk(chunk=chunk, score=0.9, source_display_name="notes.txt")
    ]
    monkeypatch.setattr("app.services.answers.retrieve_chunks", lambda **_: retrieved)

    answer = answer_question(
        session=cast(Session, None),
        notebook_id=uuid.uuid4(),
        query="What is verified?",
        embedding_provider=FakeEmbeddingProvider(),
        chat_provider=FakeChatProvider(
            ModelAnswer(
                content="Verified evidence answers the question.",
                citation_chunk_ids=[str(chunk.id)],
            ),
            suggestions=["What else?", "Give an example"],
        ),
    )

    assert answer.suggestions == ["What else?", "Give an example"]
    assert answer.citations


def test_suggestions_are_best_effort_on_failure(monkeypatch: MonkeyPatch) -> None:
    chunk = Chunk(
        source_id=uuid.uuid4(),
        ordinal=0,
        content="Verified evidence",
        char_start=0,
        char_end=17,
    )
    retrieved = [
        RetrievedChunk(chunk=chunk, score=0.9, source_display_name="notes.txt")
    ]
    monkeypatch.setattr("app.services.answers.retrieve_chunks", lambda **_: retrieved)

    class BrokenSuggestionsProvider(FakeChatProvider):
        def complete_json(self, *, prompt: str, system: str | None = None) -> dict:
            raise ChatError("suggestions provider outage")

    answer = answer_question(
        session=cast(Session, None),
        notebook_id=uuid.uuid4(),
        query="What is verified?",
        embedding_provider=FakeEmbeddingProvider(),
        chat_provider=BrokenSuggestionsProvider(
            ModelAnswer(
                content="Verified evidence answers the question.",
                citation_chunk_ids=[str(chunk.id)],
            )
        ),
    )

    assert answer.suggestions == []
    assert answer.content == "Verified evidence answers the question."


def test_answer_propagates_embedding_failure(monkeypatch: MonkeyPatch) -> None:
    """Retrieval outages must surface to callers (SSE error / 503), never
    degrade into a silent 'insufficient evidence' answer that still bills."""

    def failing_retrieve(**_: object) -> list[RetrievedChunk]:
        raise EmbeddingError("嵌入服务商返回错误 (500)：outage")

    monkeypatch.setattr("app.services.answers.retrieve_chunks", failing_retrieve)

    with pytest.raises(EmbeddingError):
        answer_question(
            session=cast(Session, None),
            notebook_id=uuid.uuid4(),
            query="What is verified?",
            embedding_provider=FakeEmbeddingProvider(),
            chat_provider=FakeChatProvider(
                ModelAnswer(content="unused", citation_chunk_ids=[])
            ),
        )


def test_answer_forwards_limit_to_retrieve_chunks(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_retrieve(**kwargs: object) -> list[RetrievedChunk]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr("app.services.answers.retrieve_chunks", fake_retrieve)

    answer_question(
        session=cast(Session, None),
        notebook_id=uuid.uuid4(),
        query="What is verified?",
        embedding_provider=FakeEmbeddingProvider(),
        chat_provider=FakeChatProvider(
            ModelAnswer(content="unused", citation_chunk_ids=[])
        ),
        limit=3,
    )

    assert captured["limit"] == 3


# --- Conversational/meta detection & retrieval contextualisation -----------


def test_conversational_detection_table() -> None:
    from app.services.answers import is_conversational_or_meta_query as is_meta

    assert is_meta("") is True
    assert is_meta("  ") is True
    assert is_meta("你好！") is True
    assert is_meta("Hey!") is True
    assert is_meta("Hey there~") is False  # two-word form is not in the anchor list
    assert is_meta("who are you") is True
    assert is_meta("你叫什么名字") is True
    # Real content questions stay False.
    assert is_meta("什么是向量检索？") is False
    assert is_meta("explain pgvector index types") is False
    # Short follow-ups only count when history context exists.
    assert is_meta("继续", history="") is False
    assert is_meta("继续", history="学习者：解释一下 HNSW") is True
    assert is_meta("上文提到的那个为什么不对呀呢", history="x") is True


def test_contextualize_retrieval_query_rules() -> None:
    from app.services.answers import contextualize_retrieval_query as ctx

    assert ctx(query="它") == "它"  # no history
    assert ctx(query="长问题" * 20, history="学习者：旧话题") == "长问题" * 20
    merged = ctx(
        query="它的优缺点是什么",
        history="助手：略\n学习者：HNSW 索引原理",
    )
    assert merged.startswith("HNSW 索引原理")
    assert merged.endswith("它的优缺点是什么")
    # Identical topic must NOT be duplicated into the query.
    same = ctx(query="HNSW 索引原理", history="学习者：HNSW 索引原理")
    assert same == "HNSW 索引原理"
