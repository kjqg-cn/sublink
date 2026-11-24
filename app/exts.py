import sqlite3
import weakref

from flask import current_app, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from sqlalchemy import event as sa_event
from sqlalchemy.engine.url import make_url

db = SQLAlchemy()  # 数据库
migrate = Migrate()
jwtmanager = JWTManager()

SQLITE_CONNECT_TIMEOUT_SECONDS = 15
SQLITE_BUSY_TIMEOUT_MS = 15000
_CONFIGURED_SQLITE_ENGINES: 'weakref.WeakSet' = weakref.WeakSet()


def _is_file_backed_sqlite_uri(uri) -> bool:
    """Return True only for file-backed SQLite URIs (skipping :memory: and non-SQLite backends)."""
    if not uri:
        return False
    try:
        url = make_url(uri)
    except Exception:
        return False
    if url.get_backend_name() != 'sqlite':
        return False
    database = (url.database or '').strip()
    lower_db = database.lower()
    if not database or lower_db == ':memory:' or lower_db.startswith('file::memory:'):
        return False
    for qk, qv in url.query.items():
        if str(qk).lower() != 'mode':
            continue
        values = qv if isinstance(qv, (list, tuple)) else (qv,)
        if any(str(item).lower() == 'memory' for item in values):
            return False
    return True


def _resolve_sqlite_busy_timeout_ms(timeout_seconds) -> int:
    """Convert positive numeric timeout seconds into milliseconds, falling back to default."""
    if isinstance(timeout_seconds, (int, float)) and not isinstance(timeout_seconds, bool) and timeout_seconds > 0:
        return int(round(timeout_seconds * 1000))
    return SQLITE_BUSY_TIMEOUT_MS


def _configure_sqlite_connection(
    dbapi_connection,
    _connection_record,
    busy_timeout_ms: int = SQLITE_BUSY_TIMEOUT_MS,
) -> None:
    """Enable busy_timeout, WAL journal mode, and NORMAL sync on file-backed SQLite connections."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute('PRAGMA database_list')
        main_db_file = next((row[2] for row in cursor.fetchall() if row[1] == 'main'), '')
        if not main_db_file or main_db_file == ':memory:':
            return
        cursor.execute(f'PRAGMA busy_timeout={int(busy_timeout_ms)}')
        mode_row = cursor.execute('PRAGMA journal_mode').fetchone()
        current_mode = str(mode_row[0]).lower() if mode_row and mode_row[0] else ''
        if current_mode != 'wal':
            cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA synchronous=NORMAL')
    finally:
        cursor.close()


def _prepare_sqlite_engine_options(app) -> bool:
    """Apply SQLite connect timeout on file-backed SQLite apps without affecting :memory: or non-SQLite URIs."""
    if not _is_file_backed_sqlite_uri(app.config.get('SQLALCHEMY_DATABASE_URI')):
        return False
    engine_options = dict(app.config.get('SQLALCHEMY_ENGINE_OPTIONS') or {})
    connect_args = dict(engine_options.get('connect_args') or {})
    if connect_args.get('timeout') is None:
        connect_args['timeout'] = SQLITE_CONNECT_TIMEOUT_SECONDS
    engine_options['connect_args'] = connect_args
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options
    return True


def _is_isolated_test_env() -> bool:
    """Return True only for isolated unit-test apps (TESTING=True or in-memory SQLite)."""
    return bool(
        current_app.config.get('TESTING')
        or current_app.config.get('SQLALCHEMY_DATABASE_URI') == 'sqlite:///:memory:'
    )


@jwtmanager.invalid_token_loader
def _handle_invalid_token(error_string):
    """Return 401 (instead of 422) on invalid/re-keyed JWTs so frontends auto-redirect to login."""
    return jsonify({'code': 401, 'msg': '令牌无效，请重新登录'}), 401


@jwtmanager.expired_token_loader
def _handle_expired_token(jwt_header, jwt_payload):
    """Return unified 401 JSON when an access or refresh JWT has expired."""
    return jsonify({'code': 401, 'msg': '令牌已过期，请刷新或重新登录'}), 401


@jwtmanager.unauthorized_loader
def _handle_missing_token(error_string):
    """Return unified 401 JSON when Authorization header is missing."""
    return jsonify({'code': 401, 'msg': '未提供认证令牌，请先登录'}), 401


@jwtmanager.revoked_token_loader
def _handle_revoked_token(jwt_header, jwt_payload):
    """Return unified 401 JSON when a JWT has been revoked."""
    return jsonify({'code': 401, 'msg': '令牌已失效，请重新登录'}), 401


@jwtmanager.token_in_blocklist_loader
def _check_if_token_revoked(jwt_header, jwt_payload):
    """Revoke tokens whose user was deleted, renamed, or had credentials updated (fail-closed in prod)."""
    identity = jwt_payload.get('sub')
    if not identity:
        return True
    token_uid = jwt_payload.get('uid')
    token_tv = jwt_payload.get('tv')
    try:
        from .model import User
        if token_uid is not None:
            user = db.session.get(User, token_uid)
            if not user:
                return True
            if user.username != identity:
                return True
            if token_tv is None or (user.token_version or 1) != token_tv:
                return True
            return False

        user = User.query.filter_by(username=identity).first()
        if user is not None:
            current_tv = user.token_version or 1
            if token_tv is not None:
                return current_tv != token_tv
            return current_tv > 1

        # Token without uid claim: always fail-closed in production or when token carries tv.
        # Only allow bare synthetic test tokens in isolated unit-test environments with an empty User table.
        if token_tv is not None or not _is_isolated_test_env():
            return True
        return User.query.count() > 0
    except Exception:
        # Fail-closed on DB errors in production or for real tokens carrying uid/tv.
        if token_uid is not None or token_tv is not None or not _is_isolated_test_env():
            return True
        return False


def init_exts(app):
    is_file_sqlite = _prepare_sqlite_engine_options(app)
    db.init_app(app=app)
    if is_file_sqlite:
        connect_args = (app.config.get('SQLALCHEMY_ENGINE_OPTIONS') or {}).get('connect_args') or {}
        busy_timeout_ms = _resolve_sqlite_busy_timeout_ms(connect_args.get('timeout'))
        with app.app_context():
            engine = db.engine
            if engine not in _CONFIGURED_SQLITE_ENGINES:
                if busy_timeout_ms == SQLITE_BUSY_TIMEOUT_MS:
                    listener = _configure_sqlite_connection
                else:
                    def listener(dbapi_conn, conn_rec, _ms=busy_timeout_ms):
                        _configure_sqlite_connection(dbapi_conn, conn_rec, busy_timeout_ms=_ms)
                sa_event.listen(engine, 'connect', listener)
                _CONFIGURED_SQLITE_ENGINES.add(engine)
    migrate.init_app(app=app, db=db)
    jwtmanager.init_app(app=app)
