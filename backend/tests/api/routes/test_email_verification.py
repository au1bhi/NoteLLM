from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import jwt
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import security
from app.core.config import settings
from app.models import User
from app.utils import generate_password_reset_token, generate_verify_email_token
from tests.utils.user import user_authentication_headers
from tests.utils.utils import random_email, random_lower_string


@contextmanager
def _email_enabled() -> Generator[Mock]:
    """Enable the mail backend and stub out the low-level sender. In the default
    test config SMTP is unset, so signups auto-verify; tests that exercise the
    verification flow opt in to a real (mocked) mail path here."""
    with (
        patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"),
        patch("app.utils.send_email", return_value=None) as mock_send,
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
        assert "/verify-email?token=" in kwargs["html_content"]
    assert _user_from_db(db, email).is_email_verified is False


def test_verify_email_success(client: TestClient, db: Session) -> None:
    with _email_enabled():
        email, _ = _signup(client)
    assert _user_from_db(db, email).is_email_verified is False

    token = generate_verify_email_token(email)
    r = client.post(
        f"{settings.API_V1_STR}/users/verify-email", json={"token": token}
    )
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
    r = client.post(
        f"{settings.API_V1_STR}/users/verify-email", json={"token": token}
    )
    assert r.status_code == 400


def test_verify_token_is_purpose_scoped(
    client: TestClient, db: Session
) -> None:
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
        client.post(
            f"{settings.API_V1_STR}/users/verify-email", json={"token": token}
        )
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
        client.post(
            f"{settings.API_V1_STR}/users/verify-email", json={"token": token}
        )
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

        # Correct password -> email changes, the account drops back to
        # unverified, and a verification message goes to the new address.
        with patch("app.utils.send_email", return_value=None) as mock_send:
            ok = client.patch(
                f"{settings.API_V1_STR}/users/me",
                headers=headers,
                json={"email": new_email, "current_password": password},
            )
        assert ok.status_code == 200
        user = _user_from_db(db, new_email)
        assert user.email == new_email
        assert user.is_email_verified is False
        mock_send.assert_called_once()
        assert mock_send.call_args.kwargs["email_to"] == new_email


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
