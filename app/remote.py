"""Remote network communication and external services for Sublink."""

import datetime
import functools
import json
import re
import sys
from typing import Any, List

from flask import request
import requests
import urllib3

from app.core.rewrite import rewrite_remote_node
from app.core.utils import decode_base64_if, get_remote_sub_host
from app.exts import db
from app.model import Login

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
request_timeout = (3, 8)


def _get_request_timeout() -> Any:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'request_timeout'):
        return view_mod.request_timeout
    return request_timeout


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
        if is_valid_url(ip):
            ip = socket.gethostbyname(ip)
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
        try:
            params = {
                'ip': ip_address,
                'json': 'true'
            }
            res = requests.get('https://whois.pconline.com.cn/ipJson.jsp', params=params, timeout=(2, 3))
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


def fetch_remote_sub(url: str) -> List[str]:
    """Fetch and decode remote subscription nodes, rewriting loopback/names."""
    active_timeout = _get_request_timeout()
    try:
        try:
            response = requests.get(url, timeout=active_timeout)
        except requests.exceptions.SSLError as error:
            print(f'远程订阅证书校验失败，临时跳过校验重试:{url} 错误信息:{str(error)}')
            response = requests.get(url, timeout=active_timeout, verify=False)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f'获取远程订阅失败:{url} 错误信息:{str(e)}')
        return []

    text = _decode_base64_if(response.text)
    host = get_remote_sub_host(url)
    return [_rewrite_remote_node(line.strip(), host) for line in text.splitlines() if line.strip()]
