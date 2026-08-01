import uuid
from dataclasses import dataclass

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import decrypt_secret
from app.core.ssrf import validate_outbound_url
from app.models import UserProviderSettings


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    api_key: str
    model: str


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


def _resolve_key(
    stored_encrypted: str | None,
    server_key: str | None,
    *,
    allow_server_fallback: bool,
) -> str:
    """Return the user's decrypted key, falling back to the server key only
    when the endpoint is the server default (so the server key is never sent
    to a URL the user controls)."""
    if stored_encrypted:
        decrypted = decrypt_secret(stored_encrypted)
        if decrypted:
            return decrypted
    if allow_server_fallback:
        return server_key or ""
    return ""


def _endpoints_match(user_value: str | None, server_value: str | None) -> bool:
    return (user_value or "").strip() == (server_value or "").strip()


def effective_chat_config(
    user_settings: UserProviderSettings | None,
) -> ProviderConfig:
    server_base_url = str(settings.LLM_BASE_URL) if settings.LLM_BASE_URL else ""
    user_base_url = user_settings.chat_base_url if user_settings else None
    base_url = _first(user_base_url, server_base_url)
    # Only the user-supplied endpoint is untrusted; validate it so the server
    # never calls internal/private targets.
    if user_base_url:
        base_url = validate_outbound_url(base_url)
    return ProviderConfig(
        base_url=base_url,
        api_key=_resolve_key(
            user_settings.chat_api_key if user_settings else None,
            settings.LLM_API_KEY,
            allow_server_fallback=not user_base_url
            or _endpoints_match(user_base_url, server_base_url),
        ),
        model=_first(
            user_settings.chat_model if user_settings else None,
            settings.LLM_MODEL,
        ),
    )


def effective_embedding_config(
    user_settings: UserProviderSettings | None,
) -> ProviderConfig:
    server_base_url = (
        str(settings.EMBEDDING_BASE_URL) if settings.EMBEDDING_BASE_URL else ""
    )
    user_base_url = user_settings.embedding_base_url if user_settings else None
    base_url = _first(user_base_url, server_base_url)
    if user_base_url:
        base_url = validate_outbound_url(base_url)
    return ProviderConfig(
        base_url=base_url,
        api_key=_resolve_key(
            user_settings.embedding_api_key if user_settings else None,
            settings.EMBEDDING_API_KEY,
            allow_server_fallback=not user_base_url
            or _endpoints_match(user_base_url, server_base_url),
        ),
        model=_first(
            user_settings.embedding_model if user_settings else None,
            settings.EMBEDDING_MODEL,
        ),
    )
