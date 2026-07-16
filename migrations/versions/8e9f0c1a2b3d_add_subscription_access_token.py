"""add subscription access token compatibility fields

Revision ID: 8e9f0c1a2b3d
Revises: 7d8f0c1a2b3c
"""
import secrets
import string
from alembic import op
import sqlalchemy as sa

revision = '8e9f0c1a2b3d'
down_revision = '7d8f0c1a2b3c'
branch_labels = None
depends_on = None
TOKEN_ALPHABET = string.ascii_lowercase + string.digits


def new_access_token(used_tokens=None):
    used_tokens = used_tokens or set()
    while True:
        token = ''.join(secrets.choice(TOKEN_ALPHABET) for _ in range(48))
        if token not in used_tokens:
            return token


def upgrade():
    connection = op.get_bind()
    columns = {column['name'] for column in sa.inspect(connection).get_columns('sub')}
    missing_access_token = 'access_token' not in columns
    missing_legacy_enabled = 'legacy_enabled' not in columns
    if missing_access_token or missing_legacy_enabled:
        with op.batch_alter_table('sub', schema=None) as batch_op:
            if missing_access_token:
                batch_op.add_column(sa.Column('access_token', sa.String(length=48), nullable=True))
            if missing_legacy_enabled:
                batch_op.add_column(sa.Column(
                    'legacy_enabled', sa.Boolean(), nullable=False, server_default=sa.true()
                ))

    groups = connection.execute(sa.text(
        'SELECT name FROM sub GROUP BY name ORDER BY MIN(id)'
    )).fetchall()
    used_tokens = set()
    for (name,) in groups:
        row = connection.execute(sa.text(
            'SELECT access_token, COUNT(*) AS token_count, MIN(id) AS first_id '
            'FROM sub WHERE ((name = :name) OR (name IS NULL AND :name IS NULL)) '
            'AND access_token IS NOT NULL AND access_token != "" '
            'GROUP BY access_token ORDER BY token_count DESC, first_id ASC LIMIT 1'
        ), {'name': name}).fetchone()
        token = row[0] if row and row[0] not in used_tokens else new_access_token(used_tokens)
        used_tokens.add(token)
        connection.execute(
            sa.text(
                'UPDATE sub SET access_token = :token '
                'WHERE ((name = :name) OR (name IS NULL AND :name IS NULL)) '
                'AND (access_token IS NULL OR access_token != :token)'
            ),
            {'token': token, 'name': name}
        )

    legacy_groups = connection.execute(sa.text(
        'SELECT name, MAX(CASE WHEN legacy_enabled THEN 1 ELSE 0 END) '
        'FROM sub GROUP BY name'
    )).fetchall()
    for name, enabled in legacy_groups:
        target = 1 if enabled else 0
        connection.execute(sa.text(
            'UPDATE sub SET legacy_enabled = :enabled '
            'WHERE ((name = :name) OR (name IS NULL AND :name IS NULL)) '
            'AND COALESCE(legacy_enabled, -1) != :enabled'
        ), {'enabled': target, 'name': name})


def downgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('sub')}
    with op.batch_alter_table('sub', schema=None) as batch_op:
        if 'legacy_enabled' in columns:
            batch_op.drop_column('legacy_enabled')
        if 'access_token' in columns:
            batch_op.drop_column('access_token')
