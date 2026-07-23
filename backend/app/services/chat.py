import json
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings


class ChatError(Exception):
    """Raised when the configured chat provider cannot produce a safe answer."""


@dataclass(frozen=True)
class ModelAnswer:
    content: str
    citation_chunk_ids: list[str]


class ChatProvider(Protocol):
    def answer(self, *, prompt: str) -> ModelAnswer: ...


class OpenAICompatibleChatProvider:
    def answer(self, *, prompt: str) -> ModelAnswer:
        if not settings.LLM_BASE_URL or not settings.LLM_API_KEY or not settings.LLM_MODEL:
            raise ChatError(
                "Chat is not configured. Set LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL."
            )

        endpoint = f"{str(settings.LLM_BASE_URL).rstrip('/')}/chat/completions"
        try:
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                json={
                    "model": settings.LLM_MODEL,
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


def get_chat_provider() -> ChatProvider:
    return OpenAICompatibleChatProvider()
