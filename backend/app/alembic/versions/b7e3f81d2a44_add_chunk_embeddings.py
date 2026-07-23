"""Add pgvector embeddings to chunks.

Revision ID: b7e3f81d2a44
Revises: 4d2a6b1c8f90
Create Date: 2026-07-23 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector


revision = "b7e3f81d2a44"
down_revision = "4d2a6b1c8f90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("chunk", sa.Column("embedding", Vector(1536), nullable=True))
    op.execute(
        "CREATE INDEX ix_chunk_embedding_hnsw ON chunk USING hnsw "
        "(embedding vector_cosine_ops) WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw")
    op.drop_column("chunk", "embedding")
