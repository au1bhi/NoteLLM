import uuid
from collections.abc import AsyncIterable

from fastapi import APIRouter, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlmodel import Session, col, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, SessionDep
from app.core.db import engine
from app.models import (
    AnswerMode,
    Chunk,
    Citation,
    CitationPublic,
    Conversation,
    ConversationDetailPublic,
    ConversationMessage,
    ConversationMessageCreate,
    ConversationMessagePublic,
    ConversationPublic,
    ConversationUpdate,
    Notebook,
    Source,
    get_datetime_utc,
)
from app.services.answers import GroundedAnswer, answer_question
from app.services.chat import ChatError, get_chat_provider
from app.services.embeddings import EmbeddingError, get_embedding_provider
from app.services.provider_settings import (
    effective_chat_config,
    effective_embedding_config,
    load_user_provider_settings,
)
from app.services.usage import record_usage

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
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def citation_public(*, session: Session, citation: Citation) -> CitationPublic:
    chunk = session.get(Chunk, citation.chunk_id)
    source = session.get(Source, chunk.source_id) if chunk else None
    if not chunk or not source:
        raise RuntimeError("Citation references a deleted chunk")
    return CitationPublic(
        chunk_id=citation.chunk_id,
        ordinal=citation.ordinal,
        quote=citation.quote,
        source_display_name=source.display_name,
        page_number=chunk.page_number,
    )


def conversation_detail(*, session: Session, conversation: Conversation) -> ConversationDetailPublic:
    messages = session.exec(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(col(ConversationMessage.created_at))
    ).all()
    message_public = []
    for message in messages:
        citations = session.exec(
            select(Citation)
            .where(Citation.message_id == message.id)
            .order_by(col(Citation.ordinal))
        ).all()
        message_public.append(
            ConversationMessagePublic(
                id=message.id,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
                suggestions=message.suggestions or [],
                citations=[citation_public(session=session, citation=citation) for citation in citations],
            )
        )
    return ConversationDetailPublic(
        id=conversation.id,
        notebook_id=conversation.notebook_id,
        title=conversation.title,
        is_pinned=conversation.is_pinned,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=message_public,
    )


def persist_answer(
    *,
    conversation_id: uuid.UUID,
    question: str,
    mode: AnswerMode = "grounded",
    source_ids: list[uuid.UUID] | None = None,
) -> GroundedAnswer:
    with Session(engine) as session:
        conversation = session.get(Conversation, conversation_id)
        if not conversation:
            raise RuntimeError("Conversation no longer exists")
        user_message = ConversationMessage(
            conversation_id=conversation.id, role="user", content=question
        )
        session.add(user_message)
        notebook = session.get(Notebook, conversation.notebook_id)
        user_settings = (
            load_user_provider_settings(session, notebook.owner_id)
            if notebook
            else None
        )
        answer = answer_question(
            session=session,
            notebook_id=conversation.notebook_id,
            query=question,
            chat_provider=get_chat_provider(effective_chat_config(user_settings)),
            embedding_provider=get_embedding_provider(
                effective_embedding_config(user_settings)
            ),
            mode=mode,
            source_ids=source_ids,
        )
        if notebook:
            record_usage(
                session=session,
                user_id=notebook.owner_id,
                chat_tokens=answer.tokens_used,
                embedding_chars=len(question) if mode != "knowledge" else 0,
            )
        assistant_message = ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=answer.content,
            suggestions=answer.suggestions,
        )
        session.add(assistant_message)
        session.flush()
        for ordinal, citation in enumerate(answer.citations):
            session.add(
                Citation(
                    message_id=assistant_message.id,
                    chunk_id=citation.chunk_id,
                    ordinal=ordinal,
                    quote=citation.quote,
                )
            )
        conversation.updated_at = get_datetime_utc()
        if conversation.title == "New conversation":
            conversation.title = question[:255]
        session.add(conversation)
        session.commit()
        return answer


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
            raise HTTPException(status_code=422, detail="Title cannot be empty")
        conversation.title = conversation_in.title.strip()
        conversation.updated_at = get_datetime_utc()
    if conversation_in.is_pinned is not None:
        conversation.is_pinned = conversation_in.is_pinned
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return ConversationPublic.model_validate(conversation)


@router.post("/{conversation_id}/messages/stream", response_class=EventSourceResponse)
async def stream_message(
    conversation_id: uuid.UUID,
    message_in: ConversationMessageCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> AsyncIterable[ServerSentEvent]:
    get_conversation_or_404(
        session=session, current_user=current_user, conversation_id=conversation_id
    )
    try:
        answer = await run_in_threadpool(
            lambda: persist_answer(
                conversation_id=conversation_id,
                question=message_in.content,
                mode=message_in.mode,
                source_ids=message_in.source_ids,
            )
        )
    except (ChatError, EmbeddingError, RuntimeError) as error:
        yield ServerSentEvent(data={"message": str(error)}, event="error")
        yield ServerSentEvent(data={"conversation_id": str(conversation_id)}, event="done")
        return
    except Exception as error:
        yield ServerSentEvent(
            data={"message": f"Unexpected error: {type(error).__name__}"},
            event="error",
        )
        yield ServerSentEvent(data={"conversation_id": str(conversation_id)}, event="done")
        return
    for word in answer.content.split(" "):
        yield ServerSentEvent(data={"text": f"{word} "}, event="delta")
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
