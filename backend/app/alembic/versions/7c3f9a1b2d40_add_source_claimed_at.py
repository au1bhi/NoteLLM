"""Add source.claimed_at for stale-processing reclaim.

Revision ID: 7c3f9a1b2d40
Revises: 6ea2d54c90f1
Create Date: 2026-08-27 00:30:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "7c3f9a1b2d40"
down_revision = "6ea2d54c90f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source", "claimed_at")
