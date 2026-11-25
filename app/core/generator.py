"""Client subscription configuration generators for Sublink."""

import base64
import builtins
import concurrent.futures
import copy
import json
import logging
import os
import re
import sys
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from app.config_manager import APP_DIR, get_runtime_config, use_runtime_config
from app.core.parsers import NodeParse, parse_bandwidth_to_mbps
from app.core.rewrite import get_node_server
from app.core.utils import check_yaml_safe_aliases, get_proxy_type, redact_uri_credentials, remote_sub_types

logger = logging.getLogger(__name__)
singbox_node_types = ('vless', 'vmess', 'ss', 'trojan', 'hysteria', 'hy2', 'hysteria2')
_CLASH_RESERVED_NAMES = frozenset({'DIRECT', 'REJECT', 'REJECT-DROP', 'PASS', 'COMPATIBLE', 'GLOBAL'})
_SURGE_RESERVED_NAMES = frozenset({
    'DIRECT', 'REJECT', 'REJECT-TINYGIF', 'REJECT-DROP', 'REJECT-NO-DROP', 'COMPATIBLE', 'PASS', 'FINAL', 'GLOBAL',
})
_SURGE_CTRL_RE = re.compile(r'[\x00-\x1f\x7f]+')
_SURGE_INVALID_HOST_RE = re.compile(r'[\x00-\x1f\x7f\s,=";#]')
_ORIGINAL_OPEN = builtins.open
_template_cache_lock = threading.Lock()
_clash_template_cache: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}
_surge_template_cache: Dict[str, Tuple[int, int, str]] = {}
_singbox_template_cache: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}


_YAML_12_AMBIGUOUS_STR_RE = re.compile(
    r'^(?:'
    r'[+-]?(?:0[xX][0-9a-fA-F]+|0[oO][0-7]+|0\d+|\d+(?:\.\d*)?[eE][+-]?\d+|\.\d+[eE][+-]?\d+)'
    r'|[+-]?\.(?:inf|Inf|INF|nan|NaN|NAN)'
    r')$'
)


class _QuotedYAMLStr(str):
    """String scalar forced to be single-quoted in Clash YAML (e.g. REALITY short-id)."""


class _ClashSafeDumper(yaml.SafeDumper):
    """YAML SafeDumper quoting _QuotedYAMLStr and YAML 1.2 numeric-ambiguous strings (e.g. 1e234567)."""


def _represent_quoted_yaml_str(dumper: yaml.SafeDumper, data: _QuotedYAMLStr) -> yaml.ScalarNode:
    return dumper.represent_scalar('tag:yaml.org,2002:str', str(data), style="'")


def _represent_safe_yaml_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    if _YAML_12_AMBIGUOUS_STR_RE.match(data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")
    return dumper.represent_str(data)


_ClashSafeDumper.add_representer(_QuotedYAMLStr, _represent_quoted_yaml_str)
_ClashSafeDumper.add_representer(str, _represent_safe_yaml_str)


def _validate_proxy_outbound(proxy_type: str, proxy: Dict[str, Any]) -> None:
    """Validate mandatory host, port range (1..65535), and protocol credentials before export."""
    server = str(proxy.get('server') or '').strip()
    if not server or any(ch.isspace() for ch in server):
        raise ValueError('节点缺少有效服务器地址')

    raw_port = proxy.get('port')
    if isinstance(raw_port, bool) or raw_port in (None, ''):
        raise ValueError('节点缺少有效端口')
    try:
        port = int(raw_port)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'节点端口格式无效: {raw_port}') from exc
    if not (1 <= port <= 65535):
        raise ValueError(f'节点端口超出合法范围 (1-65535): {port}')

    ptype = str(proxy_type or proxy.get('type') or '').lower()
    if ptype in ('vless', 'vmess'):
        if not str(proxy.get('uuid') or '').strip():
            raise ValueError(f'{ptype} 节点缺少 uuid')
    elif ptype == 'ss':
        cipher = str(proxy.get('cipher') or '').strip()
        if not cipher:
            raise ValueError('ss 节点缺少加密方式 cipher')
        if cipher.lower() != 'none' and not str(proxy.get('password') or ''):
            raise ValueError('ss 节点缺少密码')
    elif ptype == 'ssr':
        if not all(str(proxy.get(k) or '').strip() for k in ('cipher', 'protocol', 'obfs')) or not str(proxy.get('password') or ''):
            raise ValueError('ssr 节点缺少必要认证或加密字段')
    elif ptype == 'trojan':
        if not str(proxy.get('password') or ''):
            raise ValueError('trojan 节点缺少密码')
    elif ptype in ('hy2', 'hysteria2'):
        if not str(proxy.get('password') or proxy.get('auth') or ''):
            raise ValueError('hysteria2 节点缺少认证密码')


def clear_template_cache() -> None:
    """Clear parsed client template caches."""
    with _template_cache_lock:
        _clash_template_cache.clear()
        _surge_template_cache.clear()
        _singbox_template_cache.clear()


def _resolve_template_path(filename: str) -> str:
    """Resolve db/<filename>, falling back to bundled default app/<filename> if missing."""
    db_file = os.path.join(get_app_path(), 'db', filename)
    if os.path.exists(db_file):
        return db_file
    default_file = os.path.join(APP_DIR, filename)
    if os.path.exists(default_file):
        return default_file
    return db_file


