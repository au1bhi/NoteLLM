"""add provider switch cooldown

Revision ID: 794fd4b432e6
Revises: f0250b721a43
Create Date: 2026-08-01 21:51:51.857835

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '794fd4b432e6'
down_revision = 'f0250b721a43'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # When the user last switched billing between their own key and the
    # server default; drives the 24h switch-back cooldown. NULL = no switch yet.
    op.add_column(
        'userprovidersettings',
        sa.Column('provider_changed_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('userprovidersettings', 'provider_changed_at')
