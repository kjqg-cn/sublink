"""Remote network communication and external services for Sublink."""

from collections import OrderedDict, namedtuple
import datetime
import ipaddress
import json
import logging
import os
import socket
import sys
import threading
import time
from typing import Any, List, Optional, Tuple
import urllib.parse

from flask import current_app, has_app_context, request
import requests
from urllib3.connection import HTTPConnection as _Urllib3HTTPConnection
from urllib3.connection import HTTPSConnection as _Urllib3HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool as _Urllib3HTTPConnectionPool
from urllib3.connectionpool import HTTPSConnectionPool as _Urllib3HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError as _Urllib3ConnectTimeoutError
from urllib3.exceptions import NameResolutionError as _Urllib3NameResolutionError
from urllib3.exceptions import NewConnectionError as _Urllib3NewConnectionError
from urllib3.util import connection as _urllib3_connection

from app.core.rewrite import rewrite_remote_node
from app.core.utils import (
    decode_base64_if,
    get_proxy_type,
    get_remote_sub_host,
    is_truthy,
    is_valid_node_uri,
    redact_uri_credentials,
    rewritable_node_types,
)
from app.exts import _is_file_backed_sqlite_uri, db
from app.model import Login

logger = logging.getLogger(__name__)
request_timeout = (3, 8)

_ORIGINAL_REQUESTS_GET = requests.get

DEFAULT_SUB_HEADERS = {
    'User-Agent': 'Sublink/3.0 (compatible; v2rayN/6.23)'
}

REMOTE_SUB_CACHE_TTL = 180  # 3 minutes cache for remote subscriptions
REMOTE_SUB_CACHE_MAXSIZE = 256
MAX_REMOTE_SUB_BYTES = 5 * 1024 * 1024  # 5 MiB max remote subscription body
MAX_REMOTE_REDIRECTS = 5
EMOJI_CACHE_MAXSIZE = 1024
EMOJI_FAIL_CACHE_TTL = 30.0
EMOJI_FAIL_CACHE_MAXSIZE = 512
DEFAULT_MAX_LOGIN_LOG_ROWS = 500
_CGNAT_NETWORK = ipaddress.ip_network('100.64.0.0/10')
_NAT64_NETWORK = ipaddress.ip_network('64:ff9b::/96')

# Bounded LRU cache storing RAW (un-rewritten) valid node lines keyed by URL
_remote_sub_cache: "OrderedDict[str, Tuple[float, List[str]]]" = OrderedDict()
_cache_lock = threading.Lock()

_remote_session: Optional[requests.Session] = None
_session_lock = threading.Lock()

_CacheInfo = namedtuple('CacheInfo', ['hits', 'misses', 'maxsize', 'currsize'])
_emoji_cache_lock = threading.Lock()
_emoji_pos_cache: "OrderedDict[str, str]" = OrderedDict()
_emoji_fail_cache: "OrderedDict[str, float]" = OrderedDict()
_emoji_cache_hits = 0
_emoji_cache_misses = 0


class SSRFError(ValueError):
    """Raised when a remote URL targets a disallowed scheme, host, or IP range."""


class ResponseTooLargeError(ValueError):
    """Raised when a remote response exceeds the maximum allowed size."""


