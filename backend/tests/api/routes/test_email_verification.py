from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import security
from app.core.config import settings
from app.models import User
from app.services.usage import QuotaError, check_chat_quota
from app.utils import generate_password_reset_token, generate_verify_email_token
from tests.utils.user import create_random_user, user_authentication_headers
from tests.utils.utils import random_email, random_lower_string


@contextmanager
def _email_enabled() -> Generator[Mock]:
    """Enable the mail backend and stub out the low-level sender. In the default
    test config SMTP is unset, so signups auto-verify; tests that exercise the
    verification flow opt in to a real (mocked) mail path here. The per-recipient
    send cooldown is bypassed so a test can signup and then immediately resend
    (the cooldown itself has a dedicated test)."""
    with (
        patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"),
        patch("app.utils.send_email", return_value=None) as mock_send,
        patch("app.api.routes.users.recipient_send_cooldown", return_value=True),
    ):
        yield mock_send


def _signup(client: TestClient, *, email: str | None = None) -> tuple[str, str]:
    email = email or random_email()
    password = random_lower_string()
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": email, "password": password, "full_name": "测试用户"},
    )
    assert r.status_code == 200, r.text
    return email, password


def _user_from_db(db: Session, email: str) -> User:
    # The app writes via its own session; the fixture session may hold a stale
    # identity-map copy of the row. Expire everything so the query reads the
    # committed state deterministically.
    db.expire_all()
    user = db.exec(select(User).where(User.email == email)).first()
    assert user is not None
    return user


def _expired_verify_token(email: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "exp": (now - timedelta(hours=1)).timestamp(),
            "nbf": (now - timedelta(hours=2)).timestamp(),
            "sub": email,
            "purpose": "email_verify",
        },
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )


def test_signup_sends_verification_email_and_is_unverified(
    client: TestClient, db: Session
) -> None:
    with _email_enabled() as mock_send:
        email, _ = _signup(client)
        assert mock_send.call_count == 1
        kwargs = mock_send.call_args.kwargs
        assert kwargs["email_to"] == email
        assert "验证" in kwargs["subject"]
        # The verify token rides in the URL fragment (never the query string)
        # so it does not leak via proxy logs or the Referer header.
        assert "/verify-email#token=" in kwargs["html_content"]
    assert _user_from_db(db, email).is_email_verified is False


def test_verify_email_success(client: TestClient, db: Session) -> None:
    with _email_enabled():
        email, _ = _signup(client)
    assert _user_from_db(db, email).is_email_verified is False

    token = generate_verify_email_token(email)
    r = client.post(f"{settings.API_V1_STR}/users/verify-email", json={"token": token})
    assert r.status_code == 200
    assert r.json()["message"] == "邮箱验证成功"
    assert _user_from_db(db, email).is_email_verified is True


