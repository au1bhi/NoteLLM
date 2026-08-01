import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import text as sql_text
from sqlmodel import Session, select

from app.core.config import settings
from app.models import UserProviderSettings, UserUsage
from app.services.chat import estimate_tokens
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


# Reserve `:ct`/`:ec` atomically against the allowance. The `WHERE` guard runs
# under the row lock of the upsert, so concurrent reservations cannot both
# pass; returning no row means a concurrent request consumed the last of the
# allowance. A row from a previous period rolls its counters to the new period.
_RESERVE_SQL = sql_text(
    """
    INSERT INTO userusage (id, user_id, chat_tokens, embedding_chars, period_start, updated_at)
    VALUES (:id, :user_id, :ct, :ec, :period, :now)
    ON CONFLICT (user_id) DO UPDATE SET
      chat_tokens = CASE WHEN userusage.period_start IS DISTINCT FROM :period
                         THEN :ct ELSE userusage.chat_tokens + :ct END,
      embedding_chars = CASE WHEN userusage.period_start IS DISTINCT FROM :period
                             THEN :ec ELSE userusage.embedding_chars + :ec END,
      period_start = CASE WHEN userusage.period_start IS DISTINCT FROM :period
                          THEN :period ELSE userusage.period_start END,
      updated_at = :now
    WHERE (:ct = 0 OR CASE WHEN userusage.period_start IS DISTINCT FROM :period
                           THEN :ct ELSE userusage.chat_tokens + :ct END <= :chat_limit)
      AND (:ec = 0 OR CASE WHEN userusage.period_start IS DISTINCT FROM :period
                           THEN :ec ELSE userusage.embedding_chars + :ec END <= :emb_limit)
    RETURNING userusage.user_id
    """
)

_SETTLE_SQL = sql_text(
    """
    UPDATE userusage SET
      chat_tokens = GREATEST(0, chat_tokens + :chat_delta),
      embedding_chars = GREATEST(0, embedding_chars + :embedding_delta),
      updated_at = :now
    WHERE user_id = :user_id
    """
)

#: Effective upper bound for dimensions that are not server-billed (unlimited).
_MAX_LIMIT = 2**63 - 1
#: Extra tokens reserved above the question estimate to bound concurrent spend.
CHAT_RESERVE_MARGIN = 2048


def estimate_chat_reserve(question: str) -> int:
    """Conservative chat-token reservation for a question before answering."""
    return estimate_tokens(question) + CHAT_RESERVE_MARGIN


def _quota_error_for(
    status: QuotaStatus,
    chat_extra: int = 0,
    embedding_extra: int = 0,
) -> QuotaError | None:
    """Return the QuotaError for an over-limit dimension, or None if within bounds."""
    if (
        status.chat_quota is not None
        and status.chat_tokens + chat_extra > status.chat_quota
    ):
        return QuotaError(
            "本月的免费对话额度已用完（"
            f"{_fmt(status.chat_tokens + chat_extra)} / "
            f"{_fmt(status.chat_quota)} token）。"
            "你可以在“设置 → 模型配置”中填入自己的 API Key 继续使用，"
            "或等待下月额度刷新。"
        )
    if (
        status.embedding_quota is not None
        and status.embedding_chars + embedding_extra > status.embedding_quota
    ):
        return QuotaError(
            "本月的免费嵌入额度已用完（"
            f"{_fmt(status.embedding_chars + embedding_extra)} / "
            f"{_fmt(status.embedding_quota)} 字符）。"
            "你可以在“设置 → 模型配置”中填入自己的 API Key 继续使用，"
            "或等待下月额度刷新。"
        )
    return None


def reserve_usage(
    *,
    session: Session,
    user_id: uuid.UUID,
    user_settings: UserProviderSettings | None = None,
    chat_tokens: int = 0,
    embedding_chars: int = 0,
) -> tuple[int, int]:
    """Atomically reserve free-allowance capacity before a model call.

    Only server-billed dimensions are counted (BYOK or unconfigured dimensions
    pass through with a zero reservation). Concurrent requests serialize on the
    guarded upsert, so two racing checks cannot both pass; raises QuotaError
    when a server-billed dimension would exceed its allowance.

    Returns the (chat, embedding) amounts actually reserved so the caller can
    reconcile the real cost afterwards with `settle_usage`.
    """
    status = quota_status(session, user_id, user_settings)
    if status.chat_quota is None:
        chat_tokens = 0
    if status.embedding_quota is None:
        embedding_chars = 0
    if not chat_tokens and not embedding_chars:
        return 0, 0
    # Fast-path guard (also protects the brand-new-row INSERT path, which has
    # no existing row for the atomic WHERE to check).
    error = _quota_error_for(status, chat_tokens, embedding_chars)
    if error is not None:
        raise error
    result = session.execute(
        _RESERVE_SQL,
        {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "ct": chat_tokens,
            "ec": embedding_chars,
            "period": current_period(),
            "now": datetime.now(UTC),
            "chat_limit": (
                status.chat_quota if status.chat_quota is not None else _MAX_LIMIT
            ),
            "emb_limit": (
                status.embedding_quota
                if status.embedding_quota is not None
                else _MAX_LIMIT
            ),
        },
    )
    if result.first() is None:
        # A concurrent request reserved the last of the allowance first.
        session.rollback()
        error = _quota_error_for(quota_status(session, user_id, user_settings))
        if error is not None:
            raise error
        raise QuotaError("本月的免费额度已用完")
    session.commit()
    return chat_tokens, embedding_chars


def settle_usage(
    *,
    session: Session,
    user_id: uuid.UUID,
    chat_tokens: int = 0,
    embedding_chars: int = 0,
) -> None:
    """Reconcile a previous reservation with the real cost.

    Deltas are (actual − reserved) and may be negative (refund the unused
    reservation). Counters are clamped at zero. Call only for dimensions that
    were actually reserved.
    """
    if not chat_tokens and not embedding_chars:
        return
    session.execute(
        _SETTLE_SQL,
        {
            "user_id": user_id,
            "chat_delta": chat_tokens,
            "embedding_delta": embedding_chars,
            "now": datetime.now(UTC),
        },
    )
    session.commit()
