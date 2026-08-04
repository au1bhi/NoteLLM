from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlmodel import Session, delete

from app.core.config import settings
from app.core.db import engine, init_db
from app.main import app
from app.models import User
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers


@pytest.fixture(autouse=True)
def _pin_external_service_test_defaults() -> Generator[None]:
    """Make the suite independent of the developer's root ``.env``.

    Email-flow tests opt in by patching ``SMTP_HOST`` and therefore also need a
    sender address. Quota tests model server-billed usage and therefore need
    complete (fake) chat and embedding provider configs. No test may contact
    these placeholder endpoints; provider calls are mocked at their interface.
    """
    from app.core.config import settings as app_settings

    with (
        patch.object(app_settings, "EMAILS_FROM_EMAIL", "info@example.com"),
        patch.object(
            app_settings, "LLM_BASE_URL", HttpUrl("https://provider.example/v1")
        ),
        patch.object(app_settings, "LLM_API_KEY", "ci-fake-chat-key"),
        patch.object(app_settings, "LLM_MODEL", "ci-fake-chat-model"),
        patch.object(
            app_settings,
            "EMBEDDING_BASE_URL",
            HttpUrl("https://provider.example/v1"),
        ),
        patch.object(app_settings, "EMBEDDING_API_KEY", "ci-fake-embedding-key"),
        patch.object(app_settings, "EMBEDDING_MODEL", "ci-fake-embedding-model"),
    ):
        yield


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session]:
    with Session(engine) as session:
        init_db(session)
        yield session
        statement = delete(User)
        session.exec(statement)
        session.commit()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Generator[None]:
    """Auth endpoints are rate limited per IP; clear the counters so tests
    never trip the limiter across repeated login/signup requests."""
    from app.core import rate_limit

    rate_limit.reset()
    yield
    rate_limit.reset()


@pytest.fixture(autouse=True)
def _disable_email_verification_gate() -> Generator[None]:
    """Pin the mail backend off so the server-billed usage gate stays inactive.

    Test users are unverified by design, and `emails_enabled` derives from the
    developer's local `.env` — if SMTP happened to be configured there, every
    server-billed test (upload/search/overview/chat) would 429 on the
    verification gate. Tests that exercise the mail path opt in explicitly by
    patching `settings.SMTP_HOST` (see test_email_verification._email_enabled).
    """
    from app.core.config import settings as app_settings

    with patch.object(app_settings, "SMTP_HOST", None):
        yield


@pytest.fixture(autouse=True)
def _allow_all_email_domains() -> Generator[None]:
    """Let the suite register/change to any address by default.

    The signup allowlist derives from the developer's `.env` (absent there, the
    default common-provider list would reject the random `*.com` addresses most
    tests use). Whitelist-specific tests opt in by patching
    `settings.ALLOWED_EMAIL_DOMAINS` themselves (see test_email_domain_whitelist).
    """
    from app.core.config import settings as app_settings

    with patch.object(app_settings, "ALLOWED_EMAIL_DOMAINS", []):
        yield


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