class _SafeConnectionMixin:
    """Resolve DNS once, validate every IP against SSRF policy, and connect directly to a validated IP."""

    def _new_conn(self) -> socket.socket:
        if is_truthy(os.environ.get('ALLOW_PRIVATE_SUB_URLS', '0')):
            return super()._new_conn()  # type: ignore[misc]

        try:
            addr_infos = socket.getaddrinfo(self._dns_host, self.port, 0, socket.SOCK_STREAM)  # type: ignore[attr-defined]
        except socket.gaierror as exc:
            raise _Urllib3NameResolutionError(self.host, self, exc) from exc  # type: ignore[attr-defined]

        if not addr_infos:
            raise _Urllib3NameResolutionError(
                self.host, self, socket.gaierror(f'No address info for {self.host}')  # type: ignore[attr-defined]
            )

        validated_ips: List[str] = []
        for info in addr_infos:
            resolved_ip = info[4][0]
            ip_obj = _parse_ip_literal(resolved_ip)
            if ip_obj is None or _is_forbidden_ip(ip_obj):
                raise SSRFError(f'目标域名解析到了受限地址: {self.host}')  # type: ignore[attr-defined]
            ip_str = str(ip_obj)
            if ip_str not in validated_ips:
                validated_ips.append(ip_str)

        last_err: Optional[Exception] = None
        for ip_str in validated_ips:
            try:
                sock = _urllib3_connection.create_connection(
                    (ip_str, self.port),  # type: ignore[attr-defined]
                    self.timeout,  # type: ignore[attr-defined]
                    source_address=self.source_address,  # type: ignore[attr-defined]
                    socket_options=self.socket_options,  # type: ignore[attr-defined]
                )
                return sock
            except socket.timeout:
                last_err = _Urllib3ConnectTimeoutError(
                    self,
                    f'Connection to {self.host} timed out. (connect timeout={self.timeout})',  # type: ignore[attr-defined]
                )
            except OSError as exc:
                last_err = _Urllib3NewConnectionError(
                    self, f'Failed to establish a new connection: {exc}'
                )

        if last_err is not None:
            raise last_err
        raise _Urllib3NewConnectionError(self, f'Failed to establish a new connection to {self.host}')  # type: ignore[attr-defined]


class _SafeHTTPConnection(_SafeConnectionMixin, _Urllib3HTTPConnection):
    pass


class _SafeHTTPSConnection(_SafeConnectionMixin, _Urllib3HTTPSConnection):
    pass


class _SafeHTTPConnectionPool(_Urllib3HTTPConnectionPool):
    ConnectionCls = _SafeHTTPConnection


class _SafeHTTPSConnectionPool(_Urllib3HTTPSConnectionPool):
    ConnectionCls = _SafeHTTPSConnection


class _SafeHTTPAdapter(requests.adapters.HTTPAdapter):
    """HTTPAdapter enforcing socket-level SSRF validation on direct connections (prevents DNS rebinding)."""

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {
            'http': _SafeHTTPConnectionPool,
            'https': _SafeHTTPSConnectionPool,
        }


def _get_remote_session() -> requests.Session:
    global _remote_session
    if _remote_session is None:
        with _session_lock:
            if _remote_session is None:
                s = requests.Session()
                # Disable implicit env proxy (HTTP_PROXY/HTTPS_PROXY) by default so _SafeHTTPAdapter cannot be bypassed
                s.trust_env = is_truthy(os.environ.get('ALLOW_REMOTE_SUB_ENV_PROXY', '0'))
                s.headers.update(DEFAULT_SUB_HEADERS)
                adapter = _SafeHTTPAdapter(pool_connections=20, pool_maxsize=20)
                s.mount('http://', adapter)
                s.mount('https://', adapter)
                _remote_session = s
    return _remote_session


def clear_remote_sub_cache(url: Optional[str] = None) -> None:
    """Clear memory cache for a specific URL or all remote subscriptions."""
    with _cache_lock:
        if url:
            _remote_sub_cache.pop(url, None)
        else:
            _remote_sub_cache.clear()


def _cache_put(url: str, raw_nodes: List[str]) -> None:
    with _cache_lock:
        _remote_sub_cache[url] = (time.time(), list(raw_nodes))
        _remote_sub_cache.move_to_end(url)
        while len(_remote_sub_cache) > REMOTE_SUB_CACHE_MAXSIZE:
            _remote_sub_cache.popitem(last=False)


def _cache_get(url: str, *, allow_stale: bool = False) -> Optional[List[str]]:
    now = time.time()
    with _cache_lock:
        entry = _remote_sub_cache.get(url)
        if not entry:
            return None
        cached_time, cached_nodes = entry
        if allow_stale or (now - cached_time < REMOTE_SUB_CACHE_TTL):
            _remote_sub_cache.move_to_end(url)
            return list(cached_nodes)
        return None


def is_raw_ip(host: str) -> bool:
    """Determine if a hostname is an IPv4 or bracketed/raw IPv6 address."""
    clean_host = (host or '').strip().strip('[]')
    if not clean_host:
        return False
    try:
        ipaddress.ip_address(clean_host)
        return True
    except ValueError:
        return False


