import json
import math
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings
from app.services.provider_settings import ProviderConfig, resolve_api_base


class ChatError(Exception):
    """Raised when the configured chat provider cannot produce a safe answer."""


def estimate_tokens(text: str) -> int:
    """Approximate token count when a provider omits usage stats.

    CJK characters are counted as roughly one token each and other characters
    as a quarter, which is a reasonable middle ground across common LLM
    tokenizers. Used only for quota accounting.
    """
    if not text:
        return 0
    cjk = sum(1 for char in text if "一" <= char <= "鿿")
    other = len(text) - cjk
    return max(1, cjk + math.ceil(other / 4))


@dataclass(frozen=True)
class ModelAnswer:
    content: str
    citation_chunk_ids: list[str]


class ChatProvider(Protocol):
    def answer(self, *, prompt: str) -> ModelAnswer: ...
    def complete_json(self, *, prompt: str) -> dict[str, object]: ...


class OpenAICompatibleChatProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.total_tokens_used = 0

    def _chat(self, *, prompt: str) -> str:
        if not self.config.base_url or not self.config.api_key or not self.config.model:
            raise ChatError(
                "Chat is not configured. Add your API key in Settings, or set "
                "LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL on the server."
            )

        endpoint = (
            f"{resolve_api_base(self.config.base_url, self.config.api_format)}"
            "/chat/completions"
        )
        try:
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                json={
                    "model": self.config.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ChatError("对话模型未返回有效响应")
            usage = payload.get("usage")
            tokens: object = None
            if isinstance(usage, dict):
                tokens = usage.get("total_tokens")
                if isinstance(tokens, (int, float)):
                    self.total_tokens_used += int(tokens)
            if not tokens:
                # Providers that omit usage stats still need quota accounting.
                self.total_tokens_used += estimate_tokens(prompt) + estimate_tokens(
                    content
                )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as error:
            raise ChatError("对话模型未返回有效响应") from error
        return content

    def complete_json(self, *, prompt: str) -> dict[str, object]:
        """Ask the provider for any JSON object (used for structured generation)."""
        try:
            parsed = json.loads(self._chat(prompt=prompt))
        except (json.JSONDecodeError, ChatError) as error:
            raise ChatError("对话模型未返回有效 JSON") from error
        if not isinstance(parsed, dict):
            raise ChatError("对话模型未返回 JSON 对象")
        return parsed

    def answer(self, *, prompt: str) -> ModelAnswer:
        data = self.complete_json(prompt=prompt)
        raw_answer = data.get("answer")
        raw_citations = data.get("citations", [])
        if not isinstance(raw_answer, str) or not raw_answer.strip():
            raise ChatError("对话模型返回的答案格式无效")
        if not isinstance(raw_citations, list) or not all(
            isinstance(citation, str) for citation in raw_citations
        ):
            raise ChatError("对话模型返回的答案格式无效")
        return ModelAnswer(
            content=raw_answer.strip(),
            citation_chunk_ids=[
                citation for citation in raw_citations if isinstance(citation, str)
            ],
        )


def get_chat_provider(config: ProviderConfig | None = None) -> ChatProvider:
    if config is None:
        config = ProviderConfig(
            base_url=str(settings.LLM_BASE_URL) if settings.LLM_BASE_URL else "",
            api_key=settings.LLM_API_KEY or "",
            model=settings.LLM_MODEL or "",
        )
    return OpenAICompatibleChatProvider(config)
