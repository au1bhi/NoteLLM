import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlmodel import col, func, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Conversation,
    ConversationCreate,
    ConversationPublic,
    ConversationsPublic,
    Notebook,
    NotebookCreate,
    NotebookOverviewPublic,
    NotebookPublic,
    NotebooksPublic,
    NotebookUpdate,
    RetrievedChunkPublic,
    RetrievedChunksPublic,
    SearchRequest,
    Source,
    SourcePublic,
    SourcesPublic,
    StudyFaqPublic,
    StudyGuidePublic,
    StudySectionPublic,
    get_datetime_utc,
)
from app.services.chat import ChatError, get_chat_provider
from app.services.embeddings import EmbeddingError, get_embedding_provider
from app.services.overview import generate_overview, store_overview
from app.services.provider_settings import (
    effective_chat_config,
    effective_embedding_config,
    load_user_provider_settings,
)
from app.services.retrieval import retrieve_chunks
from app.services.sources import (
    create_source_from_upload,
    delete_notebook_files,
    delete_source,
    process_source_isolated,
)
from app.services.study_guide import generate_study_guide
from app.services.usage import (
    QuotaError,
    check_embedding_quota,
    estimate_chat_reserve,
    reserve_usage,
    settle_usage,
)

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


def get_notebook_or_404(
    *, session: SessionDep, current_user: CurrentUser, notebook_id: uuid.UUID
) -> Notebook:
    notebook = session.get(Notebook, notebook_id)
    if not notebook or notebook.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="笔记本不存在")
    return notebook


def get_source_or_404(
    *, session: SessionDep, notebook_id: uuid.UUID, source_id: uuid.UUID
) -> Source:
    source = session.get(Source, source_id)
    if not source or source.notebook_id != notebook_id:
        raise HTTPException(status_code=404, detail="资料不存在")
    return source


