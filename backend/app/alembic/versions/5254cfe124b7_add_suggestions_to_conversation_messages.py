"""add suggestions to conversation messages

Revision ID: 5254cfe124b7
Revises: 258ef67912f8
Create Date: 2026-08-01 04:02:27.335549

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5254cfe124b7'
down_revision = '258ef67912f8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('conversation_message', sa.Column('suggestions', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('conversation_message', 'suggestions')
