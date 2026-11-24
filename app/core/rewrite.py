"""Custom rewrite engine for remote nodes and names."""

import ipaddress
import json
import logging
import os
import re
import sys
import urllib.parse
from typing import Any, List, Optional, Tuple

from app.config_manager import get_runtime_config
from app.core.utils import (
    decode_base64_if,
    encode_base64,
    get_host_port,
    get_proxy_type,
    if_ipv6_address,
    parse_server_port,
    redact_uri_credentials,
    rewritable_node_types,
)

logger = logging.getLogger(__name__)

hk_name_prefix = '🇭🇰【香港'
_DEFAULT_HK_PREFIX = hk_name_prefix

# Note: '-' prefixes must be fully preserved as requested
node_name_rewrite_rules = [
    (('-SG',), '🇸🇬【新加坡'),
    (('-TYO',), '🇯🇵【东京'),
    (('-LAX',), '🇺🇸【洛杉矶'),
    (('-HOU',), '🇺🇸【休斯顿'),
    (('-LON', '-UK'), '🇬🇧【伦敦'),
    (('-DE',), '🇩🇪【莱比锡'),
]
_DEFAULT_REWRITE_RULES = node_name_rewrite_rules


def _get_loopback_port() -> str:
    raw = (os.environ.get('CUSTOM_LOOPBACK_PORT') or '').strip()
    if raw.isdigit() and 1 <= int(raw) <= 65535:
        return str(int(raw))
    return '443'


def _get_rewrite_rules() -> Any:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'node_name_rewrite_rules'):
        view_rules = view_mod.node_name_rewrite_rules
        if view_rules is not _DEFAULT_REWRITE_RULES:
            return view_rules
    if node_name_rewrite_rules is not _DEFAULT_REWRITE_RULES:
        return node_name_rewrite_rules
    env_rules = (os.environ.get('CUSTOM_NAME_REWRITE_RULES') or '').strip()
    if env_rules:
        try:
            loaded = json.loads(env_rules)
            if isinstance(loaded, list):
                parsed = []
                for item in loaded:
                    if (
                        isinstance(item, (list, tuple))
                        and len(item) == 2
                        and isinstance(item[0], (list, tuple))
                        and isinstance(item[1], str)
                    ):
                        kws = tuple(str(k) for k in item[0] if str(k))
                        if kws:
                            parsed.append((kws, item[1]))
                if parsed:
                    return parsed
        except Exception as exc:
            logger.warning('CUSTOM_NAME_REWRITE_RULES 解析失败，已回退默认规则: %s', exc)
    return node_name_rewrite_rules


def _get_hk_prefix() -> str:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'hk_name_prefix'):
        view_prefix = view_mod.hk_name_prefix
        if view_prefix != _DEFAULT_HK_PREFIX:
            return view_prefix
    if hk_name_prefix != _DEFAULT_HK_PREFIX:
        return hk_name_prefix
    env_prefix = os.environ.get('CUSTOM_HK_PREFIX')
    if env_prefix:
        return env_prefix
    return hk_name_prefix


def rewrite_info_host_port(info: str, host: str, port: Optional[str] = None) -> Tuple[str, bool]:
    """Rewrite 127.0.0.1 host and port in userinfo@host:port format."""
    target_port = port if port is not None else _get_loopback_port()
    prefix = ''
    host_port = info
    if '@' in info:
        prefix, host_port = info.rsplit('@', 1)
        prefix += '@'
    if ':' not in host_port:
        return info, False
    old_host, _, _ = host_port.rpartition(':')
    if old_host.strip('[]') != '127.0.0.1':
        return info, False
    return prefix + get_host_port(host, target_port), True


def rewrite_node_url(node: str, info: str) -> str:
    """Reconstruct node URL with new netloc info."""
    parse = urllib.parse.urlparse(node)
    keep_path = parse.path if (parse.netloc and parse.path not in ('', '/')) else ''
    return urllib.parse.urlunparse((parse.scheme, info, keep_path, '', parse.query, parse.fragment))


