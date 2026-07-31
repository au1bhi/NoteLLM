import json
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings
from app.services.provider_settings import ProviderConfig


class ChatError(Exception):
    """Raised when the configured chat provider cannot produce a safe answer."""


@dataclass(frozen=True)
class ModelAnswer:
    content: str
    citation_chunk_ids: list[str]


class ChatProvider(Protocol):
    def answer(self, *, prompt: str) -> ModelAnswer: ...


class OpenAICompatibleChatProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def answer(self, *, prompt: str) -> ModelAnswer:
        if (
            not self.config.base_url
            or not self.config.api_key
            or not self.config.model
        ):
            raise ChatError(
                "Chat is not configured. Add your API key in Settings, or set "
                "LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL on the server."
            )

        endpoint = f"{self.config.base_url.rstrip('/')}/chat/completions"
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
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            answer = parsed["answer"].strip()
            citations = parsed.get("citations", [])
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ChatError("The chat provider did not return a valid grounded answer") from error

        if not answer or not isinstance(citations, list) or not all(
            isinstance(citation, str) for citation in citations
        ):
            raise ChatError("The chat provider returned an invalid answer format")
        return ModelAnswer(content=answer, citation_chunk_ids=citations)


def get_chat_provider(config: ProviderConfig | None = None) -> ChatProvider:
    if config is None:
        config = ProviderConfig(
            base_url=str(settings.LLM_BASE_URL) if settings.LLM_BASE_URL else "",
            api_key=settings.LLM_API_KEY or "",
            model=settings.LLM_MODEL or "",
        )
    return OpenAICompatibleChatProvider(config)
