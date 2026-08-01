from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.models import UserUsage
from app.services.usage import current_period
from tests.utils.notebook import create_random_notebook
from tests.utils.user import authentication_token_from_email, create_random_user


def _sse_messages(text: str) -> list[dict[str, str]]:
    """Parse the `data:` payloads of a Server-Sent Events response."""
    import json

    payloads = []
    for line in text.splitlines():
        if line.startswith("data: "):
            payloads.append(json.loads(line[len("data: ") :]))
    return payloads


def _exhaust_chat_quota(db: Session, user_id) -> None:
    db.add(
        UserUsage(
            user_id=user_id,
            chat_tokens=settings.FREE_QUOTA_CHAT_TOKENS,
            period_start=current_period(),
        )
    )
    db.commit()


def _exhaust_embedding_quota(db: Session, user_id) -> None:
    db.add(
        UserUsage(
            user_id=user_id,
            embedding_chars=settings.FREE_QUOTA_EMBEDDING_CHARS,
            period_start=current_period(),
        )
    )
    db.commit()


def test_chat_quota_exhausted_returns_error_event(
    client: TestClient, db: Session
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
        json={},
    ).json()
    _exhaust_chat_quota(db, user.id)

    # The quota check runs before any provider call, so no provider mocking
    # is needed — a server-billed user at the limit must be blocked.
    response = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}/messages/stream",
        headers=headers,
        json={"content": "你好"},
    )
    assert response.status_code == 200
    messages = _sse_messages(response.text)
    assert any(
        "免费对话额度已用完" in payload.get("message", "") for payload in messages
    )


def test_embedding_quota_exhausted_blocks_search(
    client: TestClient, db: Session
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    _exhaust_embedding_quota(db, user.id)

    response = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/search",
        headers=headers,
        json={"query": "hello"},
    )
    assert response.status_code == 429
    assert "免费嵌入额度已用完" in response.json()["detail"]


def test_embedding_quota_exhausted_blocks_upload(
    client: TestClient, db: Session
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    _exhaust_embedding_quota(db, user.id)

    response = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/sources/",
        headers=headers,
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 429
    assert "免费嵌入额度已用完" in response.json()["detail"]


def test_chat_quota_exhausted_blocks_overview(client: TestClient, db: Session) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    _exhaust_chat_quota(db, user.id)

    response = client.get(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/overview", headers=headers
    )
    assert response.status_code == 429
    assert "免费对话额度已用完" in response.json()["detail"]


def test_usage_rolls_over_when_period_changes(client: TestClient, db: Session) -> None:
    user = create_random_user(db)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    from datetime import UTC, datetime

    old_period = datetime(2000, 1, 1, tzinfo=UTC)
    db.add(
        UserUsage(
            user_id=user.id,
            chat_tokens=99999,
            embedding_chars=99999,
            period_start=old_period,
        )
    )
    db.commit()

    response = client.get(f"{settings.API_V1_STR}/users/me/usage", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["chat_tokens"] == 0
    assert body["embedding_chars"] == 0
    assert body["period_start"] is not None


def test_reserve_usage_is_atomic_and_stops_at_quota(
    client: TestClient, db: Session
) -> None:
    import pytest

    from app.core.db import engine
    from app.services.usage import QuotaError, reserve_usage

    user = create_random_user(db)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)
    half = settings.FREE_QUOTA_CHAT_TOKENS // 2

    with Session(engine) as session:
        reserve_usage(session=session, user_id=user.id, chat_tokens=half)
        reserve_usage(session=session, user_id=user.id, chat_tokens=half)

        # The allowance is exactly exhausted; the next reservation must fail
        # atomically rather than pushing the counter past the limit.
        with pytest.raises(QuotaError):
            reserve_usage(session=session, user_id=user.id, chat_tokens=1)

    response = client.get(f"{settings.API_V1_STR}/users/me/usage", headers=headers)
    body = response.json()
    assert body["chat_tokens"] <= settings.FREE_QUOTA_CHAT_TOKENS


def test_reserve_with_own_key_is_unlimited(
    client: TestClient, db: Session
) -> None:
    from app.core.db import engine
    from app.services.usage import reserve_usage

    user = create_random_user(db)
    client.put(
        f"{settings.API_V1_STR}/users/me/provider-settings",
        headers=authentication_token_from_email(client=client, email=user.email, db=db),
        json={"chat_api_key": "sk-my-own-key-123456"},
    )
    with Session(engine) as session:
        chat_reserved, _ = reserve_usage(
            session=session, user_id=user.id, chat_tokens=10_000_000
        )
        assert chat_reserved == 0  # BYOK chat is not counted against free quota