def _load_clash_template() -> Dict[str, Any]:
    """Load Clash YAML template with mtime/size caching; bypasses cache if open() is patched."""
    config_file = _resolve_template_path('clash.yaml')
    if builtins.open is not _ORIGINAL_OPEN:
        with open(config_file, 'r', encoding='utf-8') as file:
            raw_text = file.read()
        check_yaml_safe_aliases(raw_text)
        return yaml.safe_load(raw_text) or {}

    stat = os.stat(config_file)
    cache_key = (stat.st_mtime_ns, stat.st_size)
    with _template_cache_lock:
        cached = _clash_template_cache.get(config_file)
        if cached and cached[0] == cache_key[0] and cached[1] == cache_key[1]:
            base_data = cached[2]
        else:
            base_data = None

    if base_data is None:
        with open(config_file, 'r', encoding='utf-8') as file:
            raw_text = file.read()
        check_yaml_safe_aliases(raw_text)
        base_data = yaml.safe_load(raw_text) or {}
        with _template_cache_lock:
            _clash_template_cache[config_file] = (cache_key[0], cache_key[1], base_data)

    # Shallow copy top-level & deep copy only mutable sections (rules list is read-only)
    data = dict(base_data)
    if 'proxy-groups' in data and isinstance(data['proxy-groups'], list):
        data['proxy-groups'] = copy.deepcopy(data['proxy-groups'])
    return data


def _load_surge_template() -> str:
    """Load Surge configuration template with mtime/size caching."""
    config_file = _resolve_template_path('surge.conf')
    if builtins.open is not _ORIGINAL_OPEN:
        with open(config_file, 'r', encoding='utf-8') as file:
            return file.read()

    stat = os.stat(config_file)
    cache_key = (stat.st_mtime_ns, stat.st_size)
    with _template_cache_lock:
        cached = _surge_template_cache.get(config_file)
        if cached and cached[0] == cache_key[0] and cached[1] == cache_key[1]:
            return cached[2]

    with open(config_file, 'r', encoding='utf-8') as file:
        content = file.read()
    with _template_cache_lock:
        _surge_template_cache[config_file] = (cache_key[0], cache_key[1], content)
    return content


def _prefetch_country_emojis(raw_nodes: List[str]) -> None:
    """Concurrently warm get_country_emoji LRU cache when emoji flag is enabled."""
    if not raw_nodes or not get_runtime_config().get('emoji'):
        return
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'get_country_emoji'):
        emoji_fn = view_mod.get_country_emoji
    else:
        from app.remote import get_country_emoji
        emoji_fn = get_country_emoji
    # Skip prefetch if function is a test mock without lru_cache to avoid double calls
    if not hasattr(emoji_fn, 'cache_info'):
        return
    servers: List[str] = []
    seen: Set[str] = set()
    for raw_node in raw_nodes:
        server = get_node_server(raw_node)
        if server and server not in seen:
            seen.add(server)
            servers.append(server)
    if len(servers) <= 1:
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(servers), 10)) as executor:
        futures = [executor.submit(emoji_fn, host) for host in servers]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception:
                pass


def _surge_bool(val: Any) -> str:
    return 'true' if val else 'false'


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


def _expand_node_entries(subs: Any) -> List[Tuple[str, str]]:
    """Expand subscription objects or strings into (node_uri, fallback_remark) pairs."""
    parsed_items: List[Tuple[str, str, str]] = []
    remote_urls = []
    for sub in subs:
        node_str = (sub.node if hasattr(sub, 'node') else str(sub)).strip()
        if not node_str:
            continue
        remark = str(getattr(sub, 'remarks', '') or '').strip()
        proxy_type = get_proxy_type(node_str)
        if proxy_type in remote_sub_types:
            parsed_items.append(('remote', node_str, ''))
            if node_str not in remote_urls:
                remote_urls.append(node_str)
        else:
            parsed_items.append(('node', node_str, remark))

    if not remote_urls:
        return [(val, rem) for kind, val, rem in parsed_items if kind == 'node']

    # Parallel fetch remote subscriptions, propagating caller's runtime config snapshot
    cfg_snapshot = dict(get_runtime_config())

    def _fetch_with_cfg(url: str) -> List[str]:
        with use_runtime_config(cfg_snapshot):
            return _fetch_remote_sub(url)

    remote_results: Dict[str, List[str]] = {}
    if len(remote_urls) == 1:
        remote_results[remote_urls[0]] = _fetch_with_cfg(remote_urls[0])
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(remote_urls), 10)) as executor:
            future_to_url = {executor.submit(_fetch_with_cfg, url): url for url in remote_urls}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    remote_results[url] = future.result()
                except Exception as e:
                    logger.warning('并发拉取远程订阅异常: %s 错误信息: %s', redact_uri_credentials(url), e)
                    remote_results[url] = []

    # Reconstruct in original order
    raw_entries: List[Tuple[str, str]] = []
    for kind, val, rem in parsed_items:
        if kind == 'node':
            raw_entries.append((val, rem))
        elif kind == 'remote':
            for remote_node in remote_results.get(val, []):
                raw_entries.append((remote_node, ''))
    return raw_entries


def expand_node_list(subs: Any) -> List[str]:
    """Expand subscription objects or strings into a flat list of node strings."""
    return [node for node, _ in _expand_node_entries(subs)]


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


def _sanitize_surge_text(val: Any) -> str:
    """Strip CR/LF/NUL and other ASCII control characters to prevent Surge INI/section injection."""
    if val is None:
        return ''
    return _SURGE_CTRL_RE.sub('', str(val))


