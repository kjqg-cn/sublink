import secrets
import sqlite3
import string
from pathlib import Path

from flask_migrate import stamp, upgrade

from app import create_app
from app.exts import db
from app.model import _init_file_lock, create_db, ensure_db_dir

DB_PATH = Path(__file__).parent / 'app' / 'db' / 'sub.db'
MIGRATIONS_DIR = str(Path(__file__).parent / 'migrations')
INITIAL_REVISION = '43914e4334c4'
LEGACY_REVISION = '4e76f839124e'
SORT_REVISION = '7d8f0c1a2b3c'
TOKEN_REVISION = '8e9f0c1a2b3d'
INDEX_REVISION = '9f0a1b2c3d4e'
USER_AUTH_REVISION = 'a1b2c3d4e5f6'
CONFIG_SCHEMA_REVISION = 'b2c3d4e5f6a7'
REVISION_ORDER = {
    INITIAL_REVISION: 0,
    LEGACY_REVISION: 1,
    SORT_REVISION: 2,
    TOKEN_REVISION: 3,
    INDEX_REVISION: 4,
    USER_AUTH_REVISION: 5,
    CONFIG_SCHEMA_REVISION: 6,
}
TOKEN_ALPHABET = string.ascii_lowercase + string.digits
SQLITE_CONNECT_TIMEOUT = 15


def new_access_token(used_tokens=None):
    used_tokens = used_tokens or set()
    while True:
        token = ''.join(secrets.choice(TOKEN_ALPHABET) for _ in range(48))
        if token not in used_tokens:
            return token


def _open_sqlite(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=SQLITE_CONNECT_TIMEOUT)
    conn.execute(f'PRAGMA busy_timeout={SQLITE_CONNECT_TIMEOUT * 1000}')
    return conn


def _resolve_db_path(app=None, db_path=None) -> Path:
    if db_path is not None:
        return Path(db_path)
    if app is not None:
        uri = str(app.config.get('SQLALCHEMY_DATABASE_URI') or '')
        if uri.startswith('sqlite:///') and uri != 'sqlite:///:memory:':
            return Path(uri[len('sqlite:///'):])
    return DB_PATH


def read_schema_state(db_path=DB_PATH):
    if not Path(db_path).exists():
        return set(), set(), None

    connection = _open_sqlite(db_path)
    try:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        schema_items = set()
        if 'sub' in tables:
            columns = {row[1] for row in connection.execute('PRAGMA table_info(sub)')}
            indexes = {row[1] for row in connection.execute('PRAGMA index_list(sub)')}
            schema_items |= columns | {f'index:{name}' for name in indexes}
        if 'user' in tables:
            user_cols = {row[1] for row in connection.execute('PRAGMA table_info(user)')}
            if 'token_version' in user_cols:
                schema_items.add('user:token_version')
            for idx_row in connection.execute('PRAGMA index_list(user)').fetchall():
                idx_name = idx_row[1]
                is_unique = bool(idx_row[2])
                if is_unique:
                    idx_cols = [
                        c[2] for c in connection.execute(f'PRAGMA index_info("{idx_name}")').fetchall()
                    ]
                    if idx_cols == ['username']:
                        schema_items.add('user:unique_username')
                        break
        if 'config' in tables:
            for idx_row in connection.execute('PRAGMA index_list(config)').fetchall():
                idx_name = idx_row[1]
                is_unique = bool(idx_row[2])
                if is_unique:
                    idx_cols = [
                        c[2] for c in connection.execute(f'PRAGMA index_info("{idx_name}")').fetchall()
                    ]
                    if idx_cols == ['key']:
                        schema_items.add('config:unique_key')
                        break
        if 'login' in tables:
            schema_items.add('login:table')
            for col_row in connection.execute('PRAGMA table_info(login)').fetchall():
                if col_row[1] == 'ip':
                    col_type = str(col_row[2] or '').upper()
                    if col_type in ('TEXT', 'VARCHAR', '') or '(' not in col_type:
                        if col_type == 'TEXT':
                            schema_items.add('login:ip_wide')
                    else:
                        import re as _re
                        m_len = _re.search(r'\((\d+)\)', col_type)
                        if m_len and int(m_len.group(1)) >= 64:
                            schema_items.add('login:ip_wide')
                    break
        return tables, schema_items, _read_alembic_revision(connection, tables)
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
    if 'index:ix_sub_access_token' not in schema_items:
        return TOKEN_REVISION
    if 'user:token_version' not in schema_items or 'user:unique_username' not in schema_items:
        return INDEX_REVISION
    if {'config:unique_key', 'login:table', 'login:ip_wide'} <= schema_items:
        return CONFIG_SCHEMA_REVISION
    return USER_AUTH_REVISION


def repair_subscription_data(schema_items, db_path=DB_PATH):
    repair_sort = 'sort_order' in schema_items
    repair_token = 'access_token' in schema_items
    repair_legacy = 'legacy_enabled' in schema_items
    if not any((repair_sort, repair_token, repair_legacy)):
        return

    connection = _open_sqlite(db_path)
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
    ensure_db_dir()
    app = app or create_app()
    db_path = _resolve_db_path(app)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _init_file_lock(str(db_path.parent)), app.app_context():
        tables, schema_items, current_revision = read_schema_state(db_path)
        app_tables = {'user', 'sub', 'login', 'config'}
        if not (tables & app_tables):
            db.create_all()
            stamp(directory=MIGRATIONS_DIR, revision='head')
            create_db()
            return

        if 'sub' not in tables:
            # Legacy partial DB (e.g. old broken 43914e4334c4 that created only user without sub):
            # reset stamp to base so idempotent 43914e4334c4 creates missing tables and full chain upgrades user/config.
            stamp(directory=MIGRATIONS_DIR, revision='base')
            upgrade(directory=MIGRATIONS_DIR, revision='head')
        else:
            repair_subscription_data(schema_items, db_path=db_path)
            tables, schema_items, current_revision = read_schema_state(db_path)
            schema_revision = detect_schema_revision(schema_items)
            align_alembic_revision(current_revision, schema_revision)
            upgrade(directory=MIGRATIONS_DIR, revision='head')

        tables, schema_items, _ = read_schema_state(db_path)
        repair_subscription_data(schema_items, db_path=db_path)
        if detect_schema_revision(schema_items) != CONFIG_SCHEMA_REVISION:
            raise RuntimeError('数据库升级后仍未达到最新结构')
        create_db()


if __name__ == '__main__':
    upgrade_database()
