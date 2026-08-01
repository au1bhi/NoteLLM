"""add usage period_start

Revision ID: f0250b721a43
Revises: 12f2e52f9281
Create Date: 2026-08-01 18:57:56.659976

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f0250b721a43'
down_revision = '12f2e52f9281'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Start of the current free-allowance period (calendar month, UTC).
    # NULL on existing rows means the counters reset on next access.
    op.add_column('userusage', sa.Column('period_start', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('userusage', 'period_start')