def test_verify_email_is_idempotent(client: TestClient, db: Session) -> None:
    with _email_enabled():
        email, _ = _signup(client)
    token = generate_verify_email_token(email)
    first = client.post(
        f"{settings.API_V1_STR}/users/verify-email", json={"token": token}
    )
    second = client.post(
        f"{settings.API_V1_STR}/users/verify-email", json={"token": token}
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert _user_from_db(db, email).is_email_verified is True


def test_verify_email_invalid_token(client: TestClient) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/users/verify-email", json={"token": "garbage"}
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "验证链接无效或已过期"


def test_verify_email_expired_token(client: TestClient, db: Session) -> None:
    with _email_enabled():
        email, _ = _signup(client)
    r = client.post(
        f"{settings.API_V1_STR}/users/verify-email",
        json={"token": _expired_verify_token(email)},
    )
    assert r.status_code == 400
    assert _user_from_db(db, email).is_email_verified is False


def test_verify_email_unknown_user_does_not_verify(client: TestClient) -> None:
    token = generate_verify_email_token(random_email())
    r = client.post(f"{settings.API_V1_STR}/users/verify-email", json={"token": token})
    assert r.status_code == 400


def test_verify_token_is_purpose_scoped(client: TestClient, db: Session) -> None:
    """A password-reset token must not work as an email-verification token."""
    with _email_enabled():
        email, _ = _signup(client)
    reset_token = generate_password_reset_token(email)

    r = client.post(
        f"{settings.API_V1_STR}/users/verify-email",
        json={"token": reset_token},
    )
    assert r.status_code == 400
    assert _user_from_db(db, email).is_email_verified is False


def test_reset_password_rejects_verify_token(client: TestClient) -> None:
    with _email_enabled():
        email, _ = _signup(client)
    verify_token = generate_verify_email_token(email)
    r = client.post(
        f"{settings.API_V1_STR}/reset-password/",
        json={"token": verify_token, "new_password": random_lower_string()},
    )
    assert r.status_code == 400


def test_resend_verification_is_generic_and_only_for_unverified(
    client: TestClient,
) -> None:
    with _email_enabled() as mock_send:
        email, _ = _signup(client)
        registered = client.post(
            f"{settings.API_V1_STR}/users/resend-verification",
            json={"email": email},
        )
        ghost = client.post(
            f"{settings.API_V1_STR}/users/resend-verification",
            json={"email": random_email()},
        )
    # Identical generic responses -> no email enumeration.
    assert registered.status_code == 200
    assert ghost.status_code == 200
    assert registered.json() == ghost.json()
    # Signup sent one; the resend sent only for the registered account.
    assert mock_send.call_count == 2


def test_resend_verification_skips_verified_account(
    client: TestClient, db: Session
) -> None:
    with _email_enabled() as mock_send:
        email, _ = _signup(client)
        token = generate_verify_email_token(email)
        client.post(f"{settings.API_V1_STR}/users/verify-email", json={"token": token})
        assert _user_from_db(db, email).is_email_verified is True
        mock_send.reset_mock()
        r = client.post(
            f"{settings.API_V1_STR}/users/resend-verification",
            json={"email": email},
        )
    assert r.status_code == 200
    mock_send.assert_not_called()


def test_resend_verification_authenticated(
    client: TestClient,
) -> None:
    with _email_enabled() as mock_send:
        email, password = _signup(client)
        mock_send.reset_mock()
        headers = user_authentication_headers(
            client=client, email=email, password=password
        )
        r = client.post(
            f"{settings.API_V1_STR}/users/me/resend-verification",
            headers=headers,
        )
    assert r.status_code == 200
    assert r.json()["message"] == "验证邮件已发送"
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["email_to"] == email


def test_resend_verification_rate_limited(client: TestClient) -> None:
    with _email_enabled():
        email, _ = _signup(client)
        statuses = []
        for _ in range(4):
            r = client.post(
                f"{settings.API_V1_STR}/users/resend-verification",
                json={"email": email},
            )
            statuses.append(r.status_code)
    assert statuses == [200, 200, 200, 429]


def test_update_email_requires_current_password(
    client: TestClient, db: Session
) -> None:
    with _email_enabled():
        email, password = _signup(client)
        # First prove ownership, then change the address.
        token = generate_verify_email_token(email)
        client.post(f"{settings.API_V1_STR}/users/verify-email", json={"token": token})
        assert _user_from_db(db, email).is_email_verified is True
        headers = user_authentication_headers(
            client=client, email=email, password=password
        )
        new_email = random_email()

        # Missing password.
        no_pw = client.patch(
            f"{settings.API_V1_STR}/users/me",
            headers=headers,
            json={"email": new_email},
        )
        assert no_pw.status_code == 422

        # Wrong password.
        wrong_pw = client.patch(
            f"{settings.API_V1_STR}/users/me",
            headers=headers,
            json={"email": new_email, "current_password": "wrong-password"},
        )
        assert wrong_pw.status_code == 400
        assert _user_from_db(db, email).email == email  # unchanged

        # Correct password -> the change is STAGED (pending_email), the account
        # drops back to unverified, and a verification message goes to the NEW
        # address. The email itself only moves once the new address verifies.
        with patch("app.utils.send_email", return_value=None) as mock_send:
            ok = client.patch(
                f"{settings.API_V1_STR}/users/me",
                headers=headers,
                json={"email": new_email, "current_password": password},
            )
        assert ok.status_code == 200
        user = _user_from_db(db, email)  # current email unchanged
        assert user.email == email
        assert user.pending_email == new_email.lower()
        assert user.is_email_verified is False
        mock_send.assert_called_once()
        assert mock_send.call_args.kwargs["email_to"] == new_email.lower()

        # Verify the new address -> the staged change is applied. The link the
        # app emails is BOUND to the staging account (a plain token cannot
        # apply a pending change) and to the password-change clock.
        from app.utils import generate_email_change_token

        verify_token = generate_email_change_token(
            pending_email=new_email,
            current_email=email,
            password_changed_at=user.password_changed_at,
        )
        r = client.post(
            f"{settings.API_V1_STR}/users/verify-email",
            json={"token": verify_token},
        )
        assert r.status_code == 200
        user = _user_from_db(db, new_email.lower())
        assert user.email == new_email.lower()
        assert user.pending_email is None
        assert user.is_email_verified is True


def test_email_change_token_revoked_after_password_rotation(
    client: TestClient, db: Session
) -> None:
    """A staged email-change link must die when the password is rotated.

    Otherwise a stolen-password attacker who already pointed pending_email at
    their inbox keeps a 72h takeover window after the victim recovers.
    """
    from app.utils import generate_email_change_token

    with _email_enabled():
        email, password = _signup(client)
        token = generate_verify_email_token(email)
        client.post(f"{settings.API_V1_STR}/users/verify-email", json={"token": token})
        headers = user_authentication_headers(
            client=client, email=email, password=password
        )
        new_email = random_email()
        staged = client.patch(
            f"{settings.API_V1_STR}/users/me",
            headers=headers,
            json={"email": new_email, "current_password": password},
        )
        assert staged.status_code == 200
        user = _user_from_db(db, email)
        assert user.pending_email == new_email.lower()
        stale_token = generate_email_change_token(
            pending_email=new_email,
            current_email=email,
            password_changed_at=user.password_changed_at,
        )
        new_password = random_lower_string()
        rotated = client.patch(
            f"{settings.API_V1_STR}/users/me/password",
            headers=headers,
            json={"current_password": password, "new_password": new_password},
        )
        assert rotated.status_code == 200
        user = _user_from_db(db, email)
        assert user.pending_email is None
        rejected = client.post(
            f"{settings.API_V1_STR}/users/verify-email",
            json={"token": stale_token},
        )
        assert rejected.status_code == 400
        assert user.email == email

        # Defense in depth: even if pending_email is re-queued after rotation,
        # a token bound to the previous password clock must still be rejected.
        user.pending_email = new_email.lower()
        db.add(user)
        db.commit()
        still_rejected = client.post(
            f"{settings.API_V1_STR}/users/verify-email",
            json={"token": stale_token},
        )
        assert still_rejected.status_code == 400
        user = _user_from_db(db, email)
        assert user.email == email


def test_email_change_cannot_take_over_with_stolen_session(
    client: TestClient, db: Session
) -> None:
    """Changing the email needs the account password, so a leaked session alone
    cannot move the account to an attacker-controlled address and then trigger
    password recovery on it."""
    with _email_enabled():
        email, password = _signup(client)
        # Valid session, but the caller only knows the email — not the password.
        headers = user_authentication_headers(
            client=client, email=email, password=password
        )
        r = client.patch(
            f"{settings.API_V1_STR}/users/me",
            headers=headers,
            json={"email": random_email(), "current_password": "not-the-password"},
        )
    assert r.status_code == 400
    assert _user_from_db(db, email).email == email


def test_signup_auto_verified_when_email_disabled(
    client: TestClient,
) -> None:
    with patch("app.core.config.settings.SMTP_HOST", None):
        email = random_email()
        r = client.post(
            f"{settings.API_V1_STR}/users/signup",
            json={"email": email, "password": random_lower_string()},
        )
        assert r.status_code == 200
        assert r.json()["is_email_verified"] is True


def test_resend_respects_per_recipient_cooldown(
    client: TestClient,
) -> None:
    """A second message to the same address within the cooldown window is
    silently skipped — a distributed caller cannot flood a target mailbox."""
    with (
        patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"),
        patch("app.utils.send_email", return_value=None) as mock_send,
    ):
        email, _ = _signup(client)  # sends once
        assert mock_send.call_count == 1
        r1 = client.post(
            f"{settings.API_V1_STR}/users/resend-verification",
            json={"email": email},
        )
        r2 = client.post(
            f"{settings.API_V1_STR}/users/resend-verification",
            json={"email": email},
        )
    # Generic 200s, but only the signup message actually went out.
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert mock_send.call_count == 1


def test_user_public_exposes_verification_flag(
    client: TestClient,
) -> None:
    with _email_enabled():
        email, password = _signup(client)
        headers = user_authentication_headers(
            client=client, email=email, password=password
        )
        r = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["is_email_verified"] is False


def test_signup_normalizes_email_case(client: TestClient, db: Session) -> None:
    """Mailbox delivery is case-insensitive, so case variants of the same
    address must resolve to a single account (no duplicate registration)."""
    mixed = "MixedCase@Example.COM"
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": mixed, "password": random_lower_string()},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "mixedcase@example.com"
    assert _user_from_db(db, "mixedcase@example.com") is not None

    # The lowercased variant is now a duplicate. The endpoint still answers
    # 200 with the identical, non-enumerating body (no id, same verification
    # flag) — it must not reveal that the account already existed.
    dup = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": "mixedcase@example.com", "password": random_lower_string()},
    )
    assert dup.status_code == 200
    assert dup.json()["email"] == "mixedcase@example.com"
    assert "id" not in dup.json()
    assert dup.json()["is_email_verified"] == r.json()["is_email_verified"]


