"""add email usage tombstone

Revision ID: 143734b60086
Revises: f864ffa3c8c6
Create Date: 2026-08-04 04:00:43.237226

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '143734b60086'
down_revision = 'f864ffa3c8c6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('emailusagetombstone',
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('period_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('chat_tokens', sa.Integer(), nullable=False),
    sa.Column('embedding_chars', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('email')
    )


def downgrade():
    op.drop_table('emailusagetombstone')