def rewrite_node_name_text(name: str, host: str = '') -> str:
    """
    Rewrite node name prefix based on region keywords.
    If target subscription host is IPv6, also rewrites carrier/line indicator to IPv6.
    """
    prefix = _get_hk_prefix()
    new_name = name
    if name and name.startswith(prefix):
        name_upper = name.upper()
        for keywords, target_prefix in _get_rewrite_rules():
            if any(keyword.upper() in name_upper for keyword in keywords):
                new_name = target_prefix + name[len(prefix):]
                break
    if host and is_ipv6_node_server(host):
        new_name = rewrite_node_name_ipv6_text(new_name)
    return new_name


def rewrite_query_name(parse: urllib.parse.ParseResult, key: str, transformer: Any = None) -> Optional[str]:
    """Rewrite name parameter in URL query string."""
    transform_fn = transformer or rewrite_node_name_text
    pairs = urllib.parse.parse_qsl(parse.query, keep_blank_values=True)
    new_pairs = []
    changed = False
    for item_key, item_value in pairs:
        if item_key == key:
            new_value = transform_fn(item_value)
            changed = changed or new_value != item_value
            item_value = new_value
        new_pairs.append((item_key, item_value))
    if not changed:
        return None
    return urllib.parse.urlencode(new_pairs)


def rewrite_fragment_name(node: str, parse: urllib.parse.ParseResult, transformer: Any = None) -> str:
    """Rewrite node name in URL fragment (#name)."""
    transform_fn = transformer or rewrite_node_name_text
    name = urllib.parse.unquote(parse.fragment)
    new_name = transform_fn(name)
    if new_name == name:
        return node
    return urllib.parse.urlunparse(
        (parse.scheme, parse.netloc, parse.path, parse.params, parse.query, urllib.parse.quote(new_name, safe=''))
    )


def rewrite_vmess_name(node: str, parse: urllib.parse.ParseResult, transformer: Any = None) -> str:
    """Rewrite VMess node name in either JSON body or query remarks."""
    transform_fn = transformer or rewrite_node_name_text
    if parse.query == '':
        info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
        proxy = json.loads(decode_base64_if(info))
        name = str(proxy.get('ps') or '')
        new_name = transform_fn(name)
        if new_name == name:
            return node
        proxy['ps'] = new_name
        return f"{parse.scheme}://{encode_base64(json.dumps(proxy, ensure_ascii=False, separators=(',', ':')))}"
    new_query = rewrite_query_name(parse, 'remarks', transformer=transform_fn)
    if new_query is None:
        return node
    return urllib.parse.urlunparse(
        (parse.scheme, parse.netloc, parse.path, parse.params, new_query, parse.fragment)
    )


def rewrite_ssr_name(node: str, parse: urllib.parse.ParseResult, transformer: Any = None) -> str:
    """Rewrite SSR node remarks parameter."""
    transform_fn = transformer or rewrite_node_name_text
    info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
    decoded_info = decode_base64_if(info)
    is_ipv6 = decoded_info.startswith('[') and ']:' in decoded_info
    if is_ipv6:
        server_bracket, _, rest = decoded_info.partition(']:')
        prefix = server_bracket + ']:'
        parts = rest.split(':', 4)
        if len(parts) < 5:
            return node
        target_idx = 4
    else:
        prefix = ''
        parts = decoded_info.split(':', 5)
        if len(parts) < 6:
            return node
        target_idx = 5

    parse2 = urllib.parse.urlparse(parts[target_idx])
    pairs = urllib.parse.parse_qsl(parse2.query, keep_blank_values=True)
    new_pairs = []
    changed = False
    for key, value in pairs:
        if key == 'remarks':
            name = decode_base64_if(value.replace(' ', '+'))
            new_name = transform_fn(name)
            if new_name != name:
                value = encode_base64(new_name)
                changed = True
        new_pairs.append((key, value))
    if not changed:
        return node
    parts[target_idx] = urllib.parse.urlunparse(
        (parse2.scheme, parse2.netloc, parse2.path, parse2.params, urllib.parse.urlencode(new_pairs), parse2.fragment)
    )
    new_decoded_info = prefix + ':'.join(parts)
    return f"{parse.scheme}://{encode_base64(new_decoded_info, urlsafe=True)}"


