"""Add shared rate-limit buckets.

Revision ID: 6ea2d54c90f1
Revises: 8f2c1a7e9d04
Create Date: 2026-08-18 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "6ea2d54c90f1"
down_revision = "8f2c1a7e9d04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_bucket",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        "ix_rate_limit_bucket_updated_at", "rate_limit_bucket", ["updated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_bucket_updated_at", table_name="rate_limit_bucket")
    op.drop_table("rate_limit_bucket")
