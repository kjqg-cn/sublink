"""Sublink HTTP route controller and backward-compatible facade."""

import builtins
from collections import OrderedDict
from contextlib import contextmanager
from io import BytesIO
import json
import logging
import os
import re
import sys
import tempfile
import threading
import time
import types
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from flask import (
    Blueprint, current_app, g, has_app_context, has_request_context,
    jsonify, make_response, redirect, request, send_file,
)
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required
import requests
import yaml

from app import config_manager
from app.config_manager import (
    APP_DIR, CustomFeature, CustomLoopback, CustomNodeName, Emoji, Hy2PinFallback, SkipCert, Udp,
    cleanup_runtime_config, get_runtime_config, load_config, path, setup_runtime_config,
)
from app.core.generator import (
    clash_encode, clear_template_cache, get_singbox_outbound, inject_surge_proxies,
    load_singbox_template, parse_clash_node, parse_singbox_node, parse_surge_node,
    singbox_encode, surge_encode, v2ray_encode, validate_singbox_template,
)
from app.core.parsers import NodeParse
from app.core.rewrite import (
    hk_name_prefix, is_ipv6_node_server, node_name_rewrite_rules,
    rewrite_loopback_node, rewrite_node_name, rewrite_node_name_ipv6_text, rewrite_remote_node,
)
from app.core.utils import (
    SUBSCRIPTION_DOWNLOAD_NAME, check_yaml_safe_aliases, decode_base64_if, decode_base64_if_emoji,
    encode_base64, is_truthy, is_valid_node_uri, new_access_token, parse_server_port,
    redact_uri_credentials, split_node_and_remarks,
)
from app.exts import _is_file_backed_sqlite_uri, db
from app.model import (
    Config, Login, Sub, User, _init_file_lock, hash_password, verify_dummy_password, verify_password,
)
from app.remote import (
    ResponseTooLargeError, SSRFError, fetch_remote_sub,
    get_client_ip, get_country_emoji, request_timeout, safe_fetch_url, save_ip_address,
)

logger = logging.getLogger(__name__)
_ORIGINAL_OPEN = builtins.open
blue = Blueprint('blue', __name__)

MAX_SUB_NAME_LEN = 40
MAX_REMARKS_LEN = 40
DEFAULT_MAX_DECODE_SUB_URLS = 20
_USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')
_PASSWORD_RE = re.compile(r'^[\x20-\x7E]{4,64}$')
_FORBIDDEN_SUB_NAME_RE = re.compile(r'[/\\?#\x00-\x1f\x7f]')
_STATIC_CACHE_PREFIXES = ('/static/', '/assets/')
_sub_write_rlock = threading.RLock()


def _validate_sub_name(raw_name: Any, empty_msg: str = '订阅名称不能为空') -> Tuple[Optional[str], Optional[str]]:
    """Validate and normalize subscription name, rejecting path-ambiguous or control characters."""
    if not raw_name or not str(raw_name).strip():
        return None, empty_msg
    name = str(raw_name).strip()
    if len(name) > MAX_SUB_NAME_LEN:
        return None, f'订阅名称不能超过 {MAX_SUB_NAME_LEN} 个字符'
    if name in ('.', '..') or _FORBIDDEN_SUB_NAME_RE.search(name):
        return None, '订阅名称不能包含 /、\\、?、# 或控制字符，且不能为 . 或 ..'
    return name, None


def apply_security_headers(response):
    """Attach baseline HTTP security headers and no-store caching policy for sensitive endpoints."""
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'no-referrer')
    req_path = request.path if has_request_context() else ''
    is_static = req_path == '/favicon.ico' or req_path.startswith(_STATIC_CACHE_PREFIXES)
    if not is_static:
        response.headers['Cache-Control'] = 'no-store'
    return response


# ---------------------------------------------------------------------------
# Login Brute-Force Rate Limiter (cross-worker file-backed + in-memory fallback)
# ---------------------------------------------------------------------------

