"""add email verification

Adds the `is_email_verified` flag used by the account email-verification
flow. Existing accounts (including the pre-seeded superuser) start unverified;
the client shows a reminder banner and a resend link.

Revision ID: 87c42fcd0445
Revises: a1b2c3d4e5f6
Create Date: 2026-08-02 14:33:10.413683

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '87c42fcd0445'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'user',
        sa.Column('is_email_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Keep the DEFAULT only for the backfill of existing rows; the application
    # now supplies the value explicitly on insert.
    op.alter_column('user', 'is_email_verified', server_default=None)


def downgrade() -> None:
    op.drop_column('user', 'is_email_verified')
