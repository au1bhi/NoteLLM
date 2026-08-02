"""drop item table

Removes the unused template CRUD `item` table (the app manages notebooks,
not generic items). The table was created by the template's initial
migrations and is never referenced by NoteLLM code.

Revision ID: a1b2c3d4e5f6
Revises: c9d88fa5641a
Create Date: 2026-08-02 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'c9d88fa5641a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('item')


def downgrade() -> None:
    # Best-effort recreation of the template's item table.
    op.create_table(
        'item',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
    )
