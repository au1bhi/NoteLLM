import re
import uuid
from dataclasses import dataclass

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import decrypt_secret
from app.core.ssrf import validate_outbound_url
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
    """True when the user configured their own (decryptable) chat API key."""
    if user_settings is None or not user_settings.chat_api_key:
        return False
    return bool(decrypt_secret(user_settings.chat_api_key))


def has_own_embedding_key(user_settings: UserProviderSettings | None) -> bool:
    """True when the user configured their own (decryptable) embedding key."""
    if user_settings is None or not user_settings.embedding_api_key:
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
    if user_key:
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
    if user_key:
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
    )
