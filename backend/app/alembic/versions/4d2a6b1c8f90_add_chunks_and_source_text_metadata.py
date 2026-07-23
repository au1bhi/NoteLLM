"""Add chunks and source text metadata

Revision ID: 4d2a6b1c8f90
Revises: 9a6f7c2d1e30
Create Date: 2026-07-23 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "4d2a6b1c8f90"
down_revision = "9a6f7c2d1e30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source", sa.Column("char_count", sa.Integer(), nullable=True))
    op.create_table(
        "chunk",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "ordinal", name="uq_chunk_source_ordinal"),
    )
    op.create_index("ix_chunk_source_id", "chunk", ["source_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chunk_source_id", table_name="chunk")
    op.drop_table("chunk")
    op.drop_column("source", "char_count")