def is_ipv6_node_server(server: str) -> bool:
    """Check if node server is an IPv6 address or an explicit IPv6 domain."""
    if not server:
        return False
    host = server.strip('[]').split('%')[0].strip()
    try:
        ip = ipaddress.ip_address(host)
        return ip.version == 6
    except ValueError:
        pass
    lower_host = host.lower()
    return bool(re.search(r'(^|\.)v6\.|\.v6$|-v6\.|-ipv6\b|\bipv6\.', lower_host))


def get_node_server(node: str) -> str:
    """Extract server hostname/IP from node URL string."""
    if not node:
        return ''
    try:
        proxy_type = get_proxy_type(node)
        parse = urllib.parse.urlparse(node)
        if proxy_type == 'vmess':
            if parse.query == '':
                info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
                proxy = json.loads(decode_base64_if(info))
                return str(proxy.get('add') or '')
            pairs = urllib.parse.parse_qs(parse.query)
            if 'add' in pairs and pairs['add']:
                return pairs['add'][0]
            info = parse.netloc if '@' in parse.netloc else decode_base64_if(parse.netloc)
            if '@' in info:
                _, _, server_port = info.rpartition('@')
            else:
                server_port = info
            server, _ = parse_server_port(server_port)
            return server
        if proxy_type == 'ssr':
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            decoded_info = decode_base64_if(info)
            if decoded_info.startswith('[') and ']:' in decoded_info:
                server_part, _, _ = decoded_info[1:].partition(']:')
                return if_ipv6_address(server_part)
            parts = decoded_info.split(':', 5)
            return parts[0] if parts else ''
        if proxy_type == 'ss':
            info = parse.netloc or (parse.path if parse.path != '/' else '')
            if '@' in info:
                _, _, host_port = info.rpartition('@')
            else:
                decoded = decode_base64_if(info)
                host_port = decoded.rpartition('@')[2] if '@' in decoded else decoded
            server, _ = parse_server_port(host_port)
            return server
        info = parse.netloc or (parse.path if parse.path != '/' else '')
        if '@' in info:
            _, _, host_port = info.rpartition('@')
        else:
            decoded = decode_base64_if(info)
            host_port = decoded.rpartition('@')[2] if '@' in decoded else info
        server, _ = parse_server_port(host_port)
        return server
    except Exception:
        pass
    return ''


def rewrite_node_name_ipv6_text(name: str) -> str:
    """
    Rewrite node name for IPv6 nodes by updating line/carrier indicator to IPv6.
    - Pattern 1: 【City | Line】 -> 【City | IPv6】
    - Pattern 2: 【City】 -> 【City | IPv6】
    - Pattern 3: Regular text without bracket -> appends [IPv6]
    """
    if not name:
        return name
    if re.search(r'【.*?\|\s*[^】]+】', name):
        return re.sub(r'【(.*?)\s*\|\s*[^】]+】', r'【\1 | IPv6】', name, count=1)
    if re.search(r'【.*?】', name):
        return re.sub(r'【(.*?)】', r'【\1 | IPv6】', name, count=1)
    lower = name.lower()
    if 'ipv6' not in lower and not re.search(r'\bv6\b', lower):
        return f"{name} [IPv6]"
    return name


def rewrite_node_name(node: str, host: str = '') -> str:
    """Rewrite node name and flag for supported protocol types, applying IPv6 indicator if host is IPv6."""
    if not node:
        return node
    transformer = lambda n: rewrite_node_name_text(n, host=host)
    try:
        proxy_type = get_proxy_type(node)
        parse = urllib.parse.urlparse(node)
        if proxy_type == 'vmess':
            return rewrite_vmess_name(node, parse, transformer=transformer)
        if proxy_type == 'ssr':
            return rewrite_ssr_name(node, parse, transformer=transformer)
        if proxy_type in rewritable_node_types:
            return rewrite_fragment_name(node, parse, transformer=transformer)
    except Exception as e:
        logger.warning('节点名称重写失败: %s 错误信息: %s', redact_uri_credentials(node), e)
    return node


