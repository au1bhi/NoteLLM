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
        "app.services.chat.trusted_provider_request", fake_trusted_request
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

    monkeypatch.setattr("app.services.chat.pinned_request", fake_request)
    provider = OpenAICompatibleChatProvider(
        ProviderConfig(
            base_url="https://models.example/v1",
            api_key="key",
            model="chat",
        )
    )

    with pytest.raises(ChatError, match="对话模型未返回 JSON 对象"):
        provider.complete_json(prompt="生成计划")
