import json
import math
import re
import threading
from collections.abc import Callable, Sequence
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


def _safe_error_text(error: BaseException, secrets: Sequence[str] = ()) -> str:
    """Redact endpoints/URLs from provider error strings before echoing them.

    Upstream transport exceptions embed the operator-side base_url/proxy host;
    these must never reach a client through shared (server-billed) features.
    """
    return _safe_error_text_from_value(str(error), secrets)


def _safe_error_text_from_value(value: object, secrets: Sequence[str] = ()) -> str:
    """Shared redaction + length cap for any value surfaced to clients.

    Besides regex-based URL/``sk-``/Bearer redaction, any concrete secret
    string handed to ``secrets`` is removed by exact-substring replacement.
    A provider key that lacks the ``sk-`` prefix (an operator key, ``ak-…``,
    or raw hex) would otherwise survive the regex redactor if an upstream
    gateway echoes it bare in an error body — scrubbing the actual in-flight
    key closes that gap with zero false positives (exact match only).
    """
    text = re.sub(r"https?://[^\s'\"]+", "<endpoint-redacted>", str(value or ""))
    # Bearer tokens / OpenAI-style keys carried in Authorization headers or
    # echoed by upstream error bodies are redacted too.
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]+", r"\1<key-redacted>", text)
    text = re.sub(r"sk-[A-Za-z0-9_]+", "<key-redacted>", text)
    for secret in secrets:
        # Skip empty / too-short values: an 8-char floor avoids redacting
        # short common substrings that happen to appear in provider prose.
        if secret and len(secret) >= 8:
            text = text.replace(secret, "<key-redacted>")
    return text[:200]


# Hard cap on a single answer's output tokens. Besides bounding latency, this
# keeps the real cost of one request inside the reserved quota margin, so a
# burst of concurrent questions cannot overspend the monthly allowance by far
# more than the reservation.
MAX_OUTPUT_TOKENS = 4096

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


def _is_thinking_rejection(message: str) -> bool:
    """True when a 400 body blames the ``thinking`` option."""
    return "thinking" in message.lower()


def _should_disable_thinking(config: ProviderConfig) -> bool:
    """True when requests should include ``thinking: {"type": "disabled"}`` upfront.

    Hybrid DeepSeek models (e.g. ``deepseek-v4-flash``, ``deepseek-flash``)
    enable reasoning by default and can spend 30–60s in ``reasoning_content``
    before emitting answer JSON. Dedicated ``reasoner`` / ``-r1`` models
    cannot disable thinking and are left untouched.
    """
    if settings.LLM_THINKING_ENABLED:
        return False
    model_lower = config.model.strip().lower()
    base_lower = config.base_url.strip().lower()
    if (
        "reasoner" in model_lower
        or model_lower.endswith("-r1")
        or "-r1-" in model_lower
    ):
        return False
    return "deepseek" in model_lower or "api.deepseek.com" in base_lower


