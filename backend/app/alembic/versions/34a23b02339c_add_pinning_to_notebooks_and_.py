"""add pinning to notebooks and conversations

Revision ID: 34a23b02339c
Revises: 7dbb6eb93293
Create Date: 2026-08-01 10:54:23.302326

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '34a23b02339c'
down_revision = '7dbb6eb93293'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'conversation',
        sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.add_column(
        'notebook',
        sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade():
    op.drop_column('notebook', 'is_pinned')
    op.drop_column('conversation', 'is_pinned')
