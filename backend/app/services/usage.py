import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlmodel import Session, select

from app.core.config import settings
from app.models import UserProviderSettings, UserUsage
from app.services.provider_settings import (
    has_own_chat_key,
    has_own_embedding_key,
    load_user_provider_settings,
)

ProviderSource = Literal["server", "user", "none"]


class QuotaError(Exception):
    """Raised when a request billed to the server's free allowance is exhausted."""


def current_period(now: datetime | None = None) -> datetime:
    """Start of the current allowance period (calendar month, UTC)."""
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _same_period(a: datetime | None, b: datetime) -> bool:
    return a is not None and a.year == b.year and a.month == b.month


def _source(has_own_key: bool, server_configured: bool) -> ProviderSource:
    if has_own_key:
        return "user"
    if server_configured:
        return "server"
    return "none"


def _chat_server_configured() -> bool:
    return bool(settings.LLM_BASE_URL and settings.LLM_API_KEY and settings.LLM_MODEL)


def _embedding_server_configured() -> bool:
    return bool(
        settings.EMBEDDING_BASE_URL
        and settings.EMBEDDING_API_KEY
        and settings.EMBEDDING_MODEL
    )


def ensure_period(session: Session, user_id: uuid.UUID) -> UserUsage:
    """Return the user's usage row, rolling the counters into the current
    period (calendar month) when they were last updated in a previous one."""
    usage = session.exec(select(UserUsage).where(UserUsage.user_id == user_id)).first()
    period = current_period()
    if usage is None:
        usage = UserUsage(user_id=user_id, period_start=period)
    elif not _same_period(usage.period_start, period):
        usage.chat_tokens = 0
        usage.embedding_chars = 0
        usage.period_start = period
    session.add(usage)
    return usage


def record_usage(
    *,
    session: Session,
    user_id: uuid.UUID,
    chat_tokens: int = 0,
    embedding_chars: int = 0,
) -> None:
    """Accumulate usage for a user within the current allowance period."""
    usage = ensure_period(session, user_id)
    usage.chat_tokens += max(0, chat_tokens)
    usage.embedding_chars += max(0, embedding_chars)
    usage.updated_at = datetime.now(UTC)
    session.add(usage)
    session.commit()


def get_usage(session: Session, user_id: uuid.UUID) -> UserUsage:
    return ensure_period(session, user_id)


@dataclass(frozen=True)
class QuotaStatus:
    chat_tokens: int
    chat_quota: int | None
    chat_source: ProviderSource
    embedding_chars: int
    embedding_quota: int | None
    embedding_source: ProviderSource
    period_start: datetime | None


def quota_status(
    session: Session,
    user_id: uuid.UUID,
    user_settings: UserProviderSettings | None = None,
) -> QuotaStatus:
    """Describe the user's current usage and the free allowance that applies.

    A user who brings their own API key is billed on that key, so no allowance
    applies for that dimension (quota is None). The same is true when nothing
    is configured (source "none") — requests would fail, but never quota-block.
    """
    usage = ensure_period(session, user_id)
    if user_settings is None:
        user_settings = load_user_provider_settings(session, user_id)
    chat_source = _source(has_own_chat_key(user_settings), _chat_server_configured())
    embedding_source = _source(
        has_own_embedding_key(user_settings), _embedding_server_configured()
    )
    return QuotaStatus(
        chat_tokens=usage.chat_tokens,
        chat_quota=(
            settings.FREE_QUOTA_CHAT_TOKENS if chat_source == "server" else None
        ),
        chat_source=chat_source,
        embedding_chars=usage.embedding_chars,
        embedding_quota=(
            settings.FREE_QUOTA_EMBEDDING_CHARS
            if embedding_source == "server"
            else None
        ),
        embedding_source=embedding_source,
        period_start=usage.period_start,
    )


def _fmt(value: int) -> str:
    return f"{value:,}"


def check_chat_quota(
    session: Session,
    user_id: uuid.UUID,
    user_settings: UserProviderSettings | None = None,
) -> QuotaStatus:
    """Raise QuotaError when the server-billed chat allowance is exhausted."""
    status = quota_status(session, user_id, user_settings)
    if status.chat_quota is not None and status.chat_tokens >= status.chat_quota:
        raise QuotaError(
            "本月的免费对话额度已用完（"
            f"{_fmt(status.chat_tokens)} / {_fmt(status.chat_quota)} token）。"
            "你可以在“设置 → 模型配置”中填入自己的 API Key 继续使用，"
            "或等待下月额度刷新。"
        )
    return status


def check_embedding_quota(
    session: Session,
    user_id: uuid.UUID,
    user_settings: UserProviderSettings | None = None,
) -> QuotaStatus:
    """Raise QuotaError when the server-billed embedding allowance is exhausted."""
    status = quota_status(session, user_id, user_settings)
    if (
        status.embedding_quota is not None
        and status.embedding_chars >= status.embedding_quota
    ):
        raise QuotaError(
            "本月的免费嵌入额度已用完（"
            f"{_fmt(status.embedding_chars)} / {_fmt(status.embedding_quota)}"
            " 字符）。你可以在“设置 → 模型配置”中填入自己的 API Key 继续使用，"
            "或等待下月额度刷新。"
        )
    return status
