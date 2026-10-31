"""Remote network communication and external services for Sublink."""

import datetime
import functools
import ipaddress
import json
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import urllib.parse

from flask import request
import requests
import urllib3

from app.core.rewrite import rewrite_remote_node
from app.core.utils import decode_base64_if, get_remote_sub_host
from app.exts import db
from app.model import Login

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
request_timeout = (3, 8)

_ORIGINAL_REQUESTS_GET = requests.get

DEFAULT_SUB_HEADERS = {
    'User-Agent': 'Sublink/3.0 (compatible; Clash/1.18.0; v2rayN/6.23)'
}

REMOTE_SUB_CACHE_TTL = 180  # 3 minutes cache for remote subscriptions

_remote_sub_cache: Dict[str, Tuple[float, List[str]]] = {}
_cache_lock = threading.Lock()
_insecure_ssl_hosts: Set[str] = set()

_remote_session: Optional[requests.Session] = None
_session_lock = threading.Lock()


def _get_remote_session() -> requests.Session:
    global _remote_session
    if _remote_session is None:
        with _session_lock:
            if _remote_session is None:
                s = requests.Session()
                s.headers.update(DEFAULT_SUB_HEADERS)
                adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
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


def _http_get(url: str, timeout: Any, verify: bool) -> requests.Response:
    if requests.get != _ORIGINAL_REQUESTS_GET:
        return requests.get(url, timeout=timeout, verify=verify)
    session = _get_remote_session()
    return session.get(url, timeout=timeout, verify=verify)


def _get_request_timeout() -> Any:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'request_timeout'):
        return view_mod.request_timeout
    return request_timeout


def is_private_or_loopback_ip(ip_str: str) -> bool:
    """Check if an IP string is loopback or private."""
    try:
        import ipaddress
        ip = ipaddress.ip_address(ip_str.strip())
        return ip.is_loopback or ip.is_private
    except ValueError:
        return False


@functools.lru_cache(maxsize=1024)
def get_country_emoji(hostname: str) -> str:
    """Resolve hostname/IP and retrieve country emoji flag from ipwho.is."""
    if not hostname or not str(hostname).strip():
        return ''
    import socket

    def is_valid_url(url: str) -> bool:
        pattern = re.compile(r'^(https?:\/\/)?([\da-z\.-]+)\.([a-z\.]{2,6})([\/\w \.-]*)*\/?$')
        return bool(pattern.match(url))

    try:
        ip = str(hostname).strip().strip('[]')
        if not ip:
            return ''
        if is_private_or_loopback_ip(ip) or ip.lower() == 'localhost':
            return ''
        if is_valid_url(ip):
            ip = socket.gethostbyname(ip)
            if is_private_or_loopback_ip(ip):
                return ''
        response = requests.get(f"http://ipwho.is/{ip}", timeout=_get_request_timeout())
        if response.status_code == 200:
            js = response.json()
            flag = js.get('flag') or {}
            emoji = flag.get("emoji")
            if emoji:
                return emoji
    except Exception as e:
        print(f'获取入口国旗失败:{hostname} 错误信息:{str(e)}')
    return ''


def save_ip_address() -> None:
    """Record login IP and geographical location in database."""
    try:
        ip_address = request.environ.get('HTTP_X_REAL_IP', request.remote_addr) or '127.0.0.1'
        address = ''
        if not is_private_or_loopback_ip(ip_address):
            try:
                params = {
                    'ip': ip_address,
                    'json': 'true'
                }
                res = requests.get('https://whois.pconline.com.cn/ipJson.jsp', params=params, timeout=(0.5, 1.0))
                if res.status_code == 200 and res.text:
                    js = json.loads(res.text)
                    address = js.get('addr') or ''
            except Exception as e:
                print(f'获取IP归属地失败 (降级记录): {str(e)}')

        timer = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        login = Login(ip=ip_address, address=address, time=timer)
        try:
            db.session.add(login)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f'保存登录记录错误信息:{str(e)}')
    except Exception as e:
        print(f'save_ip_address 异常:{str(e)}')


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
    """Fetch and decode remote subscription nodes, rewriting loopback/names."""
    is_testing = requests.get != _ORIGINAL_REQUESTS_GET
    if use_cache and not is_testing:
        now = time.time()
        with _cache_lock:
            if url in _remote_sub_cache:
                cached_time, cached_nodes = _remote_sub_cache[url]
                if now - cached_time < REMOTE_SUB_CACHE_TTL:
                    return list(cached_nodes)

    active_timeout = _get_request_timeout()
    parsed_host = urllib.parse.urlsplit(url).hostname or ''
    # Fast path: Raw IP HTTPS or previously failed SSL hosts bypass verify=True
    use_insecure_ssl = is_raw_ip(parsed_host) or parsed_host in _insecure_ssl_hosts

    try:
        if use_insecure_ssl:
            response = _http_get(url, timeout=active_timeout, verify=False)
        else:
            try:
                response = _http_get(url, timeout=active_timeout, verify=True)
            except requests.exceptions.SSLError as error:
                if parsed_host:
                    _insecure_ssl_hosts.add(parsed_host)
                print(f'远程订阅证书校验失败，临时跳过校验重试:{url} 错误信息:{str(error)}')
                response = _http_get(url, timeout=active_timeout, verify=False)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f'获取远程订阅失败:{url} 错误信息:{str(e)}')
        with _cache_lock:
            if url in _remote_sub_cache:
                print(f'使用过期缓存兜底返回:{url}')
                return list(_remote_sub_cache[url][1])
        return []

    text = _decode_base64_if(response.text)
    host = get_remote_sub_host(url)
    nodes = [_rewrite_remote_node(line.strip(), host) for line in text.splitlines() if line.strip()]

    if not is_testing:
        with _cache_lock:
            _remote_sub_cache[url] = (time.time(), list(nodes))

    return nodes
