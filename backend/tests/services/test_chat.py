from typing import Any

import httpx
import pytest

from app.services.chat import ChatError, OpenAICompatibleChatProvider
from app.services.provider_settings import ProviderConfig


def test_server_chat_provider_uses_explicit_trusted_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_trusted_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        captured["method"] = method
        captured["url"] = url
        captured["proxy_url"] = kwargs["proxy_url"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"answer":"ok","citations":[]}'}}]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(
        "app.services.chat.provider_request", fake_trusted_request
    )
    provider = OpenAICompatibleChatProvider(
        ProviderConfig(
            base_url="https://models.example/v1",
            api_key="server-key",
            model="chat",
            server_proxy_url="http://host.docker.internal:7890",
        )
    )

    assert provider.answer(prompt="hello").content == "ok"
    assert captured == {
        "method": "POST",
        "url": "https://models.example/v1/chat/completions",
        "proxy_url": "http://host.docker.internal:7890",
    }


def test_complete_json_keeps_unconfigured_provider_message() -> None:
    provider = OpenAICompatibleChatProvider(
        ProviderConfig(base_url="", api_key="", model="")
    )

    with pytest.raises(ChatError, match="对话模型尚未配置"):
        provider.complete_json(prompt="生成计划")


def test_complete_json_rejects_non_object_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "[1, 2]"}}]},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr("app.services.chat.provider_request", fake_request)
    provider = OpenAICompatibleChatProvider(
        ProviderConfig(
            base_url="https://models.example/v1",
            api_key="key",
            model="chat",
        )
    )

    with pytest.raises(ChatError, match="对话模型未返回 JSON 对象"):
        provider.complete_json(prompt="生成计划")


# --- Blocking-path retry, error mapping and payload validation --------------


def _response(status: int, payload: object) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload if not isinstance(payload, str) else None,
        text=payload if isinstance(payload, str) else None,
        request=httpx.Request("POST", "https://models.example/v1/chat"),
    )


def test_is_format_rejection_matches_only_format_complaints() -> None:
    from app.services.chat import _is_format_rejection

    assert _is_format_rejection("Response_Format is not supported") is True
    assert _is_format_rejection('field "format" invalid') is True
    assert _is_format_rejection('unsupported field: "format"') is True
    assert _is_format_rejection("invalid api key") is False
    assert _is_format_rejection("") is False


def test_blocking_retry_once_without_response_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleChatProvider(
        ProviderConfig(base_url="https://models.example/v1", api_key="k", model="m")
    )
    bodies: list[dict[str, object]] = []

    def fake_request(_method: str, _url: str, **kwargs: Any) -> httpx.Response:
        bodies.append(dict(kwargs["json"]))
        if len(bodies) == 1:
            return _response(400, {"error": {"message": "response_format unsupported"}})
        return _response(
            200,
            {"choices": [{"message": {"content": '{"answer":"ok","citations":[]}'}}]},
        )

    monkeypatch.setattr("app.services.chat.provider_request", fake_request)
    assert provider.answer(prompt="hi").content == "ok"
    assert "response_format" in bodies[0]
    assert "response_format" not in bodies[1]
    assert bodies[1]["messages"] == bodies[0]["messages"]


def test_blocking_non_200_after_retry_maps_to_chat_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleChatProvider(
        ProviderConfig(base_url="https://models.example/v1", api_key="k", model="m")
    )
    monkeypatch.setattr(
        "app.services.chat.provider_request",
        lambda *a, **k: _response(503, {"error": {"message": "upstream down"}}),
    )
    with pytest.raises(ChatError, match="503.*upstream down"):
        provider.complete_json(prompt="生成计划")


def test_provider_error_message_extraction_variants() -> None:
    provider = OpenAICompatibleChatProvider(
        ProviderConfig(base_url="https://models.example/v1", api_key="k", model="m")
    )
    nested = provider._provider_error_message(
        _response(500, {"error": {"message": "boom"}})
    )
    flat_str = provider._provider_error_message(_response(500, {"error": "plain"}))
    top_level = provider._provider_error_message(_response(500, {"message": "top"}))
    junk = provider._provider_error_message(_response(500, "not-json-body"))
    assert (nested, flat_str, top_level) == ("boom", "plain", "top")
    assert "not-json-body" in junk
    assert len(junk) <= 200


def test_blocking_payload_validation_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleChatProvider(
        ProviderConfig(base_url="https://models.example/v1", api_key="k", model="m")
    )

    def raiser(payload: object):
        def _inner(_method: str, _url: str, **_kw: Any) -> httpx.Response:
            return _response(200, payload)

        return _inner

    cases: list[tuple[object, str]] = [
        {"choices": []},                      # empty choices
        {"choices": ["nope"]},                # non-dict choice
        {"choices": [{"message": "text"}]},   # non-dict message
        {"choices": [{"message": {}}]},       # no content at all
        {"choices": [{"message": {"content": 42}}]},
    ]
    for payload, in [(c,) for c in cases]:
        monkeypatch.setattr("app.services.chat.provider_request", raiser(payload))
        with pytest.raises(ChatError, match="对话模型"):
            provider.complete_json(prompt="生成计划")


def test_reasoning_content_fallback_and_usage_estimation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleChatProvider(
        ProviderConfig(base_url="https://models.example/v1", api_key="k", model="m")
    )
    monkeypatch.setattr(
        "app.services.chat.provider_request",
        lambda *a, **k: _response(
            200,
            {
                "choices": [
                    {"message": {"content": None, "reasoning_content": "思考后的答案"}}
                ]
            },
        ),
    )
    answer = provider.answer(prompt="想想")
    assert answer.content == "思考后的答案"
    # No usage stats came back → estimation added tokens.
    assert provider.total_tokens_used > 0


def test_estimate_tokens_rules() -> None:
    from app.services.chat import estimate_tokens

    assert estimate_tokens("") == 0
    assert estimate_tokens("你好世界") == 4  # CJK ~1 token each
    assert estimate_tokens("abcd") == 1


def test_clean_json_text_extracts_object_from_fences() -> None:
    from app.services.chat import clean_json_text

    fenced = '```json\n<think>x</think>{"answer":"好","citations":[]}\n```'
    assert clean_json_text(fenced) == '{"answer":"好","citations":[]}'
    assert clean_json_text("no braces here") == "no braces here"
