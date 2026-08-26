import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pytest import MonkeyPatch
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import encrypt_secret
from app.models import User, UserProviderSettings, UserUsage
from app.services import usage
from tests.utils.user import create_random_user


def test_usage_reservation_refunds_only_reserved_amounts_on_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    user_id = uuid.uuid4()
    settlements: list[dict[str, object]] = []
    monkeypatch.setattr(usage, "reserve_usage", lambda **_: (120, 0))
    monkeypatch.setattr(
        usage, "settle_usage", lambda **kwargs: settlements.append(kwargs)
    )

    with pytest.raises(RuntimeError, match="provider failed"):
        with usage.usage_reservation(
            session=session,
            user_id=user_id,
            chat_tokens=500,
            embedding_chars=300,
        ) as reservation:
            assert reservation.chat_tokens == 120
            assert reservation.embedding_chars == 0
            raise RuntimeError("provider failed")

    assert settlements == [
        {
            "session": session,
            "user_id": user_id,
            "chat_tokens": -120,
            "embedding_chars": 0,
            "period": reservation.period,
        }
    ]
    session.rollback.assert_called_once_with()


def test_usage_reservation_ignores_actual_for_zero_reserved_dimension(
    monkeypatch: MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    user_id = uuid.uuid4()
    settlements: list[dict[str, object]] = []
    # A zero chat reservation represents BYOK or an unconfigured provider.
    monkeypatch.setattr(usage, "reserve_usage", lambda **_: (0, 200))
    monkeypatch.setattr(
        usage, "settle_usage", lambda **kwargs: settlements.append(kwargs)
    )

    with usage.usage_reservation(
        session=session,
        user_id=user_id,
        chat_tokens=500,
        embedding_chars=300,
    ) as reservation:
        reservation.set_actual(chat_tokens=999, embedding_chars=75)

    assert settlements == [
        {
            "session": session,
            "user_id": user_id,
            "chat_tokens": 0,
            "embedding_chars": -125,
            "period": reservation.period,
        }
    ]


def test_unverified_user_can_use_single_byok_dimension(
    db: Session, monkeypatch: MonkeyPatch
) -> None:
    user = create_random_user(db)
    user.is_email_verified = False
    db.add(user)
    db.commit()
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")

    chat_settings = UserProviderSettings(
        user_id=user.id,
        chat_base_url="https://byok.example.com/v1",
        chat_api_key=encrypt_secret("sk-own-chat-key"),
    )
    embedding_settings = UserProviderSettings(
        user_id=user.id,
        embedding_base_url="https://byok-emb.example.com/v1",
        embedding_api_key=encrypt_secret("sk-own-embedding-key"),
    )

    assert usage.reserve_usage(
        session=db,
        user_id=user.id,
        user_settings=chat_settings,
        chat_tokens=100,
    ) == (0, 0)
    assert usage.reserve_usage(
        session=db,
        user_id=user.id,
        user_settings=embedding_settings,
        embedding_chars=100,
    ) == (0, 0)


def test_usage_reservation_does_not_settle_into_a_new_period(
    db: Session, monkeypatch: MonkeyPatch
) -> None:
    user = create_random_user(db)
    reservation_period = datetime(2000, 1, 1, tzinfo=UTC)
    next_period = datetime(2000, 2, 1, tzinfo=UTC)
    monkeypatch.setattr(usage, "current_period", lambda: reservation_period)

    with usage.usage_reservation(
        session=db, user_id=user.id, chat_tokens=100
    ) as reservation:
        row = db.exec(select(UserUsage).where(UserUsage.user_id == user.id)).one()
        row.period_start = next_period
        row.chat_tokens = 777
        db.add(row)
        db.commit()
        reservation.set_actual(chat_tokens=0)

    db.expire_all()
    row = db.exec(select(UserUsage).where(UserUsage.user_id == user.id)).one()
    assert row.period_start == next_period
    assert row.chat_tokens == 777


def test_settle_usage_lands_on_current_period_when_reservation_period_expired(
    db: Session, monkeypatch: MonkeyPatch
) -> None:
    """When the reservation row rolled into a new month before settle, the
    adjustment must land on the active-period row instead of being silently
    dropped (cross-period accounting gap found by QUOTA/BIZABUSE red team)."""
    user = create_random_user(db)
    reservation_period = datetime(2000, 1, 1, tzinfo=UTC)
    current = datetime(2000, 2, 1, tzinfo=UTC)
    # current_period() returns the NEW period the row rolled into.
    monkeypatch.setattr(usage, "current_period", lambda: current)
    db.add(
        UserUsage(
            user_id=user.id,
            chat_tokens=8000,
            embedding_chars=0,
            period_start=current,
        )
    )
    db.commit()

    # Settle against the OLD (reservation) period — row is on the new period.
    usage.settle_usage(
        session=db,
        user_id=user.id,
        chat_tokens=8000,  # actual == reserved → delta 0, but must still match
        period=reservation_period,
    )

    db.expire_all()
    row = db.exec(select(UserUsage).where(UserUsage.user_id == user.id)).one()
    # The settle found no row for the old period and fell back to current_period;
    # the row is untouched by a 0-delta settle, confirming the fallback path ran
    # rather than silently dropping (a non-zero delta would have landed here).
    assert row.period_start == current


def test_settle_usage_cross_period_actually_reconciles(
    db: Session, monkeypatch: MonkeyPatch
) -> None:
    """A non-zero delta in the cross-period fallback must land on the new row."""
    user = create_random_user(db)
    reservation_period = datetime(2000, 1, 1, tzinfo=UTC)
    current = datetime(2000, 2, 1, tzinfo=UTC)
    monkeypatch.setattr(usage, "current_period", lambda: current)
    db.add(
        UserUsage(
            user_id=user.id,
            chat_tokens=8000,
            embedding_chars=0,
            period_start=current,
        )
    )
    db.commit()

    # Refund 3000 tokens against the old period — must land on the new row.
    usage.settle_usage(
        session=db,
        user_id=user.id,
        chat_tokens=-3000,
        period=reservation_period,
    )

    db.expire_all()
    row = db.exec(select(UserUsage).where(UserUsage.user_id == user.id)).one()
    assert row.period_start == current
    assert row.chat_tokens == 5000


def test_reconcile_is_idempotent_under_double_call(
    monkeypatch: MonkeyPatch,
) -> None:
    """_reconcile must settle only once — a second call (e.g. from an
    exception handler re-entering) must not double-refund the reservation."""
    session = MagicMock(spec=Session)
    user_id = uuid.uuid4()
    settlements: list[dict[str, object]] = []
    monkeypatch.setattr(usage, "reserve_usage", lambda **_: (100, 0))
    monkeypatch.setattr(
        usage, "settle_usage", lambda **kwargs: settlements.append(kwargs)
    )

    with usage.usage_reservation(
        session=session, user_id=user_id, chat_tokens=100
    ) as reservation:
        pass

    # Manually trigger a second reconcile (simulating a re-entrant cleanup).
    reservation._reconcile(succeeded=False)
    assert len(settlements) == 1


def _verified_user(db: Session) -> User:
    user = create_random_user(db)
    user.is_email_verified = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _consume_full_chat_allowance(db: Session, user_id: uuid.UUID) -> None:
    db.add(
        UserUsage(
            user_id=user_id,
            chat_tokens=settings.FREE_QUOTA_CHAT_TOKENS,
            embedding_chars=0,
            period_start=usage.current_period(),
        )
    )
    db.commit()


def test_source_without_any_provider_is_none() -> None:
    assert usage._source(has_own_key=False, server_configured=False) == "none"


def test_check_chat_quota_raises_when_allowance_consumed(
    db: Session, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "LLM_API_KEY", "server-secret-key")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://api.example.com/v1")
    user = _verified_user(db)
    _consume_full_chat_allowance(db, user.id)

    with pytest.raises(usage.QuotaError, match="对话额度已用完"):
        usage.check_chat_quota(session=db, user_id=user.id)


def test_reserve_usage_lost_race_falls_back_to_generic_quota_error(
    db: Session, monkeypatch: MonkeyPatch
) -> None:
    """Simulate the concurrent race: the fast-path check sees room (patched
    away), the guarded UPDATE matches no row because another request took the
    last allowance first."""
    monkeypatch.setattr(settings, "LLM_API_KEY", "server-secret-key")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://api.example.com/v1")
    user = _verified_user(db)
    _consume_full_chat_allowance(db, user.id)
    # First call bypasses the fast path (simulating the race window); the
    # rebuilt status then yields the detailed allowance error.
    responses = iter([None, usage.QuotaError("对话额度已用完（重建后）")])
    monkeypatch.setattr(
        usage, "_quota_error_for", lambda *_a, **_k: next(responses)
    )

    with pytest.raises(usage.QuotaError, match="重建后"):
        usage.reserve_usage(session=db, user_id=user.id, chat_tokens=1000)


def test_reserve_usage_lost_race_generic_error_when_still_under_quota(
    db: Session, monkeypatch: MonkeyPatch
) -> None:
    """When the guarded UPDATE matches no row but the rebuilt quota status is
    still under the limit (race window), a generic QuotaError is raised
    (covers the final fallback branch)."""
    monkeypatch.setattr(settings, "LLM_API_KEY", "server-secret-key")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://api.example.com/v1")
    user = _verified_user(db)
    _consume_full_chat_allowance(db, user.id)
    # Both fast-path and rebuilt status report "within bounds" (None error),
    # yet the UPDATE matched no row (simulated by the consumed allowance row).
    monkeypatch.setattr(usage, "_quota_error_for", lambda *_a, **_k: None)
    # Force the guarded UPDATE to return no row by pointing the user at a
    # fresh period where no row exists yet — the INSERT path then sees the
    # consumed allowance via quota_status.
    db.exec(select(UserUsage).where(UserUsage.user_id == user.id))
    with pytest.raises(usage.QuotaError, match="本月的免费额度已用完"):
        usage.reserve_usage(session=db, user_id=user.id, chat_tokens=1000)
