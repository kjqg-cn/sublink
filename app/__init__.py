from datetime import timedelta
import ipaddress
import logging
import os
import secrets
import tempfile
from typing import List, Union

from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

from .exts import init_exts
from .model import _init_file_lock, ensure_db_dir
from .view import blue

logger = logging.getLogger(__name__)

_MIN_JWT_SECRET_BYTES = 32
_NetworkType = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def _load_or_create_jwt_secret(db_dir: str) -> str:
    """
    Resolve JWT signing secret:
    1. Use non-empty JWT_SECRET_KEY environment variable when set.
    2. Otherwise generate and persist a 256-bit random secret in app/db/.jwt_secret
       under an advisory file lock + atomic os.replace so multi-worker Gunicorn processes
       always share the exact same strong key without any 0-byte read race.
    """
    env_secret = (os.environ.get('JWT_SECRET_KEY') or '').strip()
    if env_secret:
        if len(env_secret.encode('utf-8')) < _MIN_JWT_SECRET_BYTES:
            logger.warning(
                'JWT_SECRET_KEY length is below 32 bytes; consider setting a stronger secret.'
            )
        return env_secret

    secret_file = os.path.join(db_dir, '.jwt_secret')
    try:
        os.makedirs(db_dir, exist_ok=True)
        with _init_file_lock(db_dir):
            if os.path.exists(secret_file):
                with open(secret_file, 'r', encoding='utf-8') as f:
                    stored = f.read().strip()
                if stored and len(stored.encode('utf-8')) >= _MIN_JWT_SECRET_BYTES:
                    return stored

            generated = secrets.token_hex(32)
            tmp_path = None
            try:
                fd, tmp_path = tempfile.mkstemp(prefix='.tmp_jwt_', dir=db_dir)
                if os.name != 'nt':
                    os.fchmod(fd, 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(generated)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, secret_file)
                tmp_path = None
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
            return generated
    except OSError as exc:
        logger.warning('无法持久化自动生成的 JWT 密钥，回退到内存随机密钥: %s', exc)
        return secrets.token_hex(32)


def _parse_trusted_proxies(raw: str) -> List[_NetworkType]:
    networks: List[_NetworkType] = []
    for token in (raw or '').split(','):
        item = token.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning('忽略无效的 TRUSTED_PROXIES 配置项: %s', item)
    return networks


def _unwrap_ip(addr: str):
    try:
        ip_obj = ipaddress.ip_address((addr or '').strip().strip('[]').split('%', 1)[0])
    except ValueError:
        return None
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        return ip_obj.ipv4_mapped
    return ip_obj


class _ConditionalProxyFix:
    """Apply Werkzeug ProxyFix when REMOTE_ADDR belongs to trusted proxies (or unconditionally if trust_all)."""

    def __init__(
        self,
        wsgi_app,
        trusted_networks: List[_NetworkType],
        proxy_count: int = 1,
        trust_all: bool = False,
    ):
        self.raw_app = wsgi_app
        self.fixed_app = ProxyFix(
            wsgi_app,
            x_for=proxy_count,
            x_proto=proxy_count,
            x_host=proxy_count,
            x_prefix=proxy_count,
        )
        self.trusted_networks = trusted_networks
        self.trust_all = trust_all

    def __call__(self, environ, start_response):
        remote_addr = (environ.get('REMOTE_ADDR') or '').strip()
        if self.trust_all or self._is_trusted(remote_addr):
            if (environ.get('HTTP_X_FORWARDED_FOR') or '').strip():
                environ['sublink.proxy_fixed_for'] = True
            return self.fixed_app(environ, start_response)
        return self.raw_app(environ, start_response)

    def _is_trusted(self, addr: str) -> bool:
        ip_obj = _unwrap_ip(addr)
        if ip_obj is None:
            return False
        return any(ip_obj in net for net in self.trusted_networks)


def _configure_reverse_proxy(app: Flask) -> None:
    raw_count = (os.environ.get('TRUSTED_PROXY_COUNT') or '').strip()
    proxy_count = 0
    if raw_count:
        try:
            proxy_count = max(0, int(raw_count))
        except ValueError:
            logger.warning('无效的 TRUSTED_PROXY_COUNT 值: %s，已忽略', raw_count)

    trusted_networks = _parse_trusted_proxies(os.environ.get('TRUSTED_PROXIES', ''))
    app.config['TRUSTED_PROXY_NETWORKS'] = trusted_networks
    app.config['TRUSTED_PROXY_COUNT'] = proxy_count

    if trusted_networks:
        effective_count = proxy_count if proxy_count > 0 else 1
        app.wsgi_app = _ConditionalProxyFix(app.wsgi_app, trusted_networks, effective_count)
    elif proxy_count > 0:
        logger.warning(
            '已启用 TRUSTED_PROXY_COUNT=%d 但未配置 TRUSTED_PROXIES，若服务直接暴露公网可能导致客户端 IP 伪造；请结合 TRUSTED_PROXIES 或内网监听使用。',
            proxy_count,
        )
        app.wsgi_app = _ConditionalProxyFix(app.wsgi_app, [], proxy_count, trust_all=True)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(413)
    def handle_request_entity_too_large(_err):
        return jsonify({'code': 413, 'msg': '请求体过大，超过服务端限制'}), 413

    @app.errorhandler(405)
    def handle_method_not_allowed(_err):
        return jsonify({'code': 405, 'msg': '不支持的请求方法'}), 405


def _resolve_max_content_length() -> int:
    raw = (os.environ.get('MAX_CONTENT_LENGTH') or '').strip()
    if raw:
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            logger.warning('无效的 MAX_CONTENT_LENGTH 值: %s，回退默认 2 MiB', raw)
    return 2 * 1024 * 1024


def create_app():
    app = Flask(__name__)
    app.register_blueprint(blueprint=blue)
    path = os.path.dirname(os.path.abspath(__file__))
    db_dir = ensure_db_dir(path)
    db_path = os.path.join(db_dir, 'sub.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = _resolve_max_content_length()
    app.config['JWT_SECRET_KEY'] = _load_or_create_jwt_secret(db_dir)
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=30)  # 30分钟后过期
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=15)  # 15天后刷新令牌过期
    _configure_reverse_proxy(app)
    _register_error_handlers(app)
    env = os.environ.get('ENV')
    if env == 'development':
        logger.info('当前处于开发环境: %s', env)
    else:
        logger.info('当前处于部署环境: %s', env)
    init_exts(app=app)  # 第三方插件绑定app
    return app
