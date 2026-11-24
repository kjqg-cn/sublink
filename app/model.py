from contextlib import contextmanager
import hashlib
import hmac
import logging
import os
import re
import secrets
import tempfile
import threading
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from .exts import db

logger = logging.getLogger(__name__)

# PBKDF2-HMAC-SHA256 with random salt (compatible with Werkzeug 2.3+ and 3.x)
DEFAULT_PASSWORD_HASH_METHOD = 'pbkdf2:sha256:260000'
PASSWORD_HASH_METHOD = DEFAULT_PASSWORD_HASH_METHOD
_MD5_HEX_RE = re.compile(r'^[0-9a-f]{32}$')
_dummy_hash_cache = {}
_dummy_hash_lock = threading.Lock()
_thread_lock_state = threading.local()
_inproc_locks_guard = threading.Lock()
_inproc_locks = {}


def _get_dummy_password_hash() -> str:
    method = PASSWORD_HASH_METHOD
    cached = _dummy_hash_cache.get(method)
    if cached is not None:
        return cached
    with _dummy_hash_lock:
        cached = _dummy_hash_cache.get(method)
        if cached is None:
            cached = generate_password_hash('sublink-dummy-timing-guard', method=method)
            _dummy_hash_cache[method] = cached
        return cached


def is_password_hashed(stored: str) -> bool:
    """Return True if stored password uses a salted slow password hash format."""
    if not isinstance(stored, str):
        return False
    return stored.startswith(('pbkdf2:', 'scrypt:'))


def hash_password(raw_password: str) -> str:
    """Hash a password with a per-password random salt using PBKDF2-HMAC-SHA256."""
    return generate_password_hash(str(raw_password), method=PASSWORD_HASH_METHOD)


def verify_password(stored_password: str, supplied_password: str) -> tuple:
    """
    Verify supplied_password against stored_password in constant time.
    Returns (is_valid, needs_rehash).
    Supports transparent migration from legacy unsalted MD5 (plaintext input only;
    raw MD5 pass-the-hash is rejected to prevent hash reuse and PBKDF2(MD5) lockout)
    and legacy non-MD5 plaintext test fixtures.
    """
    if not isinstance(stored_password, str) or not isinstance(supplied_password, str):
        check_password_hash(_get_dummy_password_hash(), '')
        return False, False
    if is_password_hashed(stored_password):
        return check_password_hash(stored_password, supplied_password), False
    # Legacy DB stored unsalted MD5(plaintext): only accept the real plaintext password
    # so pass-the-hash is blocked and cached legacy MD5 clients cannot overwrite DB with PBKDF2(MD5).
    if _MD5_HEX_RE.match(stored_password.lower()):
        supplied_md5 = hashlib.md5(supplied_password.encode('utf-8')).hexdigest()
        if hmac.compare_digest(stored_password.lower(), supplied_md5):
            return True, True
        check_password_hash(_get_dummy_password_hash(), supplied_password)
        return False, False
    # Constant-time check against legacy non-MD5 plaintext rows (e.g. test fixtures)
    if hmac.compare_digest(stored_password, supplied_password):
        return True, True
    # Balance timing against PBKDF2 path
    check_password_hash(_get_dummy_password_hash(), supplied_password)
    return False, False


def verify_dummy_password(supplied_password: str = '') -> None:
    """Consume constant-time PBKDF2 work when username does not exist."""
    check_password_hash(_get_dummy_password_hash(), str(supplied_password or ''))


def ensure_db_dir(app_dir: str = None) -> str:
    """Ensure app/db directory exists and return its path."""
    base_dir = app_dir or os.path.dirname(os.path.abspath(__file__))
    db_dir = os.path.join(base_dir, 'db')
    os.makedirs(db_dir, exist_ok=True)
    return db_dir


@contextmanager
def _init_file_lock(db_dir: str, lock_name: str = '.init.lock'):
    """Re-entrant cross-thread and cross-process advisory file lock for DB initialization/writes."""
    os.makedirs(db_dir, exist_ok=True)
    lock_path = os.path.abspath(os.path.join(db_dir, lock_name))

    held = getattr(_thread_lock_state, 'held', None)
    if held is None:
        held = {}
        _thread_lock_state.held = held
    if held.get(lock_path, 0) > 0:
        held[lock_path] += 1
        try:
            yield
        finally:
            held[lock_path] -= 1
        return

    with _inproc_locks_guard:
        thread_lock = _inproc_locks.get(lock_path)
        if thread_lock is None:
            thread_lock = threading.Lock()
            _inproc_locks[lock_path] = thread_lock

    with thread_lock:
        lock_file = open(lock_path, 'a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            held[lock_path] = 1
            try:
                yield
            finally:
                held[lock_path] = 0
        finally:
            try:
                if os.name == 'nt':
                    import msvcrt
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            lock_file.close()


def _copy_template_atomic(src_path: str, dst_path: str) -> None:
    """Atomically copy default template to destination if missing or empty."""
    if os.path.exists(dst_path) and os.path.getsize(dst_path) > 0:
        return
    dst_dir = os.path.dirname(dst_path)
    os.makedirs(dst_dir, exist_ok=True)
    with open(src_path, 'rb') as src:
        content = src.read()
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix='.tmp_tmpl_', dir=dst_dir)
        with os.fdopen(fd, 'wb') as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, dst_path)
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# flask db init  初始化
# flask db migrate   数据迁移
# flask db upgrade   改进更新
class User(db.Model):#用户
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True, comment="主键ID")
    username = db.Column(db.String(40), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(40), unique=False)
    token_version = db.Column(db.Integer, nullable=False, default=1)