def _sanitize_surge_name(name: Any) -> str:
    """Sanitize a Surge proxy name so it never contains control chars, ',' or '='."""
    cleaned = _sanitize_surge_text(name)
    cleaned = re.sub(r'[,=]+', '-', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _sanitize_surge_host(server: Any) -> str:
    """Validate and sanitize a Surge server hostname/IP."""
    cleaned = _sanitize_surge_text(server).strip()
    if not cleaned or _SURGE_INVALID_HOST_RE.search(cleaned):
        raise ValueError(f'Surge 节点服务器地址非法: {cleaned[:40]}')
    return cleaned


def _format_surge_param(val: Any) -> str:
    """Format a Surge parameter value, quoting if it contains syntax-significant characters."""
    cleaned = _sanitize_surge_text(val)
    if not cleaned:
        return ''
    needs_quote = (
        any(ch in cleaned for ch in (',', '"', '\\', '=', ';', '#'))
        or cleaned != cleaned.strip()
        or ' ' in cleaned
    )
    if needs_quote:
        escaped = cleaned.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    return cleaned


def _sanitize_surge_token(val: Any) -> str:
    """Sanitize a strict Surge token (cipher, obfs mode, fingerprint, port list)."""
    cleaned = _sanitize_surge_text(val).strip()
    if not cleaned or any(ch in cleaned for ch in (',', '=', '"', ';', '#')) or any(ch.isspace() for ch in cleaned):
        return ''
    return cleaned


def _extract_surge_template_names(template_text: str) -> Set[str]:
    """Extract existing [Proxy] and [Proxy Group] names from Surge template to avoid collisions."""
    names: Set[str] = set()
    current_section = ''
    for raw_line in template_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or line.startswith(';'):
            continue
        if line.startswith('[') and line.endswith(']'):
            current_section = line.lower()
            continue
        if current_section in ('[proxy]', '[proxy group]') and '=' in line:
            lhs = line.partition('=')[0].strip()
            if lhs:
                names.add(lhs)
    return names


def clash_encode(subs: Any) -> str:
    """Generate Clash subscription YAML configuration."""
    data = _load_clash_template()

    used_names: Set[str] = set(_CLASH_RESERVED_NAMES)
    for grp in (data.get('proxy-groups') or []):
        if isinstance(grp, dict) and grp.get('name'):
            used_names.add(str(grp['name']).strip())

    clash_config = {
        'proxies': [],
        'proxy-groups': []
    }
    proxy_name_list = []
    counts: Dict[str, int] = {}

    raw_entries = _expand_node_entries(subs)
    _prefetch_country_emojis([node for node, _ in raw_entries])
    for index, (raw_node, fallback_remark) in enumerate(raw_entries, 1):
        try:
            proxy = _parse_clash_node(raw_node)
            if proxy:
                _validate_proxy_outbound(proxy.get('type') or get_proxy_type(raw_node), proxy)
                raw_name = str(proxy.get('name') or '').strip() or fallback_remark
                name = get_unique_proxy_name(raw_name, used_names, index, counts)
                proxy['name'] = name
                reality_opts = proxy.get('reality-opts')
                if isinstance(reality_opts, dict) and reality_opts.get('short-id') not in (None, ''):
                    reality_opts = dict(reality_opts)
                    reality_opts['short-id'] = _QuotedYAMLStr(str(reality_opts['short-id']))
                    proxy['reality-opts'] = reality_opts
                clash_config['proxies'].append(proxy)
                proxy_name_list.append(name)
        except Exception as e:
            logger.warning('clash节点解析失败: %s 错误信息: %s', redact_uri_credentials(raw_node), e)

    data['proxies'] = clash_config['proxies']
    proxy_groups = data.get('proxy-groups') or []

    replacements = proxy_name_list or ['DIRECT']
    for proxy_group in proxy_groups:
        group_proxies = proxy_group.get('proxies')
        if group_proxies is None or not isinstance(group_proxies, list):
            group_proxies = []
        if 'auto' in group_proxies:
            expanded = []
            for item in group_proxies:
                values = replacements if item == 'auto' else [item]
                for value in values:
                    if value not in expanded:
                        expanded.append(value)
            proxy_group['proxies'] = expanded or ['DIRECT']
        else:
            deduped = []
            for item in group_proxies:
                if item not in deduped:
                    deduped.append(item)
            proxy_group['proxies'] = deduped or ['DIRECT']

    return yaml.dump(data, Dumper=_ClashSafeDumper, sort_keys=False, allow_unicode=True)


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
        _validate_proxy_outbound('ss', proxy)
        name = _sanitize_surge_name(proxy.get('name'))
        server = _sanitize_surge_host(proxy.get('server'))
        port = int(proxy.get('port'))
        cipher = _sanitize_surge_token(proxy.get('cipher'))
        if not cipher:
            raise ValueError('Surge SS 节点加密方式非法')
        plugin = str(proxy.get('plugin') or '').strip().lower()
        plugin_opts = proxy.get('plugin-opts')
        if plugin:
            if plugin != 'obfs' or not isinstance(plugin_opts, dict):
                logger.info('Surge 跳过不支持的 SS 插件: %s', plugin)
                return None
            obfs_mode = str(plugin_opts.get('mode') or '').strip().lower()
            if obfs_mode not in ('http', 'tls'):
                logger.info('Surge 跳过不支持的 SS obfs 模式: %s', obfs_mode)
                return None
        password = _format_surge_param(proxy.get('password') or '')
        line = (
            f"{name} = ss, {server}, {port}, "
            f"encrypt-method={cipher}, password={password}, "
            f"tfo={_surge_bool(proxy.get('tfo'))}, udp-relay={_surge_bool(proxy.get('udp'))}"
        )
        if plugin == 'obfs' and isinstance(plugin_opts, dict):
            obfs_mode = str(plugin_opts.get('mode') or '').strip().lower()
            line += f", obfs={obfs_mode}"
            obfs_host = _format_surge_param(plugin_opts.get('host') or '')
            if obfs_host:
                line += f", obfs-host={obfs_host}"
        return line, name

    if proxy_type == 'vmess':
        proxy = node_parse.vmess()
        _validate_proxy_outbound('vmess', proxy)
        network = str(proxy.get('network') or '').strip().lower()
        ws_opts = proxy.get('ws-opts') or {}
        if network not in ('', 'tcp', 'raw', 'ws') or (network == 'ws' and isinstance(ws_opts, dict) and ws_opts.get('v2ray-http-upgrade')):
            logger.info('Surge 跳过不支持的 VMess 传输协议: %s', network or 'httpupgrade')
            return None
        name = _sanitize_surge_name(proxy.get('name'))
        server = _sanitize_surge_host(proxy.get('server'))
        port = int(proxy.get('port'))
        uuid = _format_surge_param(proxy.get('uuid') or '')
        line = (
            f"{name} = vmess,{server},{port},username={uuid},"
            f"tls={_surge_bool(proxy.get('tls'))},vmess-aead=true,"
            f"skip-cert-verify={_surge_bool(proxy.get('skip-cert-verify'))},"
            f"tfo={_surge_bool(proxy.get('tfo'))},udp-relay={_surge_bool(proxy.get('udp'))}"
        )
        sni = _format_surge_param(proxy.get('servername') or proxy.get('sni') or '')
        if proxy.get('tls') and sni:
            line += f",sni={sni}"
        if network == 'ws':
            ws_path = _format_surge_param(ws_opts.get('path') or '/') or '/'
            line += f",ws=true,ws-path={ws_path}"
            headers = ws_opts.get('headers')
            raw_host = headers.get('Host') if isinstance(headers, dict) else ''
            safe_host = _sanitize_surge_text(raw_host).replace(',', '').replace('"', '').strip()
            if safe_host:
                line += f",ws-headers=Host:{safe_host}"
                if proxy.get('tls') and not sni:
                    line += f",sni={_format_surge_param(safe_host)}"
            elif proxy.get('tls') and not sni and server:
                line += f",sni={server}"
        return line, name

    if proxy_type == 'trojan':
        proxy = node_parse.trojan()
        _validate_proxy_outbound('trojan', proxy)
        network = str(proxy.get('network') or '').strip().lower()
        ws_opts = proxy.get('ws-opts') or {}
        if network not in ('', 'tcp', 'raw', 'ws') or (
            network == 'ws' and isinstance(ws_opts, dict) and ws_opts.get('v2ray-http-upgrade')
        ):
            logger.info('Surge 跳过不支持的 Trojan 传输协议: %s', network or 'httpupgrade')
            return None
        name = _sanitize_surge_name(proxy.get('name'))
        server = _sanitize_surge_host(proxy.get('server'))
        port = int(proxy.get('port'))
        password = _format_surge_param(proxy.get('password') or '')
        line = (
            f"{name} = trojan,{server},{port},password={password},"
            f"skip-cert-verify={_surge_bool(proxy.get('skip-cert-verify'))},"
            f"tfo={_surge_bool(proxy.get('tfo'))},udp-relay={_surge_bool(proxy.get('udp'))}"
        )
        sni = _format_surge_param(proxy.get('sni') or '')
        if sni:
            line += f",sni={sni}"
        if network == 'ws':
            ws_opts = proxy.get('ws-opts') or {}
            ws_path = _format_surge_param(ws_opts.get('path') or '/') or '/'
            line += f",ws=true,ws-path={ws_path}"
            headers = ws_opts.get('headers')
            raw_host = headers.get('Host') if isinstance(headers, dict) else ''
            safe_host = _sanitize_surge_text(raw_host).replace(',', '').replace('"', '').strip()
            if safe_host:
                line += f",ws-headers=Host:{safe_host}"
        return line, name

    if proxy_type in ('hy2', 'hysteria2'):
        proxy = node_parse.hysteria2()
        _validate_proxy_outbound('hysteria2', proxy)
        name = _sanitize_surge_name(proxy.get('name'))
        server = _sanitize_surge_host(proxy.get('server'))
        port = int(proxy.get('port'))
        password = _format_surge_param(proxy.get('password') or '')
        skip_cert = _surge_bool(proxy.get('skip-cert-verify'))
        udp_relay = _surge_bool(proxy.get('udp'))
        line = (
            f"{name} = hysteria2,{server},{port},password={password},"
            f"skip-cert-verify={skip_cert},udp-relay={udp_relay}"
        )
        sni = _format_surge_param(proxy.get('sni') or '')
        if sni:
            line += f",sni={sni}"
        down_mbps = get_singbox_bandwidth(proxy.get('down'))
        if down_mbps:
            line += f",download-bandwidth={down_mbps}"
        obfs = str(proxy.get('obfs') or '').lower()
        obfs_password = _format_surge_param(proxy.get('obfs-password') or '')
        if obfs == 'salamander' and obfs_password:
            line += f",salamander-password={obfs_password}"
        elif obfs == 'gecko' and obfs_password:
            line += f",gecko-password={obfs_password}"
        fingerprint = _sanitize_surge_token(proxy.get('fingerprint') or '')
        if fingerprint:
            line += f",server-cert-fingerprint-sha256={fingerprint}"
        if proxy.get('ports'):
            port_hopping = _sanitize_surge_text(proxy['ports']).replace(',', ';').replace(' ', '')
            if port_hopping:
                line += f",port-hopping={port_hopping}"
                hop_min, _ = _parse_hop_interval_bounds(proxy.get('hop-interval'))
                if hop_min:
                    line += f",port-hopping-interval={hop_min}"
        return line, name

    return None


def _parse_surge_node(node: str) -> Optional[Tuple[str, str]]:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'parse_surge_node') and view_mod.parse_surge_node is not parse_surge_node:
        return view_mod.parse_surge_node(node)
    return parse_surge_node(node)


