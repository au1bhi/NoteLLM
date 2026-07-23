import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlmodel import col, func, select

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Conversation,
    ConversationCreate,
    ConversationPublic,
    ConversationsPublic,
    Notebook,
    NotebookCreate,
    NotebookPublic,
    NotebooksPublic,
    NotebookUpdate,
    RetrievedChunkPublic,
    RetrievedChunksPublic,
    SearchRequest,
    Source,
    SourcePublic,
    SourcesPublic,
    get_datetime_utc,
)
from app.services.embeddings import EmbeddingError, get_embedding_provider
from app.services.retrieval import retrieve_chunks
from app.services.sources import (
    create_source_from_upload,
    delete_source,
    process_source,
)

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


def get_notebook_or_404(
    *, session: SessionDep, current_user: CurrentUser, notebook_id: uuid.UUID
) -> Notebook:
    notebook = session.get(Notebook, notebook_id)
    if not notebook or notebook.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return notebook


def get_source_or_404(
    *, session: SessionDep, notebook_id: uuid.UUID, source_id: uuid.UUID
) -> Source:
    source = session.get(Source, source_id)
    if not source or source.notebook_id != notebook_id:
        raise HTTPException(status_code=404, detail="Source not found")
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
    notebook.sqlmodel_update(notebook_in.model_dump(exclude_unset=True))
    notebook.updated_at = get_datetime_utc()
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
    return {"message": "Notebook deleted successfully"}


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
        statement.order_by(col(Conversation.updated_at).desc()).offset(skip).limit(limit)
    ).all()
    return ConversationsPublic(
        data=[ConversationPublic.model_validate(conversation) for conversation in conversations],
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
        retrieved = retrieve_chunks(
            session=session,
            embedding_provider=get_embedding_provider(),
            notebook_id=notebook_id,
            query=search_in.query,
            limit=search_in.limit,
        )
    except EmbeddingError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
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
    return await create_source_from_upload(
        session=session, notebook=notebook, upload=file
    )


@router.delete("/{notebook_id}/sources/{source_id}")
def remove_source(
    notebook_id: uuid.UUID,
    source_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    source = get_source_or_404(
        session=session, notebook_id=notebook_id, source_id=source_id
    )
    delete_source(session=session, source=source)
    return {"message": "Source deleted successfully"}


@router.post("/{notebook_id}/sources/{source_id}/retry", response_model=SourcePublic)
def retry_source(
    notebook_id: uuid.UUID,
    source_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Source:
    get_notebook_or_404(
        session=session, current_user=current_user, notebook_id=notebook_id
    )
    source = get_source_or_404(
        session=session, notebook_id=notebook_id, source_id=source_id
    )
    process_source(session=session, source=source)
    return source
