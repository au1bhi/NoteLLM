"""Add persisted grounded conversations.

Revision ID: c8d6e4a9f102
Revises: b7e3f81d2a44
Create Date: 2026-07-23 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "c8d6e4a9f102"
down_revision = "b7e3f81d2a44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notebook_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebook.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_notebook_id", "conversation", ["notebook_id"])
    op.create_table(
        "conversation_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversation.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_message_conversation_id",
        "conversation_message",
        ["conversation_id"],
    )
    op.create_table(
        "citation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("quote", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"], ["conversation_message.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunk.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_citation_message_id", "citation", ["message_id"])
    op.create_index("ix_citation_chunk_id", "citation", ["chunk_id"])


def downgrade() -> None:
    op.drop_index("ix_citation_chunk_id", table_name="citation")
    op.drop_index("ix_citation_message_id", table_name="citation")
    op.drop_table("citation")
    op.drop_index("ix_conversation_message_conversation_id", table_name="conversation_message")
    op.drop_table("conversation_message")
    op.drop_index("ix_conversation_notebook_id", table_name="conversation")
    op.drop_table("conversation")