def inject_surge_proxies(template_content: str, proxy_lines: List[str]) -> str:
    """Insert formatted proxy lines into the [Proxy] section header (ignoring comments)."""
    match = re.search(r'(?m)^[ \t]*\[Proxy\][ \t]*\r?$', template_content)
    if not match:
        logger.warning('Surge 模板缺少 [Proxy] 区块')
        return template_content
    if not proxy_lines:
        return template_content
    line_ending = '\r\n' if match.group(0).endswith('\r') else '\n'
    new_key_value = line_ending.join(proxy_lines)
    insert_pos = match.end()
    if insert_pos < len(template_content) and template_content[insert_pos] == '\n':
        return template_content[:insert_pos + 1] + new_key_value + line_ending + template_content[insert_pos + 1:]
    return template_content[:insert_pos] + line_ending + new_key_value + template_content[insert_pos:]


def _inject_surge_proxies(template_content: str, proxy_lines: List[str]) -> str:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'inject_surge_proxies') and view_mod.inject_surge_proxies is not inject_surge_proxies:
        return view_mod.inject_surge_proxies(template_content, proxy_lines)
    return inject_surge_proxies(template_content, proxy_lines)


def replace_surge_group_auto(config_text: str, autos: str) -> str:
    """
    Replace 'auto' placeholder within [Proxy Group] section only,
    preserving original spacing while deduplicating repeated proxy entries (e.g. fallback DIRECT).
    """
    pattern = re.compile(r'(^\[Proxy Group\]\s*\n)(.*?)((?=^\[|\Z))', re.MULTILINE | re.DOTALL)
    match = pattern.search(config_text)
    if not match:
        return config_text
    header = match.group(1)
    body = match.group(2)
    tail = match.group(3)

    new_lines = []
    for line in body.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in line:
            new_lines.append(line)
            continue
        line_ending = '\r\n' if line.endswith('\r\n') else ('\n' if line.endswith('\n') else '')
        content = line[:-len(line_ending)] if line_ending else line
        group_name, sep, group_params = content.partition('=')
        new_params = re.sub(r'(?<=[\s,=])auto(?=[\s,]|$)', lambda _: autos, group_params)

        # Deduplicate comma-separated proxy entries on the RHS while keeping index 0
        # (group type like select/url-test) and key=value options intact.
        parts = new_params.split(',')
        if len(parts) > 1:
            kept = [parts[0]]
            seen_proxies: Set[str] = set()
            for part in parts[1:]:
                token = part.strip()
                if not token:
                    continue
                if '=' in token:
                    kept.append(part)
                    continue
                if token in seen_proxies:
                    continue
                seen_proxies.add(token)
                kept.append(part)
            new_params = ','.join(kept)

        new_lines.append(f"{group_name}{sep}{new_params}{line_ending}")

    new_body = ''.join(new_lines)
    return config_text[:match.start()] + header + new_body + tail + config_text[match.end():]


