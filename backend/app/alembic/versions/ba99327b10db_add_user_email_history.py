"""add user email_history + backfill password_changed_at

Revision ID: ba99327b10db
Revises: 143734b60086
Create Date: 2026-08-04 06:02:32.823931

"""
import json

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'ba99327b10db'
down_revision = '143734b60086'
branch_labels = None
depends_on = None


def _canonical(email: str) -> str:
    """Canonical mailbox identity (mirror of app.utils.canonical_email)."""
    local, sep, domain = email.rpartition("@")
    if not sep:
        return email.strip().lower()
    domain = domain.strip().lower()
    if domain == "googlemail.com":
        domain = "gmail.com"
    if domain in {"hotmail.com", "live.com", "msn.com"} or domain.startswith(
        ("hotmail.", "live.", "msn.", "outlook.")
    ):
        domain = "outlook.com"
    if domain in {"ymail.com", "rocketmail.com"}:
        domain = "yahoo.com"
    if domain in {"me.com", "mac.com"}:
        domain = "icloud.com"
    local = local.split("+", 1)[0]
    if domain == "gmail.com":
        local = local.replace(".", "")
    return f"{local.lower()}@{domain}"


def upgrade():
    op.add_column('user', sa.Column('email_history', sa.JSON(), nullable=True))
    # Backfill: every account must have a revocation clock so JWT revocation
    # and reset-token single-use are unconditional. NULL rows (pre-migration)
    # get their creation timestamp.
    op.execute(
        "UPDATE \"user\" SET password_changed_at = COALESCE(password_changed_at, created_at)"
    )
    # Backfill email_history using the CANONICAL mailbox identity so a later
    # deletion tombstones a key a re-registration with a dot/+tag/case variant
    # will actually hit.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, email FROM \"user\"")).fetchall()
    for row_id, email in rows:
        conn.execute(
            sa.text("UPDATE \"user\" SET email_history = :hist WHERE id = :id"),
            {"hist": json.dumps([_canonical(email)]), "id": row_id},
        )


def downgrade():
    op.drop_column('user', 'email_history')
