"""add access token index

Revision ID: 9f0a1b2c3d4e
Revises: 8e9f0c1a2b3d
"""
from alembic import op
import sqlalchemy as sa


revision = '9f0a1b2c3d4e'
down_revision = '8e9f0c1a2b3d'
branch_labels = None
depends_on = None
INDEX_NAME = 'ix_sub_access_token'


def index_exists():
    indexes = sa.inspect(op.get_bind()).get_indexes('sub')
    return any(index['name'] == INDEX_NAME for index in indexes)


def upgrade():
    if not index_exists():
        op.create_index(INDEX_NAME, 'sub', ['access_token'], unique=False)


def downgrade():
    if index_exists():
        op.drop_index(INDEX_NAME, table_name='sub')
