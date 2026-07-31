import uuid
from dataclasses import dataclass

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import decrypt_secret
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
        select(UserProviderSettings).where(
            UserProviderSettings.user_id == user_id
        )
    ).first()


def _first(*values: str | None) -> str:
    """Return the first non-empty value, else ''."""
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _resolve_key(stored_encrypted: str | None, server_key: str | None) -> str:
    if stored_encrypted:
        decrypted = decrypt_secret(stored_encrypted)
        if decrypted:
            return decrypted
    return server_key or ""


def effective_chat_config(
    user_settings: UserProviderSettings | None,
) -> ProviderConfig:
    return ProviderConfig(
        base_url=_first(
            user_settings.chat_base_url if user_settings else None,
            str(settings.LLM_BASE_URL) if settings.LLM_BASE_URL else None,
        ),
        api_key=_resolve_key(
            user_settings.chat_api_key if user_settings else None,
            settings.LLM_API_KEY,
        ),
        model=_first(
            user_settings.chat_model if user_settings else None,
            settings.LLM_MODEL,
        ),
    )


def effective_embedding_config(
    user_settings: UserProviderSettings | None,
) -> ProviderConfig:
    return ProviderConfig(
        base_url=_first(
            user_settings.embedding_base_url if user_settings else None,
            str(settings.EMBEDDING_BASE_URL)
            if settings.EMBEDDING_BASE_URL
            else None,
        ),
        api_key=_resolve_key(
            user_settings.embedding_api_key if user_settings else None,
            settings.EMBEDDING_API_KEY,
        ),
        model=_first(
            user_settings.embedding_model if user_settings else None,
            settings.EMBEDDING_MODEL,
        ),
    )
