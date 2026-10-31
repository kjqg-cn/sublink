"""Client subscription configuration generators for Sublink."""

import base64
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from app.core.parsers import NodeParse
from app.core.utils import get_proxy_type, remote_sub_types

singbox_node_types = ('vless', 'vmess', 'ss', 'trojan', 'hysteria', 'hy2', 'hysteria2')


def get_app_path() -> str:
    """Retrieve active app path, honoring monkeypatched app.view.path."""
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'path'):
        return view_mod.path
    from app.config_manager import path
    return path


def _fetch_remote_sub(url: str) -> List[str]:
    """Fetch remote subscription, respecting any monkeypatch on app.view.fetch_remote_sub."""
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'fetch_remote_sub'):
        return view_mod.fetch_remote_sub(url)
    from app.remote import fetch_remote_sub
    return fetch_remote_sub(url)


def _get_node_parse(proxy_str: str = '') -> Any:
    """Instantiate NodeParse, respecting any monkeypatch on app.view.NodeParse."""
    view_mod = sys.modules.get('app.view')
    cls = getattr(view_mod, 'NodeParse', NodeParse) if view_mod else NodeParse
    return cls(proxy_str)


def expand_node_list(subs: Any) -> List[str]:
    """Expand subscription objects or strings into a flat list of node strings."""
    raw_nodes = []
    for sub in subs:
        node_str = (sub.node if hasattr(sub, 'node') else str(sub)).strip()
        if not node_str:
            continue
        proxy_type = get_proxy_type(node_str)
        if proxy_type in remote_sub_types:
            raw_nodes.extend(_fetch_remote_sub(node_str))
        else:
            raw_nodes.append(node_str)
    return raw_nodes


def parse_clash_node(node: str) -> Optional[Dict[str, Any]]:
    """Parse node into Clash proxy dictionary. Returns None if unsupported."""
    proxy_type = get_proxy_type(node)
    proxy_str = node.strip()
    if not proxy_str:
        return None

    node_parse = _get_node_parse(proxy_str)
    if proxy_type == 'vless':
        return node_parse.vless()
    if proxy_type == 'vmess':
        return node_parse.vmess()
    if proxy_type == 'ss':
        return node_parse.ss()
    if proxy_type == 'ssr':
        return node_parse.ssr()
    if proxy_type == 'trojan':
        return node_parse.trojan()
    if proxy_type == 'hysteria':
        return node_parse.hysteria()
    if proxy_type in ('hy2', 'hysteria2'):
        return node_parse.hysteria2()
    return None


def _parse_clash_node(node: str) -> Optional[Dict[str, Any]]:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'parse_clash_node') and view_mod.parse_clash_node is not parse_clash_node:
        return view_mod.parse_clash_node(node)
    return parse_clash_node(node)


def get_unique_proxy_name(name: Any, used_names: Set[str], index: int, counts: Optional[Dict[str, int]] = None) -> str:
    """Generate a unique name for a Clash proxy."""
    base = str(name or '').strip() or f'node-{index}'
    if base not in used_names:
        used_names.add(base)
        if counts is not None:
            counts[base] = 2
        return base

    suffix = counts.get(base, 2) if counts is not None else 2
    target = f'{base} ({suffix})'
    while target in used_names:
        suffix += 1
        target = f'{base} ({suffix})'
    if counts is not None:
        counts[base] = suffix + 1
    used_names.add(target)
    return target


def clash_encode(subs: Any) -> str:
    """Generate Clash subscription YAML configuration."""
    clash_config = {
        'proxies': [],
        'proxy-groups': []
    }
    proxy_name_list = []
    used_names: Set[str] = set()
    counts: Dict[str, int] = {}

    raw_nodes = expand_node_list(subs)
    for index, raw_node in enumerate(raw_nodes, 1):
        try:
            proxy = _parse_clash_node(raw_node)
            if proxy:
                name = get_unique_proxy_name(proxy.get('name'), used_names, index, counts)
                proxy['name'] = name
                clash_config['proxies'].append(proxy)
                proxy_name_list.append(name)
        except Exception as e:
            print(f'clash节点解析失败:{raw_node} 错误信息:{str(e)}')

    config_file = os.path.join(get_app_path(), 'db', 'clash.yaml')
    with open(config_file, 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file) or {}

    data['proxies'] = clash_config['proxies']
    proxy_groups = data.get('proxy-groups') or []

    for proxy_group in proxy_groups:
        group_proxies = proxy_group.get('proxies', [])
        if 'auto' in group_proxies:
            group_proxies.remove('auto')
            for name in proxy_name_list:
                group_proxies.append(name)

    return yaml.dump(data, sort_keys=False, allow_unicode=True)