def surge_encode(subs: Any) -> str:
    """Generate Surge subscription configuration."""
    surge_template = _load_surge_template()
    used_names: Set[str] = set(_SURGE_RESERVED_NAMES) | _extract_surge_template_names(surge_template)
    proxy_lines = []
    proxy_name_list = []
    counts: Dict[str, int] = {}

    raw_entries = _expand_node_entries(subs)
    _prefetch_country_emojis([node for node, _ in raw_entries])
    for index, (raw_node, fallback_remark) in enumerate(raw_entries, 1):
        try:
            result = _parse_surge_node(raw_node)
            if result:
                line, name = result
                base_name = _sanitize_surge_name(name) or _sanitize_surge_name(fallback_remark)
                unique_name = get_unique_proxy_name(base_name, used_names, index, counts)
                if unique_name != name:
                    prefix = f"{name} ="
                    if line.startswith(prefix):
                        line = f"{unique_name} ={line[len(prefix):]}"
                    else:
                        line = line.replace(f"{name} =", f"{unique_name} =", 1)
                proxy_lines.append(line)
                proxy_name_list.append(unique_name)
        except Exception as e:
            logger.warning('surge节点解析失败: %s 错误信息: %s', redact_uri_credentials(raw_node), e)

    config_text = _inject_surge_proxies(surge_template, proxy_lines)
    autos = ','.join(proxy_name_list) or 'DIRECT'
    return replace_surge_group_auto(config_text, autos)


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
    """Load and validate Sing-Box template JSON file with mtime/size caching."""
    template_path = _resolve_template_path('sing-box.json')
    if builtins.open is not _ORIGINAL_OPEN:
        with open(template_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        validate_singbox_template(data)
        return data

    stat = os.stat(template_path)
    cache_key = (stat.st_mtime_ns, stat.st_size)
    with _template_cache_lock:
        cached = _singbox_template_cache.get(template_path)
        if cached and cached[0] == cache_key[0] and cached[1] == cache_key[1]:
            return copy.deepcopy(cached[2])

    with open(template_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    validate_singbox_template(data)
    with _template_cache_lock:
        _singbox_template_cache[template_path] = (cache_key[0], cache_key[1], data)
    return copy.deepcopy(data)


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


def get_singbox_tls(
    proxy: Dict[str, Any],
    required: bool = False,
    allow_utls: bool = True,
    force_insecure: bool = False,
) -> Optional[Dict[str, Any]]:
    """Generate Sing-Box TLS configuration object."""
    reality = proxy.get('reality-opts') or {}
    public_key = reality.get('public-key')
    enabled = required or bool(proxy.get('tls')) or bool(reality)
    if not enabled:
        return None
    if public_key:
        insecure = False
    elif force_insecure:
        insecure = True
    else:
        insecure = bool(proxy.get('skip-cert-verify'))
    tls: Dict[str, Any] = {
        'enabled': True,
        'insecure': insecure,
    }
    server_name = proxy.get('servername') or proxy.get('sni')
    if server_name:
        tls['server_name'] = server_name
    fingerprint = str(proxy.get('client-fingerprint') or '').strip()
    if public_key and (not fingerprint or fingerprint.lower() == 'none'):
        fingerprint = 'firefox'
    if allow_utls and fingerprint and fingerprint.lower() != 'none':
        tls['utls'] = {
            'enabled': True,
            'fingerprint': fingerprint,
        }
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
    if network in ('ws', 'httpupgrade'):
        options = proxy.get('ws-opts') or {}
        is_httpupgrade = network == 'httpupgrade' or bool(options.get('v2ray-http-upgrade'))
        headers = options.get('headers') if isinstance(options.get('headers'), dict) else {}
        if is_httpupgrade:
            transport: Dict[str, Any] = {
                'type': 'httpupgrade',
                'path': options.get('path') or '/',
            }
            host = next((v for k, v in headers.items() if str(k).lower() == 'host' and v), None)
            if host:
                transport['host'] = str(host)
            other_headers = {k: v for k, v in headers.items() if str(k).lower() != 'host' and v}
            if other_headers:
                transport['headers'] = other_headers
            return transport
        transport = {
            'type': 'ws',
            'path': options.get('path') or '/',
        }
        if headers:
            transport['headers'] = headers
        return transport
    if network in ('h2', 'http'):
        options = proxy.get('h2-opts') or proxy.get('http-opts') or {}
        transport = {
            'type': 'http',
            'path': options.get('path') or '/',
        }
        host = options.get('host')
        if isinstance(host, list) and host:
            transport['host'] = [str(h) for h in host if h]
        elif isinstance(host, str) and host.strip():
            transport['host'] = [host.strip()]
        return transport
    if network == 'grpc':
        options = proxy.get('grpc-opts') or {}
        return {
            'type': 'grpc',
            'service_name': options.get('grpc-service-name') or options.get('service-name') or '',
        }
    return None


def _format_singbox_server_ports(ports_spec: Any) -> List[str]:
    """Convert comma/hyphen port spec (e.g. '20000-50000,8080') to sing-box range list ['20000:50000', '8080:8080']."""
    if not ports_spec:
        return []
    result: List[str] = []
    for token in str(ports_spec).split(','):
        token = token.strip()
        if not token:
            continue
        if '-' in token or ':' in token:
            sep = '-' if '-' in token else ':'
            start_s, _, end_s = token.partition(sep)
            if start_s.strip().isdigit() and end_s.strip().isdigit():
                start, end = int(start_s.strip()), int(end_s.strip())
                if 1 <= start <= end <= 65535:
                    result.append(f'{start}:{end}')
        elif token.isdigit():
            port_num = int(token)
            if 1 <= port_num <= 65535:
                result.append(f'{port_num}:{port_num}')
    return result


def _parse_hop_interval_bounds(value: Any) -> Tuple[Optional[int], Optional[int]]:
    """Parse hop-interval ('30', '30s', '10-20') into (min_sec, max_sec)."""
    raw = str(value or '').strip().lower()
    if not raw:
        return None, None
    if '-' in raw:
        lo_s, _, hi_s = raw.partition('-')
        lo_s, hi_s = lo_s.strip().rstrip('s'), hi_s.strip().rstrip('s')
        if lo_s.isdigit() and hi_s.isdigit():
            lo, hi = int(lo_s), int(hi_s)
            if 0 < lo <= hi:
                return lo, (hi if hi != lo else None)
        return None, None
    sec_s = raw.rstrip('s')
    if sec_s.isdigit() and int(sec_s) > 0:
        return int(sec_s), None
    return None, None


def get_singbox_bandwidth(value: Any) -> Optional[int]:
    """Parse bandwidth string into positive integer Mbps, converting K/M/G/T, b/B, ps and /s accurately."""
    if value in (None, ''):
        return None
    mbps_val = parse_bandwidth_to_mbps(value)
    if mbps_val is None:
        return None
    mbps = int(round(mbps_val))
    return mbps if mbps > 0 else None


def get_singbox_outbound(
    proxy_type: str,
    proxy: Dict[str, Any],
    tag: str,
    legacy_format: bool = False,
    hy2_pin_fallback: Optional[bool] = None,
) -> Dict[str, Any]:
    """Build Sing-Box outbound configuration dictionary for a given node."""
    _validate_proxy_outbound(proxy_type, proxy)
    server = proxy.get('server')
    port = proxy.get('port')
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
        transport = get_singbox_transport(proxy)
        network = str(proxy.get('network') or '').strip().lower()
        raw_flow = str(proxy.get('flow') or '').strip().lower()
        if raw_flow == 'xtls-rprx-vision-udp443':
            raw_flow = 'xtls-rprx-vision'
        if raw_flow and raw_flow != 'none' and not transport and network in ('', 'tcp', 'raw'):
            outbound['flow'] = raw_flow
        tls = get_singbox_tls(proxy)
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
        plugin_name = proxy.get('plugin')
        plugin_opts = proxy.get('plugin-opts')
        if plugin_name:
            lower_plugin = str(plugin_name).lower()
            if lower_plugin in ('obfs', 'simple-obfs'):
                sb_plugin = 'obfs-local'
            elif lower_plugin == 'v2ray-plugin':
                sb_plugin = 'v2ray-plugin'
            else:
                sb_plugin = plugin_name
            outbound['plugin'] = sb_plugin
        if plugin_opts:
            if isinstance(plugin_opts, dict):
                parts: List[str] = []
                is_obfs = str(plugin_name or '').lower() in ('obfs', 'obfs-local', 'simple-obfs')
                is_v2ray = str(plugin_name or '').lower() == 'v2ray-plugin'
                has_host = any(
                    str(k).lower() in ('host', 'obfs-host') and plugin_opts.get(k) not in (None, '')
                    for k in plugin_opts
                )
                for k, v in plugin_opts.items():
                    if v is None or v == '':
                        continue
                    if is_v2ray and k == 'mode' and str(v).lower() == 'websocket':
                        continue
                    if isinstance(v, dict):
                        if is_v2ray and str(k).lower() == 'headers' and not has_host:
                            header_host = next(
                                (hv for hk, hv in v.items() if str(hk).lower() == 'host' and hv),
                                None,
                            )
                            if header_host:
                                parts.append(f'host={header_host}')
                                has_host = True
                        continue
                    if isinstance(v, (list, tuple)):
                        continue
                    out_k = k
                    if is_obfs:
                        if k == 'mode':
                            out_k = 'obfs'
                        elif k == 'host':
                            out_k = 'obfs-host'
                    if isinstance(v, bool):
                        if is_v2ray and out_k == 'mux':
                            # sing-box v2ray-plugin parses mux with strconv.Atoi (0 disables mux)
                            parts.append('mux=1' if v else 'mux=0')
                        elif v:
                            parts.append(out_k)
                        elif not is_v2ray or out_k not in (
                            'tls',
                            'skip-cert-verify',
                            'fast-open',
                            'v2ray-http-upgrade',
                            'v2ray-http-upgrade-fast-open',
                        ):
                            parts.append(f'{out_k}=false')
                    else:
                        parts.append(f'{out_k}={v}')
                if parts:
                    outbound['plugin_opts'] = ';'.join(parts)
            else:
                outbound['plugin_opts'] = str(plugin_opts)
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
            'tls': get_singbox_tls(proxy, required=True, allow_utls=False),
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
        has_cert_pin = bool(str(proxy.get('fingerprint') or '').strip())
        allow_pin_fallback = (
            bool(get_runtime_config().get('hy2_pin_fallback', False))
            if hy2_pin_fallback is None
            else bool(hy2_pin_fallback)
        )
        force_insecure = has_cert_pin and allow_pin_fallback
        if has_cert_pin and not proxy.get('skip-cert-verify'):
            if allow_pin_fallback:
                logger.warning(
                    'sing-box 暂不支持 Hysteria2 pinSHA256 整证书指纹校验，已按显式开关将节点 %s 的 tls.insecure 设为 true',
                    tag,
                )
            else:
                logger.info(
                    'sing-box 暂不支持 Hysteria2 pinSHA256 整证书指纹校验，节点 %s 保持 tls.insecure=false（如需兼容可在全局设置开启或附加 ?hy2_pin_fallback=1）',
                    tag,
                )
        outbound = {
            'type': 'hysteria2',
            **common,
            'password': proxy.get('password') or proxy.get('auth'),
            'tls': get_singbox_tls(
                proxy,
                required=True,
                allow_utls=False,
                force_insecure=force_insecure,
            ),
        }
        server_ports = _format_singbox_server_ports(proxy.get('ports'))
        if server_ports:
            outbound.pop('server_port', None)
            outbound['server_ports'] = server_ports
            hop_min, hop_max = _parse_hop_interval_bounds(proxy.get('hop-interval'))
            if hop_min:
                hop_min = max(5, hop_min)
                outbound['hop_interval'] = f'{hop_min}s'
                if not legacy_format and hop_max and hop_max > hop_min:
                    outbound['hop_interval_max'] = f'{hop_max}s'
        up_mbps = get_singbox_bandwidth(proxy.get('up'))
        down_mbps = get_singbox_bandwidth(proxy.get('down'))
        if up_mbps is not None:
            outbound['up_mbps'] = up_mbps
        if down_mbps is not None:
            outbound['down_mbps'] = down_mbps
        obfs_type = str(proxy.get('obfs') or '').strip().lower()
        if obfs_type in ('salamander', 'gecko') and proxy.get('obfs-password'):
            if legacy_format and obfs_type == 'gecko':
                raise ValueError('sing-box 1.12-1.13 (?legacy=1) 不支持 Hysteria2 gecko 混淆')
            obfs_obj: Dict[str, Any] = {
                'type': obfs_type,
                'password': proxy.get('obfs-password'),
            }
            if obfs_type == 'gecko':
                min_pkt = proxy.get('obfs-min-packet-size')
                max_pkt = proxy.get('obfs-max-packet-size')
                min_val = int(min_pkt) if min_pkt else None
                max_val = int(max_pkt) if max_pkt else None
                eff_min = min_val if min_val is not None else 512
                eff_max = max_val if max_val is not None else 1200
                if 1 <= eff_min <= eff_max <= 2048:
                    if min_val is not None:
                        obfs_obj['min_packet_size'] = min_val
                    if max_val is not None:
                        obfs_obj['max_packet_size'] = max_val
            outbound['obfs'] = obfs_obj
        return outbound

    raise ValueError(f'不支持的节点类型: {proxy_type}')


def _get_singbox_outbound(
    proxy_type: str,
    proxy: Dict[str, Any],
    tag: str,
    legacy_format: bool = False,
    hy2_pin_fallback: Optional[bool] = None,
) -> Dict[str, Any]:
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'get_singbox_outbound') and view_mod.get_singbox_outbound is not get_singbox_outbound:
        try:
            return view_mod.get_singbox_outbound(
                proxy_type, proxy, tag, legacy_format=legacy_format, hy2_pin_fallback=hy2_pin_fallback
            )
        except TypeError:
            try:
                return view_mod.get_singbox_outbound(proxy_type, proxy, tag, legacy_format=legacy_format)
            except TypeError:
                return view_mod.get_singbox_outbound(proxy_type, proxy, tag)
    return get_singbox_outbound(
        proxy_type, proxy, tag, legacy_format=legacy_format, hy2_pin_fallback=hy2_pin_fallback
    )


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


def migrate_singbox_legacy_options(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate deprecated sing-box 1.14+ remote rule-set options in-place:
    - Replace legacy `download_detour` with top-level `http_clients` + `default_http_client` / `http_client`.
    - Ensure remote rule-sets without explicit `http_client` have `route.default_http_client` set.
    """
    if not isinstance(data, dict):
        return data
    route = data.get('route')
    if not isinstance(route, dict):
        return data
    rule_sets = route.get('rule_set')
    if not isinstance(rule_sets, list):
        return data

    remote_sets = [rs for rs in rule_sets if isinstance(rs, dict) and rs.get('type') == 'remote']
    if not remote_sets:
        return data

    existing_clients = data.get('http_clients')
    http_clients: List[Dict[str, Any]] = (
        [c for c in existing_clients if isinstance(c, dict)]
        if isinstance(existing_clients, list)
        else []
    )
    clients_modified = False

    def ensure_http_client(detour: str) -> str:
        nonlocal clients_modified
        for client in http_clients:
            if set(client.keys()) == {'tag', 'detour'} and client.get('detour') == detour and client.get('tag'):
                return str(client['tag'])
        used_tags = {str(c.get('tag')) for c in http_clients if c.get('tag')}
        if 'remote-client' not in used_tags:
            tag = 'remote-client'
        else:
            base = f'remote-client-{detour}'
            tag = base
            idx = 2
            while tag in used_tags:
                tag = f'{base}-{idx}'
                idx += 1
        http_clients.append({'tag': tag, 'detour': detour})
        clients_modified = True
        return tag

    default_client_tag = route.get('default_http_client')
    if not isinstance(default_client_tag, str) or not default_client_tag.strip():
        default_client_tag = None

    default_client_detour: Optional[str] = None
    if default_client_tag:
        for client in http_clients:
            if client.get('tag') == default_client_tag and set(client.keys()) == {'tag', 'detour'}:
                default_client_detour = client.get('detour')
                break

    legacy_entries: List[Tuple[Dict[str, Any], str]] = []
    for rs in remote_sets:
        if 'download_detour' not in rs:
            continue
        detour_val = rs.pop('download_detour')
        if isinstance(detour_val, str) and detour_val.strip():
            legacy_entries.append((rs, detour_val.strip()))

    if legacy_entries:
        distinct_detours = list(dict.fromkeys(detour for _, detour in legacy_entries))
        all_without_explicit_client = all(not rs.get('http_client') for rs, _ in legacy_entries)
        legacy_ids = {id(rs) for rs, _ in legacy_entries}
        other_remote_missing_client = [
            rs for rs in remote_sets
            if id(rs) not in legacy_ids and not rs.get('http_client')
        ]
        if (
            default_client_tag is None
            and len(distinct_detours) == 1
            and all_without_explicit_client
            and not other_remote_missing_client
        ):
            default_client_tag = ensure_http_client(distinct_detours[0])
            route['default_http_client'] = default_client_tag
        else:
            for rs, detour in legacy_entries:
                if rs.get('http_client'):
                    continue
                if default_client_tag and default_client_detour == detour:
                    continue
                rs['http_client'] = ensure_http_client(detour)

    if default_client_tag is None and any(not rs.get('http_client') for rs in remote_sets):
        fallback_detour = route.get('final')
        if not isinstance(fallback_detour, str) or not fallback_detour.strip():
            fallback_detour = 'direct'
        default_client_tag = ensure_http_client(fallback_detour.strip())
        route['default_http_client'] = default_client_tag

    if clients_modified:
        data['http_clients'] = http_clients
    return data


def convert_singbox_to_legacy_options(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert sing-box 1.14+ `http_clients` / `default_http_client` / `http_client`
    back to legacy `download_detour` for sing-box 1.12 - 1.13 compatibility.
    """
    if not isinstance(data, dict):
        return data
    route = data.get('route')
    if not isinstance(route, dict):
        return data
    rule_sets = route.get('rule_set')
    if not isinstance(rule_sets, list):
        return data

    clients_map: Dict[str, str] = {}
    for client in (data.get('http_clients') or []):
        if isinstance(client, dict) and client.get('tag') and client.get('detour'):
            clients_map[str(client['tag'])] = str(client['detour'])

    default_tag = route.pop('default_http_client', None)
    default_detour = clients_map.get(str(default_tag)) if default_tag else None

    for rs in rule_sets:
        if not isinstance(rs, dict) or rs.get('type') != 'remote':
            continue
        explicit_tag = rs.pop('http_client', None)
        if not rs.get('download_detour'):
            detour = clients_map.get(str(explicit_tag)) if explicit_tag else default_detour
            if detour:
                rs['download_detour'] = detour

    data.pop('http_clients', None)
    return data


def singbox_encode(
    subs: Any,
    legacy_format: bool = False,
    hy2_pin_fallback: Optional[bool] = None,
) -> str:
    """Generate Sing-Box subscription configuration with flat early-return control flow."""
    data = _load_singbox_template()
    if legacy_format:
        convert_singbox_to_legacy_options(data)
    else:
        migrate_singbox_legacy_options(data)
    template_outbounds = data['outbounds']
    used_tags = {
        outbound.get('tag')
        for outbound in template_outbounds
        if isinstance(outbound, dict) and outbound.get('tag')
    }
    node_outbounds = []
    node_tags = []

    raw_entries = _expand_node_entries(subs)
    _prefetch_country_emojis([node for node, _ in raw_entries])
    for raw_node, fallback_remark in raw_entries:
        proxy_type = get_proxy_type(raw_node)
        if proxy_type == 'ssr':
            logger.info('sing-box跳过不支持的节点类型: ssr')
            continue
        if proxy_type not in singbox_node_types:
            logger.info('sing-box跳过不支持的节点类型: %s', proxy_type)
            continue
        tag = None
        try:
            proxy = _parse_singbox_node(proxy_type, raw_node)
            raw_name = str(proxy.get('name') or '').strip() or fallback_remark
            tag = get_unique_singbox_tag(raw_name, used_tags, len(node_tags) + 1)
            outbound = _get_singbox_outbound(
                proxy_type,
                proxy,
                tag,
                legacy_format=legacy_format,
                hy2_pin_fallback=hy2_pin_fallback,
            )
            node_outbounds.append(outbound)
            node_tags.append(tag)
        except Exception as e:
            if tag is not None:
                used_tags.discard(tag)
            logger.warning('sing-box节点解析失败，类型: %s 节点: %s 错误信息: %s', proxy_type, redact_uri_credentials(raw_node), e)

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
