from fastapi.encoders import jsonable_encoder
from pwdlib.hashers.bcrypt import BcryptHasher
from sqlmodel import Session

from app import crud
from app.core.security import verify_password
from app.models import User, UserCreate, UserUpdate
from tests.utils.utils import random_email, random_lower_string


def test_create_user(db: Session) -> None:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, password=password)
    user = crud.create_user(session=db, user_create=user_in)
    assert user.email == email
    assert hasattr(user, "hashed_password")


def test_authenticate_user(db: Session) -> None:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, password=password)
    user = crud.create_user(session=db, user_create=user_in)
    authenticated_user = crud.authenticate(session=db, email=email, password=password)
    assert authenticated_user
    assert user.email == authenticated_user.email


def test_not_authenticate_user(db: Session) -> None:
    email = random_email()
    password = random_lower_string()
    user = crud.authenticate(session=db, email=email, password=password)
    assert user is None


def test_check_if_user_is_active(db: Session) -> None:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, password=password)
    user = crud.create_user(session=db, user_create=user_in)
    assert user.is_active is True


def test_check_if_user_is_active_inactive(db: Session) -> None:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, password=password, is_active=False)
    user = crud.create_user(session=db, user_create=user_in)
    assert user.is_active is False


def test_check_if_user_is_superuser(db: Session) -> None:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, password=password, is_superuser=True)
    user = crud.create_user(session=db, user_create=user_in)
    assert user.is_superuser is True


def test_check_if_user_is_superuser_normal_user(db: Session) -> None:
    username = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=username, password=password)
    user = crud.create_user(session=db, user_create=user_in)
    assert user.is_superuser is False


def test_get_user(db: Session) -> None:
    password = random_lower_string()
    username = random_email()
    user_in = UserCreate(email=username, password=password, is_superuser=True)
    user = crud.create_user(session=db, user_create=user_in)
    user_2 = db.get(User, user.id)
    assert user_2
    assert user.email == user_2.email
    assert jsonable_encoder(user) == jsonable_encoder(user_2)


def test_update_user(db: Session) -> None:
    password = random_lower_string()
    email = random_email()
    user_in = UserCreate(email=email, password=password, is_superuser=True)
    user = crud.create_user(session=db, user_create=user_in)
    new_password = random_lower_string()
    user_in_update = UserUpdate(password=new_password, is_superuser=True)
    if user.id is not None:
        crud.update_user(session=db, db_user=user, user_in=user_in_update)
    user_2 = db.get(User, user.id)
    assert user_2
    assert user.email == user_2.email
    verified, _ = verify_password(new_password, user_2.hashed_password)
    assert verified


def test_authenticate_user_with_bcrypt_upgrades_to_argon2(db: Session) -> None:
    """Test that a user with bcrypt password hash gets upgraded to argon2 on login."""
    email = random_email()
    password = random_lower_string()

    # Create a bcrypt hash directly (simulating legacy password)
    bcrypt_hasher = BcryptHasher()
    bcrypt_hash = bcrypt_hasher.hash(password)
    assert bcrypt_hash.startswith("$2")  # bcrypt hashes start with $2

    # Create user with bcrypt hash directly in the database
    user = User(email=email, hashed_password=bcrypt_hash, email_canonical=email.lower())
    db.add(user)
    db.commit()
    db.refresh(user)

    # Verify the hash is bcrypt before authentication
    assert user.hashed_password.startswith("$2")

    # Authenticate - this should upgrade the hash to argon2
    authenticated_user = crud.authenticate(session=db, email=email, password=password)
    assert authenticated_user
    assert authenticated_user.email == email

    db.refresh(authenticated_user)

    # Verify the hash was upgraded to argon2
    assert authenticated_user.hashed_password.startswith("$argon2")

    verified, updated_hash = verify_password(
        password, authenticated_user.hashed_password
    )
    assert verified
    # Should not need another update since it's already argon2
    assert updated_hash is None


def test_authenticate_not_found_runs_both_dummy_hashers(
    db: Session, monkeypatch
) -> None:
    """The not-found branch must run BOTH dummy verifies (argon2 + bcrypt) so
    its total work matches the found-wrong paths, which each cost one argon2 +
    one bcrypt verify (red-team round 4: a single argon2 dummy left a ~130ms
    delta distinguishing legacy-bcrypt accounts)."""
    from app.core import security

    calls: list[str] = []

    real_verify = security.verify_password

    def tracking_verify(plain: str, hashed: str):
        calls.append(hashed)
        return real_verify(plain, hashed)

    monkeypatch.setattr(crud, "verify_password", tracking_verify)
    # An email absent from the DB → get_user_by_email returns None → the
    # not-found branch runs both dummy verifies.
    crud.authenticate(session=db, email="nobody@example.com", password="x")
    assert crud.DUMMY_HASH_ARGON2 in calls
    assert crud.DUMMY_HASH_BCRYPT in calls


