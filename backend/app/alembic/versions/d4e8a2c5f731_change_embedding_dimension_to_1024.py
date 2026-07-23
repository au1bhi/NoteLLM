"""Change embeddings to the configured 1024-dimension model.

Revision ID: d4e8a2c5f731
Revises: c8d6e4a9f102
Create Date: 2026-07-23 00:00:00.000000
"""

from alembic import op
from pgvector.sqlalchemy import Vector


revision = "d4e8a2c5f731"
down_revision = "c8d6e4a9f102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw")
    op.execute("UPDATE chunk SET embedding = NULL WHERE embedding IS NOT NULL")
    op.alter_column(
        "chunk",
        "embedding",
        type_=Vector(1024),
        postgresql_using="embedding::vector(1024)",
    )
    op.execute(
        "CREATE INDEX ix_chunk_embedding_hnsw ON chunk USING hnsw "
        "(embedding vector_cosine_ops) WHERE embedding IS NOT NULL"
    )
    op.execute(
        "UPDATE source SET status = 'failed', "
        "error_message = 'Embeddings need regeneration after the vector dimension change; retry this source.', "
        "processed_at = NULL WHERE status = 'ready'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw")
    op.execute("UPDATE chunk SET embedding = NULL WHERE embedding IS NOT NULL")
    op.alter_column(
        "chunk",
        "embedding",
        type_=Vector(1536),
        postgresql_using="embedding::vector(1536)",
    )
    op.execute(
        "CREATE INDEX ix_chunk_embedding_hnsw ON chunk USING hnsw "
        "(embedding vector_cosine_ops) WHERE embedding IS NOT NULL"
    )
