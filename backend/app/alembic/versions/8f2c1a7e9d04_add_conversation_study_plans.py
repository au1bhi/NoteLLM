"""Add conversation study plans and Gantt tasks.

Revision ID: 8f2c1a7e9d04
Revises: 46a98a434c83
Create Date: 2026-08-04 23:10:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "8f2c1a7e9d04"
down_revision = "46a98a434c83"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_plan",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=16), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column(
            "reminder_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("last_reminder_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversation.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id"),
    )
    op.create_index("ix_study_plan_conversation_id", "study_plan", ["conversation_id"])
    op.create_table(
        "study_task",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "is_completed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["study_plan.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_study_task_plan_id", "study_task", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_study_task_plan_id", table_name="study_task")
    op.drop_table("study_task")
    op.drop_index("ix_study_plan_conversation_id", table_name="study_plan")
    op.drop_table("study_plan")
