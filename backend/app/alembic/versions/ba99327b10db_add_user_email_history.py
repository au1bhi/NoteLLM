"""add user email_history + backfill password_changed_at

Revision ID: ba99327b10db
Revises: 143734b60086
Create Date: 2026-08-04 06:02:32.823931

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'ba99327b10db'
down_revision = '143734b60086'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('email_history', sa.JSON(), nullable=True))
    # Backfill: every account must have a revocation clock so JWT revocation
    # and reset-token single-use are unconditional. NULL rows (pre-migration)
    # get their creation timestamp.
    op.execute(
        "UPDATE \"user\" SET password_changed_at = COALESCE(password_changed_at, created_at)"
    )
    # Backfill email_history for pre-existing accounts so a later deletion
    # tombstones the right canonical identity.
    op.execute(
        "UPDATE \"user\" SET email_history = json_build_array(lower(email)) "
        "WHERE email_history IS NULL OR email_history::text = '[]'"
    )


def downgrade():
    op.drop_column('user', 'email_history')
