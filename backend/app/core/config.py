import secrets
import warnings
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    # Text overlaid as a full-viewport watermark by the frontend (anti-screen-
    # shot branding). Served by GET /meta/watermark so a modified frontend
    # bundle still has to talk to the backend to know what to render.
    WATERMARK_TEXT: str = "notellm.au1bhi.com"
    # Master switch. Set to false to disable the watermark entirely (e.g. an
    # internal deployment that does not need anti-screenshot branding).
    WATERMARK_ENABLED: bool = True

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    UPLOADS_DIR: Path = Path("data/uploads")
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024
    # Total bytes one user may hold across all sources (bounds the uploads
    # volume against many small files slipping past the single-file cap).
    MAX_USER_STORAGE_BYTES: int = 100 * 1024 * 1024
    LLM_BASE_URL: HttpUrl | None = None
    LLM_API_KEY: str | None = None
    LLM_MODEL: str | None = None
    EMBEDDING_BASE_URL: HttpUrl | None = None
    EMBEDDING_API_KEY: str | None = None
    EMBEDDING_MODEL: str | None = None
    EMBEDDING_DIMENSIONS: int = 1024

    # Free-tier allowance, applied only to usage billed to the server's own
    # keys. Users who bring their own API key are not limited by these.
    FREE_QUOTA_CHAT_TOKENS: int = 100_000
    FREE_QUOTA_EMBEDDING_CHARS: int = 300_000
    # How long a user must wait before switching their provider billing back
    # to the server's default after configuring their own API key.
    PROVIDER_SWITCH_COOLDOWN_HOURS: int = 24
    # Whether brute-force protection is active on auth endpoints.
    RATE_LIMIT_ENABLED: bool = True
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None
    # Mailbox domains allowed for registration / email change (comma-separated
    # in .env). Enforced before any message is queued, so an attacker can never
    # point the app at an inbox outside this list. Unset = this default list;
    # a literal `*` (or empty list in code) = any domain allowed.
    # The `| str` union mirrors BACKEND_CORS_ORIGINS: without it pydantic_settings
    # tries to JSON-decode the env var for the list type and chokes on the
    # comma-separated string.
    ALLOWED_EMAIL_DOMAINS: Annotated[
        list[str] | str, BeforeValidator(parse_cors)
    ] = [
        "163.com",
        "qq.com",
        "gmail.com",
        "126.com",
        "outlook.com",
        "hotmail.com",
        "foxmail.com",
        "139.com",
        "sina.com",
        "icloud.com",
    ]

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48
    # How long an email-verification link stays valid after it is sent.
    EMAIL_VERIFY_TOKEN_EXPIRE_HOURS: int = 72

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis" or (value and value.startswith("replace-with-")):
            message = (
                f'The value of {var_name} is "{value}", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )
        if len(self.SECRET_KEY or "") < 32:
            message = (
                "SECRET_KEY must be at least 32 characters — it signs JWTs and "
                "derives the key that encrypts stored API keys. Generate one "
                "with e.g. `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

        if self.SMTP_TLS and self.SMTP_SSL:
            raise ValueError("SMTP_TLS and SMTP_SSL cannot both be enabled")

        if self.ENVIRONMENT != "local":
            if not str(self.FRONTEND_HOST).startswith("https://"):
                raise ValueError(
                    "FRONTEND_HOST must use https:// in production — verification "
                    "and password-reset links point there and http would send "
                    "their tokens in cleartext."
                )
            if "localhost" in str(self.FRONTEND_HOST).lower():
                raise ValueError(
                    "FRONTEND_HOST must be the public domain in production, "
                    "not localhost — email links must be reachable by users."
                )

        return self


settings = Settings()  # type: ignore