def parse_surge_node(node: str) -> Optional[Tuple[str, str]]:
    """
    Parse node into Surge proxy line string and proxy name.
    Returns (surge_proxy_line, proxy_name) or None if unsupported.
    """
    proxy_type = get_proxy_type(node)
    proxy_str = node.strip()
    if not proxy_str:
        return None

    node_parse = _get_node_parse(proxy_str)

    if proxy_type == 'ss':
        proxy = node_parse.ss()
        name = proxy.get('name')
        line = (
            f"{name} = ss, {proxy.get('server')}, {proxy.get('port')}, "
            f"encrypt-method={proxy.get('cipher')}, password={proxy.get('password')}, "
            f"tfo={proxy.get('tfo')}, udp-relay={proxy.get('udp')}"
        )
        return line, name

    if proxy_type == 'vmess':
        proxy = node_parse.vmess()
        name = proxy.get('name')
        line = (
            f"{name} = vmess,{proxy.get('server')},{proxy.get('port')},username={proxy.get('uuid')},"
            f"tls={proxy.get('tls')},vmess-aead=true,skip-cert-verify={proxy.get('skip-cert-verify')},"
            f"tfo={proxy.get('tfo')},udp-relay={proxy.get('udp')}"
        )
        if proxy.get('network') == 'ws':
            ws_opts = proxy.get('ws-opts') or {}
            line += f",ws=true,ws-path={ws_opts.get('path', '/')},sni={proxy.get('server')}"
            headers = ws_opts.get('headers')
            if headers and isinstance(headers, dict) and headers.get('Host'):
                line += f",ws-headers=Host:{headers['Host']}"
        return line, name

    if proxy_type == 'trojan':
        proxy = node_parse.trojan()
        name = proxy.get('name')
        line = (
            f"{name} = trojan,{proxy.get('server')},{proxy.get('port')},password={proxy.get('password')},"
            f"skip-cert-verify={proxy.get('skip-cert-verify')},tfo={proxy.get('tfo')},udp-relay={proxy.get('udp')}"
        )
        if proxy.get('sni'):
            line += f",sni={proxy['sni']}"
        if proxy.get('network') == 'ws':
            ws_opts = proxy.get('ws-opts') or {}
            line += f",ws=true,ws-path={ws_opts.get('path', '/')}"
            headers = ws_opts.get('headers')
            if headers and isinstance(headers, dict) and headers.get('Host'):
                line += f",ws-headers=Host:{headers['Host']}"
        return line, name

    if proxy_type in ('hy2', 'hysteria2'):
        proxy = node_parse.hysteria2()
        name = proxy.get('name')
        line = (
            f"{name} = hysteria2,{proxy.get('server')},{proxy.get('port')},password={proxy.get('password')},"
            f"skip-cert-verify={proxy.get('skip-cert-verify')},udp-relay={proxy.get('udp')}"
        )
        if proxy.get('sni'):
            line += f",sni={proxy['sni']}"
        return line, name

    return None


def _parse_surge_node(node: str) -> Optional[Tuple[str, str]]:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'parse_surge_node') and view_mod.parse_surge_node is not parse_surge_node:
        return view_mod.parse_surge_node(node)
    return parse_surge_node(node)


def inject_surge_proxies(template_content: str, proxy_lines: List[str]) -> str:
    """Insert formatted proxy lines into the [Proxy] section of Surge configuration."""
    proxy_index = template_content.find('[Proxy]')
    if proxy_index == -1:
        print("Proxy section not found in the configuration file.")
        return template_content
    new_key_value = '\n'.join(proxy_lines)
    return (
        template_content[:proxy_index]
        + template_content[proxy_index:].replace('[Proxy]', f'[Proxy]\n{new_key_value}', 1)
    )


