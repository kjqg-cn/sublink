"""Custom rewrite engine for remote nodes and names."""

import ipaddress
import json
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
    parse_server_port,
    rewritable_node_types,
)

hk_name_prefix = '🇭🇰【香港'

# Note: '-' prefixes must be fully preserved as requested
node_name_rewrite_rules = [
    (('-SG',), '🇸🇬【新加坡'),
    (('-TYO',), '🇯🇵【东京'),
    (('-LAX',), '🇺🇸【洛杉矶'),
    (('-HOU',), '🇺🇸【休斯顿'),
    (('-LON', '-UK'), '🇬🇧【伦敦'),
    (('-DE',), '🇩🇪【莱比锡'),
]


def _get_rewrite_rules() -> Any:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'node_name_rewrite_rules'):
        return view_mod.node_name_rewrite_rules
    return node_name_rewrite_rules


def _get_hk_prefix() -> str:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'hk_name_prefix'):
        return view_mod.hk_name_prefix
    return hk_name_prefix


def rewrite_info_host_port(info: str, host: str, port: str = '443') -> Tuple[str, bool]:
    """Rewrite 127.0.0.1 host and port in userinfo@host:port format."""
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
    return prefix + get_host_port(host, port), True


def rewrite_node_url(node: str, info: str) -> str:
    """Reconstruct node URL with new netloc info."""
    parse = urllib.parse.urlparse(node)
    return urllib.parse.urlunparse((parse.scheme, info, '', '', parse.query, parse.fragment))


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
    parts = decoded_info.split(':', 5)
    if len(parts) < 6:
        return node
    parse2 = urllib.parse.urlparse(parts[5])
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
    parts[5] = urllib.parse.urlunparse(
        (parse2.scheme, parse2.netloc, parse2.path, parse2.params, urllib.parse.urlencode(new_pairs), parse2.fragment)
    )
    return f"{parse.scheme}://{encode_base64(':'.join(parts), urlsafe=True)}"


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
            info = decode_base64_if(parse.netloc)
            if '@' in info:
                _, _, server_port = info.rpartition('@')
            else:
                server_port = info
            server, _ = parse_server_port(server_port)
            return server
        if proxy_type == 'ssr':
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            decoded_info = decode_base64_if(info)
            parts = decoded_info.split(':', 5)
            return parts[0] if parts else ''
        info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
        decoded = decode_base64_if(info)
        if '@' in decoded:
            _, _, host_port = decoded.rpartition('@')
        else:
            host_port = decoded
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


def rewrite_node_ipv6(node: str) -> str:
    """Rewrite node name if the node connects to an IPv6 server."""
    if not node:
        return node
    server = get_node_server(node)
    if not is_ipv6_node_server(server):
        return node
    try:
        proxy_type = get_proxy_type(node)
        parse = urllib.parse.urlparse(node)
        if proxy_type == 'vmess':
            return rewrite_vmess_name(node, parse, transformer=rewrite_node_name_ipv6_text)
        if proxy_type == 'ssr':
            return rewrite_ssr_name(node, parse, transformer=rewrite_node_name_ipv6_text)
        if proxy_type in rewritable_node_types:
            return rewrite_fragment_name(node, parse, transformer=rewrite_node_name_ipv6_text)
    except Exception as e:
        print(f'IPv6节点名称重写失败:{node} 错误信息:{str(e)}')
    return node


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
        print(f'节点名称重写失败:{node} 错误信息:{str(e)}')
    return node


def rewrite_loopback_node(node: str, host: str) -> str:
    """Rewrite 127.0.0.1 node addresses to subscription host."""
    if not node or not host:
        return node
    try:
        proxy_type = get_proxy_type(node)
        parse = urllib.parse.urlparse(node)
        if proxy_type == 'vmess' and parse.query == '':
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            proxy = json.loads(decode_base64_if(info))
            if str(proxy.get('add')).strip('[]') != '127.0.0.1':
                return node
            proxy['add'] = host
            proxy['port'] = '443'
            return f"{parse.scheme}://{encode_base64(json.dumps(proxy, ensure_ascii=False, separators=(',', ':')))}"
        if proxy_type == 'vmess':
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            rewritten_info, changed = rewrite_info_host_port(decode_base64_if(info), host)
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
            parts[1] = '443'
            return f"{parse.scheme}://{encode_base64(':'.join(parts), urlsafe=True)}"
        if proxy_type == 'ss':
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            decoded = decode_base64_if(info)
            if '@' not in decoded:
                return node
            userinfo, _, host_port = decoded.rpartition('@')
            if ':' not in host_port:
                return node
            old_host, _, _ = host_port.rpartition(':')
            if old_host.strip('[]') != '127.0.0.1':
                return node
            new_host_port = get_host_port(host, '443')
            encoded_userinfo = encode_base64(userinfo, urlsafe=True)
            new_netloc = f"{encoded_userinfo}@{new_host_port}"
            return urllib.parse.urlunparse((parse.scheme, new_netloc, '', '', parse.query, parse.fragment))
        if proxy_type in rewritable_node_types:
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            rewritten_info, changed = rewrite_info_host_port(decode_base64_if(info), host)
            if changed:
                return rewrite_node_url(node, rewritten_info)
    except Exception as e:
        print(f'127.0.0.1节点重写失败:{node} 错误信息:{str(e)}')
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
