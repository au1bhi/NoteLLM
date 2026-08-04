import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import crud
from app.core.config import settings
from app.core.security import verify_password
from app.models import User, UserCreate
from tests.utils.user import create_random_user, user_authentication_headers
from tests.utils.utils import random_email, random_lower_string


def test_get_users_superuser_me(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=superuser_token_headers)
    current_user = r.json()
    assert current_user
    assert current_user["is_active"] is True
    assert current_user["is_superuser"]
    assert current_user["email"] == settings.FIRST_SUPERUSER


def test_get_users_normal_user_me(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=normal_user_token_headers)
    current_user = r.json()
    assert current_user
    assert current_user["is_active"] is True
    assert current_user["is_superuser"] is False
    assert current_user["email"] == settings.EMAIL_TEST_USER


def test_create_user_new_email(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    with (
        patch("app.utils.send_email", return_value=None),
        patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"),
        patch("app.core.config.settings.SMTP_USER", "admin@example.com"),
    ):
        username = random_email()
        password = random_lower_string()
        data = {"email": username, "password": password}
        r = client.post(
            f"{settings.API_V1_STR}/users/",
            headers=superuser_token_headers,
            json=data,
        )
        assert 200 <= r.status_code < 300
        created_user = r.json()
        user = crud.get_user_by_email(session=db, email=username)
        assert user
        assert user.email == created_user["email"]


def test_get_existing_user_as_superuser(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)
    user_id = user.id
    r = client.get(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=superuser_token_headers,
    )
    assert 200 <= r.status_code < 300
    api_user = r.json()
    existing_user = crud.get_user_by_email(session=db, email=username)
    assert existing_user
    assert existing_user.email == api_user["email"]


def test_get_non_existing_user_as_superuser(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.get(
        f"{settings.API_V1_STR}/users/{uuid.uuid4()}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404
    assert r.json() == {"detail": "用户不存在"}


def test_get_existing_user_current_user(client: TestClient, db: Session) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)
    user_id = user.id

    login_data = {
        "username": username,
        "password": password,
    }
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    tokens = r.json()
    a_token = tokens["access_token"]
    headers = {"Authorization": f"Bearer {a_token}"}

    r = client.get(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=headers,
    )
    assert 200 <= r.status_code < 300
    api_user = r.json()
    existing_user = crud.get_user_by_email(session=db, email=username)
    assert existing_user
    assert existing_user.email == api_user["email"]


def test_get_existing_user_permissions_error(
    db: Session,
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    user = create_random_user(db)

    r = client.get(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=normal_user_token_headers,
    )
    assert r.status_code == 403
    assert r.json() == {"detail": "该用户权限不足"}


def test_get_non_existing_user_permissions_error(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    user_id = uuid.uuid4()

    r = client.get(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=normal_user_token_headers,
    )
    assert r.status_code == 403
    assert r.json() == {"detail": "该用户权限不足"}


def test_create_user_existing_username(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    # username = email
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    crud.create_user(session=db, user_create=user_in)
    data = {"email": username, "password": password}
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=superuser_token_headers,
        json=data,
    )
    created_user = r.json()
    assert r.status_code == 400
    assert "_id" not in created_user


def test_create_user_by_normal_user(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    username = random_email()
    password = random_lower_string()
    data = {"email": username, "password": password}
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=normal_user_token_headers,
        json=data,
    )
    assert r.status_code == 403


def test_retrieve_users(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    crud.create_user(session=db, user_create=user_in)

    username2 = random_email()
    password2 = random_lower_string()
    user_in2 = UserCreate(email=username2, password=password2)
    crud.create_user(session=db, user_create=user_in2)

    r = client.get(f"{settings.API_V1_STR}/users/", headers=superuser_token_headers)
    all_users = r.json()

    assert len(all_users["data"]) > 1
    assert "count" in all_users
    for item in all_users["data"]:
        assert "email" in item


def test_update_user_me(client: TestClient, db: Session) -> None:
    # Changing the email requires the current password, so use an account whose
    # password is known rather than the shared fixture.
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    crud.create_user(session=db, user_create=user_in)
    login = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": username, "password": password},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    full_name = "Updated Name"
    email = random_email()
    data = {"full_name": full_name, "email": email, "current_password": password}
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json=data,
    )
    assert r.status_code == 200
    updated_user = r.json()
    # With the mail backend off (this test fixture), the change applies
    # immediately (nothing could verify a staged one).
    assert updated_user["email"] == email.lower()
    assert updated_user["full_name"] == full_name

    # The PATCH wrote through the app's own session; expire the fixture session
    # so this query observes the committed email rather than a stale copy.
    db.expire_all()
    user_db = db.exec(select(User).where(User.email == email.lower())).first()
    assert user_db
    assert user_db.email == email.lower()
    assert user_db.full_name == full_name


def test_update_password_me(
    client: TestClient, db: Session
) -> None:
    # Use a dedicated account: password rotation now bumps password_changed_at
    # and revokes every previously issued JWT, which would invalidate the
    # module-scoped superuser token used by the rest of this file.
    username = random_email()
    password = random_lower_string()
    crud.create_user(
        session=db, user_create=UserCreate(email=username, password=password)
    )
    login = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": username, "password": password},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    new_password = random_lower_string()
    data = {
        "current_password": password,
        "new_password": new_password,
    }
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/password",
        headers=headers,
        json=data,
    )
    assert r.status_code == 200
    assert r.json()["message"] == "密码更新成功"

    # The pre-change token must now be revoked (password_changed_at bumped).
    stale = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert stale.status_code == 401

    # A fresh login with the new password works, and lets us restore the old
    # one to keep the account usable for the DB assertions.
    login2 = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": username, "password": new_password},
    )
    headers2 = {"Authorization": f"Bearer {login2.json()['access_token']}"}
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/password",
        headers=headers2,
        json={
            "current_password": new_password,
            "new_password": password,
        },
    )
    assert r.status_code == 200

    user_query = select(User).where(User.email == username)
    user_db = db.exec(user_query).first()
    assert user_db
    assert user_db.email == username
    verified, _ = verify_password(password, user_db.hashed_password)
    assert verified
    assert verified


def test_update_password_me_incorrect_password(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    new_password = random_lower_string()
    data = {"current_password": new_password, "new_password": new_password}
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/password",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 400
    updated_user = r.json()
    assert updated_user["detail"] == "密码错误"


def test_update_user_me_email_exists(
    client: TestClient, db: Session
) -> None:
    # A second registered account whose address the actor tries to claim.
    target_user = create_random_user(db)
    actor_email = random_email()
    actor_password = random_lower_string()
    crud.create_user(
        session=db,
        user_create=UserCreate(email=actor_email, password=actor_password),
    )
    headers = user_authentication_headers(
        client=client, email=actor_email, password=actor_password
    )
    data = {"email": target_user.email, "current_password": actor_password}
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json=data,
    )
    # Mail backend off -> the change applies immediately, and the canonical
    # uniqueness conflict surfaces as a generic 422 (no enumeration).
    assert r.status_code == 422
    assert r.json()["detail"] == "无法修改为指定邮箱"


def test_update_password_me_same_password_error(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {
        "current_password": settings.FIRST_SUPERUSER_PASSWORD,
        "new_password": settings.FIRST_SUPERUSER_PASSWORD,
    }
    r = client.patch(
        f"{settings.API_V1_STR}/users/me/password",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 400
    updated_user = r.json()
    assert updated_user["detail"] == "新密码不能与当前密码相同"


@patch("app.utils.send_email", return_value=None)
def test_register_user(
    _mock_send_email, client: TestClient, db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    full_name = random_lower_string()
    data = {"email": username, "password": password, "full_name": full_name}
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json=data,
    )
    assert r.status_code == 200
    created_user = r.json()
    assert created_user["email"] == username
    # The signup body is deliberately minimal (anti-enumeration): no id, no
    # full_name, just the email and whether verification is required.
    assert "id" not in created_user
    assert "full_name" not in created_user

    user_query = select(User).where(User.email == username)
    user_db = db.exec(user_query).first()
    assert user_db
    assert user_db.email == username
    assert user_db.full_name == full_name
    verified, _ = verify_password(password, user_db.hashed_password)
    assert verified


def test_register_user_does_not_enumerate_existing_account(
    client: TestClient,
) -> None:
    """Signup must not reveal whether an address is already registered: an
    existing account returns the same 200 body as a fresh signup, with no
    account id or verification state of the real account."""
    password = random_lower_string()
    full_name = random_lower_string()
    data = {
        "email": settings.FIRST_SUPERUSER,
        "password": password,
        "full_name": full_name,
    }
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json=data,
    )
    assert r.status_code == 200
    assert "id" not in r.json()
    assert r.json()["email"] == settings.FIRST_SUPERUSER


def test_update_user(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)

    data = {"full_name": "Updated_full_name"}
    r = client.patch(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 200
    updated_user = r.json()

    assert updated_user["full_name"] == "Updated_full_name"

    user_query = select(User).where(User.email == username)
    user_db = db.exec(user_query).first()
    db.refresh(user_db)
    assert user_db
    assert user_db.full_name == "Updated_full_name"


def test_update_user_not_exists(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {"full_name": "Updated_full_name"}
    r = client.patch(
        f"{settings.API_V1_STR}/users/{uuid.uuid4()}",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "系统中不存在该 ID 的用户"


def test_update_user_email_exists(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)

    username2 = random_email()
    password2 = random_lower_string()
    user_in2 = UserCreate(email=username2, password=password2)
    user2 = crud.create_user(session=db, user_create=user_in2)

    data = {"email": user2.email}
    r = client.patch(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=superuser_token_headers,
        json=data,
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "该邮箱的用户已存在"


def test_delete_user_me(client: TestClient, db: Session) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)
    user_id = user.id

    login_data = {
        "username": username,
        "password": password,
    }
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    tokens = r.json()
    a_token = tokens["access_token"]
    headers = {"Authorization": f"Bearer {a_token}"}

    r = client.delete(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
    )
    assert r.status_code == 200
    deleted_user = r.json()
    assert deleted_user["message"] == "用户删除成功"
    result = db.exec(select(User).where(User.id == user_id)).first()
    assert result is None

    user_query = select(User).where(User.id == user_id)
    user_db = db.execute(user_query).first()
    assert user_db is None


def test_token_for_deleted_user_returns_401(client: TestClient, db: Session) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    crud.create_user(session=db, user_create=user_in)

    login_data = {
        "username": username,
        "password": password,
    }
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.delete(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 200

    r = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 401


def test_delete_user_me_as_superuser(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.delete(
        f"{settings.API_V1_STR}/users/me",
        headers=superuser_token_headers,
    )
    assert r.status_code == 403
    response = r.json()
    assert response["detail"] == "超级管理员不能删除自己"


def test_delete_user_super_user(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)
    user_id = user.id
    r = client.delete(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 200
    deleted_user = r.json()
    assert deleted_user["message"] == "用户删除成功"
    result = db.exec(select(User).where(User.id == user_id)).first()
    assert result is None


def test_delete_user_not_found(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.delete(
        f"{settings.API_V1_STR}/users/{uuid.uuid4()}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "用户不存在"


def test_delete_user_current_super_user_error(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    super_user = crud.get_user_by_email(session=db, email=settings.FIRST_SUPERUSER)
    assert super_user
    user_id = super_user.id

    r = client.delete(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "超级管理员不能删除自己"


def test_delete_user_without_privileges(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)

    r = client.delete(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=normal_user_token_headers,
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "该用户权限不足"


def test_admin_password_reset_revokes_existing_jwts(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    """An admin-issued password reset must bump password_changed_at so every
    previously issued JWT (and outstanding reset token) is revoked."""
    email = random_email()
    password = random_lower_string()
    user = crud.create_user(
        session=db,
        user_create=UserCreate(email=email, password=password),
    )
    headers = user_authentication_headers(client=client, email=email, password=password)
    # The pre-reset token authenticates before the reset.
    assert client.get(f"{settings.API_V1_STR}/users/me", headers=headers).status_code == 200
    new_password = random_lower_string()
    r = client.patch(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=superuser_token_headers,
        json={"password": new_password},
    )
    assert r.status_code == 200
    # The stolen/pre-reset JWT must now be rejected.
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 401


def test_delete_and_reregister_preserves_allowance(
    client: TestClient, db: Session
) -> None:
    """Deleting an account and re-registering the same email must not reset the
    monthly free allowance (the usage is carried on an email tombstone)."""
    from app.models import EmailUsageTombstone, UserUsage

    email = random_email()
    password = random_lower_string()
    crud.create_user(session=db, user_create=UserCreate(email=email, password=password))
    headers = user_authentication_headers(client=client, email=email, password=password)
    me = client.get(f"{settings.API_V1_STR}/users/me", headers=headers).json()
    db.add(
        UserUsage(user_id=me["id"], chat_tokens=42_000, embedding_chars=200_000)
    )
    db.commit()
    # Delete the account.
    r = client.delete(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 200
    assert db.get(EmailUsageTombstone, email) is not None
    # Re-register the same address.
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": email, "password": random_lower_string()},
    )
    assert r.status_code == 200
    user = crud.get_user_by_email(session=db, email=email)
    assert user is not None
    usage = db.exec(
        select(UserUsage).where(UserUsage.user_id == user.id)
    ).first()
    # The allowance is NOT refreshed: the restored counters leave the quota
    # exhausted for the current period.
    assert usage is not None
    assert usage.chat_tokens >= 42_000
    assert usage.embedding_chars >= 200_000


def test_email_change_then_delete_preserves_allowance(
    client: TestClient, db: Session
) -> None:
    """The round-1 tombstone bypass: change email E1->E2, delete, re-register
    E1 must NOT mint a fresh allowance (the tombstone now covers every canonical
    email the account has used)."""
    from app.models import EmailUsageTombstone, UserUsage
    from app.utils import canonical_email

    e1 = random_email()
    e2 = random_email()
    password = random_lower_string()
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": e1, "password": password},
    )
    assert r.status_code == 200
    headers = user_authentication_headers(client=client, email=e1, password=password)
    me = client.get(f"{settings.API_V1_STR}/users/me", headers=headers).json()
    db.add(UserUsage(user_id=me["id"], chat_tokens=99_000, embedding_chars=250_000))
    db.commit()
    # Change email E1 -> E2 (password verified). Mail backend is off in this
    # fixture, so the change applies immediately.
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"email": e2, "current_password": password},
    )
    assert r.status_code == 200
    db.expire_all()
    # Delete the account (tombstone must cover BOTH canonical emails).
    r = client.delete(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 200
    for addr in (e1, e2):
        assert db.get(EmailUsageTombstone, canonical_email(addr)) is not None
    # Re-register E1: the allowance must NOT be refreshed.
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": e1, "password": random_lower_string()},
    )
    assert r.status_code == 200
    user = crud.get_user_by_email(session=db, email=e1)
    assert user is not None
    usage = db.exec(select(UserUsage).where(UserUsage.user_id == user.id)).first()
    assert usage is not None
    assert usage.chat_tokens >= 99_000
    assert usage.embedding_chars >= 250_000


def test_case_and_alias_variant_reregister_preserves_allowance(
    client: TestClient, db: Session
) -> None:
    """Case variants and Gmail dot/+ subaddressing of the same mailbox must not
    escape the allowance tombstone (canonical email keying)."""
    from app.models import EmailUsageTombstone, UserUsage
    from app.utils import canonical_email

    # Register with a subaddressed Gmail address.
    raw = random_lower_string()
    gmail = f"{raw}+tag@gmail.com"
    password = random_lower_string()
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": gmail, "password": password},
    )
    assert r.status_code == 200
    headers = user_authentication_headers(client=client, email=gmail, password=password)
    me = client.get(f"{settings.API_V1_STR}/users/me", headers=headers).json()
    db.add(UserUsage(user_id=me["id"], chat_tokens=80_000, embedding_chars=200_000))
    db.commit()
    r = client.delete(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 200
    # A case-variant / dot-stripped / no-tag re-registration of the SAME mailbox.
    variant = f"{raw.upper()}@GMAIL.COM"
    assert canonical_email(variant) == canonical_email(gmail)
    assert db.get(EmailUsageTombstone, canonical_email(variant)) is not None
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": variant, "password": random_lower_string()},
    )
    assert r.status_code == 200
    user = crud.get_user_by_email(session=db, email=variant.lower())
    assert user is not None
    usage = db.exec(select(UserUsage).where(UserUsage.user_id == user.id)).first()
    assert usage is not None
    assert usage.chat_tokens >= 80_000


def test_access_token_without_pwd_snapshot_is_rejected(
    client: TestClient, db: Session
) -> None:
    """A legacy JWT carrying no `pwd` snapshot is rejected once the account has
    a revocation clock (closes the NULL/legacy-token revocation gap)."""
    from datetime import timedelta

    from app.core.security import create_access_token

    user = create_random_user(db)
    token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=30),
        password_changed_at=None,
    )
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 401


def test_subaddress_duplicate_signup_is_blocked(
    client: TestClient, db: Session
) -> None:
    """A Gmail subaddress/dot-variant of an existing account's canonical mailbox
    cannot register a second live account (concurrent allowance farming)."""
    from app.utils import canonical_email

    raw = random_lower_string()
    base = f"{raw}@gmail.com"
    alias = f"{raw}+tag@gmail.com"
    password = random_lower_string()
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": base, "password": password},
    )
    assert r.status_code == 200
    # The alias delivers to the same inbox — registering it must NOT mint a
    # second account.
    r2 = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": alias, "password": random_lower_string()},
    )
    assert r2.status_code == 200  # generic anti-enumeration body
    users = db.exec(
        select(User).where(User.email_canonical == canonical_email(base))
    ).all()
    assert len(users) == 1


def test_email_change_to_taken_canonical_is_rejected(
    client: TestClient, db: Session
) -> None:
    """Changing an account's email to a subaddress/case-variant of another
    account's mailbox is rejected (one live account per physical mailbox)."""
    from app.utils import canonical_email

    raw = random_lower_string()
    base = f"{raw}@gmail.com"
    actor_email = random_email()
    actor_password = random_lower_string()
    crud.create_user(
        session=db,
        user_create=UserCreate(email=base, password=random_lower_string()),
    )
    crud.create_user(
        session=db,
        user_create=UserCreate(email=actor_email, password=actor_password),
    )
    headers = user_authentication_headers(
        client=client, email=actor_email, password=actor_password
    )
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={
            "email": f"{raw.upper()}@GMAIL.COM",
            "current_password": actor_password,
        },
    )
    # Mail backend off -> immediate apply; the canonical conflict returns a
    # generic 422 and the account's email did not change.
    assert r.status_code == 422
    me = client.get(f"{settings.API_V1_STR}/users/me", headers=headers).json()
    assert me["email"] == actor_email
    assert canonical_email(me["email"]) != canonical_email(base)


def test_pending_email_collision_applies_to_staging_account(
    client: TestClient, db: Session
) -> None:
    """Round-5 fix: when two accounts stage the SAME target pending email, a
    victim's bound verification link applies the change to the victim's own
    account — never to the other account that staged it first."""
    from unittest.mock import patch

    from app.utils import generate_email_change_token

    with patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"):
        target = random_email()
        # Attacker account A.
        a_email, a_pw = random_email(), random_lower_string()
        assert client.post(
            f"{settings.API_V1_STR}/users/signup",
            json={"email": a_email, "password": a_pw},
        ).status_code == 200
        a_headers = user_authentication_headers(
            client=client, email=a_email, password=a_pw
        )
        # Victim account V.
        v_email, v_pw = random_email(), random_lower_string()
        assert client.post(
            f"{settings.API_V1_STR}/users/signup",
            json={"email": v_email, "password": v_pw},
        ).status_code == 200
        v_headers = user_authentication_headers(
            client=client, email=v_email, password=v_pw
        )
        # A stages the target first.
        assert client.patch(
            f"{settings.API_V1_STR}/users/me",
            headers=a_headers,
            json={"email": target, "current_password": a_pw},
        ).status_code == 200
        # V stages the SAME target.
        assert client.patch(
            f"{settings.API_V1_STR}/users/me",
            headers=v_headers,
            json={"email": target, "current_password": v_pw},
        ).status_code == 200
        # V's own BOUND link applies the change to V, not A.
        v_bound = generate_email_change_token(
            pending_email=target, current_email=v_email
        )
        r = client.post(
            f"{settings.API_V1_STR}/users/verify-email", json={"token": v_bound}
        )
        assert r.status_code == 200
        db.expire_all()
        v_db = crud.get_user_by_email(session=db, email=target.lower())
        assert v_db is not None
        assert v_db.email == target.lower()
        # A's account is untouched (still has its own email).
        a_db = crud.get_user_by_email(session=db, email=a_email.lower())
        assert a_db is not None
        assert a_db.email == a_email.lower()


def test_plain_token_cannot_apply_staged_change(
    client: TestClient, db: Session
) -> None:
    """Round-6 fix: a plain (unbound) verification token — e.g. one generated by
    the resend path — must NEVER apply a staged email change, so a collision
    cannot redirect the change to a non-staging account."""
    from unittest.mock import patch

    from app.utils import generate_verify_email_token

    with patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"):
        target = random_email()
        a_email, a_pw = random_email(), random_lower_string()
        assert client.post(
            f"{settings.API_V1_STR}/users/signup",
            json={"email": a_email, "password": a_pw},
        ).status_code == 200
        a_headers = user_authentication_headers(
            client=client, email=a_email, password=a_pw
        )
        v_email, v_pw = random_email(), random_lower_string()
        assert client.post(
            f"{settings.API_V1_STR}/users/signup",
            json={"email": v_email, "password": v_pw},
        ).status_code == 200
        v_headers = user_authentication_headers(
            client=client, email=v_email, password=v_pw
        )
        assert client.patch(
            f"{settings.API_V1_STR}/users/me",
            headers=a_headers,
            json={"email": target, "current_password": a_pw},
        ).status_code == 200
        assert client.patch(
            f"{settings.API_V1_STR}/users/me",
            headers=v_headers,
            json={"email": target, "current_password": v_pw},
        ).status_code == 200
        # A PLAIN token for the target (as the resend path used to emit) must
        # not apply the change to the first staging account (attacker A).
        plain = generate_verify_email_token(target)
        r = client.post(
            f"{settings.API_V1_STR}/users/verify-email", json={"token": plain}
        )
        assert r.status_code == 400
        db.expire_all()
        a_db = crud.get_user_by_email(session=db, email=a_email.lower())
        assert a_db is not None and a_db.email == a_email.lower()
        v_db = crud.get_user_by_email(session=db, email=v_email.lower())
        assert v_db is not None and v_db.email == v_email.lower()


def test_email_change_tombstones_released_address(
    client: TestClient, db: Session
) -> None:
    """Changing email must carry the account's usage onto the RELEASED address,
    so re-registering it cannot mint a fresh allowance WITHOUT deletion.

    The round-1 tombstone mechanism only ran on account deletion; this closes
    the "change email -> re-register the old address" variant (mail-disabled
    mode applies the change immediately).
    """
    from app.models import EmailUsageTombstone, UserUsage
    from app.utils import canonical_email

    e1 = random_email()
    e2 = random_email()
    password = random_lower_string()
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": e1, "password": password},
    )
    assert r.status_code == 200
    headers = user_authentication_headers(client=client, email=e1, password=password)
    me = client.get(f"{settings.API_V1_STR}/users/me", headers=headers).json()
    db.add(UserUsage(user_id=me["id"], chat_tokens=99_000, embedding_chars=250_000))
    db.commit()
    # Change email E1 -> E2 (mail backend off in this fixture -> immediate).
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"email": e2, "current_password": password},
    )
    assert r.status_code == 200
    db.expire_all()
    # The RELEASED address E1 carries the usage on a tombstone.
    tombstone = db.get(EmailUsageTombstone, canonical_email(e1))
    assert tombstone is not None
    assert tombstone.chat_tokens >= 99_000
    assert tombstone.embedding_chars >= 250_000
    # Re-registering E1 restores the usage instead of a fresh allowance.
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": e1, "password": random_lower_string()},
    )
    assert r.status_code == 200
    user = crud.get_user_by_email(session=db, email=e1)
    assert user is not None
    usage = db.exec(select(UserUsage).where(UserUsage.user_id == user.id)).first()
    assert usage is not None
    assert usage.chat_tokens >= 99_000
    assert usage.embedding_chars >= 250_000