def _inject_surge_proxies(template_content: str, proxy_lines: List[str]) -> str:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'inject_surge_proxies') and view_mod.inject_surge_proxies is not inject_surge_proxies:
        return view_mod.inject_surge_proxies(template_content, proxy_lines)
    return inject_surge_proxies(template_content, proxy_lines)


def surge_encode(subs: Any) -> str:
    """Generate Surge subscription configuration."""
    proxy_lines = []
    proxy_name_list = []

    raw_nodes = expand_node_list(subs)
    for raw_node in raw_nodes:
        try:
            result = _parse_surge_node(raw_node)
            if result:
                line, name = result
                proxy_lines.append(line)
                proxy_name_list.append(name)
        except Exception as e:
            print(f'surge节点解析失败:{raw_node} 错误信息:{str(e)}')

    config_file = os.path.join(get_app_path(), 'db', 'surge.conf')
    with open(config_file, 'r', encoding='utf-8') as file:
        surge_template = file.read()

    config_text = _inject_surge_proxies(surge_template, proxy_lines)
    autos = ','.join(proxy_name_list) or 'DIRECT'
    return re.sub('auto', autos, config_text)


def v2ray_encode(subs: Any) -> str:
    """Generate V2Ray base64 subscription format."""
    raw_nodes = expand_node_list(subs)
    return base64.b64encode('\n'.join(raw_nodes).encode('utf-8')).decode('utf-8')


def validate_singbox_template(data: Any) -> None:
    """Validate Sing-Box template structure and mandatory fields."""
    if not isinstance(data, dict):
        raise ValueError('sing-box 配置根节点必须是 JSON 对象')
    outbounds = data.get('outbounds')
    if not isinstance(outbounds, list):
        raise ValueError('sing-box 配置必须包含 outbounds 数组')
    if not all(isinstance(item, dict) for item in outbounds):
        raise ValueError('sing-box outbounds 数组只能包含 JSON 对象')
    tags = [item.get('tag') for item in outbounds]
    if any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        raise ValueError('sing-box 每个出站都必须包含非空 tag')
    if len(tags) != len(set(tags)):
        raise ValueError('sing-box 出站 tag 不能重复')
    direct = next((item for item in outbounds if item.get('tag') == 'direct'), None)
    if not direct or direct.get('type') != 'direct':
        raise ValueError('sing-box 配置必须保留 tag 为 direct 的出站')
    if 'auto' in tags:
        raise ValueError('auto 是节点占位符，不能用作出站 tag')
    has_auto = any(
        isinstance(item.get('outbounds'), list) and 'auto' in item.get('outbounds')
        for item in outbounds
    )
    if not has_auto:
        raise ValueError('sing-box 策略组中必须保留 auto 节点占位符')


def load_singbox_template() -> Dict[str, Any]:
    """Load and validate Sing-Box template JSON file."""
    template_path = os.path.join(get_app_path(), 'db', 'sing-box.json')
    with open(template_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    validate_singbox_template(data)
    return data


def _load_singbox_template() -> Dict[str, Any]:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'load_singbox_template') and view_mod.load_singbox_template is not load_singbox_template:
        return view_mod.load_singbox_template()
    return load_singbox_template()


def get_unique_singbox_tag(name: Any, used_tags: Set[str], index: int) -> str:
    """Generate a unique tag for a Sing-Box outbound."""
    base = str(name or '').strip() or f'node-{index}'
    tag = base
    suffix = 2
    while tag in used_tags:
        tag = f'{base} ({suffix})'
        suffix += 1
    used_tags.add(tag)
    return tag


