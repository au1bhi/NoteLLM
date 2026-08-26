import base64
import hashlib
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.fernet import Fernet

from app.core import security
from app.core.config import settings


def test_hkdf_separates_jwt_and_fernet_keys() -> None:
    assert security.jwt_signing_key() != security._derive_key(  # type: ignore[attr-defined]
        b"fernet/provider-secrets/v1"
    )


def test_decrypt_secret_accepts_legacy_sha256_ciphertext() -> None:
    legacy_key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    )
    ciphertext = Fernet(legacy_key).encrypt(b"legacy-provider-key").decode()
    assert security.decrypt_secret(ciphertext) == "legacy-provider-key"


def test_new_jwt_uses_derived_key_and_legacy_jwt_still_decodes() -> None:
    claims = {
        "sub": "test",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    current = security.encode_jwt(claims)
    assert security.decode_jwt(current)["sub"] == "test"
    try:
        jwt.decode(current, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
    except jwt.InvalidTokenError:
        pass
    else:
        raise AssertionError("new JWT unexpectedly used the raw master secret")

    legacy = jwt.encode(claims, settings.SECRET_KEY, algorithm=security.ALGORITHM)
    assert security.decode_jwt(legacy)["sub"] == "test"


def test_decrypt_secret_returns_none_for_undecryptable_ciphertext() -> None:
    """A ciphertext under a foreign key fails both the HKDF key and the legacy
    SHA-256 fallback — the caller gets None instead of an exception."""
    from cryptography.fernet import Fernet

    foreign = Fernet(Fernet.generate_key()).encrypt(b"x").decode()
    assert security.decrypt_secret(foreign) is None
    assert security.decrypt_secret("not-a-token-at-all") is None


def test_decode_jwt_rejects_token_without_exp() -> None:
    """A token with no ``exp`` must be rejected — otherwise a no-exp token is
    a permanent credential that never expires (red-team finding)."""
    token = security.encode_jwt({"sub": "user-1"})  # no exp
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_jwt(token)


def test_decode_jwt_rejects_token_without_sub() -> None:
    """A token with no ``sub`` is not a valid access token."""
    token = security.encode_jwt(
        {"exp": datetime.now(UTC) + timedelta(minutes=5)}
    )
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_jwt(token)


def test_decode_jwt_rejects_legacy_token_without_exp() -> None:
    """The legacy raw-secret decode path must enforce exp too."""
    token = jwt.encode({"sub": "u"}, settings.SECRET_KEY, algorithm=security.ALGORITHM)
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_jwt(token)
