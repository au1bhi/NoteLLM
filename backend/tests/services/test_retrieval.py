import uuid
from collections.abc import Sequence

from sqlmodel import Session

from app.core.config import settings
from app.models import Chunk, Notebook, Source
from app.services.retrieval import retrieve_chunks
from tests.utils.user import create_random_user


class FixedEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [vector(0) for _ in texts]


def vector(index: int) -> list[float]:
    values = [0.0] * settings.EMBEDDING_DIMENSIONS
    values[index] = 1.0
    return values


def create_source(*, session: Session, notebook_id: uuid.UUID, name: str) -> Source:
    source = Source(
        notebook_id=notebook_id,
        display_name=name,
        media_type="text/plain",
        file_size_bytes=1,
        storage_path=f"{uuid.uuid4()}.txt",
        status="ready",
    )
    session.add(source)
    session.flush()
    return source


def test_retrieval_orders_by_cosine_similarity_and_isolates_notebooks(
    db: Session,
) -> None:
    user = create_random_user(db)
    notebook = Notebook(title="Target", owner_id=user.id)
    other_notebook = Notebook(title="Other", owner_id=user.id)
    db.add(notebook)
    db.add(other_notebook)
    db.flush()
    source = create_source(session=db, notebook_id=notebook.id, name="target.txt")
    other_source = create_source(
        session=db, notebook_id=other_notebook.id, name="private.txt"
    )
    db.add_all(
        [
            Chunk(
                source_id=source.id,
                ordinal=0,
                content="closest evidence",
                char_start=0,
                char_end=16,
                embedding=vector(0),
            ),
            Chunk(
                source_id=source.id,
                ordinal=1,
                content="less relevant evidence",
                char_start=0,
                char_end=22,
                embedding=vector(1),
            ),
            Chunk(
                source_id=other_source.id,
                ordinal=0,
                content="must not be retrieved",
                char_start=0,
                char_end=21,
                embedding=vector(0),
            ),
        ]
    )
    db.commit()

    results = retrieve_chunks(
        session=db,
        embedding_provider=FixedEmbeddingProvider(),
        notebook_id=notebook.id,
        query="evidence",
    )

    assert [result.chunk.content for result in results] == [
        "closest evidence",
        "less relevant evidence",
    ]
    assert results[0].score > results[1].score
