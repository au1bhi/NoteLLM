import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from app.models import UserUsage


def record_usage(
    *,
    session: Session,
    user_id: uuid.UUID,
    chat_tokens: int = 0,
    embedding_chars: int = 0,
) -> None:
    """Atomically accumulate usage for a user (insert-or-increment)."""
    now = datetime.now(UTC)
    stmt = insert(UserUsage).values(
        user_id=user_id,
        chat_tokens=max(0, chat_tokens),
        embedding_chars=max(0, embedding_chars),
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id"],
        set_={
            "chat_tokens": UserUsage.chat_tokens + max(0, chat_tokens),
            "embedding_chars": UserUsage.embedding_chars + max(0, embedding_chars),
            "updated_at": now,
        },
    )
    # session.exec is for SELECT; INSERT..ON CONFLICT requires execute()
    session.execute(stmt)  # ty: ignore[deprecated]
    session.commit()


def get_usage(session: Session, user_id: uuid.UUID) -> UserUsage | None:
    return session.exec(
        select(UserUsage).where(UserUsage.user_id == user_id)
    ).first()
