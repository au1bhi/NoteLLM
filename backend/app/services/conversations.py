import uuid

from sqlmodel import Session, col, select

from app.core.db import engine
from app.models import (
    AnswerMode,
    Chunk,
    Citation,
    CitationPublic,
    Conversation,
    ConversationDetailPublic,
    ConversationMessage,
    ConversationMessagePublic,
    Notebook,
    Source,
    get_datetime_utc,
)
from app.services.answers import GroundedAnswer, answer_question
from app.services.chat import get_chat_provider
from app.services.embeddings import get_embedding_provider
from app.services.provider_settings import (
    effective_chat_config,
    effective_embedding_config,
    load_user_provider_settings,
)
from app.services.usage import estimate_chat_reserve, usage_reservation


def _citation_public(
    *, citation: Citation, chunk: Chunk, source: Source
) -> CitationPublic:
    return CitationPublic(
        chunk_id=citation.chunk_id,
        ordinal=citation.ordinal,
        quote=citation.quote,
        source_display_name=source.display_name,
        page_number=chunk.page_number,
    )


def conversation_detail(
    *, session: Session, conversation: Conversation
) -> ConversationDetailPublic:
    """Build a conversation view with citations loaded in bounded queries."""
    messages = session.exec(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(col(ConversationMessage.created_at))
    ).all()
    message_ids = [message.id for message in messages]
    citations = (
        session.exec(
            select(Citation)
            .where(col(Citation.message_id).in_(message_ids))
            .order_by(col(Citation.ordinal))
        ).all()
        if message_ids
        else []
    )
    chunk_ids = {citation.chunk_id for citation in citations}
    chunks_by_id = (
        {
            chunk.id: chunk
            for chunk in session.exec(
                select(Chunk).where(col(Chunk.id).in_(chunk_ids))
            ).all()
        }
        if chunk_ids
        else {}
    )
    source_ids = {chunk.source_id for chunk in chunks_by_id.values()}
    sources_by_id = (
        {
            source.id: source
            for source in session.exec(
                select(Source).where(col(Source.id).in_(source_ids))
            ).all()
        }
        if source_ids
        else {}
    )
    citations_by_message: dict[uuid.UUID, list[CitationPublic]] = {
        message_id: [] for message_id in message_ids
    }
    for citation in citations:
        chunk = chunks_by_id.get(citation.chunk_id)
        source = sources_by_id.get(chunk.source_id) if chunk else None
        if not chunk or not source:
            raise RuntimeError("Citation references a deleted chunk")
        citations_by_message[citation.message_id].append(
            _citation_public(citation=citation, chunk=chunk, source=source)
        )
    return ConversationDetailPublic(
        id=conversation.id,
        notebook_id=conversation.notebook_id,
        title=conversation.title,
        is_pinned=conversation.is_pinned,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            ConversationMessagePublic(
                id=message.id,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
                suggestions=message.suggestions or [],
                citations=citations_by_message[message.id],
            )
            for message in messages
        ],
    )


def persist_answer(
    *,
    conversation_id: uuid.UUID,
    question: str,
    mode: AnswerMode = "grounded",
    source_ids: list[uuid.UUID] | None = None,
) -> GroundedAnswer:
    """Generate and atomically persist one user/assistant exchange."""
    with Session(engine) as session:
        conversation = session.get(Conversation, conversation_id)
        if not conversation:
            raise RuntimeError("Conversation no longer exists")
        notebook = session.get(Notebook, conversation.notebook_id)
        if not notebook:
            raise RuntimeError("Notebook no longer exists")

        user_settings = load_user_provider_settings(session, notebook.owner_id)
        embedding_reserve = len(question) if mode != "knowledge" else 0
        with usage_reservation(
            session=session,
            user_id=notebook.owner_id,
            user_settings=user_settings,
            chat_tokens=estimate_chat_reserve(question),
            embedding_chars=embedding_reserve,
        ) as reservation:
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
                conversation_id=conversation.id,
            )
            reservation.set_actual(
                chat_tokens=answer.tokens_used,
                embedding_chars=embedding_reserve,
            )

        user_message = ConversationMessage(
            conversation_id=conversation.id, role="user", content=question
        )
        assistant_message = ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=answer.content,
            suggestions=answer.suggestions,
        )
        session.add(user_message)
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
        if conversation.title in ("New conversation", "新建会话", "会话"):
            clean_title = question.strip().replace("\n", " ")
            conversation.title = (
                clean_title[:32] + "…" if len(clean_title) > 32 else clean_title
            )
        session.add(conversation)
        session.commit()
        return answer
