import json
import math
import re
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.ssrf import (
    provider_request,
    provider_stream,
)
from app.services.chat_stream import JsonAnswerValueStream, ThinkSuppressor
from app.services.provider_settings import ProviderConfig, resolve_api_base


def _safe_error_text(error: BaseException) -> str:
    """Redact endpoints/URLs from provider error strings before echoing them.

    Upstream transport exceptions embed the operator-side base_url/proxy host;
    these must never reach a client through shared (server-billed) features.
    """
    return _safe_error_text_from_value(str(error))


def _safe_error_text_from_value(value: object) -> str:
    """Shared redaction + length cap for any value surfaced to clients."""
    text = re.sub(r"https?://[^\s'\"]+", "<endpoint-redacted>", str(value or ""))
    # Bearer tokens / OpenAI-style keys carried in Authorization headers or
    # echoed by upstream error bodies are redacted too.
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]+", r"\1<key-redacted>", text)
    text = re.sub(r"sk-[A-Za-z0-9_]+", "<key-redacted>", text)
    return text[:200]


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


class _ProviderStatus(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"{status_code}: {message}")
        self.status_code = status_code
        self.message = message


def _is_format_rejection(message: str) -> bool:
    """True when a 400 body blames the ``response_format`` option.

    Match the explicit option name (OpenAI/vLLM style) or a JSON-key-style
    mention of ``format``; unrelated prose containing the word must not spend
    a second billable request on a retry that will fail the same way.
    """
    lowered = message.lower()
    return "response_format" in lowered or '"format"' in lowered


def _is_cjk(char: str) -> bool:
    """CJK punctuation, kana, extended-A/compat ideographs, and fullwidth forms
    each cost roughly one token; the old U+4E00–U+9FFF range alone missed them."""
    o = ord(char)
    return (
        0x3000 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or 0xFF00 <= o <= 0xFFEF
    )


