"""add user provider settings

Revision ID: 258ef67912f8
Revises: d4e8a2c5f731
Create Date: 2026-08-01 02:12:27.645621

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '258ef67912f8'
down_revision = 'd4e8a2c5f731'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('userprovidersettings',
    sa.Column('chat_base_url', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
    sa.Column('chat_api_key', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
    sa.Column('chat_model', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('embedding_base_url', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
    sa.Column('embedding_api_key', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
    sa.Column('embedding_model', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_userprovidersettings_user_id'), 'userprovidersettings', ['user_id'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_userprovidersettings_user_id'), table_name='userprovidersettings')
    op.drop_table('userprovidersettings')