def get_singbox_tls(proxy: Dict[str, Any], required: bool = False) -> Optional[Dict[str, Any]]:
    """Generate Sing-Box TLS configuration object."""
    reality = proxy.get('reality-opts') or {}
    enabled = required or bool(proxy.get('tls')) or bool(reality)
    if not enabled:
        return None
    tls = {
        'enabled': True,
        'insecure': bool(proxy.get('skip-cert-verify')),
    }
    server_name = proxy.get('servername') or proxy.get('sni')
    if server_name:
        tls['server_name'] = server_name
    fingerprint = proxy.get('client-fingerprint')
    if fingerprint:
        tls['utls'] = {
            'enabled': True,
            'fingerprint': fingerprint,
        }
    public_key = reality.get('public-key')
    if public_key:
        tls['reality'] = {
            'enabled': True,
            'public_key': public_key,
            'short_id': reality.get('short-id', ''),
        }
    alpn = proxy.get('alpn')
    if alpn:
        tls['alpn'] = alpn if isinstance(alpn, list) else [item for item in str(alpn).split(',') if item]
    return tls


def get_singbox_transport(proxy: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Generate Sing-Box transport configuration object."""
    network = str(proxy.get('network') or '').lower()
    if network == 'ws':
        options = proxy.get('ws-opts') or {}
        transport = {
            'type': 'ws',
            'path': options.get('path') or '/',
        }
        headers = options.get('headers')
        if headers:
            transport['headers'] = headers
        return transport
    if network == 'grpc':
        options = proxy.get('grpc-opts') or {}
        return {
            'type': 'grpc',
            'service_name': options.get('grpc-service-name') or options.get('service-name') or '',
        }
    return None


def get_singbox_bandwidth(value: Any) -> Optional[int]:
    """Parse numeric bandwidth from string value."""
    if value in (None, ''):
        return None
    match = re.search(r'\d+(?:\.\d+)?', str(value))
    if not match:
        return None
    return int(float(match.group()))


def get_singbox_outbound(proxy_type: str, proxy: Dict[str, Any], tag: str) -> Dict[str, Any]:
    """Build Sing-Box outbound configuration dictionary for a given node."""
    server = proxy.get('server')
    port = proxy.get('port')
    if not server or port in (None, ''):
        raise ValueError('节点缺少服务器地址或端口')
    common = {
        'tag': tag,
        'server': server,
        'server_port': int(port),
    }
    if proxy.get('tfo'):
        common['tcp_fast_open'] = True

    if proxy_type == 'vless':
        outbound = {
            'type': 'vless',
            **common,
            'uuid': proxy.get('uuid'),
        }
        if proxy.get('flow'):
            outbound['flow'] = proxy.get('flow')
        tls = get_singbox_tls(proxy)
        transport = get_singbox_transport(proxy)
        if tls:
            outbound['tls'] = tls
        if transport:
            outbound['transport'] = transport
        return outbound

    if proxy_type == 'vmess':
        outbound = {
            'type': 'vmess',
            **common,
            'uuid': proxy.get('uuid'),
            'security': proxy.get('cipher') or 'auto',
            'alter_id': int(proxy.get('alterId') or 0),
        }
        tls = get_singbox_tls(proxy)
        transport = get_singbox_transport(proxy)
        if tls:
            outbound['tls'] = tls
        if transport:
            outbound['transport'] = transport
        return outbound

    if proxy_type == 'ss':
        outbound = {
            'type': 'shadowsocks',
            **common,
            'method': proxy.get('cipher'),
            'password': proxy.get('password'),
        }
        if proxy.get('plugin'):
            outbound['plugin'] = proxy.get('plugin')
        if proxy.get('plugin-opts'):
            outbound['plugin_opts'] = proxy.get('plugin-opts')
        return outbound

    if proxy_type == 'trojan':
        outbound = {
            'type': 'trojan',
            **common,
            'password': proxy.get('password'),
            'tls': get_singbox_tls(proxy, required=True),
        }
        transport = get_singbox_transport(proxy)
        if transport:
            outbound['transport'] = transport
        return outbound

    if proxy_type == 'hysteria':
        outbound = {
            'type': 'hysteria',
            **common,
            'tls': get_singbox_tls(proxy, required=True),
        }
        if proxy.get('auth_str'):
            outbound['auth_str'] = proxy.get('auth_str')
        if proxy.get('obfs'):
            outbound['obfs'] = proxy.get('obfs')
        up_mbps = get_singbox_bandwidth(proxy.get('up'))
        down_mbps = get_singbox_bandwidth(proxy.get('down'))
        if not up_mbps or not down_mbps:
            raise ValueError('Hysteria 节点缺少有效的上下行带宽')
        outbound['up_mbps'] = up_mbps
        outbound['down_mbps'] = down_mbps
        return outbound

    if proxy_type in ('hy2', 'hysteria2'):
        outbound = {
            'type': 'hysteria2',
            **common,
            'password': proxy.get('password') or proxy.get('auth'),
            'tls': get_singbox_tls(proxy, required=True),
        }
        up_mbps = get_singbox_bandwidth(proxy.get('up'))
        down_mbps = get_singbox_bandwidth(proxy.get('down'))
        if up_mbps is not None:
            outbound['up_mbps'] = up_mbps
        if down_mbps is not None:
            outbound['down_mbps'] = down_mbps
        if proxy.get('obfs') and proxy.get('obfs-password'):
            outbound['obfs'] = {
                'type': proxy.get('obfs'),
                'password': proxy.get('obfs-password'),
            }
        return outbound

    raise ValueError(f'不支持的节点类型: {proxy_type}')


def _get_singbox_outbound(proxy_type: str, proxy: Dict[str, Any], tag: str) -> Dict[str, Any]:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'get_singbox_outbound') and view_mod.get_singbox_outbound is not get_singbox_outbound:
        return view_mod.get_singbox_outbound(proxy_type, proxy, tag)
    return get_singbox_outbound(proxy_type, proxy, tag)


def parse_singbox_node(proxy_type: str, node: str) -> Dict[str, Any]:
    """Parse node for Sing-Box configuration."""
    node_parse = _get_node_parse(node)
    method = 'hysteria2' if proxy_type in ('hy2', 'hysteria2') else proxy_type
    return getattr(node_parse, method)()


def _parse_singbox_node(proxy_type: str, node: str) -> Dict[str, Any]:
    """Dispatch to app.view.parse_singbox_node if monkeypatched."""
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'parse_singbox_node') and view_mod.parse_singbox_node is not parse_singbox_node:
        return view_mod.parse_singbox_node(proxy_type, node)
    return parse_singbox_node(proxy_type, node)


def singbox_encode(subs: Any) -> str:
    """Generate Sing-Box subscription configuration with flat early-return control flow."""
    data = _load_singbox_template()
    template_outbounds = data['outbounds']
    used_tags = {
        outbound.get('tag')
        for outbound in template_outbounds
        if isinstance(outbound, dict) and outbound.get('tag')
    }
    node_outbounds = []
    node_tags = []

    raw_nodes = expand_node_list(subs)
    for raw_node in raw_nodes:
        proxy_type = get_proxy_type(raw_node)
        if proxy_type == 'ssr':
            print('sing-box跳过不支持的节点类型:ssr')
            continue
        if proxy_type not in singbox_node_types:
            print(f'sing-box跳过不支持的节点类型:{proxy_type}')
            continue
        try:
            proxy = _parse_singbox_node(proxy_type, raw_node)
            tag = get_unique_singbox_tag(proxy.get('name'), used_tags, len(node_tags) + 1)
            node_outbounds.append(_get_singbox_outbound(proxy_type, proxy, tag))
            node_tags.append(tag)
        except Exception as e:
            print(f'sing-box节点解析失败，类型:{proxy_type} 错误信息:{str(e)}')

    replacements = node_tags or ['direct']
    for outbound in template_outbounds:
        choices = outbound.get('outbounds') if isinstance(outbound, dict) else None
        if not isinstance(choices, list) or 'auto' not in choices:
            continue
        expanded = []
        for choice in choices:
            values = replacements if choice == 'auto' else [choice]
            for value in values:
                if value not in expanded:
                    expanded.append(value)
        outbound['outbounds'] = expanded

    data['outbounds'] = node_outbounds + template_outbounds
    return json.dumps(data, ensure_ascii=False, indent=2) + '\n'