def _is_forbidden_ip(ip_obj: Any) -> bool:
    """Return True if IP address is non-global (private, loopback, link-local, metadata, etc.)."""
    if isinstance(ip_obj, ipaddress.IPv6Address):
        if ip_obj.ipv4_mapped is not None:
            return _is_forbidden_ip(ip_obj.ipv4_mapped)
        if ip_obj.sixtofour is not None and _is_forbidden_ip(ip_obj.sixtofour):
            return True
        if ip_obj.teredo is not None and any(_is_forbidden_ip(addr) for addr in ip_obj.teredo):
            return True
        if ip_obj in _NAT64_NETWORK:
            embedded_v4 = ipaddress.IPv4Address(int(ip_obj) & 0xFFFFFFFF)
            if _is_forbidden_ip(embedded_v4):
                return True
    if isinstance(ip_obj, ipaddress.IPv4Address) and ip_obj in _CGNAT_NETWORK:
        return True
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
        or not ip_obj.is_global
    )


def _parse_ip_literal(host: str) -> Optional[Any]:
    clean = (host or '').strip().strip('[]')
    if not clean:
        return None
    # Strip IPv6 zone identifier if present (e.g. fe80::1%eth0)
    clean_no_zone = clean.split('%', 1)[0]
    try:
        return ipaddress.ip_address(clean_no_zone)
    except ValueError:
        pass
    # Detect alternative IPv4 notations (decimal/octal/hex/shortened like 127.1, 0x7f000001)
    try:
        packed = socket.inet_aton(clean)
        return ipaddress.IPv4Address(packed)
    except OSError:
        return None


def validate_remote_url(url: str, *, allow_unresolved_when_mocked: bool = False) -> str:
    """
    Validate remote subscription URL against SSRF rules.
    Enforces http/https scheme and blocks private/loopback/link-local/metadata targets
    unless ALLOW_PRIVATE_SUB_URLS is explicitly enabled.
    """
    if not isinstance(url, str) or not url.strip():
        raise SSRFError('URL不能为空')
    cleaned = url.strip()
    parsed = urllib.parse.urlsplit(cleaned)
    scheme = (parsed.scheme or '').lower()
    if scheme not in ('http', 'https'):
        raise SSRFError(f'仅支持 http 或 https 协议: {cleaned}')
    hostname = (parsed.hostname or '').strip()
    if not hostname:
        raise SSRFError(f'无效的订阅地址: {cleaned}')

    if is_truthy(os.environ.get('ALLOW_PRIVATE_SUB_URLS', '0')):
        return cleaned

    lower_host = hostname.lower().rstrip('.')
    if lower_host == 'localhost' or lower_host.endswith('.localhost') or lower_host.endswith('.local'):
        raise SSRFError(f'禁止访问本地或内网地址: {hostname}')

    ip_literal = _parse_ip_literal(hostname)
    if ip_literal is not None:
        if _is_forbidden_ip(ip_literal):
            raise SSRFError(f'禁止访问内网、回环或保留地址: {hostname}')
        return cleaned

    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise SSRFError(f'无效的订阅地址端口: {cleaned}') from exc
    port = parsed_port or (443 if scheme == 'https' else 80)
    try:
        addr_infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        if allow_unresolved_when_mocked:
            return cleaned
        raise SSRFError(f'无法解析目标主机地址: {hostname}') from exc

    if not addr_infos:
        if allow_unresolved_when_mocked:
            return cleaned
        raise SSRFError(f'无法解析目标主机地址: {hostname}')

    for info in addr_infos:
        resolved_ip = info[4][0]
        ip_obj = _parse_ip_literal(resolved_ip)
        if ip_obj is None or _is_forbidden_ip(ip_obj):
            raise SSRFError(f'目标域名解析到了受限地址: {hostname}')
    return cleaned


def _http_get(
    url: str,
    timeout: Any,
    verify: bool,
    allow_redirects: bool = False,
    stream: bool = False,
) -> requests.Response:
    if requests.get != _ORIGINAL_REQUESTS_GET:
        try:
            return requests.get(url, timeout=timeout, verify=verify, allow_redirects=allow_redirects)
        except TypeError:
            return requests.get(url, timeout=timeout, verify=verify)
    session = _get_remote_session()
    return session.get(url, timeout=timeout, verify=verify, allow_redirects=allow_redirects, stream=stream)


_ORIGINAL_HTTP_GET = _http_get


