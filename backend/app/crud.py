from typing import Any

from sqlmodel import Session, select

from app.core.security import get_password_hash, verify_password
from app.models import User, UserCreate, UserUpdate, get_datetime_utc
from app.utils import canonical_email


def create_user(*, session: Session, user_create: UserCreate) -> User:
    # Emails are stored lowercase (mailbox delivery is case-insensitive).
    normalized = user_create.model_copy(
        update={"email": user_create.email.strip().lower()}
    )
    db_obj = User.model_validate(
        normalized,
        update={
            "hashed_password": get_password_hash(normalized.password),
            "email_history": [canonical_email(normalized.email)],
            "email_canonical": canonical_email(normalized.email),
        },
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data: dict[str, Any] = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
        # Every password change must rotate the JWT/reset-token revocation
        # clock. get_current_user (deps.py) and reset_password (login.py) key
        # off password_changed_at, so skipping this (e.g. the admin PATCH
        # /users/{id} reset) would silently leave stolen JWTs and outstanding
        # reset tokens valid for up to ACCESS_TOKEN_EXPIRE_MINUTES.
        extra_data["password_changed_at"] = get_datetime_utc()
        extra_data["pending_email"] = None
    if user_data.get("email"):
        user_data["email"] = user_data["email"].strip().lower()
        # Keep the unique canonical identity in sync with the current email
        # (one live account per physical mailbox).
        canonical = canonical_email(user_data["email"])
        extra_data["email_canonical"] = canonical
        # Track every canonical email the account has used so the allowance
        # tombstone on a later deletion covers the admin-assigned address too
        # (mirrors the self-service path in users.py update_user_me).
        history = list(db_user.email_history or [])
        if canonical not in history:
            history.append(canonical)
        extra_data["email_history"] = history
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email.strip().lower())
    session_user = session.exec(statement).first()
    return session_user


# Dummy hashes for timing-equalization. pwdlib verifies a stored hash with the
# single hasher matching its format (argon2 ~54ms, bcrypt ~187ms), so the three
# outcomes — not-found, found-argon2-wrong, found-bcrypt-wrong — span a 4.5x
# cost range. To remove BOTH the not-found oracle AND the stored-hash-type
# fingerprint, every wrong/not-found path must do the *same total work*: one
# argon2 verify + one bcrypt verify (~240ms). The not-found branch runs both
# dummies; the found-wrong branch runs the real verify plus the OTHER hasher's
# dummy. Hash format is detected via the leading prefix (red-team round 4).
DUMMY_HASH_ARGON2 = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"
DUMMY_HASH_BCRYPT = "$2b$12$xsPUgT6uNDP5pBEeATRrheducE/NFrCh3Fvokm1oJqphq3vXJ8YjO"


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    # The OAuth2 form sends the raw string, so normalize here too.
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        # Not-found runs both dummies (~240ms) so it cannot be distinguished
        # from a found-wrong path, which also costs one argon2 + one bcrypt.
        verify_password(password, DUMMY_HASH_ARGON2)
        verify_password(password, DUMMY_HASH_BCRYPT)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        # Pad the found-wrong path with the *other* hasher's dummy so its total
        # cost matches not-found (one argon2 + one bcrypt), removing the
        # stored-hash-type fingerprint (red-team round 4).
        if db_user.hashed_password.startswith("$argon2"):
            verify_password(password, DUMMY_HASH_BCRYPT)
        elif db_user.hashed_password.startswith("$2"):
            verify_password(password, DUMMY_HASH_ARGON2)
        return None
    # Equalize the success path too. A correct argon2 login would otherwise return
    # in ~55ms — far faster than every wrong/not-found path (~240ms) — giving an
    # online brute-forcer a latency success-oracle at the rate-limit ceiling. A
    # bcrypt-success already costs bcrypt verify + argon2 rehash (~240ms) when a
    # rehash is due, so only the argon2-success path is under-padded (red-team R5).
    if db_user.hashed_password.startswith("$argon2"):
        verify_password(password, DUMMY_HASH_BCRYPT)
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user
