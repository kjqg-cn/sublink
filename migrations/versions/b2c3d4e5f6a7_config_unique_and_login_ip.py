"""enforce unique config.key and widen login.ip to 64 chars

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None
CONFIG_UNIQUE_INDEX_NAME = 'uq_config_key'


def _has_unique_config_key(inspector) -> bool:
    for idx in inspector.get_indexes('config'):
        if idx.get('unique') and idx.get('column_names') == ['key']:
            return True
    for uc in inspector.get_unique_constraints('config'):
        if uc.get('column_names') == ['key']:
            return True
    return False


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())

    if 'config' not in tables:
        op.create_table(
            'config',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('key', sa.String(length=64), nullable=False),
            sa.Column('value', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(CONFIG_UNIQUE_INDEX_NAME, 'config', ['key'], unique=True)
    else:
        # Remove empty/null keys and keep latest row (MAX(id)) per config.key before adding unique index
        connection.execute(sa.text("DELETE FROM config WHERE key IS NULL OR TRIM(key) = ''"))
        connection.execute(sa.text(
            'DELETE FROM config WHERE id NOT IN ('
            'SELECT MAX(id) FROM config GROUP BY key'
            ')'
        ))
        cols = {col['name']: col for col in inspector.get_columns('config')}
        key_col = cols.get('key')
        key_type = key_col['type'] if key_col else None
        needs_key_alter = not isinstance(key_type, sa.String) or getattr(key_type, 'length', None) != 64
        if needs_key_alter or (key_col and key_col.get('nullable', True)):
            with op.batch_alter_table('config', schema=None) as batch_op:
                batch_op.alter_column(
                    'key',
                    existing_type=key_type or sa.Text(),
                    type_=sa.String(length=64),
                    nullable=False,
                )
        inspector = sa.inspect(connection)
        if not _has_unique_config_key(inspector):
            op.create_index(CONFIG_UNIQUE_INDEX_NAME, 'config', ['key'], unique=True)

    if 'login' not in tables:
        op.create_table(
            'login',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('ip', sa.String(length=64), nullable=True),
            sa.Column('address', sa.Text(), nullable=True),
            sa.Column('time', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
    else:
        login_cols = {col['name']: col for col in inspector.get_columns('login')}
        ip_col = login_cols.get('ip')
        ip_len = getattr(ip_col['type'], 'length', None) if ip_col else None
        if ip_col is not None and (ip_len is None or ip_len < 64):
            with op.batch_alter_table('login', schema=None) as batch_op:
                batch_op.alter_column(
                    'ip',
                    existing_type=ip_col['type'],
                    type_=sa.String(length=64),
                    existing_nullable=bool(ip_col.get('nullable', True)),
                )


def downgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    if 'config' in tables:
        indexes = {idx['name'] for idx in inspector.get_indexes('config')}
        if CONFIG_UNIQUE_INDEX_NAME in indexes:
            op.drop_index(CONFIG_UNIQUE_INDEX_NAME, table_name='config')