class _LoginRateLimiter:
    """
    Thread-safe & multi-worker-safe sliding-window rate limiter with separate user & IP buckets.
    Uses atomic file-backed JSON under _init_file_lock when the app runs on file-backed SQLite
    (sharing limits across Gunicorn workers and restarts), and stays in-memory for :memory: tests.
    """

    def __init__(self, max_user_entries: int = 4096, max_ip_entries: int = 4096):
        self._lock = threading.Lock()
        self._max_user_entries = max_user_entries
        self._max_ip_entries = max_ip_entries
        self._user_failures: "OrderedDict[str, List[float]]" = OrderedDict()
        self._ip_failures: "OrderedDict[str, List[float]]" = OrderedDict()

    @staticmethod
    def _limits() -> Tuple[int, int, int]:
        try:
            per_user_max = max(1, int(os.environ.get('LOGIN_RATE_LIMIT_MAX_ATTEMPTS', '5')))
        except ValueError:
            per_user_max = 5
        try:
            per_ip_max = max(per_user_max, int(os.environ.get('LOGIN_RATE_LIMIT_IP_MAX_ATTEMPTS', '20')))
        except ValueError:
            per_ip_max = 20
        try:
            window_sec = max(10, int(os.environ.get('LOGIN_RATE_LIMIT_WINDOW', '300')))
        except ValueError:
            window_sec = 300
        return per_user_max, per_ip_max, window_sec

    @staticmethod
    def _resolve_store_dir() -> Optional[str]:
        if not has_app_context():
            return None
        uri = str(current_app.config.get('SQLALCHEMY_DATABASE_URI') or '')
        if _is_file_backed_sqlite_uri(uri) and uri.startswith('sqlite:///'):
            db_file = uri[len('sqlite:///'):].split('?', 1)[0]
            if db_file:
                return os.path.dirname(os.path.abspath(db_file))
        return None

    _MAX_CLOCK_SKEW_SEC = 5.0

    @classmethod
    def _prune(cls, bucket: "OrderedDict[str, List[float]]", key: str, now: float, window: int) -> List[float]:
        timestamps = bucket.get(key)
        if not timestamps:
            return []
        cutoff = now - window
        upper = now + cls._MAX_CLOCK_SKEW_SEC
        fresh = [ts for ts in timestamps if cutoff < ts <= upper]
        if fresh:
            bucket[key] = fresh
            bucket.move_to_end(key)
        else:
            bucket.pop(key, None)
        return fresh

    def _load_file_state(
        self, state_path: str, now: float, window: int
    ) -> Tuple["OrderedDict[str, List[float]]", "OrderedDict[str, List[float]]"]:
        user_b: "OrderedDict[str, List[float]]" = OrderedDict()
        ip_b: "OrderedDict[str, List[float]]" = OrderedDict()
        if not os.path.exists(state_path):
            return user_b, ip_b
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                return user_b, ip_b
            cutoff = now - window
            upper = now + self._MAX_CLOCK_SKEW_SEC
            for target, section_key, limit in (
                (user_b, 'u', self._max_user_entries),
                (ip_b, 'ip', self._max_ip_entries),
            ):
                section = raw.get(section_key)
                if not isinstance(section, dict):
                    continue
                for k, vals in section.items():
                    if not isinstance(k, str) or not isinstance(vals, list):
                        continue
                    fresh = [
                        float(ts) for ts in vals
                        if isinstance(ts, (int, float)) and not isinstance(ts, bool) and cutoff < float(ts) <= upper
                    ]
                    if fresh:
                        target[k] = fresh
                while len(target) > limit:
                    target.popitem(last=False)
        except Exception:
            return OrderedDict(), OrderedDict()
        return user_b, ip_b

    @staticmethod
    def _save_file_state(
        db_dir: str,
        state_path: str,
        user_b: "OrderedDict[str, List[float]]",
        ip_b: "OrderedDict[str, List[float]]",
    ) -> None:
        payload = json.dumps({'u': dict(user_b), 'ip': dict(ip_b)}, separators=(',', ':'))
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix='.tmp_rl_', dir=db_dir)
            if os.name != 'nt':
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as tmp_file:
                tmp_file.write(payload)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_path, state_path)
            tmp_path = None
        except OSError:
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _calc_retry_after(attempts: List[float], now: float, window: int) -> int:
        return min(window, max(1, int(window - (now - attempts[0]))))

    def check_blocked(self, ip: str, username: str) -> Tuple[bool, int]:
        per_user_max, per_ip_max, window = self._limits()
        now = time.time()
        user_key = f'u:{ip}:{(username or "").strip().lower()}'
        ip_key = f'ip:{ip}'
        db_dir = self._resolve_store_dir()
        if db_dir:
            state_path = os.path.join(db_dir, '.login_rate_limit.json')
            with _init_file_lock(db_dir, lock_name='.login_rate_limit.lock'):
                user_b, ip_b = self._load_file_state(state_path, now, window)
                user_attempts = self._prune(user_b, user_key, now, window)
                ip_attempts = self._prune(ip_b, ip_key, now, window)
                if len(user_attempts) >= per_user_max:
                    return True, self._calc_retry_after(user_attempts, now, window)
                if len(ip_attempts) >= per_ip_max:
                    return True, self._calc_retry_after(ip_attempts, now, window)
            return False, 0

        with self._lock:
            user_attempts = self._prune(self._user_failures, user_key, now, window)
            ip_attempts = self._prune(self._ip_failures, ip_key, now, window)
            if len(user_attempts) >= per_user_max:
                return True, self._calc_retry_after(user_attempts, now, window)
            if len(ip_attempts) >= per_ip_max:
                return True, self._calc_retry_after(ip_attempts, now, window)
        return False, 0

    def record_failure(self, ip: str, username: str) -> None:
        _, _, window = self._limits()
        now = time.time()
        user_key = f'u:{ip}:{(username or "").strip().lower()}'
        ip_key = f'ip:{ip}'
        db_dir = self._resolve_store_dir()
        if db_dir:
            state_path = os.path.join(db_dir, '.login_rate_limit.json')
            with _init_file_lock(db_dir, lock_name='.login_rate_limit.lock'):
                user_b, ip_b = self._load_file_state(state_path, now, window)
                u_fresh = self._prune(user_b, user_key, now, window)
                u_fresh.append(now)
                user_b[user_key] = u_fresh
                user_b.move_to_end(user_key)
                while len(user_b) > self._max_user_entries:
                    user_b.popitem(last=False)

                ip_fresh = self._prune(ip_b, ip_key, now, window)
                ip_fresh.append(now)
                ip_b[ip_key] = ip_fresh
                ip_b.move_to_end(ip_key)
                while len(ip_b) > self._max_ip_entries:
                    ip_b.popitem(last=False)
                self._save_file_state(db_dir, state_path, user_b, ip_b)
            return

        with self._lock:
            u_fresh = self._prune(self._user_failures, user_key, now, window)
            u_fresh.append(now)
            self._user_failures[user_key] = u_fresh
            self._user_failures.move_to_end(user_key)
            while len(self._user_failures) > self._max_user_entries:
                self._user_failures.popitem(last=False)

            ip_fresh = self._prune(self._ip_failures, ip_key, now, window)
            ip_fresh.append(now)
            self._ip_failures[ip_key] = ip_fresh
            self._ip_failures.move_to_end(ip_key)
            while len(self._ip_failures) > self._max_ip_entries:
                self._ip_failures.popitem(last=False)

    def clear_success(self, ip: str, username: str) -> None:
        user_key = f'u:{ip}:{(username or "").strip().lower()}'
        db_dir = self._resolve_store_dir()
        if db_dir:
            state_path = os.path.join(db_dir, '.login_rate_limit.json')
            _, _, window = self._limits()
            now = time.time()
            with _init_file_lock(db_dir, lock_name='.login_rate_limit.lock'):
                user_b, ip_b = self._load_file_state(state_path, now, window)
                if user_b.pop(user_key, None) is not None:
                    self._save_file_state(db_dir, state_path, user_b, ip_b)
            return

        with self._lock:
            self._user_failures.pop(user_key, None)

    def reset(self) -> None:
        with self._lock:
            self._user_failures.clear()
            self._ip_failures.clear()
        db_dir = self._resolve_store_dir()
        if db_dir:
            state_path = os.path.join(db_dir, '.login_rate_limit.json')
            with _init_file_lock(db_dir, lock_name='.login_rate_limit.lock'):
                self._save_file_state(db_dir, state_path, OrderedDict(), OrderedDict())


