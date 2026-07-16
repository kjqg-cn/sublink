import secrets
import sqlite3
import string
from pathlib import Path

from flask_migrate import stamp, upgrade

from app import create_app
from app.exts import db

DB_PATH = Path(__file__).parent / 'app' / 'db' / 'sub.db'
MIGRATIONS_DIR = str(Path(__file__).parent / 'migrations')
INITIAL_REVISION = '43914e4334c4'
LEGACY_REVISION = '4e76f839124e'
SORT_REVISION = '7d8f0c1a2b3c'
TOKEN_REVISION = '8e9f0c1a2b3d'
INDEX_REVISION = '9f0a1b2c3d4e'
REVISION_ORDER = {
    INITIAL_REVISION: 0,
    LEGACY_REVISION: 1,
    SORT_REVISION: 2,
    TOKEN_REVISION: 3,
    INDEX_REVISION: 4,
}
TOKEN_ALPHABET = string.ascii_lowercase + string.digits


def new_access_token(used_tokens=None):
    used_tokens = used_tokens or set()
    while True:
        token = ''.join(secrets.choice(TOKEN_ALPHABET) for _ in range(48))
        if token not in used_tokens:
            return token


def read_schema_state(db_path=DB_PATH):
    if not Path(db_path).exists():
        return set(), set(), None

    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if 'sub' not in tables:
            return tables, set(), _read_alembic_revision(connection, tables)

        columns = {row[1] for row in connection.execute('PRAGMA table_info(sub)')}
        indexes = {row[1] for row in connection.execute('PRAGMA index_list(sub)')}
        return tables, columns | {f'index:{name}' for name in indexes}, _read_alembic_revision(
            connection, tables
        )
    finally:
        connection.close()


def _read_alembic_revision(connection, tables):
    if 'alembic_version' not in tables:
        return None
    row = connection.execute('SELECT version_num FROM alembic_version LIMIT 1').fetchone()
    return row[0] if row else None


def detect_schema_revision(schema_items):
    new_columns = {'sort_order', 'access_token', 'legacy_enabled'}
    present = schema_items & new_columns
    if 'remarks' not in schema_items:
        return INITIAL_REVISION
    if 'sort_order' not in present:
        return LEGACY_REVISION
    if present != new_columns:
        return SORT_REVISION
    if 'index:ix_sub_access_token' in schema_items:
        return INDEX_REVISION
    return TOKEN_REVISION


def repair_subscription_data(schema_items, db_path=DB_PATH):
    repair_sort = 'sort_order' in schema_items
    repair_token = 'access_token' in schema_items
    repair_legacy = 'legacy_enabled' in schema_items
    if not any((repair_sort, repair_token, repair_legacy)):
        return

    connection = sqlite3.connect(db_path)
    try:
        connection.execute('BEGIN IMMEDIATE')
        if repair_sort:
            _repair_sort_orders(connection)
        if repair_token:
            _repair_access_tokens(connection)
        if repair_legacy:
            _repair_legacy_enabled(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _repair_sort_orders(connection):
    groups = connection.execute(
        'SELECT name, MIN(id), COUNT(DISTINCT sort_order), MIN(sort_order), '
        'SUM(CASE WHEN sort_order IS NULL THEN 1 ELSE 0 END) '
        'FROM sub GROUP BY name ORDER BY MIN(id)'
    ).fetchall()
    orders = [row[3] for row in groups]
    valid = all(row[2] == 1 and row[3] is not None and row[4] == 0 for row in groups)
    valid = valid and sorted(orders) == list(range(len(groups)))
    if valid:
        return
    groups.sort(key=lambda row: (
        row[3] is None,
        row[3] if row[3] is not None else 0,
        row[1]
    ))
    for sort_order, (name, _, _, _, _) in enumerate(groups):
        connection.execute(
            'UPDATE sub SET sort_order = ? WHERE name IS ?',
            (sort_order, name)
        )


def _repair_access_tokens(connection):
    groups = connection.execute(
        'SELECT name FROM sub GROUP BY name ORDER BY MIN(id)'
    ).fetchall()
    used_tokens = set()
    for (name,) in groups:
        row = connection.execute(
            'SELECT access_token, COUNT(*) AS token_count, MIN(id) AS first_id '
            'FROM sub WHERE name IS ? AND access_token IS NOT NULL AND access_token != "" '
            'GROUP BY access_token ORDER BY token_count DESC, first_id ASC LIMIT 1',
            (name,)
        ).fetchone()
        token = row[0] if row and row[0] not in used_tokens else new_access_token(used_tokens)
        used_tokens.add(token)
        connection.execute(
            'UPDATE sub SET access_token = ? '
            'WHERE name IS ? AND (access_token IS NULL OR access_token != ?)',
            (token, name, token)
        )


def _repair_legacy_enabled(connection):
    groups = connection.execute(
        'SELECT name, MAX(CASE WHEN legacy_enabled THEN 1 ELSE 0 END) '
        'FROM sub GROUP BY name'
    ).fetchall()
    for name, enabled in groups:
        target = 1 if enabled else 0
        connection.execute(
            'UPDATE sub SET legacy_enabled = ? '
            'WHERE name IS ? AND COALESCE(legacy_enabled, -1) != ?',
            (target, name, target)
        )


def align_alembic_revision(current_revision, schema_revision):
    if current_revision is None:
        stamp(directory=MIGRATIONS_DIR, revision=schema_revision)
        return

    current_order = REVISION_ORDER.get(current_revision)
    schema_order = REVISION_ORDER[schema_revision]
    if current_order is None:
        return
    if current_order != schema_order:
        stamp(directory=MIGRATIONS_DIR, revision=schema_revision)


def upgrade_database(app=None):
    app = app or create_app()
    with app.app_context():
        tables, schema_items, current_revision = read_schema_state()
        if 'sub' not in tables:
            db.create_all()
            stamp(directory=MIGRATIONS_DIR, revision='head')
            return

        repair_subscription_data(schema_items)
        tables, schema_items, current_revision = read_schema_state()
        schema_revision = detect_schema_revision(schema_items)
        align_alembic_revision(current_revision, schema_revision)
        upgrade(directory=MIGRATIONS_DIR, revision='head')
        tables, schema_items, _ = read_schema_state()
        repair_subscription_data(schema_items)
        if detect_schema_revision(schema_items) != INDEX_REVISION:
            raise RuntimeError('数据库升级后仍未达到最新结构')


if __name__ == '__main__':
    upgrade_database()