def _get_header_ci(headers: Any, name: str) -> Optional[str]:
    """Case-insensitive HTTP header lookup compatible with plain dicts and CaseInsensitiveDict."""
    if not headers:
        return None
    if hasattr(headers, 'get'):
        direct = headers.get(name)
        if direct is not None:
            return direct
    target = name.lower()
    if hasattr(headers, 'items'):
        for k, v in headers.items():
            if isinstance(k, str) and k.lower() == target:
                return v
    return None


def _decode_response_bytes(raw_bytes: bytes, response: requests.Response) -> str:
    """Decode response bytes without letting RFC 2616 ISO-8859-1 default corrupt UTF-8 subscriptions."""
    headers = getattr(response, 'headers', None) or {}
    content_type = _get_header_ci(headers, 'Content-Type') or ''
    has_explicit_charset = 'charset=' in str(content_type).lower()
    encoding = getattr(response, 'encoding', None)

    if has_explicit_charset and encoding:
        return raw_bytes.decode(encoding, errors='replace')
    try:
        return raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        fallback = encoding or getattr(response, 'apparent_encoding', None) or 'utf-8'
        return raw_bytes.decode(fallback, errors='replace')


def _read_bounded_response(response: requests.Response, max_bytes: int, is_streamed: bool) -> str:
    headers = getattr(response, 'headers', None) or {}
    content_length = _get_header_ci(headers, 'Content-Length')
    if content_length is not None:
        try:
            parsed_length = int(content_length)
        except (ValueError, TypeError):
            parsed_length = None
        if parsed_length is not None and parsed_length > max_bytes:
            close_fn = getattr(response, 'close', None)
            if callable(close_fn):
                close_fn()
            raise ResponseTooLargeError(f'远程订阅响应体积超过限制 ({max_bytes} 字节)')

    if is_streamed and hasattr(response, 'iter_content'):
        chunks: List[bytes] = []
        total = 0
        try:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ResponseTooLargeError(f'远程订阅响应体积超过限制 ({max_bytes} 字节)')
                chunks.append(chunk)
        finally:
            close_fn = getattr(response, 'close', None)
            if callable(close_fn):
                close_fn()
        raw_bytes = b''.join(chunks)
        return _decode_response_bytes(raw_bytes, response)

    text = response.text if isinstance(getattr(response, 'text', None), str) else ''
    if len(text.encode('utf-8')) > max_bytes:
        raise ResponseTooLargeError(f'远程订阅响应体积超过限制 ({max_bytes} 字节)')
    return text


def safe_fetch_url(
    url: str,
    timeout: Any = None,
    max_bytes: int = MAX_REMOTE_SUB_BYTES,
    max_redirects: int = MAX_REMOTE_REDIRECTS,
) -> Tuple[int, str]:
    """
    Fetch a remote HTTP/HTTPS URL safely:
    - Enforces SSRF protection on the initial URL and every 3xx redirect target.
    - Enforces TLS certificate verification by default (no silent downgrade on SSLError).
    - Enforces maximum response body size to prevent memory exhaustion.
    """
    active_timeout = timeout if timeout is not None else _get_request_timeout()
    verify = not is_truthy(os.environ.get('ALLOW_INSECURE_SUB_SSL', '0'))
    is_mocked = (requests.get != _ORIGINAL_REQUESTS_GET) or (_http_get is not _ORIGINAL_HTTP_GET)

    current_url = url
    for hop in range(max_redirects + 1):
        current_url = validate_remote_url(current_url, allow_unresolved_when_mocked=is_mocked)
        stream_mode = not is_mocked
        if _http_get is not _ORIGINAL_HTTP_GET:
            response = _http_get(current_url, timeout=active_timeout, verify=verify)
        else:
            response = _http_get(
                current_url,
                timeout=active_timeout,
                verify=verify,
                allow_redirects=False,
                stream=stream_mode,
            )

        status = getattr(response, 'status_code', 200)
        headers = getattr(response, 'headers', None) or {}
        location = _get_header_ci(headers, 'Location')
        if status in (301, 302, 303, 307, 308) and isinstance(location, str) and location.strip():
            close_fn = getattr(response, 'close', None)
            if callable(close_fn):
                close_fn()
            if hop >= max_redirects:
                raise requests.TooManyRedirects(f'重定向次数超过限制 ({max_redirects})')
            current_url = urllib.parse.urljoin(current_url, location.strip())
            continue

        body = _read_bounded_response(response, max_bytes=max_bytes, is_streamed=stream_mode)
        return status, body

    raise requests.TooManyRedirects(f'重定向次数超过限制 ({max_redirects})')