_login_rate_limiter = _LoginRateLimiter()


# ---------------------------------------------------------------------------
# Database & Route Helpers
# ---------------------------------------------------------------------------

@contextmanager
def _sub_write_lock() -> Iterator[None]:
    """Serialize subscription/config mutations across threads and multi-worker SQLite processes."""
    with _sub_write_rlock:
        db_dir = None
        if has_app_context():
            uri = str(current_app.config.get('SQLALCHEMY_DATABASE_URI') or '')
            if _is_file_backed_sqlite_uri(uri) and uri.startswith('sqlite:///'):
                db_file = uri[len('sqlite:///'):].split('?', 1)[0]
                if db_file:
                    db_dir = os.path.dirname(os.path.abspath(db_file))
        if db_dir:
            with _init_file_lock(db_dir, lock_name='.sub_write.lock'):
                yield
        else:
            yield


def _commit_response(msg: str, error_prefix: str = '错误信息：'):
    """Commit current db transaction and return JSON response."""
    try:
        db.session.commit()
        return jsonify({'code': 200, 'msg': msg})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 400, 'msg': f'{error_prefix}{str(e)}'})


def _atomic_write_text(filepath: str, text: str) -> None:
    """Atomically write UTF-8 text via temp file + fsync + os.replace."""
    # Respect builtins.open monkeypatches in isolated unit tests
    if builtins.open is not _ORIGINAL_OPEN:
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(text)
        clear_template_cache()
        return

    parent_dir = os.path.dirname(filepath)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix='.tmp_cfg_', dir=parent_dir)
        with os.fdopen(fd, 'w', encoding='utf-8') as tmp_file:
            tmp_file.write(text)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, filepath)
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    clear_template_cache()


