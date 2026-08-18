import base64
import hashlib
from datetime import UTC, datetime, timedelta

import jwt
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