def _get_request_timeout() -> Any:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'request_timeout'):
        return view_mod.request_timeout
    return request_timeout


def is_private_or_loopback_ip(ip_str: str) -> bool:
    """Check if an IP string is loopback, private, or link-local."""
    ip_obj = _parse_ip_literal(ip_str)
    if ip_obj is None:
        return False
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        ip_obj = ip_obj.ipv4_mapped
    return ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local


def get_client_ip() -> str:
    """
    Resolve the client IP address securely.
    Never blindly trusts X-Real-IP unless reverse-proxy trust is configured (TRUSTED_PROXIES
    matching REMOTE_ADDR, or TRUSTED_PROXY_COUNT > 0) and ProxyFix has not already rewritten
    REMOTE_ADDR via X-Forwarded-For.
    """
    remote_addr = (getattr(request, 'remote_addr', None) or '').strip() or '127.0.0.1'
    if has_app_context() and not request.environ.get('sublink.proxy_fixed_for'):
        trusted_networks = current_app.config.get('TRUSTED_PROXY_NETWORKS') or []
        trusted_count = int(current_app.config.get('TRUSTED_PROXY_COUNT') or 0)
        is_trusted_proxy = False
        if trusted_networks:
            remote_ip = _parse_ip_literal(remote_addr)
            if isinstance(remote_ip, ipaddress.IPv6Address) and remote_ip.ipv4_mapped is not None:
                remote_ip = remote_ip.ipv4_mapped
            if remote_ip is not None and any(remote_ip in net for net in trusted_networks):
                is_trusted_proxy = True
        elif trusted_count > 0:
            is_trusted_proxy = True

        if is_trusted_proxy:
            x_real_ip = (request.environ.get('HTTP_X_REAL_IP') or '').strip()
            if x_real_ip and _parse_ip_literal(x_real_ip) is not None:
                return x_real_ip
    return remote_addr


def _emoji_cache_info():
    with _emoji_cache_lock:
        return _CacheInfo(_emoji_cache_hits, _emoji_cache_misses, EMOJI_CACHE_MAXSIZE, len(_emoji_pos_cache))


def _emoji_cache_clear() -> None:
    global _emoji_cache_hits, _emoji_cache_misses
    with _emoji_cache_lock:
        _emoji_pos_cache.clear()
        _emoji_fail_cache.clear()
        _emoji_cache_hits = 0
        _emoji_cache_misses = 0


def _record_emoji_fail(key: str) -> None:
    if EMOJI_FAIL_CACHE_TTL <= 0:
        return
    with _emoji_cache_lock:
        _emoji_fail_cache[key] = time.monotonic() + EMOJI_FAIL_CACHE_TTL
        _emoji_fail_cache.move_to_end(key)
        while len(_emoji_fail_cache) > EMOJI_FAIL_CACHE_MAXSIZE:
            _emoji_fail_cache.popitem(last=False)