def test_login_is_case_insensitive(client: TestClient) -> None:
    email, password = _signup(client)
    r = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": email.upper(), "password": password},
    )
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_server_quota_requires_verified_email(client: TestClient, db: Session) -> None:
    """With the mail backend on, server-billed free usage is gated on email
    verification (bring-your-own-key usage is not)."""
    with _email_enabled():
        email, _ = _signup(client)
        user = _user_from_db(db, email)
    # Signup created the account unverified.
    with patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"):
        with pytest.raises(QuotaError):
            check_chat_quota(db, user.id)
        # Verifying unlocks the server allowance.
        token = generate_verify_email_token(user.email)
        client.post(f"{settings.API_V1_STR}/users/verify-email", json={"token": token})
        db.expire_all()
        check_chat_quota(db, user.id)  # no raise


def test_recover_password_never_500s_when_smtp_disabled(
    client: TestClient, db: Session
) -> None:
    """The password-recovery endpoint must not turn SMTP absence into a 500.
    A registered address still reports the link as sent (SMTP failures are
    swallowed by design); an unregistered one returns the identical 200 body
    (anti-enumeration). Neither path may 500."""
    user = create_random_user(db)
    with patch("app.core.config.settings.SMTP_HOST", None):
        registered = client.post(
            f"{settings.API_V1_STR}/password-recovery/{user.email}"
        )
        ghost = client.post(f"{settings.API_V1_STR}/password-recovery/{random_email()}")
    assert registered.status_code == 200
    assert registered.json() == {"message": "密码重置链接已发送，请查收"}
    assert ghost.status_code == 200
    assert ghost.json() == {"message": "密码重置链接已发送，请查收"}


def test_purpose_token_as_bearer_is_403_not_500(
    client: TestClient,
) -> None:
    email, _ = _signup(client)
    verify_token = generate_verify_email_token(email)
    r = client.get(
        f"{settings.API_V1_STR}/users/me",
        headers={"Authorization": f"Bearer {verify_token}"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "无法验证凭据"


def test_update_email_null_is_rejected(client: TestClient, db: Session) -> None:
    email, password = _signup(client)
    headers = user_authentication_headers(client=client, email=email, password=password)
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"email": None, "current_password": password},
    )
    assert r.status_code == 422
    assert _user_from_db(db, email).email == email


def test_verify_email_rate_limited(client: TestClient) -> None:
    statuses = []
    for _ in range(11):
        r = client.post(
            f"{settings.API_V1_STR}/users/verify-email",
            json={"token": "garbage"},
        )
        statuses.append(r.status_code)
    assert statuses == [400] * 10 + [429]


def test_superuser_created_account_is_verified(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    email = random_email()
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=superuser_token_headers,
        json={"email": email, "password": random_lower_string()},
    )
    assert r.status_code == 200
    assert r.json()["is_email_verified"] is True
