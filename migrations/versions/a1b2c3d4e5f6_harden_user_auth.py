"""harden user auth fields (password length, token_version, unique username)

Revision ID: a1b2c3d4e5f6
Revises: 9f0a1b2c3d4e
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '9f0a1b2c3d4e'
branch_labels = None
depends_on = None
UNIQUE_INDEX_NAME = 'uq_user_username'


def _has_unique_username(inspector) -> bool:
    for idx in inspector.get_indexes('user'):
        if idx.get('unique') and idx.get('column_names') == ['username']:
            return True
    for uc in inspector.get_unique_constraints('user'):
        if uc.get('column_names') == ['username']:
            return True
    return False


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if 'user' not in inspector.get_table_names():
        return

    # Deduplicate any historical duplicate usernames (keep lowest id row) before creating unique index
    connection.execute(sa.text(
        'DELETE FROM user WHERE id NOT IN ('
        'SELECT MIN(id) FROM user GROUP BY username'
        ') AND username IS NOT NULL'
    ))
    connection.execute(sa.text(
        "DELETE FROM user WHERE username IS NULL OR TRIM(username) = ''"
    ))

    columns = {col['name']: col for col in inspector.get_columns('user')}
    needs_token_version = 'token_version' not in columns
    pw_col = columns.get('password')
    pw_len = getattr(pw_col['type'], 'length', None) if pw_col else None
    needs_password_widen = pw_len is not None and pw_len < 255

    if needs_token_version or needs_password_widen:
        with op.batch_alter_table('user', schema=None) as batch_op:
            if needs_password_widen:
                batch_op.alter_column(
                    'password',
                    existing_type=sa.String(length=pw_len),
                    type_=sa.String(length=255),
                    existing_nullable=bool(pw_col.get('nullable', True)),
                )
            if needs_token_version:
                batch_op.add_column(
                    sa.Column('token_version', sa.Integer(), nullable=False, server_default='1')
                )

    inspector = sa.inspect(connection)
    if not _has_unique_username(inspector):
        op.create_index(UNIQUE_INDEX_NAME, 'user', ['username'], unique=True)


def downgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if 'user' not in inspector.get_table_names():
        return
    indexes = {idx['name'] for idx in inspector.get_indexes('user')}
    if UNIQUE_INDEX_NAME in indexes:
        op.drop_index(UNIQUE_INDEX_NAME, table_name='user')
    columns = {col['name'] for col in inspector.get_columns('user')}
    if 'token_version' in columns:
        with op.batch_alter_table('user', schema=None) as batch_op:
            batch_op.drop_column('token_version')
