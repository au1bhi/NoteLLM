import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pytest import MonkeyPatch
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import encrypt_secret
from app.models import UserProviderSettings, UserUsage
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
        chat_api_key=encrypt_secret("sk-own-chat-key"),
    )
    embedding_settings = UserProviderSettings(
        user_id=user.id,
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
