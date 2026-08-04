"""Registration / email-change domain allowlist.

The policy: a NEW email only enters the system through signup, admin creation
or email change, and every one of those paths must reject addresses outside
`ALLOWED_EMAIL_DOMAINS` *before* any message is queued. These tests pin that
down so an attacker can never use the app to deliver mail to an arbitrary
inbox, or register under a domain the operator did not approve.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import crud
from app.core.config import settings
from app.models import User, UserCreate
from app.utils import is_allowed_email
from tests.utils.user import create_random_user, user_authentication_headers
from tests.utils.utils import random_lower_string

ALLOWED = ["163.com", "qq.com", "gmail.com"]


def _patch_allowlist() -> patch:
    return patch.object(settings, "ALLOWED_EMAIL_DOMAINS", ALLOWED)


def _url(path: str) -> str:
    return f"{settings.API_V1_STR}{path}"


# --- unit: is_allowed_email bypass battery --------------------------------


def test_is_allowed_email_bypass_battery() -> None:
    with _patch_allowlist():
        allowed = [
            "user@qq.com",
            "USER@QQ.COM",  # case-insensitive domain
            "user+tag@163.com",  # plus-address stays on the allowed domain
            "user.name@Gmail.COM",
        ]
        for email in allowed:
            assert is_allowed_email(email), email

        rejected = [
            "user@qq.com.evil.com",  # suffix trick
            "user@evilqq.com",  # prefix lookalike
            "user@mail.qq.com",  # subdomain is not the mailbox domain
            "user@qq.com.cn",
            "user@163.com@evil.com",  # extra @ — domain is evil.com
            "user@qq。com",  # full-width dot / IDN
            "user@ｑｑ.com",  # full-width letters
        ]
        for email in rejected:
            assert not is_allowed_email(email), email


def test_is_allowed_email_empty_allowlist_allows_everything() -> None:
    with patch.object(settings, "ALLOWED_EMAIL_DOMAINS", []):
        assert is_allowed_email("user@whatever-corporate.example")


def test_is_allowed_email_star_sentinel_allows_everything() -> None:
    # `*` is the documented way to disable the policy via .env (an empty value
    # is ignored by env_ignore_empty, so the default list would silently apply).
    with patch.object(settings, "ALLOWED_EMAIL_DOMAINS", ["*"]):
        assert is_allowed_email("user@anything-corporate.example")
        assert is_allowed_email("user@qq.com")


# --- signup ---------------------------------------------------------------


def test_signup_allows_whitelisted_domain(client: TestClient) -> None:
    with _patch_allowlist(), patch("app.utils.send_email", return_value=None):
        r = client.post(
            _url("/users/signup"),
            json={"email": "user@qq.com", "password": random_lower_string()},
        )
    assert r.status_code == 200


def test_signup_rejects_other_domain_and_sends_nothing(
    client: TestClient, db: Session
) -> None:
    sent: list[dict] = []

    def fake_send(**kwargs: object) -> None:
        sent.append(kwargs)

    with _patch_allowlist(), patch("app.utils.send_email", side_effect=fake_send):
        r = client.post(
            _url("/users/signup"),
            json={"email": "attacker@evil.com", "password": random_lower_string()},
        )
    assert r.status_code == 400
    assert "仅支持" in r.json()["detail"]
    assert sent == [], "no message may go out for a disallowed address"
    row = db.exec(select(User).where(User.email == "attacker@evil.com")).first()
    assert row is None


def test_signup_domain_check_is_case_insensitive(client: TestClient) -> None:
    with _patch_allowlist(), patch("app.utils.send_email", return_value=None):
        r = client.post(
            _url("/users/signup"),
            json={"email": "User@QQ.COM", "password": random_lower_string()},
        )
    assert r.status_code == 200


def test_signup_rejects_lookalike_domains(client: TestClient) -> None:
    for bad in [
        "user@qq.com.evil.com",
        "user@evilqq.com",
        "user@mail.qq.com",
        "user@163.com.cn",
    ]:
        with _patch_allowlist(), patch("app.utils.send_email", return_value=None):
            r = client.post(
                _url("/users/signup"),
                json={"email": bad, "password": random_lower_string()},
            )
        assert r.status_code == 400, bad


def test_signup_malformed_email_cannot_bypass(client: TestClient) -> None:
    # A second `@` is rejected by EmailStr outright, not passed through a
    # normalization gap into the allowlist. (Full-width characters and trailing
    # whitespace are *normalized* by EmailStr to the real ASCII address — so
    # `user@qq。com` becomes `user@qq.com` and stays allowed, while
    # `user@ｅｖｉｌ.com` would normalize to `evil.com` and be rejected — they
    # are not a way to smuggle a different domain in.)
    with _patch_allowlist(), patch("app.utils.send_email", return_value=None):
        r = client.post(
            _url("/users/signup"),
            json={"email": "user@qq.com@evil.com", "password": random_lower_string()},
        )
    assert r.status_code == 422


# --- email change (PATCH /users/me) --------------------------------------


def _known_user(db: Session) -> tuple[str, str]:
    email = random_lower_string() + "@qq.com"
    password = random_lower_string()
    crud.create_user(session=db, user_create=UserCreate(email=email, password=password))
    return email, password


def test_update_email_me_rejects_disallowed_and_sends_nothing(
    client: TestClient, db: Session
) -> None:
    email, password = _known_user(db)
    headers = user_authentication_headers(client=client, email=email, password=password)
    sent: list[dict] = []

    def fake_send(**kwargs: object) -> None:
        sent.append(kwargs)

    with _patch_allowlist(), patch("app.utils.send_email", side_effect=fake_send):
        r = client.patch(
            _url("/users/me"),
            headers=headers,
            json={"email": "victim@evil.com", "current_password": password},
        )
    assert r.status_code == 400
    assert "仅支持" in r.json()["detail"]
    assert sent == [], "no verification message to a disallowed address"
    db.expire_all()
    assert db.exec(select(User).where(User.email == email)).first() is not None
    assert db.exec(select(User).where(User.email == "victim@evil.com")).first() is None


def test_update_email_me_allows_whitelisted_domain(
    client: TestClient, db: Session
) -> None:
    email, password = _known_user(db)
    headers = user_authentication_headers(client=client, email=email, password=password)
    with _patch_allowlist(), patch("app.utils.send_email", return_value=None):
        r = client.patch(
            _url("/users/me"),
            headers=headers,
            json={"email": "new@163.com", "current_password": password},
        )
    assert r.status_code == 200


# --- admin paths (defense-in-depth; still constrained by policy) -----------


def test_admin_create_user_rejects_disallowed(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    sent: list[dict] = []

    def fake_send(**kwargs: object) -> None:
        sent.append(kwargs)

    with _patch_allowlist(), patch("app.utils.send_email", side_effect=fake_send):
        r = client.post(
            _url("/users/"),
            headers=superuser_token_headers,
            json={"email": "evil@corp.example", "password": random_lower_string()},
        )
    assert r.status_code == 400
    assert sent == []


def test_admin_update_user_email_rejects_disallowed(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    user = create_random_user(db)
    with _patch_allowlist():
        r = client.patch(
            _url(f"/users/{user.id}"),
            headers=superuser_token_headers,
            json={"email": "evil@corp.example"},
        )
    assert r.status_code == 400
    assert "仅支持" in r.json()["detail"]


# --- password recovery honesty --------------------------------------------


def test_recovery_password_registered_returns_sent(
    client: TestClient, db: Session
) -> None:
    email, _password = _known_user(db)
    with _patch_allowlist(), patch("app.utils.send_email", return_value=None):
        r = client.post(_url(f"/password-recovery/{email}"))
    assert r.status_code == 200
    assert r.json() == {"message": "密码重置链接已发送，请查收"}


def test_recovery_password_unregistered_returns_200(client: TestClient) -> None:
    # Anti-enumeration: an unregistered address returns the same 200 body as a
    # registered one (no email is actually sent), so the endpoint cannot be
    # used to probe which addresses have accounts.
    r = client.post(_url("/password-recovery/nobody@qq.com"))
    assert r.status_code == 200
    assert r.json() == {"message": "密码重置链接已发送，请查收"}


def test_recovery_password_respects_recipient_cooldown(
    client: TestClient, db: Session
) -> None:
    """The recovery send path uses the same per-recipient cooldown as every
    other send path, so a second request within the window does not fire a
    second message to the same mailbox."""
    email, _password = _known_user(db)
    sent: list[dict] = []

    def fake_send(**kwargs: object) -> None:
        sent.append(kwargs)

    with _patch_allowlist(), patch("app.utils.send_email", side_effect=fake_send):
        first = client.post(_url(f"/password-recovery/{email}"))
        second = client.post(_url(f"/password-recovery/{email}"))
    assert first.status_code == 200
    assert second.status_code == 200
    assert len(sent) == 1, "the cooldown must suppress the second send"