def test_authenticate_found_wrong_pads_with_opposite_hasher(
    db: Session, monkeypatch
) -> None:
    """A found-wrong path must be padded with the *other* hasher's dummy so its
    total cost matches not-found (one argon2 + one bcrypt), removing the
    stored-hash-type fingerprint. A security review found that only padding
    not-found re-opened an argon2-user-vs-not-found oracle (~190ms delta)."""
    from app.core import security

    real_verify = security.verify_password

    def tracking_factory(expected_real_prefix: str):
        seen: dict[str, list[str]] = {"dummies": []}

        def tracking_verify(plain: str, hashed: str):
            if hashed in (crud.DUMMY_HASH_ARGON2, crud.DUMMY_HASH_BCRYPT):
                seen["dummies"].append(hashed)
            else:
                assert hashed.startswith(expected_real_prefix)
            return real_verify(plain, hashed)

        return tracking_verify, seen

    # argon2 user, wrong password → real argon2 verify + bcrypt dummy
    email = random_email()
    user = User(
        email=email,
        hashed_password=security.get_password_hash("pw"),
        email_canonical=email.lower(),
    )
    db.add(user)
    db.commit()
    verify, seen = tracking_factory("$argon2")
    monkeypatch.setattr(crud, "verify_password", verify)
    assert crud.authenticate(session=db, email=email, password="wrong") is None
    assert crud.DUMMY_HASH_BCRYPT in seen["dummies"]

    # bcrypt user, wrong password → real bcrypt verify + argon2 dummy
    bcrypt_hasher = BcryptHasher()
    bcrypt_hash = bcrypt_hasher.hash("legacy-pw")
    other = User(
        email=random_email(),
        hashed_password=bcrypt_hash,
        email_canonical=random_email().lower(),
    )
    db.add(other)
    db.commit()
    verify2, seen2 = tracking_factory("$2")
    monkeypatch.setattr(crud, "verify_password", verify2)
    assert (
        crud.authenticate(session=db, email=other.email, password="wrong") is None
    )
    assert crud.DUMMY_HASH_ARGON2 in seen2["dummies"]


def test_authenticate_wrong_paths_cost_within_equalization_band(db: Session) -> None:
    """All three wrong/not-found outcomes must cost ~(argon2+bcrypt) within a
    generous band, so no timing distinguisher exists between not-found,
    found-argon2-wrong, and found-bcrypt-wrong (red-team round 4)."""
    import time

    # not-found
    t = time.perf_counter()
    assert (
        crud.authenticate(session=db, email="absent@example.com", password="wrong")
        is None
    )
    not_found_ms = (time.perf_counter() - t) * 1000

    # found-argon2 wrong
    email = random_email()
    user = User(
        email=email,
        hashed_password=crud.get_password_hash("pw"),
        email_canonical=email.lower(),
    )
    db.add(user)
    db.commit()
    t = time.perf_counter()
    assert crud.authenticate(session=db, email=email, password="wrong") is None
    found_argon_ms = (time.perf_counter() - t) * 1000

    # found-bcrypt wrong
    bcrypt_hasher = BcryptHasher()
    other = User(
        email=random_email(),
        hashed_password=bcrypt_hasher.hash("legacy"),
        email_canonical=random_email().lower(),
    )
    db.add(other)
    db.commit()
    t = time.perf_counter()
    assert (
        crud.authenticate(session=db, email=other.email, password="wrong") is None
    )
    found_bcrypt_ms = (time.perf_counter() - t) * 1000

    # Each path costs one argon2 (~54ms) + one bcrypt (~187ms) ≈ 240ms. A genuine
    # oracle needs a *large* non-overlapping delta; the prior bugs were ~130ms
    # and ~190ms. Require all three within 1.4x of the median — far tighter than
    # the oracle gaps, with slack for CI/host jitter.
    med = sorted([not_found_ms, found_argon_ms, found_bcrypt_ms])[1]
    for ms in (not_found_ms, found_argon_ms, found_bcrypt_ms):
        assert med * 0.6 <= ms <= med * 1.4


def test_authenticate_argon2_success_pads_with_bcrypt_dummy(
    db: Session, monkeypatch
) -> None:
    """A correct argon2 login must also run the bcrypt dummy, else it returns in
    ~55ms — far faster than every wrong/not-found path (~240ms) — giving an
    online brute-forcer a latency success-oracle at the rate-limit ceiling
    (red-team round 5)."""
    from app.core import security

    real_verify = security.verify_password
    seen: list[str] = []

    def tracking_verify(plain: str, hashed: str):
        seen.append(hashed)
        return real_verify(plain, hashed)

    email = random_email()
    user = User(
        email=email,
        hashed_password=security.get_password_hash("correct-pw"),
        email_canonical=email.lower(),
    )
    db.add(user)
    db.commit()

    monkeypatch.setattr(crud, "verify_password", tracking_verify)
    authenticated = crud.authenticate(session=db, email=email, password="correct-pw")
    assert authenticated is not None
    # The real argon2 verify ran, plus the bcrypt dummy pads the success path
    # up to the same ~240ms as every wrong/not-found path.
    assert any(h.startswith("$argon2") for h in seen)
    assert crud.DUMMY_HASH_BCRYPT in seen


def test_authenticate_success_paths_cost_within_equalization_band(db: Session) -> None:
    """A correct login must not be distinguishable from a wrong/not-found one by
    timing — the prior fix left the argon2-success path ~187ms faster (red-team
    round 5 success oracle)."""
    import time

    # argon2 correct (padded) — fresh argon2 user
    email = random_email()
    user = User(
        email=email,
        hashed_password=crud.get_password_hash("pw"),
        email_canonical=email.lower(),
    )
    db.add(user)
    db.commit()
    t = time.perf_counter()
    assert crud.authenticate(session=db, email=email, password="pw") is not None
    success_argon_ms = (time.perf_counter() - t) * 1000

    # not-found
    t = time.perf_counter()
    assert (
        crud.authenticate(session=db, email="absent@example.com", password="wrong")
        is None
    )
    not_found_ms = (time.perf_counter() - t) * 1000

    med = sorted([success_argon_ms, not_found_ms])[0]
    for ms in (success_argon_ms, not_found_ms):
        assert med * 0.6 <= ms <= med * 1.4

