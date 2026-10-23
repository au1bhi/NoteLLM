import uuid
from collections.abc import Sequence
from typing import cast

import pytest
from pytest import MonkeyPatch
from sqlmodel import Session

from app.models import AnswerMode, Chunk
from app.services import answers
from app.services.chat import ModelAnswer
from app.services.retrieval import RetrievedChunk


class EmbeddingStub:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0] for _ in texts]


class ChatStub:
    total_tokens_used = 0

    def __init__(self, ids: list[str] | None = None) -> None:
        self.ids = ids or []
        self.calls = 0
        self.prompt = ""

    def answer(
        self, *, prompt: str, system: str | None = None, on_delta: object = None
    ) -> ModelAnswer:
        self.calls += 1
        self.prompt = prompt
        return ModelAnswer(
            content="Evidence-scoped answer", citation_chunk_ids=self.ids
        )

    def complete_json(
        self, *, prompt: str, system: str | None = None
    ) -> dict[str, object]:
        return {"questions": []}


def invoke(
    monkeypatch: MonkeyPatch,
    *,
    query: str,
    history: str,
    evidence: bool,
    cited: bool,
    mode: str = "grounded",
) -> tuple[answers.GroundedAnswer, ChatStub, list[str], Chunk]:
    content = (
        "合成证据开头。" * 90
        + "AFTER_SNAPSHOT_MARKER: evidence after character five hundred."
    )
    chunk = Chunk(
        source_id=uuid.uuid4(),
        ordinal=0,
        content=content,
        char_start=0,
        char_end=len(content),
    )
    calls: list[str] = []

    def retrieve(**kwargs: object) -> list[RetrievedChunk]:
        calls.append(str(kwargs["query"]))
        return (
            [
                RetrievedChunk(
                    chunk=chunk, score=1.0, source_display_name="synthetic.txt"
                )
            ]
            if evidence
            else []
        )

    monkeypatch.setattr(answers, "build_conversation_history", lambda **_: history)
    monkeypatch.setattr(answers, "retrieve_chunks", retrieve)
    chat = ChatStub([str(chunk.id)] if cited else [])
    result = answers.answer_question(
        session=cast(Session, None),
        notebook_id=uuid.uuid4(),
        query=query,
        chat_provider=chat,
        embedding_provider=EmbeddingStub(),
        mode=cast(AnswerMode, mode),
    )
    return result, chat, calls, chunk


@pytest.mark.parametrize(
    "query",
    [
        "我刚才说计划几天完成？这是否就是规范规定的周期？",
        "总结我们刚才的安排，并核对文档中的正式要求。",
        "你好，请按来源说明保留期限。",
        "What did I say about my schedule, and what duration does the document require?",
        "Summarize our conversation and compare it with the written policy.",
        "Who are you, and what does the source say about the required review?",
        "我刚才说的5天是否符合资料规定？",
        "What did I say about my schedule compared to what the policy requires?",
        "我刚才上传了什么资料？并核对文档规定的保留条件。",
        "What did I say about the document, and what does the policy actually require?",
    ],
)
def test_mixed_history_and_document_query_keeps_evidence(
    monkeypatch: MonkeyPatch, query: str
) -> None:
    result, chat, calls, chunk = invoke(
        monkeypatch,
        query=query,
        history="学习者：我有自己的安排。",
        evidence=True,
        cited=True,
    )
    assert len(calls) == 1
    assert chat.calls == 1
    assert str(chunk.id) in chat.prompt
    assert [c.chunk_id for c in result.citations] == [chunk.id]


@pytest.mark.parametrize(
    "query",
    [
        "我刚才希望按什么顺序学习？",
        "Summarize our conversation",
        "继续",
        "hello",
        "我刚才上传了什么资料？",
        "What did I say about the document?",
    ],
)
def test_pure_history_or_greeting_preserves_no_evidence_path(
    monkeypatch: MonkeyPatch, query: str
) -> None:
    result, chat, calls, _ = invoke(
        monkeypatch,
        query=query,
        history="学习者：先阅读再练习。",
        evidence=False,
        cited=False,
    )
    assert calls == []
    assert chat.calls == 1
    assert result.content == "Evidence-scoped answer"
    assert result.citations == []


@pytest.mark.parametrize("history", ["学习者：你好。", "学习者：我们讨论过索引。"])
@pytest.mark.parametrize("evidence", [False, True])
def test_document_question_cannot_use_any_history_to_bypass_grounding(
    monkeypatch: MonkeyPatch, history: str, evidence: bool
) -> None:
    result, chat, calls, _ = invoke(
        monkeypatch,
        query="What does the document prescribe for retention?",
        history=history,
        evidence=evidence,
        cited=False,
    )
    assert len(calls) == 1
    assert result.content == answers.INSUFFICIENT_EVIDENCE_ANSWER
    assert result.citations == []
    assert chat.calls == (1 if evidence else 0)


@pytest.mark.parametrize("mode", ["knowledge", "hybrid"])
def test_request_mode_exceptions_remain_intact(
    monkeypatch: MonkeyPatch, mode: str
) -> None:
    result, chat, calls, _ = invoke(
        monkeypatch,
        query="What does the document prescribe?",
        history="学习者：你好。",
        evidence=False,
        cited=False,
        mode=mode,
    )
    assert chat.calls == 1
    assert len(calls) == (0 if mode == "knowledge" else 1)
    assert result.content == "Evidence-scoped answer"


def test_full_citation_content_does_not_replace_snapshot(
    monkeypatch: MonkeyPatch,
) -> None:
    result, _, _, chunk = invoke(
        monkeypatch,
        query="What does the document prescribe?",
        history="",
        evidence=True,
        cited=True,
    )
    citation = result.citations[0]
    assert citation.quote == chunk.content[:500]
    assert "AFTER_SNAPSHOT_MARKER" not in citation.quote
    assert getattr(citation, "chunk_content", None) == chunk.content


@pytest.mark.parametrize("mode", ["grounded", "hybrid"])
def test_prompt_requires_claim_level_support_and_scope(mode: str) -> None:
    rules = answers.build_system_rules(mode=cast(AnswerMode, mode))
    for phrase in [
        "Every verifiable document claim",
        "necessary",
        "sufficient",
        "not specified",
        "Only answer",
        "history is not document evidence",
    ]:
        assert phrase in rules
    assert "untrusted" in rules
    assert '"answer"' in rules and '"citations"' in rules


def test_max_five_citation_order_remains_unchanged(monkeypatch: MonkeyPatch) -> None:
    chunks = [
        Chunk(
            source_id=uuid.uuid4(),
            ordinal=i,
            content=f"Evidence {i}",
            char_start=0,
            char_end=10,
        )
        for i in range(7)
    ]
    ids = [
        str(uuid.uuid4()),
        str(chunks[6].id),
        str(chunks[2].id),
        str(chunks[6].id),
        str(chunks[5].id),
        str(chunks[1].id),
        str(chunks[0].id),
    ]
    monkeypatch.setattr(
        answers,
        "retrieve_chunks",
        lambda **_: [
            RetrievedChunk(chunk=c, score=1.0, source_display_name="s.txt")
            for c in chunks
        ],
    )
    result = answers.answer_question(
        session=cast(Session, None),
        notebook_id=uuid.uuid4(),
        query="Explain the document.",
        chat_provider=ChatStub(ids),
        embedding_provider=EmbeddingStub(),
    )
    assert [c.chunk_id for c in result.citations] == [
        chunks[i].id for i in [6, 2, 5, 1]
    ]
