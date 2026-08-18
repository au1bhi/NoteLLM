import pytest
from pytest import MonkeyPatch
from sqlmodel import Session, col, select

from app.models import Conversation, ConversationMessage, UserUsage
from app.services import conversations
from app.services.answers import GroundedAnswer
from app.services.chat import ChatError
from tests.utils.notebook import create_random_notebook
from tests.utils.user import create_random_user


def test_persist_answer_stores_exchange_and_updates_default_title(
    db: Session, monkeypatch: MonkeyPatch
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    conversation = Conversation(notebook_id=notebook.id, title="New conversation")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    monkeypatch.setattr(conversations, "get_chat_provider", lambda *_: object())
    monkeypatch.setattr(conversations, "get_embedding_provider", lambda *_: object())
    monkeypatch.setattr(
        conversations,
        "answer_question",
        lambda **_: GroundedAnswer(
            content="基于资料的回答",
            citations=[],
            suggestions=["继续阅读"],
            tokens_used=37,
        ),
    )

    answer = conversations.persist_answer(
        conversation_id=conversation.id,
        question="资料的核心结论是什么？",
    )

    db.expire_all()
    messages = db.exec(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(col(ConversationMessage.created_at))
    ).all()
    stored = db.get(Conversation, conversation.id)
    assert answer.content == "基于资料的回答"
    assert [(message.role, message.content) for message in messages] == [
        ("user", "资料的核心结论是什么？"),
        ("assistant", "基于资料的回答"),
    ]
    assert messages[1].suggestions == ["继续阅读"]
    assert stored is not None
    assert stored.title == "资料的核心结论是什么？"


def test_persist_answer_provider_failure_leaves_no_messages(
    db: Session, monkeypatch: MonkeyPatch
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    conversation = Conversation(notebook_id=notebook.id, title="New conversation")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    monkeypatch.setattr(conversations, "get_chat_provider", lambda *_: object())
    monkeypatch.setattr(conversations, "get_embedding_provider", lambda *_: object())

    def fail_answer(**_: object) -> GroundedAnswer:
        raise ChatError("provider failed")

    monkeypatch.setattr(conversations, "answer_question", fail_answer)

    with pytest.raises(ChatError, match="provider failed"):
        conversations.persist_answer(
            conversation_id=conversation.id,
            question="不会被持久化的问题",
        )

    db.expire_all()
    messages = db.exec(
        select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation.id
        )
    ).all()
    usage_row = db.exec(select(UserUsage).where(UserUsage.user_id == user.id)).one()
    assert messages == []
    assert usage_row.chat_tokens == 0
    assert usage_row.embedding_chars == 0