def get_country_emoji(hostname: str) -> str:
    """
    Resolve hostname/IP (IPv4 & IPv6) and retrieve country emoji flag from ipwho.is over HTTPS.
    Caches valid flags in a bounded LRU cache; transient failures and local/private DNS hits
    both use a short negative TTL so repeated subscription generations avoid redundant lookups.
    """
    global _emoji_cache_hits, _emoji_cache_misses
    if not hostname or not str(hostname).strip():
        return ''

    key = str(hostname).strip()
    now = time.monotonic()
    with _emoji_cache_lock:
        if key in _emoji_pos_cache:
            _emoji_pos_cache.move_to_end(key)
            _emoji_cache_hits += 1
            return _emoji_pos_cache[key]
        fail_until = _emoji_fail_cache.get(key)
        if fail_until is not None:
            if now < fail_until:
                _emoji_cache_hits += 1
                return ''
            _emoji_fail_cache.pop(key, None)
        _emoji_cache_misses += 1

    try:
        ip = key.strip('[]')
        if not ip:
            return ''
        lower_ip = ip.lower().rstrip('.')
        if lower_ip == 'localhost' or lower_ip.endswith('.localhost') or lower_ip.endswith('.local'):
            _record_emoji_fail(key)
            return ''
        parsed_ip = _parse_ip_literal(ip)
        if parsed_ip is not None:
            if _is_forbidden_ip(parsed_ip):
                _record_emoji_fail(key)
                return ''
            target_ip = str(parsed_ip)
        else:
            addr_infos = socket.getaddrinfo(ip, None, type=socket.SOCK_STREAM)
            if not addr_infos:
                _record_emoji_fail(key)
                return ''
            target_ip = ''
            for info in addr_infos:
                resolved_ip = _parse_ip_literal(info[4][0])
                if resolved_ip is None or _is_forbidden_ip(resolved_ip):
                    _record_emoji_fail(key)
                    return ''
                if not target_ip:
                    target_ip = str(resolved_ip)
            if not target_ip:
                _record_emoji_fail(key)
                return ''
        safe_ip = urllib.parse.quote(target_ip, safe='')
        url = f'https://ipwho.is/{safe_ip}'
        if requests.get != _ORIGINAL_REQUESTS_GET:
            response = requests.get(url, timeout=_get_request_timeout())
        else:
            response = _get_remote_session().get(url, timeout=_get_request_timeout(), allow_redirects=False)
        if response.status_code == 200:
            js = response.json()
            flag = js.get('flag') or {}
            emoji = flag.get('emoji')
            if emoji:
                with _emoji_cache_lock:
                    _emoji_pos_cache[key] = emoji
                    _emoji_pos_cache.move_to_end(key)
                    while len(_emoji_pos_cache) > EMOJI_CACHE_MAXSIZE:
                        _emoji_pos_cache.popitem(last=False)
                    _emoji_fail_cache.pop(key, None)
                return emoji
    except Exception as e:
        logger.warning('获取入口国旗失败: %s 错误信息: %s', key, e)

    _record_emoji_fail(key)
    return ''


get_country_emoji.cache_info = _emoji_cache_info  # type: ignore[attr-defined]
get_country_emoji.cache_clear = _emoji_cache_clear  # type: ignore[attr-defined]


def _max_login_log_rows() -> int:
    raw = (os.environ.get('MAX_LOGIN_LOG_ROWS') or '').strip()
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return DEFAULT_MAX_LOGIN_LOG_ROWS


def _lookup_login_geoip(ip_address: str) -> str:
    try:
        params = {
            'ip': ip_address,
            'json': 'true'
        }
        url = 'https://whois.pconline.com.cn/ipJson.jsp'
        if requests.get != _ORIGINAL_REQUESTS_GET:
            res = requests.get(url, params=params, timeout=(0.5, 1.0))
        else:
            res = _get_remote_session().get(url, params=params, timeout=(0.5, 1.0), allow_redirects=False)
        if res.status_code == 200 and res.text:
            js = json.loads(res.text)
            return str(js.get('addr') or '')
    except Exception as e:
        logger.warning('获取IP归属地失败 (降级记录): %s', e)
    return ''


_GEOIP_BACKFILL_MAX_WORKERS = 2
_geoip_backfill_sem = threading.BoundedSemaphore(_GEOIP_BACKFILL_MAX_WORKERS)


def _backfill_login_geoip_async(app_obj: Any, login_id: int, ip_address: str) -> None:
    try:
        address = _lookup_login_geoip(ip_address)
        if not address:
            return
        with app_obj.app_context():
            try:
                row = Login.query.filter_by(id=login_id).first()
                if row and not row.address:
                    row.address = address
                    db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.warning('异步回填登录归属地失败: %s', e)
    except Exception as e:
        logger.warning('异步回填登录归属地异常: %s', e)
    finally:
        _geoip_backfill_sem.release()


