import re
import uuid
from dataclasses import dataclass

import httpx
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import decrypt_secret
from app.core.ssrf import provider_request, validate_outbound_url
from app.models import UserProviderSettings

#: Trailing version path segment such as `/v1` or `/v4`.
_VERSION_PATH = re.compile(r"/v\d+$")

ApiFormat = str  # "openai" | "openai_v1"


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    api_key: str
    model: str
    # How to interpret base_url when building endpoint paths.
    #   "openai"     — base already contains the version path (e.g. .../v1).
    #   "openai_v1"  — base is a root domain; ensure a trailing /v1.
    api_format: str = "openai"
    # Set only for an operator-configured provider. User BYOK URLs always stay
    # on the strict DNS-pinned request path.
    server_proxy_url: str = ""


def resolve_api_base(base_url: str, api_format: str) -> str:
    """Return the API root the endpoints are appended to, honouring format."""
    base = base_url.rstrip("/")
    if not base:
        return ""
    if api_format == "openai_v1" and not _VERSION_PATH.search(base):
        return f"{base}/v1"
    return base


def mask_secret(value: str | None) -> str:
    """Return a masked preview of a secret (e.g. 'sk-***abcd'), or '' if unset."""
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


def load_user_provider_settings(
    session: Session, user_id: uuid.UUID
) -> UserProviderSettings | None:
    return session.exec(
        select(UserProviderSettings).where(UserProviderSettings.user_id == user_id)
    ).first()


def has_own_chat_key(user_settings: UserProviderSettings | None) -> bool:
    """True when the user is on their own chat endpoint with a decryptable key.

    A key without a user-supplied base_url is not BYOK: the call would land on
    the server's endpoint, so it is server-billed regardless of the key. This
    keeps the quota ``source`` consistent with ``effective_chat_config``.
    """
    if user_settings is None or not user_settings.chat_api_key:
        return False
    if not (user_settings.chat_base_url or "").strip():
        return False
    return bool(decrypt_secret(user_settings.chat_api_key))


def has_own_embedding_key(user_settings: UserProviderSettings | None) -> bool:
    """True when the user is on their own embedding endpoint with a decryptable key."""
    if user_settings is None or not user_settings.embedding_api_key:
        return False
    if not (user_settings.embedding_base_url or "").strip():
        return False
    return bool(decrypt_secret(user_settings.embedding_api_key))


def _first(*values: str | None) -> str:
    """Return the first non-empty value, else ''."""
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _endpoints_match(user_value: str | None, server_value: str | None) -> bool:
    return (user_value or "").strip() == (server_value or "").strip()


def effective_chat_config(
    user_settings: UserProviderSettings | None,
) -> ProviderConfig:
    server_base_url = str(settings.LLM_BASE_URL) if settings.LLM_BASE_URL else ""
    server_key = settings.LLM_API_KEY or ""
    server_model = settings.LLM_MODEL or ""
    user_base_url = user_settings.chat_base_url if user_settings else None
    base_url = _first(user_base_url, server_base_url)
    # Only the user-supplied endpoint is untrusted; validate it so the server
    # never calls internal/private targets.
    if user_base_url:
        base_url = validate_outbound_url(base_url)
    allow_server_fallback = not user_base_url or _endpoints_match(
        user_base_url, server_base_url
    )
    # Decrypt the user's own key if present; it is the only thing that makes a
    # call user-billed (and thus user-model) instead of server-billed.
    user_key = ""
    if user_settings and user_settings.chat_api_key:
        user_key = decrypt_secret(user_settings.chat_api_key) or ""
    # A user key is only meaningful against a user-supplied endpoint. Sending a
    # user key to the server's endpoint/proxy (when the user supplied no
    # base_url) only generates rejected requests that burn operator resources;
    # the operator key is the one authorized for the server endpoint.
    if user_key and user_base_url:
        api_key = user_key
        # User-billed: honoring the user's model choice only costs them.
        model = _first(
            user_settings.chat_model if user_settings else None, server_model
        )
    else:
        api_key = server_key if allow_server_fallback else ""
        # Server-billed: the operator pays, so only the operator's configured
        # model may be used. Honoring a user-supplied model here would let any
        # user pick an arbitrarily expensive model on the server's endpoint,
        # amplifying the operator's LLM spend without limit.
        model = server_model
    return ProviderConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        api_format=(
            user_settings.chat_api_format
            if user_settings and user_settings.chat_api_format
            else "openai"
        ),
        server_proxy_url=(
            str(settings.SERVER_PROVIDER_PROXY_URL)
            if not user_base_url and settings.SERVER_PROVIDER_PROXY_URL
            else ""
        ),
    )


