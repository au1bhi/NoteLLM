"""Unit tests for incremental answer streaming.

Covers both layers of the pipeline: the feed-style parsers
(``ThinkSuppressor`` / ``JsonAnswerValueStream``) and the provider SSE loop in
``OpenAICompatibleChatProvider._chat_streaming``, using a scripted stub
response instead of a real provider endpoint.
"""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import cast

import pytest

from app.services import chat as chat_module
from app.services.chat import OpenAICompatibleChatProvider
from app.services.chat_stream import JsonAnswerValueStream, ThinkSuppressor
from app.services.provider_settings import ProviderConfig


def _config() -> ProviderConfig:
    return ProviderConfig(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="test-model",
        server_proxy_url="",
    )


class TestThinkSuppressor:
    def test_passthrough_without_think_tags(self) -> None:
        suppressor = ThinkSuppressor()
        assert suppressor.feed("hello world") == "hello world"
        assert suppressor.flush() == ""

    def test_filters_complete_block_single_feed(self) -> None:
        suppressor = ThinkSuppressor()
        out = suppressor.feed("A<think>secret reasoning</think>B")
        assert out == "AB"

    def test_filter_survives_arbitrary_chunk_boundaries(self) -> None:
        text = 'pre<think>hidden "</think>post'
        for size in range(1, len(text) + 1):
            suppressor = ThinkSuppressor()
            collected = "".join(
                suppressor.feed(text[i : i + size]) for i in range(0, len(text), size)
            )
            collected += suppressor.flush()
            assert collected == "prepost", f"chunk size {size}"

    def test_multiple_blocks(self) -> None:
        suppressor = ThinkSuppressor()
        out = suppressor.feed("<think>a</think>X<think>b</think>Y")
        assert out == "XY"

    def test_unclosed_block_holds_tail_but_flush_recovers_text(self) -> None:
        suppressor = ThinkSuppressor()
        out = suppressor.feed('{"answer": "ok"} <thi')
        assert out == '{"answer": "ok"} '
        # The trailing partial tag may still become real text.
        assert suppressor.flush() == "<thi"


class TestJsonAnswerValueStream:
    def _collect(self, envelope: str, *sizes: int) -> str:
        stream = JsonAnswerValueStream()
        if not sizes:
            sizes = (len(envelope),)
        index = 0
        step = 0
        pieces: list[str] = []
        while index < len(envelope):
            size = sizes[step % len(sizes)]
            pieces.append(stream.feed(envelope[index : index + size]))
            index += size
            step += 1
        return "".join(pieces)

    def test_plain_envelope(self) -> None:
        envelope = '{"answer": "你好，世界", "citations": []}'
        assert self._collect(envelope) == "你好，世界"
        assert self._collect(envelope, 1) == "你好，世界"  # one char at a time
        assert self._collect(envelope, 2, 5, 1) == "你好，世界"

    def test_escapes_decoded_across_feeds(self) -> None:
        envelope = r'{"answer": "line\nbreak \"quoted\" ok", "citations": []}'
        for size in range(1, 6):
            assert (
                self._collect(envelope, size)
                == 'line\nbreak "quoted" ok'
            ), f"chunk size {size}"

    def test_unicode_escape_split_across_feeds(self) -> None:
        # 你 = 你, split at every possible point inside the escape.
        envelope = '{"answer": "\\u4f60好", "citations": []}'
        raw = json.dumps({"answer": "你好", "citations": []})
        assert self._collect(raw, 3) == "你好"
        assert self._collect(raw, 7) == "你好"
        assert self._collect(envelope, 4) == "你好"

    def test_identifier_lookalike_key_is_ignored(self) -> None:
        envelope = '{"answers": [1], "answer": "real", "citations": []}'
        assert self._collect(envelope, 2) == "real"

    def test_stops_at_closing_quote(self) -> None:
        stream = JsonAnswerValueStream()
        stream.feed('{"answer": "visible", "citations": ["whatever"]}')
        assert stream.closed
        assert stream.feed('"more"]}') == ""

    def test_non_string_answer_value_stops_cleanly(self) -> None:
        envelope = '{"answer": 42, "citations": []}'
        assert self._collect(envelope, 3) == ""


def sse(content: str) -> str:
    return f'data: {json.dumps({"choices": [{"delta": {"content": content}}]})}'


class StubResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        lines: list[str] | None = None,
        body: str = "",
    ) -> None:
        self.status_code = status_code
        self._lines = lines or []
        self.text = body

    def iter_lines(self) -> Iterator[str]:
        return iter(self._lines)

    def read(self) -> bytes:
        return self.text.encode()

    def json(self) -> dict[str, object]:
        parsed = json.loads(self.text)
        assert isinstance(parsed, dict)
        return parsed


class TestChatStreamingLoop:
    def _patch_stream(
        self,
        monkeypatch: pytest.MonkeyPatch,
        responder_factory: Callable[[list[dict[str, object]]], StubResponse],
    ) -> list[dict[str, object]]:
        calls: list[dict[str, object]] = []

        @contextmanager
        def fake_stream(_method: str, _url: str, **kwargs: object):
            body = kwargs.get("json")
            calls.append(cast(dict[str, object], body if body else {}))
            yield responder_factory(calls)

        monkeypatch.setattr(chat_module, "pinned_stream", fake_stream)
        return calls

    def test_answer_streams_answer_value_only_and_parses_full_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        envelope = '{"answer": "你好世界", "citations": []}'
        pieces = ['{"ans', 'wer": "你', '好世', '界", ', '"cit', 'ations": []}']
        lines = [sse(piece) for piece in pieces]

        def responder(_calls: list[dict[str, object]]) -> StubResponse:
            return StubResponse(lines=lines)

        self._patch_stream(monkeypatch, responder)

        provider = OpenAICompatibleChatProvider(_config())
        deltas: list[str] = []
        answer = provider.answer(prompt="hi", on_delta=deltas.append)

        assert "".join(deltas) == "你好世界"
        assert answer.content == "你好世界"
        assert answer.citation_chunk_ids == []
        expected = chat_module.estimate_tokens("hi") + chat_module.estimate_tokens(
            envelope
        )
        assert provider.total_tokens_used == expected

    def test_usage_chunk_overrides_estimate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lines = [
            sse('{"answer": "hi", '),
            'data: {"choices": [], "usage": {"total_tokens": 123}}',
            "data: [DONE]",
        ]

        def responder(_calls: list[dict[str, object]]) -> StubResponse:
            return StubResponse(lines=lines)

        self._patch_stream(monkeypatch, responder)

        provider = OpenAICompatibleChatProvider(_config())
        deltas: list[str] = []
        provider.answer(prompt="q", on_delta=deltas.append)

        assert deltas == ["hi"]
        assert provider.total_tokens_used == 123

    def test_reasoning_deltas_never_reach_the_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        full = '<think>chain of thought</think>{"answer": "visible", "citations": []}'
        step = 4
        lines = [sse(full[i : i + step]) for i in range(0, len(full), step)]

        def responder(_calls: list[dict[str, object]]) -> StubResponse:
            return StubResponse(lines=lines)

        self._patch_stream(monkeypatch, responder)

        provider = OpenAICompatibleChatProvider(_config())
        deltas: list[str] = []
        answer = provider.answer(prompt="p", on_delta=deltas.append)

        assert "".join(deltas) == "visible"
        assert "thought" not in "".join(deltas)
        assert answer.content == "visible"

    def test_format_fallback_retries_once_without_response_format(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts: list[dict[str, object]] = []
        responders = [
            StubResponse(status_code=400, body='{"error": {"message": "response_format unsupported"}}'),
            StubResponse(lines=[sse('{"answer": "ok", "citations": []}')]),
        ]
        current = {"index": -1}

        @contextmanager
        def fake_stream(_method: str, _url: str, **kwargs: object):
            current["index"] += 1
            body = kwargs.get("json")
            attempts.append(cast(dict[str, object], body if body else {}))
            yield responders[current["index"]]

        monkeypatch.setattr(chat_module, "pinned_stream", fake_stream)

        provider = OpenAICompatibleChatProvider(_config())
        deltas: list[str] = []
        answer = provider.answer(prompt="q", on_delta=deltas.append)

        assert answer.content == "ok"
        assert len(attempts) == 2
        assert "response_format" in attempts[0]
        assert "response_format" not in attempts[1]
        # No duplicate emission from the failed first attempt.
        assert deltas == ["ok"]

    def test_provider_error_status_raises_chat_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def responder(_calls: list[dict[str, object]]) -> StubResponse:
            return StubResponse(
                status_code=429,
                body='{"error": {"message": "rate limited"}}',
            )

        self._patch_stream(monkeypatch, responder)

        provider = OpenAICompatibleChatProvider(_config())
        with pytest.raises(chat_module.ChatError, match="rate limited"):
            provider.answer(prompt="q", on_delta=(lambda _t: None))