def estimate_tokens(text: str) -> int:
    """Approximate token count when a provider omits usage stats.

    CJK characters are counted as roughly one token each and other characters
    as a quarter, which is a reasonable middle ground across common LLM
    tokenizers. Used only for quota accounting.
    """
    if not text:
        return 0
    cjk = sum(1 for char in text if _is_cjk(char))
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
    # Total provider tokens billed through this instance so far; used for quota
    # accounting. Declared on the protocol so call sites can read it directly.
    total_tokens_used: int

    def answer(
        self,
        *,
        prompt: str,
        system: str | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> ModelAnswer: ...

    def complete_json(
        self, *, prompt: str, system: str | None = None
    ) -> dict[str, object]: ...


class OpenAICompatibleChatProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.total_tokens_used = 0
        self._tokens_lock = threading.Lock()

    def _provider_error_message(self, response: httpx.Response) -> str:
        try:
            err_payload = response.json()
            if isinstance(err_payload, dict):
                err_data = err_payload.get("error")
                if isinstance(err_data, dict):
                    return _safe_error_text_from_value(err_data.get("message"))
                if isinstance(err_data, str):
                    return _safe_error_text_from_value(err_data)
                if "message" in err_payload:
                    return _safe_error_text_from_value(err_payload["message"])
        except Exception:
            pass
        return _safe_error_text_from_value(response.text[:200])

    def _request_body(
        self,
        *,
        messages: list[dict[str, str]],
        streaming: bool,
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self.config.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
        if streaming:
            body["stream"] = True
            # Non-OpenAI gateways ignore unknown options; OpenAI needs it to
            # include usage stats in the final chunk.
            body["stream_options"] = {"include_usage": True}
        return body

    def _open_stream(
        self,
        *,
        endpoint: str,
        headers: dict[str, str],
        body: dict[str, object],
    ) -> AbstractContextManager[httpx.Response]:
        return provider_stream(
            "POST",
            endpoint,
            proxy_url=self.config.server_proxy_url or None,
            headers=headers,
            json=body,
            timeout=60.0,
        )

    def _attempt_stream(
        self,
        *,
        endpoint: str,
        body: dict[str, object],
        prompt: str,
        on_delta: Callable[[str], None],
        raw_parts: list[str],
    ) -> None:
        """Run one streaming attempt; raises _ProviderStatus on HTTP errors.

        Appends the full think-filtered payload text to ``raw_parts`` so the
        caller can authoritatively parse answer+citations afterwards. Only the
        decoded ``"answer"`` value is forwarded to ``on_delta`` (display view);
        raw envelope/reasoning text never reaches the client. Tokens are
        recorded here; a rejected attempt (non-200) records none.
        """
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        suppressor = ThinkSuppressor()
        value_stream = JsonAnswerValueStream()
        usage_tokens: int | None = None
        with self._open_stream(
            endpoint=endpoint, headers=headers, body=body
        ) as response:
            if response.status_code != 200:
                # Inside a streaming context the body isn't buffered yet;
                # materialize the (small) error document before inspecting it.
                response.read()
                raise _ProviderStatus(
                    response.status_code,
                    self._provider_error_message(response),
                )
            for line in response.iter_lines():
                line = line.strip()
                if not line.startswith("data:") or line == "data:":
                    continue
                payload_text = line[len("data:") :].strip()
                if payload_text == "[DONE]":
                    break
                try:
                    payload = json.loads(payload_text)
                except json.JSONDecodeError:
                    continue
                usage = payload.get("usage")
                if isinstance(usage, dict) and isinstance(
                    usage.get("total_tokens"), (int, float)
                ):
                    usage_tokens = int(usage["total_tokens"])
                choices = payload.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                first_choice = choices[0]
                delta_obj = (
                    first_choice.get("delta", {})
                    if isinstance(first_choice, dict)
                    else {}
                )
                piece = (
                    delta_obj.get("content")
                    if isinstance(delta_obj, dict)
                    else None
                )
                if not isinstance(piece, str) or not piece:
                    continue
                filtered = suppressor.feed(piece)
                if filtered:
                    raw_parts.append(filtered)
                visible = value_stream.feed(filtered)
                if visible:
                    on_delta(visible)

        tail = suppressor.flush()
        if tail:
            raw_parts.append(tail)
            visible_tail = value_stream.feed(tail)
            if visible_tail:
                on_delta(visible_tail)
        prompt_cost = estimate_tokens(prompt)
        if usage_tokens is not None:
            # A provider that under-reports usage to near-zero could zero out the
            # bill via settle_usage. Floor the reported figure at the prompt's
            # own token cost, which the operator pays regardless of the response.
            actual = max(usage_tokens, prompt_cost)
        else:
            actual = prompt_cost + estimate_tokens("".join(raw_parts))
        with self._tokens_lock:
            self.total_tokens_used += actual

    def _chat(
        self,
        *,
        prompt: str,
        system: str | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> str:
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

        try:
            if on_delta is not None:
                return self._chat_streaming(
                    endpoint=endpoint,
                    messages=messages,
                    prompt=prompt,
                    on_delta=on_delta,
                )
            return self._chat_blocking(endpoint=endpoint, messages=messages, prompt=prompt)
        except ChatError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as error:
            raise ChatError(
                f"对话模型通信失败：{type(error).__name__} {_safe_error_text(error)}"
            ) from error

    def _chat_streaming(
        self,
        *,
        endpoint: str,
        messages: list[dict[str, str]],
        prompt: str,
        on_delta: Callable[[str], None],
    ) -> str:
        request_body = self._request_body(messages=messages, streaming=True)
        fallback_body = {
            key: val for key, val in request_body.items() if key != "response_format"
        }
        raw_parts: list[str] = []
        try:
            with _PROVIDER_SEMAPHORE:
                body = request_body
                format_fallback_tried = False
                while True:
                    try:
                        self._attempt_stream(
                            endpoint=endpoint,
                            body=body,
                            prompt=prompt,
                            on_delta=on_delta,
                            raw_parts=raw_parts,
                        )
                        break
                    except _ProviderStatus as status_error:
                        if (
                            status_error.status_code == 400
                            and not format_fallback_tried
                            and _is_format_rejection(status_error.message)
                        ):
                            # Some OpenAI-compatible gateways reject
                            # response_format; retry once without it. A 400
                            # precedes any body bytes, so no deltas were sent
                            # under the failed attempt.
                            format_fallback_tried = True
                            body = fallback_body
                            continue
                        raise ChatError(
                            f"模型服务商返回错误"
                            f" ({status_error.status_code})：{status_error.message}"
                        ) from None
        except ChatError:
            # A mid-stream network failure can leave partial text delivered;
            # surfacing the error lets callers send an error event too.
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as error:
            raise ChatError(
                f"对话模型通信失败：{type(error).__name__} {_safe_error_text(error)}"
            ) from error
        return "".join(raw_parts)

    def _chat_blocking(
        self,
        *,
        endpoint: str,
        messages: list[dict[str, str]],
        prompt: str,
    ) -> str:
        request_body = self._request_body(messages=messages, streaming=False)
        headers = {"Authorization": f"Bearer {self.config.api_key}"}

        def send(body: dict[str, object]) -> httpx.Response:
            return provider_request(
                "POST",
                endpoint,
                proxy_url=self.config.server_proxy_url or None,
                headers=headers,
                json=body,
                timeout=60.0,
            )

        try:
            with _PROVIDER_SEMAPHORE:
                response = send(request_body)
                if response.status_code == 400 and _is_format_rejection(
                    self._provider_error_message(response)
                ):
                    # Some OpenAI-compatible gateways reject response_format;
                    # retry once without it.
                    response = send(
                        {
                            key: val
                            for key, val in request_body.items()
                            if key != "response_format"
                        }
                    )

            if response.status_code != 200:
                raise ChatError(
                    f"模型服务商返回错误 ({response.status_code})："
                    f"{self._provider_error_message(response)}"
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
            prompt_cost = estimate_tokens(prompt)
            if isinstance(tokens, (int, float)):
                # Floor reported usage at the prompt cost to prevent a provider
                # from under-reporting and zeroing out the bill via settle_usage.
                actual = max(int(tokens), prompt_cost)
                with self._tokens_lock:
                    self.total_tokens_used += actual
            else:
                with self._tokens_lock:
                    self.total_tokens_used += prompt_cost + estimate_tokens(
                        content
                    )
        except ChatError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as error:
            raise ChatError(
                f"对话模型通信失败：{type(error).__name__} {_safe_error_text(error)}"
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

    def answer(
        self,
        *,
        prompt: str,
        system: str | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> ModelAnswer:
        raw_content = self._chat(prompt=prompt, system=system, on_delta=on_delta)
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
