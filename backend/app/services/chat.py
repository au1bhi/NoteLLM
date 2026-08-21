import json
import math
import re
import threading
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.ssrf import pinned_request, trusted_provider_request
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


def clean_json_text(text: str) -> str:
    """Strip thinking tags, markdown code fences, and extract JSON object."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if "```" in cleaned:
        cleaned = re.sub(r"```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace("```", "")
    cleaned = cleaned.strip()
    if "{" in cleaned and "}" in cleaned:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        return cleaned[start:end]
    return cleaned


@dataclass(frozen=True)
class ModelAnswer:
    content: str
    citation_chunk_ids: list[str]


class ChatProvider(Protocol):
    def answer(self, *, prompt: str, system: str | None = None) -> ModelAnswer: ...
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
                "对话模型尚未配置。请在设置中填写 API Key，或由管理员配置服务端模型。"
            )

        endpoint = (
            f"{resolve_api_base(self.config.base_url, self.config.api_format)}"
            "/chat/completions"
        )
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        request_body: dict[str, object] = {
            "model": self.config.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }

        def _do_post(body: dict[str, object]) -> httpx.Response:
            if self.config.server_proxy_url:
                return trusted_provider_request(
                    "POST",
                    endpoint,
                    proxy_url=self.config.server_proxy_url,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    json=body,
                    timeout=60.0,
                )
            return pinned_request(
                "POST",
                endpoint,
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                json=body,
                timeout=60.0,
            )

        try:
            with _PROVIDER_SEMAPHORE:
                response = _do_post(request_body)
                if response.status_code == 400 and (
                    "response_format" in response.text or "format" in response.text
                ):
                    body_fallback = dict(request_body)
                    body_fallback.pop("response_format", None)
                    response = _do_post(body_fallback)

            if response.status_code != 200:
                err_msg = ""
                try:
                    err_payload = response.json()
                    if isinstance(err_payload, dict):
                        err_data = err_payload.get("error")
                        if isinstance(err_data, dict):
                            err_msg = str(err_data.get("message") or "")
                        elif isinstance(err_data, str):
                            err_msg = err_data
                        elif "message" in err_payload:
                            err_msg = str(err_payload["message"])
                except Exception:
                    pass
                if not err_msg:
                    err_msg = response.text[:200]
                raise ChatError(
                    f"模型服务商返回错误 ({response.status_code})：{err_msg}"
                )

            payload = response.json()
            choices = payload.get("choices")
            if not isinstance(choices, list) or not choices:
                raise ChatError("对话模型未返回有效响应 choices")
            first_choice = choices[0]
            if not isinstance(first_choice, dict):
                raise ChatError("对话模型未返回有效 choices 结构体")
            message_obj = first_choice.get("message")
            if not isinstance(message_obj, dict):
                raise ChatError("对话模型未返回有效 message")
            content = message_obj.get("content")
            if not isinstance(content, str):
                reasoning = message_obj.get("reasoning_content")
                if isinstance(reasoning, str) and reasoning.strip():
                    content = reasoning
                else:
                    raise ChatError("对话模型未返回有效文本内容")

            usage = payload.get("usage")
            tokens: object = None
            if isinstance(usage, dict):
                tokens = usage.get("total_tokens")
                if isinstance(tokens, (int, float)):
                    with self._tokens_lock:
                        self.total_tokens_used += int(tokens)
            if not tokens:
                with self._tokens_lock:
                    self.total_tokens_used += estimate_tokens(prompt) + estimate_tokens(
                        content
                    )
        except ChatError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as error:
            raise ChatError(
                f"对话模型通信失败：{type(error).__name__} {error}"
            ) from error
        return content

    def complete_json(
        self, *, prompt: str, system: str | None = None
    ) -> dict[str, object]:
        """Ask the provider for any JSON object (used for structured generation)."""
        raw = self._chat(prompt=prompt, system=system)
        cleaned = clean_json_text(raw)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise ChatError("对话模型未返回有效 JSON") from error
        if not isinstance(parsed, dict):
            raise ChatError("对话模型未返回 JSON 对象")
        return parsed

    def answer(self, *, prompt: str, system: str | None = None) -> ModelAnswer:
        raw_content = self._chat(prompt=prompt, system=system)
        cleaned = clean_json_text(raw_content)
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                raw_answer = data.get("answer")
                raw_citations = data.get("citations", [])
                if isinstance(raw_answer, str) and raw_answer.strip():
                    citations = (
                        [
                            citation
                            for citation in raw_citations
                            if isinstance(citation, str)
                        ]
                        if isinstance(raw_citations, list)
                        else []
                    )
                    return ModelAnswer(
                        content=raw_answer.strip(),
                        citation_chunk_ids=citations,
                    )
        except Exception:
            pass

        clean_text = re.sub(
            r"<think>.*?</think>", "", raw_content, flags=re.DOTALL
        ).strip()
        if clean_text:
            return ModelAnswer(
                content=clean_text,
                citation_chunk_ids=[],
            )
        raise ChatError("对话模型未返回有效答案内容")


def get_chat_provider(config: ProviderConfig | None = None) -> ChatProvider:
    if config is None:
        config = ProviderConfig(
            base_url=str(settings.LLM_BASE_URL) if settings.LLM_BASE_URL else "",
            api_key=settings.LLM_API_KEY or "",
            model=settings.LLM_MODEL or "",
            server_proxy_url=(
                str(settings.SERVER_PROVIDER_PROXY_URL)
                if settings.SERVER_PROVIDER_PROXY_URL
                else ""
            ),
        )
    return OpenAICompatibleChatProvider(config)
