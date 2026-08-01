"""add user usage

Revision ID: 12f2e52f9281
Revises: 34a23b02339c
Create Date: 2026-08-01 11:34:57.218988

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '12f2e52f9281'
down_revision = '34a23b02339c'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('userusage',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('chat_tokens', sa.Integer(), nullable=False),
    sa.Column('embedding_chars', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_userusage_user_id'), 'userusage', ['user_id'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_userusage_user_id'), table_name='userusage')
    op.drop_table('userusage')