def _is_cjk(char: str) -> bool:
    """CJK punctuation, kana, extended-A/compat ideographs, and fullwidth forms
    each cost roughly one token; the old U+4E00–U+9FFF range alone missed them."""
    o = ord(char)
    return 0x3000 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or 0xFF00 <= o <= 0xFFEF


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
                    return _safe_error_text_from_value(
                        err_data.get("message"), [self.config.api_key]
                    )
                if isinstance(err_data, str):
                    return _safe_error_text_from_value(err_data, [self.config.api_key])
                if "message" in err_payload:
                    return _safe_error_text_from_value(
                        err_payload["message"], [self.config.api_key]
                    )
        except Exception:
            pass
        return _safe_error_text_from_value(response.text[:200], [self.config.api_key])

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
        if _should_disable_thinking(self.config):
            body["thinking"] = {"type": "disabled"}
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
    ) -> tuple[str | None, bool]:
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
        finish_reason: str | None = None
        saw_reasoning = False
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
                if isinstance(first_choice, dict):
                    fr = first_choice.get("finish_reason")
                    if isinstance(fr, str) and fr:
                        finish_reason = fr
                    delta_obj = first_choice.get("delta", {})
                else:
                    delta_obj = {}
                if isinstance(delta_obj, dict):
                    reasoning_piece = delta_obj.get("reasoning_content")
                    if isinstance(reasoning_piece, str) and reasoning_piece:
                        saw_reasoning = True
                    piece = delta_obj.get("content")
                else:
                    piece = None
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
        return finish_reason, saw_reasoning

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
            return self._chat_blocking(
                endpoint=endpoint, messages=messages, prompt=prompt
            )
        except ChatError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as error:
            raise ChatError(
                f"对话模型通信失败：{type(error).__name__} "
                f"{_safe_error_text(error, [self.config.api_key])}"
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
        raw_parts: list[str] = []
        finish_reason: str | None = None
        saw_reasoning = False
        try:
            with _PROVIDER_SEMAPHORE:
                body = request_body
                format_fallback_tried = False
                thinking_stripped = False
                exhaustion_retry_tried = False
                while True:
                    try:
                        finish_reason, saw_reasoning = self._attempt_stream(
                            endpoint=endpoint,
                            body=body,
                            prompt=prompt,
                            on_delta=on_delta,
                            raw_parts=raw_parts,
                        )
                        if (
                            not "".join(raw_parts).strip()
                            and finish_reason == "length"
                            and saw_reasoning
                            and "thinking" not in body
                            and not thinking_stripped
                            and not exhaustion_retry_tried
                        ):
                            # Reasoning models can spend the whole output cap in
                            # reasoning_content; zero deltas reached the client,
                            # so retry once with thinking disabled.
                            exhaustion_retry_tried = True
                            raw_parts.clear()
                            body = {**body, "thinking": {"type": "disabled"}}
                            continue
                        break
                    except _ProviderStatus as status_error:
                        if (
                            status_error.status_code == 400
                            and not exhaustion_retry_tried
                            and "thinking" in body
                            and not thinking_stripped
                            and _is_thinking_rejection(status_error.message)
                        ):
                            # Strip upfront thinking option if an OpenAI-compatible
                            # gateway rejects it; a 400 precedes any body bytes so
                            # zero deltas were emitted.
                            thinking_stripped = True
                            body = {
                                key: val
                                for key, val in body.items()
                                if key != "thinking"
                            }
                            continue
                        if (
                            status_error.status_code == 400
                            and "response_format" in body
                            and not format_fallback_tried
                            and _is_format_rejection(status_error.message)
                        ):
                            # Some OpenAI-compatible gateways reject
                            # response_format; retry once without it. A 400
                            # precedes any body bytes, so no deltas were sent
                            # under the failed attempt.
                            format_fallback_tried = True
                            body = {
                                key: val
                                for key, val in body.items()
                                if key != "response_format"
                            }
                            continue
                        if exhaustion_retry_tried and status_error.status_code == 400:
                            raise ChatError(
                                "对话模型在思考阶段耗尽了输出长度上限，未能生成正文，"
                                "请精简问题或切换非思考模型重试"
                            ) from None
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
                f"对话模型通信失败：{type(error).__name__} "
                f"{_safe_error_text(error, [self.config.api_key])}"
            ) from error
        if (
            not "".join(raw_parts).strip()
            and finish_reason == "length"
            and saw_reasoning
        ):
            raise ChatError(
                "对话模型在思考阶段耗尽了输出长度上限，未能生成正文，"
                "请精简问题或切换非思考模型重试"
            )
        return "".join(raw_parts)

    def _record_blocking_usage(
        self, payload: dict[str, object], *, prompt: str, content: str
    ) -> None:
        usage = payload.get("usage")
        tokens: object = None
        if isinstance(usage, dict):
            tokens = usage.get("total_tokens")
        prompt_cost = estimate_tokens(prompt)
        if isinstance(tokens, (int, float)):
            # Floor reported usage at the prompt cost to prevent a provider
            # from under-reporting and zeroing out the bill via settle_usage.
            actual = max(int(tokens), prompt_cost)
        else:
            actual = prompt_cost + estimate_tokens(content)
        with self._tokens_lock:
            self.total_tokens_used += actual

    @staticmethod
    def _parse_blocking_choice(
        payload: dict[str, object],
    ) -> tuple[object, object, object]:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ChatError("对话模型未返回有效响应 choices")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ChatError("对话模型未返回有效 choices 结构体")
        message_obj = first_choice.get("message")
        if not isinstance(message_obj, dict):
            raise ChatError("对话模型未返回有效 message")
        return (
            first_choice.get("finish_reason"),
            message_obj.get("content"),
            message_obj.get("reasoning_content"),
        )

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
            active_body = request_body
            thinking_rejected = False
            format_fallback_tried = False
            with _PROVIDER_SEMAPHORE:
                while True:
                    response = send(active_body)
                    if response.status_code != 400:
                        break
                    error_message = self._provider_error_message(response)
                    if (
                        "thinking" in active_body
                        and not thinking_rejected
                        and _is_thinking_rejection(error_message)
                    ):
                        # Strip upfront thinking option if an OpenAI-compatible
                        # gateway rejects the non-standard field.
                        thinking_rejected = True
                        active_body = {
                            key: val
                            for key, val in active_body.items()
                            if key != "thinking"
                        }
                        continue
                    if (
                        "response_format" in active_body
                        and not format_fallback_tried
                        and _is_format_rejection(error_message)
                    ):
                        # Some OpenAI-compatible gateways reject response_format;
                        # retry once without it.
                        format_fallback_tried = True
                        active_body = {
                            key: val
                            for key, val in active_body.items()
                            if key != "response_format"
                        }
                        continue
                    break

            if response.status_code != 200:
                raise ChatError(
                    f"模型服务商返回错误 ({response.status_code})："
                    f"{self._provider_error_message(response)}"
                )

            payload = response.json()
            finish_reason, content, reasoning = self._parse_blocking_choice(payload)
            if (
                (not isinstance(content, str) or not content.strip())
                and finish_reason == "length"
                and isinstance(reasoning, str)
                and reasoning.strip()
            ):
                self._record_blocking_usage(payload, prompt=prompt, content="")
                if "thinking" in active_body or thinking_rejected:
                    raise ChatError(
                        "对话模型在思考阶段耗尽了输出长度上限，未能生成正文，"
                        "请精简问题或切换非思考模型重试"
                    )
                with _PROVIDER_SEMAPHORE:
                    retry_resp = send({**active_body, "thinking": {"type": "disabled"}})
                if retry_resp.status_code != 200:
                    raise ChatError(
                        "对话模型在思考阶段耗尽了输出长度上限，未能生成正文，"
                        "请精简问题或切换非思考模型重试"
                    )
                retry_payload = retry_resp.json()
                retry_fr, retry_content, retry_reasoning = self._parse_blocking_choice(
                    retry_payload
                )
                if isinstance(retry_content, str) and retry_content.strip():
                    self._record_blocking_usage(
                        retry_payload, prompt=prompt, content=retry_content
                    )
                    return retry_content
                self._record_blocking_usage(retry_payload, prompt=prompt, content="")
                if (
                    retry_fr != "length"
                    and retry_content is None
                    and isinstance(retry_reasoning, str)
                    and retry_reasoning.strip()
                ):
                    return retry_reasoning
                raise ChatError(
                    "对话模型在思考阶段耗尽了输出长度上限，未能生成正文，"
                    "请精简问题或切换非思考模型重试"
                )

            if not isinstance(content, str):
                if isinstance(reasoning, str) and reasoning.strip():
                    content = reasoning
                else:
                    raise ChatError("对话模型未返回有效文本内容")

            self._record_blocking_usage(payload, prompt=prompt, content=content)
        except ChatError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as error:
            raise ChatError(
                f"对话模型通信失败：{type(error).__name__} "
                f"{_safe_error_text(error, [self.config.api_key])}"
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