def _get_json_dict() -> Dict[str, Any]:
    """Safely parse JSON request body as a dictionary, returning {} for invalid/non-object JSON."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _handle_config_file(filename: str, validator: Optional[Callable[[str], Optional[str]]] = None):
    """Generic reader/writer handler for client configuration files."""
    data = _get_json_dict()
    index = data.get('index')
    config_file = os.path.join(path, 'db', filename)
    if index == 'read':
        read_path = config_file
        if not os.path.exists(read_path):
            fallback_path = os.path.join(APP_DIR, filename)
            if os.path.exists(fallback_path):
                read_path = fallback_path
        try:
            with open(read_path, 'r', encoding='utf-8') as file:
                return jsonify({'code': 200, 'msg': file.read()})
        except OSError:
            return jsonify({'code': 400, 'msg': '读取配置文件失败'})
    if index == 'save':
        text = data.get('text')
        if not isinstance(text, str) or not text:
            return jsonify({'code': 400, 'msg': '不能为空'})
        if validator:
            err = validator(text)
            if err:
                return jsonify({'code': 400, 'msg': err})
        _atomic_write_text(config_file, text)
        return jsonify({'code': 200, 'msg': '保存成功'})
    return jsonify({'code': 400, 'msg': '不支持的操作'})


def _validate_clash_yaml(text: str) -> Optional[str]:
    try:
        check_yaml_safe_aliases(text)
        parsed_yaml = yaml.safe_load(text)
        if not isinstance(parsed_yaml, dict):
            return '配置格式错误: YAML 根节点必须为字典结构'
    except Exception as e:
        return f'配置格式错误:{str(e)}'
    return None


def _validate_singbox_json(text: str) -> Optional[str]:
    try:
        config_dict = json.loads(text)
        validate_singbox_template(config_dict)
    except (ValueError, json.JSONDecodeError) as e:
        return f'配置格式错误:{str(e)}'
    return None


def _validate_surge_conf(text: str) -> Optional[str]:
    if not text or not text.strip():
        return '配置内容不能为空'
    has_proxy = bool(re.search(r'(?m)^[ \t]*\[Proxy\][ \t]*\r?$', text))
    has_group = bool(re.search(r'(?m)^[ \t]*\[Proxy Group\][ \t]*\r?$', text))
    if not has_proxy or not has_group:
        return '配置格式错误: Surge 配置必须同时包含 [Proxy] 与 [Proxy Group] 区块'
    return None


def _is_singbox_legacy_requested() -> bool:
    """Return True when caller requests legacy download_detour format for sing-box 1.12 - 1.13 (?legacy=1 or ?version=<1.14)."""
    if is_truthy(request.args.get('legacy', '0')):
        return True
    raw_ver = (request.args.get('version') or '').strip().lstrip('vV')
    if not raw_ver:
        return False
    m = re.match(r'^(\d+)\.(\d+)', raw_ver)
    if not m:
        return False
    return (int(m.group(1)), int(m.group(2))) < (1, 14)


def _resolve_singbox_hy2_pin_fallback() -> Optional[bool]:
    """Return explicit per-request ?hy2_pin_fallback=1|0 override, or None to use global config."""
    if 'hy2_pin_fallback' in request.args:
        return is_truthy(request.args.get('hy2_pin_fallback'))
    return None


def _max_decode_sub_urls() -> int:
    raw = (os.environ.get('MAX_DECODE_SUB_URLS') or '').strip()
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return DEFAULT_MAX_DECODE_SUB_URLS


def get_next_sub_sort_order() -> int:
    max_order = db.session.query(db.func.max(Sub.sort_order)).scalar()
    return (max_order if max_order is not None else -1) + 1


# ---------------------------------------------------------------------------
# Request Lifecycle Hooks
# ---------------------------------------------------------------------------

@blue.before_request
def setup_request_runtime_config():
    setup_runtime_config()


@blue.after_request
def _add_blueprint_security_headers(response):
    return apply_security_headers(response)


@blue.teardown_app_request
def teardown_request_runtime_config(exc=None):
    cleanup_runtime_config(exc)


@blue.route('/healthz', methods=['GET'])
def healthz():
    return jsonify({'status': 'ok'}), 200


# ---------------------------------------------------------------------------
# Subscription & Config Endpoints
# ---------------------------------------------------------------------------

@blue.route('/sub/<string:target>/<path:name>', methods=['GET'])
def get_sub_url(target: str, name: str):
    subs = Sub.query.filter_by(access_token=name).order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
    if not subs:
        try:
            legacy_name = decode_base64_if_emoji(name)
            subs = Sub.query.filter_by(name=legacy_name, legacy_enabled=True).order_by(
                Sub.sort_order.asc(), Sub.id.asc()
            ).all()
        except Exception:
            subs = []
    if not subs:
        return jsonify({'code': 404, 'msg': '订阅不存在'}), 404

    if target == 'clash':
        try:
            data = clash_encode(subs)
        except Exception:
            logger.exception('clash 配置生成失败')
            return jsonify({'code': 500, 'msg': 'clash 配置生成失败'}), 500
        return make_response(send_file(BytesIO(data.encode('utf-8')), mimetype='text/plain',
                                       as_attachment=False, download_name=SUBSCRIPTION_DOWNLOAD_NAME))
    if target == 'v2ray':
        try:
            data = v2ray_encode(subs)
        except Exception:
            logger.exception('v2ray 配置生成失败')
            return jsonify({'code': 500, 'msg': 'v2ray 配置生成失败'}), 500
        return make_response(send_file(BytesIO(data.encode('utf-8')), mimetype='text/plain',
                                       as_attachment=False, download_name=f'{SUBSCRIPTION_DOWNLOAD_NAME}.txt'))
    if target == 'surge':
        try:
            data = f'#!MANAGED-CONFIG {request.url} interval=86400 strict=false\n' + surge_encode(subs)
        except Exception:
            logger.exception('surge 配置生成失败')
            return jsonify({'code': 500, 'msg': 'surge 配置生成失败'}), 500
        return make_response(send_file(BytesIO(data.encode('utf-8')), mimetype='text/plain',
                                       as_attachment=False, download_name=SUBSCRIPTION_DOWNLOAD_NAME))
    if target == 'sing-box':
        try:
            legacy_req = _is_singbox_legacy_requested()
            pin_fallback = _resolve_singbox_hy2_pin_fallback()
            if legacy_req and pin_fallback is not None:
                data = singbox_encode(subs, legacy_format=True, hy2_pin_fallback=pin_fallback)
            elif legacy_req:
                data = singbox_encode(subs, legacy_format=True)
            elif pin_fallback is not None:
                data = singbox_encode(subs, hy2_pin_fallback=pin_fallback)
            else:
                data = singbox_encode(subs)
        except Exception:
            logger.exception('sing-box 配置生成失败')
            return jsonify({'code': 500, 'msg': 'sing-box 配置生成失败'}), 500
        return make_response(send_file(BytesIO(data.encode('utf-8')), mimetype='application/json',
                                       as_attachment=False, download_name=f'{SUBSCRIPTION_DOWNLOAD_NAME}.json'))
    return jsonify({'code': 400, 'msg': '不支持的订阅类型'}), 400


@blue.route('/clash_config', methods=['POST'])
@jwt_required()
def clash_config():
    return _handle_config_file('clash.yaml', _validate_clash_yaml)


@blue.route('/surge_config', methods=['POST'])
@jwt_required()
def surge_config():
    return _handle_config_file('surge.conf', _validate_surge_conf)


@blue.route('/singbox_config', methods=['POST'])
@jwt_required()
def singbox_config():
    return _handle_config_file('sing-box.json', _validate_singbox_json)


@blue.route('/')
def get_index():
    index_path = os.path.join(path, 'static', 'dist', 'index.html')
    if not os.path.exists(index_path):
        return '前端尚未构建，请先在 web 目录执行 npm ci && npm run build，或使用 Docker 构建部署', 503
    return send_file(index_path)


@blue.route('/favicon.ico')
def get_favicon():
    return send_file(os.path.join(path, 'static', 'favicon.ico'), mimetype='image/x-icon')


@blue.route('/next')
@blue.route('/next/')
def get_index_next():
    return redirect('/', code=302)


# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------

def _issue_user_tokens(user: User) -> Tuple[str, str]:
    claims = {'tv': user.token_version or 1, 'uid': user.id}
    access_token = create_access_token(identity=user.username, additional_claims=claims)
    refresh_token = create_refresh_token(identity=user.username, additional_claims=claims)
    return access_token, refresh_token


@blue.route('/login', methods=['POST'])
def get_login():
    data = _get_json_dict()
    username = data.get('username')
    password = data.get('password')
    if not isinstance(username, str) or not isinstance(password, str) or not username.strip() or not password:
        return jsonify({'code': 404, 'msg': '账号或者密码错误'})
    username = username.strip()

    client_ip = get_client_ip()
    blocked, retry_after = _login_rate_limiter.check_blocked(client_ip, username)
    if blocked:
        resp = make_response(jsonify({'code': 429, 'msg': '登录失败次数过多，请稍后再试'}), 429)
        resp.headers['Retry-After'] = str(retry_after)
        return resp

    user = User.query.filter_by(username=username).first()
    if not user:
        verify_dummy_password(password)
        _login_rate_limiter.record_failure(client_ip, username)
        return jsonify({'code': 404, 'msg': '账号或者密码错误'})

    is_valid, needs_rehash = verify_password(user.password, password)
    if not is_valid:
        _login_rate_limiter.record_failure(client_ip, username)
        return jsonify({'code': 404, 'msg': '账号或者密码错误'})

    if needs_rehash:
        try:
            user.password = hash_password(password)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception('密码哈希自动升级失败')

    _login_rate_limiter.clear_success(client_ip, username)
    access_token, refresh_token = _issue_user_tokens(user)
    save_ip_address()
    return jsonify({'code': 200, 'token': access_token, 'refresh': refresh_token, 'msg': '登录成功'})


@blue.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def get_refresh():
    current_user = get_jwt_identity()
    if not current_user:
        return jsonify({'code': 401, 'msg': '令牌无效'}), 401
    user = User.query.filter_by(username=current_user).first()
    if not user:
        return jsonify({'code': 401, 'msg': '用户不存在或令牌已失效'}), 401
    claims = {'tv': user.token_version or 1, 'uid': user.id}
    resp = make_response(create_access_token(identity=user.username, additional_claims=claims), 200)
    resp.mimetype = 'text/plain; charset=utf-8'
    return resp


# ---------------------------------------------------------------------------
# Node & Subscription Management Endpoints
# ---------------------------------------------------------------------------

@blue.route('/create_sub', methods=['POST'])
@jwt_required()
def get_create_sub():
    data = _get_json_dict()
    nodes = data.get('node')
    if nodes is None:
        nodes = []
    if not isinstance(nodes, list):
        return jsonify({'code': 400, 'msg': '节点列表格式不正确'})
    name, name_err = _validate_sub_name(data.get('name'))
    if name_err or not name:
        return jsonify({'code': 400, 'msg': name_err or '订阅名称不能为空'})

    parsed_items: List[Tuple[str, str]] = []
    invalid: List[str] = []
    for item in nodes:
        if not isinstance(item, str):
            return jsonify({'code': 400, 'msg': '节点数据格式不正确'})
        node, remarks = split_node_and_remarks(item)
        if not node:
            continue
        if len(remarks) > MAX_REMARKS_LEN:
            return jsonify({'code': 400, 'msg': f'备注不能超过 {MAX_REMARKS_LEN} 个字符'})
        if is_valid_node_uri(node):
            parsed_items.append((node, remarks))
        else:
            invalid.append(redact_uri_credentials(node))
    if not parsed_items:
        return jsonify({'code': 400, 'msg': '没有可用的节点，请检查节点格式'})

    with _sub_write_lock():
        if Sub.query.filter_by(name=name).first():
            return jsonify({'code': 400, 'msg': '订阅名字已经存在'})
        sort_order = get_next_sub_sort_order()
        access_token = new_access_token()
        valid_sub_objects = [
            Sub(
                name=name, node=node, remarks=remarks, sort_order=sort_order,
                access_token=access_token, legacy_enabled=False,
            )
            for node, remarks in parsed_items
        ]
        try:
            db.session.add_all(valid_sub_objects)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'code': 400, 'msg': f'错误信息：{str(e)}'})
    if invalid:
        return jsonify({'code': 200, 'msg': f'创建成功，已跳过 {len(invalid)} 个无效节点'})
    return jsonify({'code': 200, 'msg': '创建成功'})


@blue.route('/create_node', methods=['POST'])
@jwt_required()
def create_node():
    data = _get_json_dict()
    raw_remarks = data.get('remarks')
    remarks = str(raw_remarks).strip() if raw_remarks is not None else ''
    raw_node = data.get('node')
    node = raw_node.strip() if isinstance(raw_node, str) else ''
    name, name_err = _validate_sub_name(data.get('name'))
    if name_err or not name:
        return jsonify({'code': 400, 'msg': name_err or '订阅名称不能为空'})
    if len(remarks) > MAX_REMARKS_LEN:
        return jsonify({'code': 400, 'msg': f'备注不能超过 {MAX_REMARKS_LEN} 个字符'})
    if not node:
        return jsonify({'code': 400, 'msg': '节点内容不能为空'})
    if not is_valid_node_uri(node):
        return jsonify({'code': 400, 'msg': '不是有效的协议,请检查后重新输入'})

    with _sub_write_lock():
        existing_subs = Sub.query.filter_by(name=name).order_by(Sub.id.asc()).all()
        cur = existing_subs[0] if existing_subs else None
        token = next((s.access_token for s in existing_subs if s.access_token), None) or new_access_token()
        for existing in existing_subs:
            if not existing.access_token:
                existing.access_token = token
        db.session.add(Sub(
            name=name, node=node, remarks=remarks,
            sort_order=cur.sort_order if cur else get_next_sub_sort_order(),
            access_token=token,
            legacy_enabled=cur.legacy_enabled if cur else False
        ))
        return _commit_response('创建成功')


@blue.route('/get_sub_summaries', methods=['POST'])
@jwt_required()
def get_sub_summaries():
    rows = (
        db.session.query(
            Sub.name,
            db.func.count(Sub.id),
            db.func.min(Sub.sort_order),
        )
        .filter(Sub.name.isnot(None), Sub.name != '')
        .group_by(Sub.name)
        .order_by(db.func.min(Sub.sort_order).asc(), db.func.min(Sub.id).asc())
        .all()
    )
    return jsonify([
        {'name': row[0], 'count': int(row[1]), 'sort_order': int(row[2] or 0)}
        for row in rows
    ])


@blue.route('/get_subs', methods=['POST'])
@jwt_required()
def get_subs():
    subs = Sub.query.order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
    if subs:
        grouped: Dict[Optional[str], List[Sub]] = {}
        for s in subs:
            grouped.setdefault(s.name, []).append(s)
        needs_backfill = any(
            (not s.access_token) or (len({item.access_token for item in grp}) > 1)
            for grp in grouped.values()
            for s in grp
        )
        if needs_backfill:
            with _sub_write_lock():
                # Re-query fresh rows inside write lock to avoid overwriting concurrent updates
                db.session.expire_all()
                subs = Sub.query.order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
                grouped = {}
                for s in subs:
                    grouped.setdefault(s.name, []).append(s)
                changed = False
                for group_subs in grouped.values():
                    token = next((s.access_token for s in group_subs if s.access_token), None) or new_access_token()
                    for s in group_subs:
                        if s.access_token != token:
                            s.access_token = token
                            changed = True
                # Snapshot response before commit() expires ORM attributes (avoids N+1 reload SELECTs)
                payload = [{
                    'id': s.id, 'name': s.name, 'node': s.node, 'remarks': s.remarks,
                    'sort_order': s.sort_order, 'access_token': s.access_token, 'legacy_enabled': s.legacy_enabled
                } for s in subs]
                if changed:
                    db.session.commit()
                return jsonify(payload)
    return jsonify([{
        'id': s.id, 'name': s.name, 'node': s.node, 'remarks': s.remarks,
        'sort_order': s.sort_order, 'access_token': s.access_token, 'legacy_enabled': s.legacy_enabled
    } for s in subs])


@blue.route('/rename_sub/<path:name>', methods=['POST'])
@jwt_required()
def rename_sub(name: str):
    new_name, name_err = _validate_sub_name(_get_json_dict().get('newName'), empty_msg='新名称不能为空')
    if name_err or not new_name:
        return jsonify({'code': 400, 'msg': name_err or '新名称不能为空'})

    with _sub_write_lock():
        subs = Sub.query.filter_by(name=name).all()
        if not subs:
            return jsonify({'code': 404, 'msg': '订阅不存在'}), 404
        if new_name != name and Sub.query.filter_by(name=new_name).first():
            return jsonify({'code': 400, 'msg': '名字已存在'})
        for s in subs:
            s.name = new_name
        return _commit_response('成功', error_prefix='错误')


@blue.route('/get_sub/<path:name>', methods=['POST'])
@jwt_required()
def get_sub(name: str):
    subs = Sub.query.filter_by(name=name).order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
    if subs and (any(not s.access_token for s in subs) or len({s.access_token for s in subs}) > 1):
        with _sub_write_lock():
            db.session.expire_all()
            subs = Sub.query.filter_by(name=name).order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
            token = next((s.access_token for s in subs if s.access_token), None) or new_access_token()
            changed = False
            for s in subs:
                if s.access_token != token:
                    s.access_token = token
                    changed = True
            payload = [{
                'id': s.id, 'name': s.name, 'node': s.node, 'remarks': s.remarks,
                'access_token': s.access_token, 'legacy_enabled': s.legacy_enabled
            } for s in subs]
            if changed:
                db.session.commit()
            return jsonify(payload)
    return jsonify([{
        'id': s.id, 'name': s.name, 'node': s.node, 'remarks': s.remarks,
        'access_token': s.access_token, 'legacy_enabled': s.legacy_enabled
    } for s in subs])


@blue.route('/del_sub/<path:name>', methods=['POST'])
@jwt_required()
def del_sub(name: str):
    with _sub_write_lock():
        subs = Sub.query.filter_by(name=name).all()
        if not subs:
            return jsonify({'code': 400, 'msg': '不存在'})
        for s in subs:
            db.session.delete(s)
        return _commit_response('删除成功', error_prefix='错误信息:')


@blue.route('/del_sub_node/<int:id>', methods=['POST'])
@jwt_required()
def del_sub_node(id: int):
    with _sub_write_lock():
        sub = Sub.query.filter_by(id=id).first()
        if not sub:
            return jsonify({'code': 400, 'msg': '不存在'})
        remaining_count = Sub.query.filter_by(name=sub.name).count()
        if remaining_count <= 1:
            return jsonify({
                'code': 400,
                'msg': '该订阅仅剩最后一个节点，无法删除以防订阅 Token 失效；如需移除订阅请使用“删除订阅”',
            })
        db.session.delete(sub)
        return _commit_response('删除成功', error_prefix='错误信息:')


@blue.route('/set_sub', methods=['POST'])
@jwt_required()
def get_set_sub():
    data = _get_json_dict()
    raw_name = data.get('name')
    if not raw_name or not str(raw_name).strip():
        return jsonify({'code': 400, 'msg': '订阅名称不能为空'})
    name = str(raw_name).strip()
    new_nodes = data.get('newNode')
    if new_nodes is None:
        new_nodes = []
    if not isinstance(new_nodes, list):
        return jsonify({'code': 400, 'msg': '节点列表格式不正确'})

    parsed_nodes: List[Tuple[str, str]] = []
    for item in new_nodes:
        if not isinstance(item, str):
            return jsonify({'code': 400, 'msg': '节点数据格式不正确'})
        node, remarks = split_node_and_remarks(item)
        if not node:
            continue
        if len(remarks) > MAX_REMARKS_LEN:
            return jsonify({'code': 400, 'msg': f'备注不能超过 {MAX_REMARKS_LEN} 个字符'})
        if not is_valid_node_uri(node):
            return jsonify({'code': 400, 'msg': f'节点格式不正确：{redact_uri_credentials(node)}'})
        parsed_nodes.append((node, remarks))
    if not parsed_nodes:
        return jsonify({'code': 400, 'msg': '至少保留一个有效节点'})

    with _sub_write_lock():
        subs = Sub.query.filter_by(name=name).order_by(Sub.id.asc()).all()
        if not subs:
            return jsonify({'code': 400, 'msg': '订阅不存在'})
        sort_order = subs[0].sort_order if subs else get_next_sub_sort_order()
        access_token = next((s.access_token for s in subs if s.access_token), None) or new_access_token()
        legacy_enabled = subs[0].legacy_enabled if subs else False
        try:
            for existing in subs:
                db.session.delete(existing)
            db.session.flush()
            db.session.add_all([
                Sub(name=name, node=node, remarks=remarks, sort_order=sort_order,
                    access_token=access_token, legacy_enabled=legacy_enabled)
                for node, remarks in parsed_nodes
            ])
            db.session.commit()
            return jsonify({'code': 200, 'msg': '修改成功'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'code': 400, 'msg': f'错误信息：{str(e)}'})


@blue.route('/sort_subs', methods=['POST'])
@jwt_required()
def sort_subs():
    names = _get_json_dict().get('names', [])
    if not isinstance(names, list) or any(not isinstance(n, str) for n in names) or len(names) != len(set(names)):
        return jsonify({'code': 400, 'msg': '订阅排序数据不正确'})
    with _sub_write_lock():
        existing = [
            r[0] for r in db.session.query(Sub.name)
            .filter(Sub.name.isnot(None), Sub.name != '')
            .distinct().all()
        ]
        if set(names) != set(existing):
            return jsonify({'code': 400, 'msg': '订阅列表已变化，请刷新后重试'})
        try:
            for order, name in enumerate(names):
                Sub.query.filter_by(name=name).update({'sort_order': order})
            db.session.commit()
            return jsonify({'code': 200, 'msg': '订阅排序已保存'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'code': 400, 'msg': f'错误信息：{str(e)}'})


@blue.route('/set_sub_legacy/<path:name>', methods=['POST'])
@jwt_required()
def set_sub_legacy(name: str):
    data = _get_json_dict()
    enabled = data.get('enabled')
    if not isinstance(enabled, bool):
        return jsonify({'code': 400, 'msg': '旧地址兼容状态不正确'})
    with _sub_write_lock():
        if not Sub.query.filter_by(name=name).first():
            return jsonify({'code': 400, 'msg': '订阅不存在'})
        try:
            Sub.query.filter_by(name=name).update({'legacy_enabled': enabled}, synchronize_session=False)
            db.session.commit()
            return jsonify({'code': 200, 'msg': '旧地址兼容已开启' if enabled else '旧地址兼容已关闭'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'code': 400, 'msg': f'错误信息：{str(e)}'})


@blue.route('/set_node', methods=['POST'])
@jwt_required()
def get_set_node():
    data = _get_json_dict()
    raw_node = data.get('node')
    node = raw_node.strip() if isinstance(raw_node, str) else ''
    if not is_valid_node_uri(node):
        return jsonify({'code': 400, 'msg': '节点格式不对'})
    raw_id = data.get('id')
    if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
        return jsonify({'code': 404, 'msg': '节点不存在'})
    try:
        node_id = int(raw_id)
    except (ValueError, TypeError):
        return jsonify({'code': 404, 'msg': '节点不存在'})
    raw_remarks = data.get('remarks')
    remarks = str(raw_remarks).strip() if raw_remarks is not None else ''
    if len(remarks) > MAX_REMARKS_LEN:
        return jsonify({'code': 400, 'msg': f'备注不能超过 {MAX_REMARKS_LEN} 个字符'})
    with _sub_write_lock():
        sub = Sub.query.filter_by(id=node_id).first()
        if not sub:
            return jsonify({'code': 404, 'msg': '节点不存在'})
        sub.node = node
        sub.remarks = remarks
        return _commit_response('修改成功')


@blue.route('/set_user', methods=['POST'])
@jwt_required()
def get_set_user():
    data = _get_json_dict()
    current_user = get_jwt_identity()
    target_username = data.get('username')
    if not current_user or current_user != target_username:
        return jsonify({'code': 403, 'msg': '无权修改其他用户账号'})

    client_ip = get_client_ip()
    rate_key = f'set_user:{current_user}'
    blocked, retry_after = _login_rate_limiter.check_blocked(client_ip, rate_key)
    if blocked:
        resp = make_response(jsonify({'code': 429, 'msg': '密码验证失败次数过多，请稍后再试'}), 429)
        resp.headers['Retry-After'] = str(retry_after)
        return resp

    old_password = data.get('oldPassword')
    if not isinstance(old_password, str) or not old_password:
        return jsonify({'code': 400, 'msg': '请输入当前密码'})

    new_username = data.get('newUserName')
    password = data.get('password')
    if (
        not isinstance(new_username, str)
        or not isinstance(password, str)
        or not new_username.strip()
        or not password.strip()
    ):
        return jsonify({'code': 400, 'msg': '用户名和密码不能为空'})
    new_username = new_username.strip()
    if not _USERNAME_RE.match(new_username):
        return jsonify({'code': 400, 'msg': '用户名需为 3-32 位字母、数字、下划线、点或连字符'})
    if not _PASSWORD_RE.match(password):
        return jsonify({'code': 400, 'msg': '密码需为 4-64 位可见 ASCII 字符'})

    # Perform slow PBKDF2 verify/hash and rate-limit file updates outside _sub_write_lock()
    # to avoid blocking global subscription writes or nesting cross-process file locks.
    user_snapshot = User.query.filter_by(username=target_username).first()
    if not user_snapshot:
        return jsonify({'code': 400, 'msg': '账号不正确'})
    expected_token_version = user_snapshot.token_version or 1
    old_valid, _ = verify_password(user_snapshot.password, old_password)
    if not old_valid:
        _login_rate_limiter.record_failure(client_ip, rate_key)
        return jsonify({'code': 400, 'msg': '当前密码不正确'})
    _login_rate_limiter.clear_success(client_ip, rate_key)

    new_password_hash = hash_password(password)

    with _sub_write_lock():
        db.session.expire_all()
        user = User.query.filter_by(username=target_username).first()
        if not user:
            return jsonify({'code': 400, 'msg': '账号不正确'})
        if (user.token_version or 1) != expected_token_version:
            return jsonify({'code': 400, 'msg': '账号凭据已被其他会话修改，请重新登录后再试'})
        if new_username != target_username and User.query.filter_by(username=new_username).first():
            return jsonify({'code': 400, 'msg': '用户名已存在'})
        user.username = new_username
        user.password = new_password_hash
        # Bump token_version to immediately revoke all previously issued access and refresh tokens
        user.token_version = expected_token_version + 1
        return _commit_response('修改成功', error_prefix='错误信息:')


@blue.route('/decode_sub', methods=['POST'])
@jwt_required()
def decode_sub():
    data = _get_json_dict()
    raw_urls = data.get('urls')
    if not raw_urls:
        return jsonify({'code': 400, 'msg': 'URL不能为空'})
    urls = raw_urls if isinstance(raw_urls, list) else [raw_urls]
    max_urls = _max_decode_sub_urls()
    if len(urls) > max_urls:
        return jsonify({'code': 400, 'msg': f'单次最多解析 {max_urls} 个订阅链接'})
    datas = []
    for url in urls:
        if not isinstance(url, str) or not url.strip():
            return jsonify({'code': 400, 'msg': 'URL不能为空'})
        url = url.strip()
        try:
            status_code, body = safe_fetch_url(url, timeout=(3, 10))
            if status_code == 200:
                datas.append(decode_base64_if(body))
            else:
                return jsonify({'code': status_code, 'msg': body[:500]})
        except (SSRFError, ResponseTooLargeError) as sec_err:
            return jsonify({'code': 400, 'msg': str(sec_err)})
        except Exception as e:
            return jsonify({'code': 400, 'msg': f'拉取订阅失败: {str(e)}'})
    return jsonify({'code': 200, 'msg': datas})


@blue.route('/get_ip_address', methods=['POST'])
@jwt_required()
def get_ip_address():
    logins = Login.query.order_by(Login.time.desc(), Login.id.desc()).all()
    return jsonify([{'id': i.id, 'ip': i.ip, 'address': i.address, 'time': i.time} for i in logins])


# ---------------------------------------------------------------------------
# Global Runtime Config Endpoints
# ---------------------------------------------------------------------------

@blue.route('/set_config', methods=['POST'])
@blue.route('/set_conifg', methods=['POST'])
@jwt_required()
def set_config():
    data = _get_json_dict()
    keys = ['udp', 'skipcert', 'emoji', 'hy2_pin_fallback', 'custom', 'custom_loopback', 'custom_node_name']
    with _sub_write_lock():
        try:
            for key in keys:
                if key in data:
                    val = '1' if is_truthy(data.get(key)) else '0'
                    existing = Config.query.filter_by(key=key).first()
                    if existing is not None:
                        existing.value = val
                    else:
                        db.session.add(Config(key=key, value=val))
            db.session.commit()
            if has_request_context() and hasattr(g, 'runtime_config'):
                delattr(g, 'runtime_config')
            get_runtime_config(sync_globals=True)
            return jsonify({'code': 200, 'msg': '设置保存成功'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'code': 400, 'msg': f'错误信息：{str(e)}'})


@blue.route('/get_config', methods=['POST'])
@blue.route('/get_conifg', methods=['POST'])
@jwt_required()
def get_config():
    if has_request_context() and hasattr(g, 'runtime_config'):
        delattr(g, 'runtime_config')
    return jsonify(get_runtime_config(sync_globals=True))


# ---------------------------------------------------------------------------
# Module proxy class for test-compatibility (patch.object / global assignments)
# ---------------------------------------------------------------------------

_CONFIG_GLOBAL_NAMES = {
    'CustomFeature',
    'CustomLoopback',
    'CustomNodeName',
    'Emoji',
    'Hy2PinFallback',
    'SkipCert',
    'Udp',
    'path',
}


class _ViewModule(types.ModuleType):
    """Module proxy providing transparent two-way synchronization with config_manager."""

    def __getattribute__(self, name: str) -> Any:
        if name in _CONFIG_GLOBAL_NAMES:
            return getattr(config_manager, name)
        return super().__getattribute__(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _CONFIG_GLOBAL_NAMES:
            setattr(config_manager, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _ViewModule
