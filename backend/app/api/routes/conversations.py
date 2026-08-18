import uuid
from collections.abc import AsyncIterable, Iterable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, SessionDep
from app.core.rate_limit import rate_limit
from app.models import (
    Conversation,
    ConversationDetailPublic,
    ConversationMessageCreate,
    ConversationPublic,
    ConversationUpdate,
    Notebook,
    get_datetime_utc,
)
from app.services.chat import ChatError
from app.services.conversations import conversation_detail, persist_answer
from app.services.embeddings import EmbeddingError
from app.services.usage import QuotaError

router = APIRouter(prefix="/conversations", tags=["conversations"])


def get_conversation_or_404(
    *, session: Session, current_user: CurrentUser, conversation_id: uuid.UUID
) -> Conversation:
    conversation = session.exec(
        select(Conversation)
        .join(Notebook)
        .where(Conversation.id == conversation_id)
        .where(Notebook.owner_id == current_user.id)
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conversation


@router.get("/{conversation_id}", response_model=ConversationDetailPublic)
def read_conversation(
    conversation_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> ConversationDetailPublic:
    conversation = get_conversation_or_404(
        session=session, current_user=current_user, conversation_id=conversation_id
    )
    return conversation_detail(session=session, conversation=conversation)


@router.patch("/{conversation_id}", response_model=ConversationPublic)
def update_conversation(
    conversation_id: uuid.UUID,
    conversation_in: ConversationUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ConversationPublic:
    conversation = get_conversation_or_404(
        session=session, current_user=current_user, conversation_id=conversation_id
    )
    if conversation_in.title is not None:
        if not conversation_in.title.strip():
            raise HTTPException(status_code=422, detail="标题不能为空")
        conversation.title = conversation_in.title.strip()
        conversation.updated_at = get_datetime_utc()
    if conversation_in.is_pinned is not None:
        conversation.is_pinned = conversation_in.is_pinned
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return ConversationPublic.model_validate(conversation)


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Delete a conversation and its messages/citations (cascade)."""
    conversation = get_conversation_or_404(
        session=session, current_user=current_user, conversation_id=conversation_id
    )
    session.delete(conversation)
    session.commit()
    return {"message": "会话删除成功"}


def get_owned_conversation_or_404(
    conversation_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Conversation:
    """Resolve a conversation the current user owns (raises 404 otherwise).

    Used as a FastAPI dependency so ownership is enforced *before* the response
    is committed — an async generator cannot raise HTTPException cleanly after
    it has started streaming.
    """
    return get_conversation_or_404(
        session=session, current_user=current_user, conversation_id=conversation_id
    )


def _iter_stream_chunks(content: str) -> Iterable[str]:
    """Yield small display chunks for SSE streaming.

    Splitting on spaces alone breaks Chinese text (no spaces between words),
    which would emit the whole answer as a single delta and defeat streaming.
    Emit each CJK character individually and each Latin word (with its trailing
    space) separately so both scripts stream at a natural reading pace.
    """
    buffer: list[str] = []

    def flush() -> Iterable[str]:
        if buffer:
            yield "".join(buffer)
            buffer.clear()

    for char in content:
        if ord(char) > 0x2E7F:  # CJK and full-width ranges start above U+2E7F
            yield from flush()
            yield char
        else:
            buffer.append(char)
            if char == " ":
                yield from flush()
    yield from flush()


@router.post(
    "/{conversation_id}/messages/stream",
    response_class=EventSourceResponse,
    dependencies=[Depends(rate_limit(limit=60, window=60))],
)
async def stream_message(
    conversation: Annotated[Conversation, Depends(get_owned_conversation_or_404)],
    message_in: ConversationMessageCreate,
) -> AsyncIterable[ServerSentEvent]:
    conversation_id = conversation.id
    try:
        answer = await run_in_threadpool(
            lambda: persist_answer(
                conversation_id=conversation_id,
                question=message_in.content,
                mode=message_in.mode,
                source_ids=message_in.source_ids,
            )
        )
    except (ChatError, EmbeddingError, QuotaError, RuntimeError) as error:
        yield ServerSentEvent(data={"message": str(error)}, event="error")
        yield ServerSentEvent(
            data={"conversation_id": str(conversation_id)}, event="done"
        )
        return
    except Exception as error:
        yield ServerSentEvent(
            data={"message": f"意外错误：{type(error).__name__}"},
            event="error",
        )
        yield ServerSentEvent(
            data={"conversation_id": str(conversation_id)}, event="done"
        )
        return
    for chunk in _iter_stream_chunks(answer.content):
        yield ServerSentEvent(data={"text": chunk}, event="delta")
    yield ServerSentEvent(
        data={
            "citations": [
                {
                    "chunk_id": str(citation.chunk_id),
                    "quote": citation.quote,
                    "source_display_name": citation.source_display_name,
                    "page_number": citation.page_number,
                }
                for citation in answer.citations
            ]
        },
        event="citations",
    )
    yield ServerSentEvent(data={"conversation_id": str(conversation_id)}, event="done")