def effective_embedding_config(
    user_settings: UserProviderSettings | None,
) -> ProviderConfig:
    server_base_url = (
        str(settings.EMBEDDING_BASE_URL) if settings.EMBEDDING_BASE_URL else ""
    )
    server_key = settings.EMBEDDING_API_KEY or ""
    server_model = settings.EMBEDDING_MODEL or ""
    user_base_url = user_settings.embedding_base_url if user_settings else None
    base_url = _first(user_base_url, server_base_url)
    if user_base_url:
        base_url = validate_outbound_url(base_url)
    allow_server_fallback = not user_base_url or _endpoints_match(
        user_base_url, server_base_url
    )
    user_key = ""
    if user_settings and user_settings.embedding_api_key:
        user_key = decrypt_secret(user_settings.embedding_api_key) or ""
    # A user key only counts against a user-supplied endpoint; a user key
    # without a user endpoint is not sent to the server endpoint/proxy.
    if user_key and user_base_url:
        api_key = user_key
        model = _first(
            user_settings.embedding_model if user_settings else None, server_model
        )
    else:
        api_key = server_key if allow_server_fallback else ""
        model = server_model
    return ProviderConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        api_format=(
            user_settings.embedding_api_format
            if user_settings and user_settings.embedding_api_format
            else "openai"
        ),
        server_proxy_url=(
            str(settings.SERVER_PROVIDER_PROXY_URL)
            if not user_base_url and settings.SERVER_PROVIDER_PROXY_URL
            else ""
        ),
    )


class ProviderProbeError(Exception):
    """A /models probe cannot proceed; ``detail`` is user-facing Chinese."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class ModelProbeTarget:
    root: str
    fallback_root: str | None
    api_key: str
    # Operator-proxy routing (server config only); BYOK always pins locally.
    proxy_url: str | None
    # Server-key probes spend shared quota, so callers must reserve tokens.
    billed_by_server: bool


def resolve_probe_target(
    *,
    session: Session,
    user_id: uuid.UUID,
    user_base_url: str,
    user_api_key: str,
    api_format: str,
) -> ModelProbeTarget:
    """Resolve the /models probe destination for a user's BYOK-or-server config.

    Empty base_url/api_key fall back to the server's configured LLM provider; a
    user-supplied base_url is validated against internal-network targets, and a
    masked-out key falls back to the one saved in provider settings (never to
    the *server* key on a user-controlled endpoint).
    """
    server_base = str(settings.LLM_BASE_URL) if settings.LLM_BASE_URL else ""
    server_key = settings.LLM_API_KEY or ""
    base = user_base_url.strip()
    key = user_api_key.strip()
    if base and not key:
        # The form masks stored keys, so an empty key may just mean "use mine".
        stored = load_user_provider_settings(session, user_id)
        if stored and stored.chat_api_key:
            key = decrypt_secret(stored.chat_api_key) or ""
        if not key:
            raise ProviderProbeError(422, "自定义 Base URL 需要同时提供 API Key")
    billed_by_server = not key
    base_url = base or server_base
    api_key = key or server_key
    if base:
        base_url = validate_outbound_url(base_url)
    if not base_url or not api_key:
        raise ProviderProbeError(422, "请先配置 API Key，或使用服务端默认配置")

    root = resolve_api_base(base_url, api_format)
    # When the base URL has no version path, the service may still serve the
    # OpenAI API under /v1 (common for aggregator gateways) — probe it.
    fallback_root: str | None = resolve_api_base(base_url, "openai_v1")
    if api_format == "openai_v1" or fallback_root == root:
        fallback_root = None
    # The server-configured endpoint rides the operator proxy when configured
    # (mirrors chat/embedding); a user-supplied BYOK URL stays DNS-pinned.
    proxy_url = (
        str(settings.SERVER_PROVIDER_PROXY_URL)
        if not base and settings.SERVER_PROVIDER_PROXY_URL
        else None
    )
    return ModelProbeTarget(
        root=root,
        fallback_root=fallback_root,
        api_key=api_key,
        proxy_url=proxy_url,
        billed_by_server=billed_by_server,
    )


def fetch_models_payload(root: str, api_key: str, *, proxy_url: str | None) -> object:
    response = provider_request(
        "GET",
        f"{root}/models",
        proxy_url=proxy_url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_model_ids(
    root: str,
    api_key: str,
    *,
    proxy_url: str | None,
    fallback_root: str | None = None,
) -> list[str]:
    try:
        payload = fetch_models_payload(root, api_key, proxy_url=proxy_url)
    except (httpx.HTTPError, ValueError, TypeError) as error:
        if fallback_root is None:
            raise ProviderProbeError(
                503, "无法获取模型，请检查 Base URL 与 API Key 是否正确"
            ) from error
        try:
            payload = fetch_models_payload(fallback_root, api_key, proxy_url=proxy_url)
        except (httpx.HTTPError, ValueError, TypeError) as fallback_error:
            raise ProviderProbeError(
                503,
                "无法获取模型。若 Base URL 是根域名（如 https://host），"
                "请在“API 格式”中选择“根域名，自动加 /v1”后重试。",
            ) from fallback_error

    data = payload.get("data", []) if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise ProviderProbeError(502, "模型提供方返回了异常数据")
    # Bind the extracted id to a variable so isinstance() narrows it — ty does
    # not narrow a repeated `item.get("id")` call expression.
    model_ids = [
        model_id
        for item in data
        if isinstance(item, dict)
        for model_id in [item.get("id")]
        if isinstance(model_id, str)
    ][:100]
    if not model_ids:
        raise ProviderProbeError(502, "模型提供方未返回任何模型")
    return model_ids
