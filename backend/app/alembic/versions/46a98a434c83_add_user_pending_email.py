"""add user pending_email

Revision ID: 46a98a434c83
Revises: ae6f11ab0923
Create Date: 2026-08-04 08:22:41.068138

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '46a98a434c83'
down_revision = 'ae6f11ab0923'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'user',
        sa.Column('pending_email', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    )


def downgrade():
    op.drop_column('user', 'pending_email')