def rewrite_loopback_node(node: str, host: str) -> str:
    """Rewrite 127.0.0.1 node addresses to subscription host."""
    if not node or not host:
        return node
    target_port = _get_loopback_port()
    try:
        proxy_type = get_proxy_type(node)
        parse = urllib.parse.urlparse(node)
        if proxy_type == 'vmess' and parse.query == '':
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            proxy = json.loads(decode_base64_if(info))
            if str(proxy.get('add')).strip('[]') != '127.0.0.1':
                return node
            proxy['add'] = host
            proxy['port'] = target_port
            return f"{parse.scheme}://{encode_base64(json.dumps(proxy, ensure_ascii=False, separators=(',', ':')))}"
        if proxy_type == 'vmess':
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            if '@' in info:
                rewritten_info, changed = rewrite_info_host_port(info, host, target_port)
                if changed:
                    return rewrite_node_url(node, rewritten_info)
            else:
                rewritten_info, changed = rewrite_info_host_port(decode_base64_if(info), host, target_port)
                if changed:
                    return urllib.parse.urlunparse(
                        (parse.scheme, encode_base64(rewritten_info), '', '', parse.query, parse.fragment)
                    )
        if proxy_type == 'ssr':
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            decoded_info = decode_base64_if(info)
            parts = decoded_info.split(':', 5)
            if len(parts) < 6 or parts[0].strip('[]') != '127.0.0.1':
                return node
            ssr_host = f'[{host}]' if (':' in host and not host.startswith('[')) else host
            parts[0] = ssr_host
            parts[1] = target_port
            return f"{parse.scheme}://{encode_base64(':'.join(parts), urlsafe=True)}"
        if proxy_type == 'ss':
            info = parse.netloc or (parse.path if parse.path != '/' else '')
            if '@' in info:
                userinfo_raw, _, host_port = info.rpartition('@')
                userinfo_unquoted = urllib.parse.unquote(userinfo_raw)
                userinfo = userinfo_unquoted if ':' in userinfo_unquoted else decode_base64_if(userinfo_unquoted)
            else:
                decoded = decode_base64_if(info)
                if '@' not in decoded:
                    return node
                userinfo, _, host_port = decoded.rpartition('@')
            if ':' not in host_port:
                return node
            old_host, _, _ = host_port.rpartition(':')
            if old_host.strip('[]') != '127.0.0.1':
                return node
            new_host_port = get_host_port(host, target_port)
            encoded_userinfo = encode_base64(userinfo, urlsafe=True)
            new_netloc = f"{encoded_userinfo}@{new_host_port}"
            return urllib.parse.urlunparse((parse.scheme, new_netloc, '', '', parse.query, parse.fragment))
        if proxy_type in rewritable_node_types:
            info = parse.netloc or (parse.path if parse.path != '/' else '')
            if '@' not in info:
                decoded_candidate = decode_base64_if(info)
                if '@' in decoded_candidate:
                    info = decoded_candidate
            rewritten_info, changed = rewrite_info_host_port(info, host, target_port)
            if changed:
                return rewrite_node_url(node, rewritten_info)
    except Exception as e:
        logger.warning('127.0.0.1节点重写失败: %s 错误信息: %s', redact_uri_credentials(node), e)
    return node


def _rewrite_loopback_node(node: str, host: str) -> str:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'rewrite_loopback_node') and view_mod.rewrite_loopback_node is not rewrite_loopback_node:
        return view_mod.rewrite_loopback_node(node, host)
    return rewrite_loopback_node(node, host)


def _rewrite_node_name(node: str, host: str = '') -> str:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'rewrite_node_name') and view_mod.rewrite_node_name is not rewrite_node_name:
        try:
            return view_mod.rewrite_node_name(node, host)
        except TypeError:
            return view_mod.rewrite_node_name(node)
    return rewrite_node_name(node, host)


def rewrite_remote_node(node: str, host: str) -> str:
    """Master rewrite function applying loopback and node name rules if enabled."""
    if not node:
        return node
    cfg = get_runtime_config()
    if not cfg.get('custom'):
        return node
    if cfg.get('custom_loopback'):
        node = _rewrite_loopback_node(node, host)
    if cfg.get('custom_node_name'):
        node = _rewrite_node_name(node, host)
    return node
