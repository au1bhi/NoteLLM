"""add api format

Revision ID: c9d88fa5641a
Revises: 794fd4b432e6
Create Date: 2026-08-01 22:23:32.776152

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c9d88fa5641a'
down_revision = '794fd4b432e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # API format per provider: "openai" (base URL already has a version path)
    # or "openai_v1" (root domain, append /v1). NULL = default "openai".
    op.add_column(
        'userprovidersettings',
        sa.Column('chat_api_format', sa.String(length=32), nullable=True),
    )
    op.add_column(
        'userprovidersettings',
        sa.Column('embedding_api_format', sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('userprovidersettings', 'embedding_api_format')
    op.drop_column('userprovidersettings', 'chat_api_format')
