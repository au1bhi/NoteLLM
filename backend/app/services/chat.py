import json
import math
import threading
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.ssrf import pinned_request
from app.services.provider_settings import ProviderConfig, resolve_api_base

# Hard cap on a single answer's output tokens. Besides bounding latency, this
# keeps the real cost of one request inside the reserved quota margin, so a
# burst of concurrent questions cannot overspend the monthly allowance by far
# more than the reservation.
MAX_OUTPUT_TOKENS = 2000

# Bounds concurrent outbound provider calls per process. The chat/embedding
# calls run on the shared anyio worker threadpool (default 40 workers); without
# a bound a single authenticated BYOK user pointing at a slow endpoint could
# pin all workers and stall every other request (availability DoS).
_PROVIDER_SEMAPHORE = threading.Semaphore(8)


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
    def answer(
        self, *, prompt: str, system: str | None = None
    ) -> ModelAnswer: ...
    def complete_json(
        self, *, prompt: str, system: str | None = None
    ) -> dict[str, object]: ...


class OpenAICompatibleChatProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.total_tokens_used = 0
        self._tokens_lock = threading.Lock()

    def _chat(self, *, prompt: str, system: str | None = None) -> str:
        if not self.config.base_url or not self.config.api_key or not self.config.model:
            raise ChatError(
                "Chat is not configured. Add your API key in Settings, or set "
                "LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL on the server."
            )

        endpoint = (
            f"{resolve_api_base(self.config.base_url, self.config.api_format)}"
            "/chat/completions"
        )
        messages: list[dict[str, str]] = []
        if system:
            # A system role gives the rules a hard boundary from the untrusted
            # user content (question + retrieved source text), which makes
            # prompt injection via uploaded documents much less effective.
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            with _PROVIDER_SEMAPHORE:
                response = pinned_request(
                    "POST",
                    endpoint,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    json={
                        "model": self.config.model,
                        "messages": messages,
                        "response_format": {"type": "json_object"},
                        "temperature": 0,
                        "max_tokens": MAX_OUTPUT_TOKENS,
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
                    with self._tokens_lock:
                        self.total_tokens_used += int(tokens)
            if not tokens:
                # Providers that omit usage stats still need quota accounting.
                with self._tokens_lock:
                    self.total_tokens_used += estimate_tokens(prompt) + estimate_tokens(
                        content
                    )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as error:
            raise ChatError("对话模型未返回有效响应") from error
        return content

    def complete_json(
        self, *, prompt: str, system: str | None = None
    ) -> dict[str, object]:
        """Ask the provider for any JSON object (used for structured generation)."""
        try:
            parsed = json.loads(self._chat(prompt=prompt, system=system))
        except (json.JSONDecodeError, ChatError) as error:
            raise ChatError("对话模型未返回有效 JSON") from error
        if not isinstance(parsed, dict):
            raise ChatError("对话模型未返回 JSON 对象")
        return parsed

    def answer(self, *, prompt: str, system: str | None = None) -> ModelAnswer:
        data = self.complete_json(prompt=prompt, system=system)
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