def save_ip_address() -> None:
    """Record login IP and optional geographical location in database, trimming old logs."""
    try:
        ip_address = get_client_ip()
        geoip_enabled = is_truthy(os.environ.get('ENABLE_LOGIN_GEOIP', '1'))
        should_lookup = geoip_enabled and not is_private_or_loopback_ip(ip_address)
        use_async = False
        app_obj = None
        if (
            should_lookup
            and has_app_context()
            and not current_app.config.get('TESTING')
            and requests.get == _ORIGINAL_REQUESTS_GET
        ):
            uri = str(current_app.config.get('SQLALCHEMY_DATABASE_URI') or '')
            if _is_file_backed_sqlite_uri(uri):
                use_async = True
                app_obj = current_app._get_current_object()

        address = ''
        if should_lookup and not use_async:
            address = _lookup_login_geoip(ip_address)

        timer = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        login = Login(ip=ip_address, address=address, time=timer)
        login_id: Optional[int] = None
        try:
            db.session.add(login)
            db.session.flush()
            login_id = login.id
            max_rows = _max_login_log_rows()
            cutoff = (
                db.session.query(Login.id)
                .order_by(Login.id.desc())
                .offset(max_rows)
                .limit(1)
                .scalar()
            )
            if cutoff is not None:
                Login.query.filter(Login.id <= cutoff).delete(synchronize_session=False)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.warning('保存登录记录失败: %s', e)
            return

        if use_async and app_obj is not None and login_id is not None:
            if _geoip_backfill_sem.acquire(blocking=False):
                try:
                    threading.Thread(
                        target=_backfill_login_geoip_async,
                        args=(app_obj, login_id, ip_address),
                        daemon=True,
                        name=f'geoip-{login_id}',
                    ).start()
                except Exception as e:
                    _geoip_backfill_sem.release()
                    logger.warning('启动异步归属地回填线程失败: %s', e)
    except Exception as e:
        logger.warning('save_ip_address 异常: %s', e)


def _rewrite_remote_node(node: str, host: str) -> str:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'rewrite_remote_node') and view_mod.rewrite_remote_node is not rewrite_remote_node:
        return view_mod.rewrite_remote_node(node, host)
    return rewrite_remote_node(node, host)


def _decode_base64_if(text: str) -> str:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'decode_base64_if') and view_mod.decode_base64_if is not decode_base64_if:
        return view_mod.decode_base64_if(text)
    return decode_base64_if(text)


def fetch_remote_sub(url: str, use_cache: bool = True) -> List[str]:
    """
    Fetch and decode remote subscription nodes, caching raw lines and applying
    current runtime rewrite rules on every retrieval so config changes take effect immediately.
    """
    is_testing = requests.get != _ORIGINAL_REQUESTS_GET
    host = get_remote_sub_host(url)

    if use_cache and not is_testing:
        cached_raw = _cache_get(url, allow_stale=False)
        if cached_raw is not None:
            return [_rewrite_remote_node(line, host) for line in cached_raw]

    try:
        status_code, body = safe_fetch_url(url, timeout=_get_request_timeout())
        if status_code >= 400:
            raise requests.HTTPError(f'HTTP {status_code}')
    except (SSRFError, ResponseTooLargeError) as sec_err:
        logger.warning('远程订阅被安全策略拦截: %s 错误信息: %s', redact_uri_credentials(url), sec_err)
        return []
    except requests.RequestException as e:
        logger.warning('获取远程订阅失败: %s 错误信息: %s', redact_uri_credentials(url), e)
        stale_raw = _cache_get(url, allow_stale=True)
        if stale_raw is not None:
            logger.info('使用过期缓存兜底返回: %s', redact_uri_credentials(url))
            return [_rewrite_remote_node(line, host) for line in stale_raw]
        return []

    text = _decode_base64_if(body)
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    valid_lines = [
        line for line in raw_lines
        if is_valid_node_uri(line) and get_proxy_type(line) in rewritable_node_types
    ]
    if raw_lines and not valid_lines:
        stripped_text = text.lstrip()
        if stripped_text.startswith('{') and '"outbounds"' in stripped_text:
            logger.warning(
                '远程订阅返回疑似 sing-box JSON 而非节点 URI 列表，已忽略: %s',
                redact_uri_credentials(url),
            )
        elif any(line.startswith('proxies:') for line in raw_lines[:50]):
            logger.warning(
                '远程订阅返回疑似 Clash YAML 而非节点 URI 列表，已忽略: %s',
                redact_uri_credentials(url),
            )

    if not is_testing:
        _cache_put(url, valid_lines)

    return [_rewrite_remote_node(line, host) for line in valid_lines]
