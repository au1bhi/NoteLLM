import uuid

from sqlmodel import Session, select

from app.models import UserUsage


def record_usage(
    *,
    session: Session,
    user_id: uuid.UUID,
    chat_tokens: int = 0,
    embedding_chars: int = 0,
) -> None:
    usage = session.exec(
        select(UserUsage).where(UserUsage.user_id == user_id)
    ).first()
    if usage is None:
        usage = UserUsage(user_id=user_id)
        session.add(usage)
    usage.chat_tokens += max(0, chat_tokens)
    usage.embedding_chars += max(0, embedding_chars)
    session.add(usage)
    session.commit()


def get_usage(session: Session, user_id: uuid.UUID) -> UserUsage | None:
    return session.exec(
        select(UserUsage).where(UserUsage.user_id == user_id)
    ).first()
