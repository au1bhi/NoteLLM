import base64
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings

password_hash = PasswordHash(
    (
        Argon2Hasher(),
        BcryptHasher(),
    )
)


def _derive_key(info: bytes) -> bytes:
    """Derive a domain-separated key from the application master secret."""
    return base64.urlsafe_b64encode(
        HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"notellm/" + info,
        ).derive(settings.SECRET_KEY.encode())
    )


def jwt_signing_key() -> bytes:
    return _derive_key(b"jwt-signing/v1")


def _fernet() -> Fernet:
    return Fernet(_derive_key(b"fernet/provider-secrets/v1"))


def encrypt_secret(value: str) -> str:
    """Encrypt a sensitive value (e.g. an API key) for storage at rest."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str | None:
    """Decrypt a stored secret; returns None if the value cannot be decrypted."""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        # Read pre-HKDF ciphertexts during migration; all new writes use HKDF.
        try:
            legacy_key = base64.urlsafe_b64encode(
                hashlib.sha256(settings.SECRET_KEY.encode()).digest()
            )
            return Fernet(legacy_key).decrypt(value.encode()).decode()
        except (InvalidToken, ValueError):
            return None


ALGORITHM = "HS256"


def create_access_token(
    subject: str | Any,
    expires_delta: timedelta,
    password_changed_at: datetime | None = None,
) -> str:
    expire = datetime.now(UTC) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    if password_changed_at is not None:
        # Snapshot of when the password was last changed (microsecond
        # precision — whole seconds are too coarse when login and a rotation
        # happen within the same second). `get_current_user` rejects tokens
        # whose snapshot predates the user's current value, so a password
        # change revokes every previously issued JWT immediately.
        to_encode["pwd"] = int(password_changed_at.timestamp() * 1_000_000)
    encoded_jwt = jwt.encode(to_encode, jwt_signing_key(), algorithm=ALGORITHM)
    return encoded_jwt


def encode_jwt(claims: dict[str, Any]) -> str:
    return jwt.encode(claims, jwt_signing_key(), algorithm=ALGORITHM)


def decode_jwt(token: str) -> dict[str, Any]:
    """Decode HKDF tokens, accepting legacy raw-secret tokens during upgrade."""
    try:
        return jwt.decode(token, jwt_signing_key(), algorithms=[ALGORITHM])
    except jwt.InvalidTokenError as current_error:
        try:
            return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        except jwt.InvalidTokenError:
            raise current_error


def verify_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    return password_hash.verify_and_update(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)