@router.get("/", response_model=NotebooksPublic)
def read_notebooks(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    statement = select(Notebook).where(Notebook.owner_id == current_user.id)
    count = session.exec(
        select(func.count())
        .select_from(Notebook)
        .where(Notebook.owner_id == current_user.id)
    ).one()
    notebooks = session.exec(
        statement.order_by(col(Notebook.updated_at).desc()).offset(skip).limit(limit)
    ).all()
    return NotebooksPublic(
        data=[NotebookPublic.model_validate(notebook) for notebook in notebooks],
        count=count,
    )


@router.post("/", response_model=NotebookPublic)
def create_notebook(
    *, session: SessionDep, current_user: CurrentUser, notebook_in: NotebookCreate
) -> Notebook:
    notebook = Notebook.model_validate(
        notebook_in, update={"owner_id": current_user.id}
    )
    session.add(notebook)
    session.commit()
    session.refresh(notebook)
    return notebook


@router.get("/{notebook_id}", response_model=NotebookPublic)
def read_notebook(
    notebook_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Notebook:
    return get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )


@router.put("/{notebook_id}", response_model=NotebookPublic)
def update_notebook(
    *,
    notebook_id: uuid.UUID,
    notebook_in: NotebookUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Notebook:
    notebook = get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    data = notebook_in.model_dump(exclude_unset=True)
    # Only touch updated_at when the content actually changed; a pin toggle
    # should not rewrite the "last updated" timestamp that drives recency.
    if "title" in data or "description" in data:
        notebook.updated_at = get_datetime_utc()
    notebook.sqlmodel_update(data)
    session.add(notebook)
    session.commit()
    session.refresh(notebook)
    return notebook


@router.delete("/{notebook_id}")
def delete_notebook(
    notebook_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> dict[str, str]:
    notebook = get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    session.delete(notebook)
    session.commit()
    # The DB rows cascade away; also unlink the uploaded files so deleted
    # notebooks leave no residue on the uploads volume.
    delete_notebook_files(notebook_id)
    return {"message": "笔记本删除成功"}


@router.get("/{notebook_id}/sources/", response_model=SourcesPublic)
def read_sources(
    notebook_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    statement = select(Source).where(Source.notebook_id == notebook_id)
    count = session.exec(
        select(func.count())
        .select_from(Source)
        .where(Source.notebook_id == notebook_id)
    ).one()
    sources = session.exec(
        statement.order_by(col(Source.created_at).desc()).offset(skip).limit(limit)
    ).all()
    return SourcesPublic(
        data=[SourcePublic.model_validate(source) for source in sources], count=count
    )


@router.get("/{notebook_id}/conversations/", response_model=ConversationsPublic)
def read_conversations(
    notebook_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> ConversationsPublic:
    get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    statement = select(Conversation).where(Conversation.notebook_id == notebook_id)
    count = session.exec(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.notebook_id == notebook_id)
    ).one()
    conversations = session.exec(
        statement.order_by(col(Conversation.updated_at).desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return ConversationsPublic(
        data=[
            ConversationPublic.model_validate(conversation)
            for conversation in conversations
        ],
        count=count,
    )


@router.post("/{notebook_id}/conversations/", response_model=ConversationPublic)
def create_conversation(
    notebook_id: uuid.UUID,
    conversation_in: ConversationCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Conversation:
    notebook = get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    conversation = Conversation(
        notebook_id=notebook.id,
        title=conversation_in.title or "New conversation",
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


@router.post("/{notebook_id}/search", response_model=RetrievedChunksPublic)
def search_notebook(
    notebook_id: uuid.UUID,
    search_in: SearchRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> RetrievedChunksPublic:
    get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    try:
        user_settings = load_user_provider_settings(session, current_user.id)
        # Reserve the exact query length atomically before embedding it.
        embedding_reserved = len(search_in.query)
        reserve_usage(
            session=session,
            user_id=current_user.id,
            user_settings=user_settings,
            embedding_chars=embedding_reserved,
        )
        retrieved = retrieve_chunks(
            session=session,
            embedding_provider=get_embedding_provider(
                effective_embedding_config(user_settings)
            ),
            notebook_id=notebook_id,
            query=search_in.query,
            limit=search_in.limit,
        )
    except EmbeddingError as error:
        # Refund the embedding reservation — the provider call failed, so the
        # allowance must not be permanently consumed.
        if embedding_reserved:
            settle_usage(
                session=session,
                user_id=current_user.id,
                embedding_chars=-embedding_reserved,
            )
        raise HTTPException(status_code=503, detail=str(error)) from error
    except QuotaError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    return RetrievedChunksPublic(
        data=[
            RetrievedChunkPublic(
                id=result.chunk.id,
                source_id=result.chunk.source_id,
                source_display_name=result.source_display_name,
                content=result.chunk.content,
                page_number=result.chunk.page_number,
                score=result.score,
            )
            for result in retrieved
        ]
    )


def _clear_overview(session: SessionDep, notebook: Notebook) -> None:
    notebook.overview = None
    notebook.overview_topics = []
    notebook.overview_updated_at = None
    session.add(notebook)
    session.commit()


def _generate_and_store_overview(
    *, session: SessionDep, notebook: Notebook, current_user: CurrentUser
) -> None:
    user_settings = load_user_provider_settings(session, current_user.id)
    chat_provider = get_chat_provider(effective_chat_config(user_settings))
    chat_reserved = 0
    try:
        chat_reserved, _ = reserve_usage(
            session=session,
            user_id=current_user.id,
            user_settings=user_settings,
            chat_tokens=estimate_chat_reserve(notebook.title or ""),
        )
        overview = generate_overview(
            session=session, notebook_id=notebook.id, chat_provider=chat_provider
        )
    except QuotaError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except ChatError as error:
        # The provider call failed after a reservation was made: refund it so a
        # burst of failing calls cannot drain the monthly allowance.
        if chat_reserved:
            settle_usage(
                session=session,
                user_id=current_user.id,
                chat_tokens=-chat_reserved,
            )
        raise HTTPException(status_code=503, detail=str(error)) from error
    store_overview(session=session, notebook=notebook, overview=overview)
    if chat_reserved:
        settle_usage(
            session=session,
            user_id=current_user.id,
            chat_tokens=getattr(chat_provider, "total_tokens_used", 0) - chat_reserved,
        )


@router.get("/{notebook_id}/overview", response_model=NotebookOverviewPublic)
def read_notebook_overview(
    notebook_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> NotebookOverviewPublic:
    """Return the notebook overview, generating it lazily on first view."""
    notebook = get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    if notebook.overview is None:
        _generate_and_store_overview(
            session=session, notebook=notebook, current_user=current_user
        )
    return NotebookOverviewPublic(
        summary=notebook.overview or "",
        topics=notebook.overview_topics or [],
        updated_at=notebook.overview_updated_at,
    )


@router.post(
    "/{notebook_id}/overview/regenerate", response_model=NotebookOverviewPublic
)
def regenerate_notebook_overview(
    notebook_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> NotebookOverviewPublic:
    notebook = get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    _generate_and_store_overview(
        session=session, notebook=notebook, current_user=current_user
    )
    return NotebookOverviewPublic(
        summary=notebook.overview or "",
        topics=notebook.overview_topics or [],
        updated_at=notebook.overview_updated_at,
    )


@router.post("/{notebook_id}/study-guide", response_model=StudyGuidePublic)
def generate_notebook_study_guide(
    notebook_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> StudyGuidePublic:
    """Generate a printable study guide (sections + FAQs) from the notebook."""
    get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    user_settings = load_user_provider_settings(session, current_user.id)
    chat_provider = get_chat_provider(effective_chat_config(user_settings))
    chat_reserved = 0
    try:
        chat_reserved, _ = reserve_usage(
            session=session,
            user_id=current_user.id,
            user_settings=user_settings,
            chat_tokens=estimate_chat_reserve("学习指南"),
        )
        guide = generate_study_guide(
            session=session, notebook_id=notebook_id, chat_provider=chat_provider
        )
    except QuotaError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except ChatError as error:
        # Refund the reservation on a failed provider call (see overview).
        if chat_reserved:
            settle_usage(
                session=session,
                user_id=current_user.id,
                chat_tokens=-chat_reserved,
            )
        raise HTTPException(status_code=503, detail=str(error)) from error
    if chat_reserved:
        settle_usage(
            session=session,
            user_id=current_user.id,
            chat_tokens=getattr(chat_provider, "total_tokens_used", 0) - chat_reserved,
        )
    return StudyGuidePublic(
        sections=[
            StudySectionPublic(title=section.title, content=section.content)
            for section in guide.sections
        ],
        faqs=[
            StudyFaqPublic(question=faq.question, answer=faq.answer)
            for faq in guide.faqs
        ],
    )


@router.post("/{notebook_id}/sources/", response_model=SourcePublic)
async def upload_source(
    notebook_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> Source:
    notebook = get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    user_settings = load_user_provider_settings(session, current_user.id)
    try:
        check_embedding_quota(session, current_user.id, user_settings)
    except QuotaError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    created = await create_source_from_upload(
        session=session, notebook=notebook, upload=file
    )
    # Offload the blocking PDF/text extraction + embedding HTTP calls off the
    # async event loop (a large upload would otherwise freeze the API for all
    # users while it runs).
    await run_in_threadpool(process_source_isolated, created.id)
    session.refresh(created)
    _clear_overview(session, notebook)
    return created


@router.delete("/{notebook_id}/sources/{source_id}")
def remove_source(
    notebook_id: uuid.UUID,
    source_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    notebook = get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    source = get_source_or_404(
        session=session, notebook_id=notebook_id, source_id=source_id
    )
    delete_source(session=session, source=source)
    _clear_overview(session, notebook)
    return {"message": "资料删除成功"}


@router.post("/{notebook_id}/sources/{source_id}/retry", response_model=SourcePublic)
async def retry_source(
    notebook_id: uuid.UUID,
    source_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Source:
    notebook = get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    source = get_source_or_404(
        session=session, notebook_id=notebook_id, source_id=source_id
    )
    await run_in_threadpool(process_source_isolated, source.id)
    session.refresh(source)
    _clear_overview(session, notebook)
    return source
