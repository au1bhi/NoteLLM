import uuid
from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.models import Chunk, Source
from app.services.embeddings import EmbeddingProvider

DEFAULT_RETRIEVAL_LIMIT = 5
MAX_RETRIEVAL_LIMIT = 10


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float
    source_display_name: str


def retrieve_chunks(
    *,
    session: Session,
    embedding_provider: EmbeddingProvider,
    notebook_id: uuid.UUID,
    query: str,
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
) -> list[RetrievedChunk]:
    query_embedding = embedding_provider.embed([query])[0]
    chunk_table = Chunk.__dict__["__table__"]
    embedding_column = chunk_table.c.embedding
    distance = embedding_column.cosine_distance(query_embedding).label("distance")
    statement = (
        select(Chunk, Source.display_name, distance)
        .join(Source, Chunk.source_id == Source.id)  # type: ignore[arg-type]
        .where(Source.notebook_id == notebook_id)
        .where(Source.status == "ready")
        .where(col(Chunk.embedding).is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    rows = session.exec(statement).all()
    return [
        RetrievedChunk(
            chunk=chunk,
            source_display_name=display_name,
            score=1.0 - float(row_distance),
        )
        for chunk, display_name, row_distance in rows
    ]
