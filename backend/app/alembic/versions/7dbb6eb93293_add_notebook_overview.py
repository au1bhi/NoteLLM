"""add notebook overview

Revision ID: 7dbb6eb93293
Revises: 5254cfe124b7
Create Date: 2026-08-01 04:41:15.156191

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '7dbb6eb93293'
down_revision = '5254cfe124b7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('notebook', sa.Column('overview', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('notebook', sa.Column('overview_topics', sa.JSON(), nullable=True))
    op.add_column('notebook', sa.Column('overview_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('notebook', 'overview_updated_at')
    op.drop_column('notebook', 'overview_topics')
    op.drop_column('notebook', 'overview')