class Sub(db.Model):#订阅管理
    __tablename__ = 'sub'
    id = db.Column(db.Integer, primary_key=True, comment="主键ID")
    name = db.Column(db.String(40), unique=False) #订阅名称
    node = db.Column(db.Text, unique=False) #节点
    remarks = db.Column(db.String(40), unique=False) #备注
    sort_order = db.Column(db.Integer, nullable=False, default=0) #订阅排序
    access_token = db.Column(db.String(48), nullable=True, index=True) #订阅访问Token
    legacy_enabled = db.Column(db.Boolean, nullable=False, default=False) #兼容旧地址
class Login(db.Model):#登录记录
    __tablename__ = 'login'
    id = db.Column(db.Integer, primary_key=True, comment="主键ID")
    ip = db.Column(db.String(64), unique=False) #ip
    address = db.Column(db.Text, unique=False) #地址
    time = db.Column(db.Text, unique=False) #时间
class Config(db.Model):#全局配置
    __tablename__ = 'config'
    id = db.Column(db.Integer, primary_key=True, comment="主键ID")
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.Text, unique=False)
def create_db():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    db_dir = ensure_db_dir(app_dir)
    with _init_file_lock(db_dir):
        db.create_all() # 创建所有表
        if User.query.count() == 0: # 如果用户表为空
            print('初始化用户表')
            init_username = (os.environ.get('INIT_ADMIN_USERNAME') or 'admin').strip() or 'admin'
            env_password = (os.environ.get('INIT_ADMIN_PASSWORD') or '').strip()
            generated = False
            if env_password:
                raw_password = env_password
            else:
                raw_password = secrets.token_urlsafe(12)
                generated = True
            user = User(
                username=init_username,
                password=hash_password(raw_password),
                name='管理员',
                token_version=1,
            )
            try:
                db.session.add(user)
                db.session.commit()
                if generated:
                    print('=' * 60)
                    print(f'[Sublink] 已生成初始管理员账号: {init_username}')
                    print(f'[Sublink] 已生成随机初始密码: {raw_password}')
                    print('[Sublink] 请尽快登录后台并修改账号与密码！（可通过环境变量 INIT_ADMIN_PASSWORD 指定）')
                    print('=' * 60)
            except IntegrityError:
                db.session.rollback()
            except Exception as e:
                db.session.rollback()
                print('错误信息:' + str(e))

        _copy_template_atomic(os.path.join(app_dir, 'clash.yaml'), os.path.join(db_dir, 'clash.yaml'))
        _copy_template_atomic(os.path.join(app_dir, 'surge.conf'), os.path.join(db_dir, 'surge.conf'))
        _copy_template_atomic(os.path.join(app_dir, 'sing-box.json'), os.path.join(db_dir, 'sing-box.json'))
    try:
        from .view import load_config
        load_config()
    except Exception:
        pass
def init_user_pass():
    def handle_error(e):
        db.session.rollback()
        print('错误信息:' + str(e))

    db_dir = ensure_db_dir()
    init_username = (os.environ.get('INIT_ADMIN_USERNAME') or 'admin').strip() or 'admin'
    env_password = (os.environ.get('INIT_ADMIN_PASSWORD') or '').strip()
    raw_password = env_password or secrets.token_urlsafe(12)
    user = User(
        username=init_username,
        password=hash_password(raw_password),
        name='管理员',
        token_version=secrets.randbelow(2_000_000_000) + 2,
    )
    with _init_file_lock(db_dir):
        try:
            User.query.delete()
            db.session.flush()
            db.session.add(user)
            db.session.commit()
            print("成功清空用户表并初始化账号")
            if not env_password:
                print(f'[Sublink] 重置后的管理员账号: {init_username}')
                print(f'[Sublink] 重置后的随机密码: {raw_password}')
        except Exception as e:
            handle_error(e)
def init_login_log():
    def handle_error(e):
        db.session.rollback()
        print('错误信息:' + str(e))

    try:
        Login.query.delete()
        db.session.commit()
        print("成功清空登录日志表")
    except Exception as e:
        handle_error(e)
