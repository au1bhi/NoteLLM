"""add user email_canonical

Revision ID: ae6f11ab0923
Revises: ba99327b10db
Create Date: 2026-08-04 06:59:48.074991

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'ae6f11ab0923'
down_revision = 'ba99327b10db'
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
    if domain in {"hotmail.com", "live.com", "msn.com"}:
        domain = "outlook.com"
    local = local.split("+", 1)[0]
    if domain == "gmail.com":
        local = local.replace(".", "")
    return f"{local.lower()}@{domain}"


def upgrade():
    # Nullable first; backfill below, then enforce NOT NULL + unique.
    op.add_column(
        'user',
        sa.Column('email_canonical', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    )
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, email FROM \"user\"")).fetchall()
    for row_id, email in rows:
        conn.execute(
            sa.text("UPDATE \"user\" SET email_canonical = :c WHERE id = :id"),
            {"c": _canonical(email), "id": row_id},
        )
    op.alter_column('user', 'email_canonical', nullable=False)
    op.create_index(
        op.f('ix_user_email_canonical'), 'user', ['email_canonical'], unique=True
    )


def downgrade():
    op.drop_index(op.f('ix_user_email_canonical'), table_name='user')
    op.drop_column('user', 'email_canonical')
