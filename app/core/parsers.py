"""Node protocol parsers for Sublink."""

import json
import re
import sys
import urllib.parse
from typing import Any, Dict, Optional, Tuple

from app import config_manager
from app.config_manager import get_runtime_config
from app.core.utils import decode_base64_if, if_ipv6_address, parse_server_port


def _get_country_emoji(hostname: str) -> str:
    """Retrieve country emoji, respecting any monkeypatch on app.view.get_country_emoji."""
    view_mod = sys.modules.get('app.view')
    if view_mod and hasattr(view_mod, 'get_country_emoji'):
        return view_mod.get_country_emoji(hostname)
    from app.remote import get_country_emoji
    return get_country_emoji(hostname)


def _extract_userinfo_host(parse: urllib.parse.ParseResult) -> Tuple[str, str]:
    """Extract (userinfo, server_port) without base64-corrupting plaintext credentials."""
    urlpath = parse.netloc or (parse.path if parse.path != '/' else '')
    if '@' in urlpath:
        userinfo_raw, _, server_port = urlpath.rpartition('@')
        return urllib.parse.unquote(userinfo_raw), server_port
    decoded = decode_base64_if(urlpath)
    if '@' in decoded:
        userinfo, _, server_port = decoded.rpartition('@')
        return userinfo, server_port
    return '', urlpath


def parse_vless(proxy_test: str) -> Dict[str, Any]:
    """Parse VLESS node URI into proxy dictionary."""
    parse = urllib.parse.urlparse(proxy_test)
    raw_query = urllib.parse.parse_qs(parse.query)
    query = {k: v[0] for k, v in raw_query.items()}

    uuid, server_port = _extract_userinfo_host(parse)

    proxy_name = urllib.parse.unquote(parse.fragment)
    server, port = parse_server_port(server_port, default_port=443)
    cfg = get_runtime_config()
    if cfg.get('emoji'):
        proxy_name = (_get_country_emoji(server) or '') + (proxy_name or '')

    proxy: Dict[str, Any] = {
        'name': proxy_name,
        'type': 'vless',
        'uuid': uuid,
        'server': server,
        'client-fingerprint': 'chrome',
        'port': int(port),
        'udp': cfg.get('udp', config_manager.Udp),
        'skip-cert-verify': cfg.get('skipcert', config_manager.SkipCert),
        'tfo': False,
        'tls': str(query.get('security') or '').strip().lower() not in ('', 'none', 'false', '0'),
    }
    network = query.get('type')
    if network:
        proxy['network'] = network

    if query.get('fp'):
        proxy['client-fingerprint'] = query.get('fp')
    if query.get('sni'):
        proxy['servername'] = query.get('sni')
    if query.get('alpn'):
        proxy['alpn'] = [item for item in query.get('alpn').split(',') if item]
    if query.get('flow'):
        proxy['flow'] = query.get('flow')
    if str(query.get('security') or '').strip().lower() == 'reality':
        public_key = (query.get('pbk') or '').strip() or (query.get('publicKey') or '').strip()
        if public_key:
            reality_opts: Dict[str, Any] = {'public-key': public_key}
            sid = (query.get('sid') or '').strip() or (query.get('shortId') or '').strip()
            if sid:
                reality_opts['short-id'] = sid
            proxy['reality-opts'] = reality_opts
    if network == 'ws':
        proxy['ws-opts'] = {
            'path': query.get('path') or '/'
        }
        host = query.get('host')
        if host:
            proxy['ws-opts']['headers'] = {'Host': host}
    if network == 'grpc':
        proxy['grpc-opts'] = {
            'grpc-service-name': query.get('serviceName') or query.get('service-name') or ''
        }
    if str(query.get('insecure') or query.get('allowInsecure') or '').lower() in ('1', 'true'):
        proxy['skip-cert-verify'] = True
    if query.get('cert'):
        proxy['skip-cert-verify'] = query.get('cert').lower() == 'true'

    return proxy


def parse_vmess(proxy_test: str) -> Dict[str, Any]:
    """Parse VMess node URI into proxy dictionary."""
    parse = urllib.parse.urlparse(proxy_test)
    cert = None
    insecure = None
    cfg = get_runtime_config()

    if parse.query != '':
        raw_query = urllib.parse.parse_qs(parse.query)
        query = {k: v[0] for k, v in raw_query.items()}
        info = parse.netloc if '@' in parse.netloc else decode_base64_if(parse.netloc)
        name = query.get('remarks') or urllib.parse.unquote(parse.fragment) or ''
        if '@' in info:
            userinfo, _, server_port = info.rpartition('@')
            userinfo = urllib.parse.unquote(userinfo)
        else:
            userinfo, server_port = '', info
        if ':' in userinfo:
            cipher, _, uuid = userinfo.partition(':')
        else:
            cipher = 'auto'
            uuid = userinfo
        if not cipher:
            cipher = 'auto'
        server, port = parse_server_port(server_port, default_port=443)
        aid = int(query.get('alterId') or 0)
        network = 'ws' if query.get('obfs') == 'websocket' else (query.get('net') or query.get('type') or '')
        if network == 'none':
            network = ''
        tls = query.get('tls')
        path_a = query.get('path')
        host = query.get('obfsParam') or query.get('host')
        sni = query.get('sni') or query.get('peer')
        fingerprint = query.get('fp')
        alpn = query.get('alpn')
        grpc_service_name = query.get('serviceName') or query.get('service-name') or path_a
        if cfg.get('emoji'):
            name = (_get_country_emoji(server) or '') + (name or '')
        cert = query.get('cert')
        insecure = query.get('insecure') or query.get('allowInsecure') or query.get('allowinsecure')
    else:
        info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
        proxy = json.loads(decode_base64_if(info))
        name = proxy.get('ps') or ''
        uuid = proxy.get('id')
        server = proxy.get('add')
        port = int(proxy.get('port') or 443)
        aid = int(proxy.get('aid') or 0)
        cipher = proxy.get('scy') if proxy.get('scy') else 'auto'
        network = proxy.get('net') or ''
        tls = proxy.get('tls')
        path_a = proxy.get('path')
        host = proxy.get('host')
        sni = proxy.get('sni')
        fingerprint = proxy.get('fp')
        alpn = proxy.get('alpn')
        grpc_service_name = proxy.get('serviceName') or proxy.get('path')
        cert = proxy.get('cert')
        for key_name in ('insecure', 'allowInsecure', 'allowinsecure', 'skip-cert-verify'):
            if proxy.get(key_name) not in (None, ''):
                insecure = proxy.get(key_name)
                break
        if cfg.get('emoji'):
            name = (_get_country_emoji(server) or '') + (name or '')

    proxys: Dict[str, Any] = {
        'name': name,
        'type': 'vmess',
        'uuid': uuid,
        'server': server,
        'port': port,
        'client-fingerprint': 'chrome',
        'tfo': False,
        'udp': cfg.get('udp', config_manager.Udp),
        'skip-cert-verify': cfg.get('skipcert', config_manager.SkipCert),
        'alterId': aid,
        'cipher': cipher,
        'tls': str(tls or '').lower() not in ('', 'none', 'false', '0')
    }
    if network:
        proxys['network'] = network
    if sni:
        proxys['servername'] = sni
    if fingerprint:
        proxys['client-fingerprint'] = fingerprint
    if alpn:
        proxys['alpn'] = alpn if isinstance(alpn, list) else [item for item in alpn.split(',') if item]
    if str(insecure if insecure is not None else '').strip().lower() in ('1', 'true'):
        proxys['skip-cert-verify'] = True
    if cert is not None and str(cert).strip() != '':
        proxys['skip-cert-verify'] = str(cert).strip().lower() == 'true'

    if network == 'ws':
        proxys['ws-opts'] = {
            'path': path_a or '/',
        }
        if host is not None and host != '':
            proxys['ws-opts']['headers'] = {
                'Host': host
            }
    if network == 'grpc':
        proxys['grpc-opts'] = {
            'grpc-service-name': grpc_service_name or ''
        }
    return proxys


def _unescape_sip003(val: str) -> str:
    return val.replace(r'\;', ';').replace(r'\=', '=').replace(r'\\', '\\')


_SS_PLUGIN_BOOL_KEYS = frozenset({
    'tls',
    'skip-cert-verify',
    'fast-open',
    'v2ray-http-upgrade',
    'v2ray-http-upgrade-fast-open',
})


def _coerce_ss_mux_opt(val: Any) -> bool:
    """Normalize SS plugin 'mux' option value to bool across JSON and SIP003 string inputs."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val > 0
    low = str(val).strip().lower()
    try:
        return int(low) > 0
    except ValueError:
        return low in ('true', 'yes')


def _coerce_ss_bool_opt(val: Any) -> bool:
    """Normalize SS plugin boolean flag value across JSON and SIP003 string inputs."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val > 0
    return str(val).strip().lower() in ('1', 'true', 'yes')


def _normalize_ss_plugin_opt(clash_plugin: str, key: str, val: Any) -> Tuple[str, Any]:
    """Normalize SS plugin key aliases and boolean option values uniformly."""
    lower_key = key.lower()
    if clash_plugin == 'obfs':
        if lower_key == 'obfs':
            return 'mode', val
        if lower_key == 'obfs-host':
            return 'host', val
    if lower_key == 'mux':
        return 'mux', _coerce_ss_mux_opt(val)
    if lower_key in _SS_PLUGIN_BOOL_KEYS:
        return lower_key, _coerce_ss_bool_opt(val)
    if lower_key in ('mode', 'host', 'path', 'headers', 'fingerprint'):
        return lower_key, val
    return key, val


def _parse_ss_plugin_opts(plugin_name: str, opts_str: str) -> Tuple[str, Dict[str, Any]]:
    """Parse SIP003 plugin name and semicolon/JSON options into Clash plugin/plugin-opts dict."""
    raw_name = str(plugin_name or '').strip()
    lower_name = raw_name.lower()
    if lower_name in ('obfs-local', 'simple-obfs', 'obfs'):
        clash_plugin = 'obfs'
    elif lower_name == 'v2ray-plugin':
        clash_plugin = 'v2ray-plugin'
    else:
        clash_plugin = raw_name

    parsed_opts: Dict[str, Any] = {}
    if opts_str and str(opts_str).strip():
        raw_opts = str(opts_str).strip()
        parsed_from_json = False
        if raw_opts.startswith('{'):
            try:
                loaded = json.loads(raw_opts)
                if isinstance(loaded, dict):
                    parsed_from_json = True
                    for k, v in loaded.items():
                        key = str(k).strip()
                        if not key or v is None:
                            continue
                        norm_key, norm_val = _normalize_ss_plugin_opt(clash_plugin, key, v)
                        parsed_opts[norm_key] = norm_val
            except Exception:
                pass
        if not parsed_from_json:
            tokens = re.split(r'(?<!\\);', raw_opts)
            for token in tokens:
                token = token.strip()
                if not token:
                    continue
                if '=' in token:
                    key_raw, _, val_raw = token.partition('=')
                    key = _unescape_sip003(key_raw.strip())
                    val = _unescape_sip003(val_raw.strip())
                    if not key:
                        continue
                    norm_key, norm_val = _normalize_ss_plugin_opt(clash_plugin, key, val)
                    parsed_opts[norm_key] = norm_val
                else:
                    flag = _unescape_sip003(token)
                    if flag:
                        norm_key, norm_val = _normalize_ss_plugin_opt(clash_plugin, flag, True)
                        parsed_opts[norm_key] = norm_val

    if clash_plugin == 'v2ray-plugin' and not str(parsed_opts.get('mode') or '').strip():
        parsed_opts = {'mode': 'websocket', **{k: v for k, v in parsed_opts.items() if k != 'mode'}}

    return clash_plugin, parsed_opts


def parse_ss(proxy_test: str) -> Dict[str, Any]:
    """Parse Shadowsocks node URI into proxy dictionary."""
    parse = urllib.parse.urlparse(proxy_test)
    info = parse.netloc or (parse.path if parse.path != '/' else '')
    raw_query = urllib.parse.parse_qs(parse.query)
    query = {k: v[0] for k, v in raw_query.items()}
    name = urllib.parse.unquote(parse.fragment)
    if '@' in info:
        userinfo_raw, _, server_port = info.rpartition('@')
        userinfo = urllib.parse.unquote(userinfo_raw)
    else:
        urlpath = decode_base64_if(info)
        if '@' in urlpath:
            userinfo, _, server_port = urlpath.rpartition('@')
        else:
            userinfo, server_port = '', urlpath
    server, port = parse_server_port(server_port, default_port=8388)
    cfg = get_runtime_config()
    if cfg.get('emoji'):
        name = (_get_country_emoji(server) or '') + (name or '')
    if ':' in userinfo:
        decode = userinfo
    else:
        decode = decode_base64_if(userinfo)
    if ':' in decode:
        cipher, _, password = decode.partition(':')
    else:
        cipher = decode
        password = ''
    proxy: Dict[str, Any] = {
        'name': name,
        'type': 'ss',
        'server': server,
        'port': port,
        'cipher': cipher,
        'password': password,
        'client-fingerprint': 'chrome',
        'tfo': False,
        'udp': cfg.get('udp', config_manager.Udp),
        'skip-cert-verify': cfg.get('skipcert', config_manager.SkipCert)
    }
    plugin = query.get('plugin')
    explicit_opts = query.get('plugin-opts')
    if plugin:
        plugin_name, separator, plugin_options = plugin.partition(';')
        opts_source = explicit_opts if explicit_opts is not None else (plugin_options if separator else '')
        clash_plugin, plugin_opts_dict = _parse_ss_plugin_opts(plugin_name, opts_source)
        proxy['plugin'] = clash_plugin
        if plugin_opts_dict:
            proxy['plugin-opts'] = plugin_opts_dict
    elif explicit_opts:
        _, plugin_opts_dict = _parse_ss_plugin_opts('', explicit_opts)
        if plugin_opts_dict:
            proxy['plugin-opts'] = plugin_opts_dict
    return proxy


def parse_ssr(proxy_test: str) -> Dict[str, Any]:
    """Parse ShadowsocksR node URI into proxy dictionary."""
    parse = urllib.parse.urlparse(proxy_test)
    info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
    urlpath = decode_base64_if(info)
    query = urllib.parse.parse_qs(parse.query)
    if urlpath.startswith('[') and ']:' in urlpath:
        server_part, _, rest = urlpath[1:].partition(']:')
        server = if_ipv6_address(server_part)
        parts = rest.split(':')
        port = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 443
        protocol = parts[1] if len(parts) > 1 else 'origin'
        cipher = parts[2] if len(parts) > 2 else 'none'
        obfs = parts[3] if len(parts) > 3 else 'plain'
        password_part = ':'.join(parts[4:]) if len(parts) > 4 else ''
    else:
        parts = urlpath.split(':')
        server = if_ipv6_address(parts[0])
        port = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 443
        protocol = parts[2] if len(parts) > 2 else 'origin'
        cipher = parts[3] if len(parts) > 3 else 'none'
        obfs = parts[4] if len(parts) > 4 else 'plain'
        password_part = ':'.join(parts[5:]) if len(parts) > 5 else ''
    parse2 = urllib.parse.urlparse(password_part)
    password = decode_base64_if(parse2.path.rstrip('/'))
    query2 = urllib.parse.parse_qs(parse2.query)
    name = ''
    if query.get('remarks'):
        name = decode_base64_if(query.get('remarks')[0].replace(' ', '+'))
    if query2.get('remarks'):
        name = decode_base64_if(query2.get('remarks')[0].replace(' ', '+'))
    obfs_param = ''
    if query.get('obfsparam'):
        obfs_param = decode_base64_if(query.get('obfsparam')[0].replace(' ', '+'))
    if query2.get('obfsparam'):
        obfs_param = decode_base64_if(query2.get('obfsparam')[0].replace(' ', '+'))
    proto_param = ''
    if query.get('protoparam'):
        proto_param = decode_base64_if(query.get('protoparam')[0].replace(' ', '+'))
    if query2.get('protoparam'):
        proto_param = decode_base64_if(query2.get('protoparam')[0].replace(' ', '+'))
    cfg = get_runtime_config()
    if cfg.get('emoji'):
        name = (_get_country_emoji(server) or '') + (name or '')
    proxy: Dict[str, Any] = {
        'name': name,
        'type': 'ssr',
        'server': server,
        'port': port,
        'protocol': protocol,
        'cipher': cipher,
        'obfs': obfs,
        'password': password,
        'udp': cfg.get('udp', config_manager.Udp),
        'skip-cert-verify': cfg.get('skipcert', config_manager.SkipCert)
    }
    if obfs_param:
        proxy['obfs-param'] = obfs_param
    if proto_param:
        proxy['protocol-param'] = proto_param
    insecure_vals = query.get('insecure') or query.get('allowInsecure') or query2.get('insecure') or query2.get('allowInsecure')
    if insecure_vals and str(insecure_vals[0]).strip().lower() in ('1', 'true'):
        proxy['skip-cert-verify'] = True
    cert_vals = query.get('cert') or query2.get('cert')
    if cert_vals and cert_vals[0]:
        proxy['skip-cert-verify'] = str(cert_vals[0]).strip().lower() == 'true'
    return proxy


def parse_trojan(proxy_test: str) -> Dict[str, Any]:
    """Parse Trojan node URI into proxy dictionary."""
    parse = urllib.parse.urlparse(proxy_test)
    password, server_port = _extract_userinfo_host(parse)
    name = urllib.parse.unquote(parse.fragment)
    raw_query = urllib.parse.parse_qs(parse.query)
    query = {k: v[0] for k, v in raw_query.items()}
    server, port = parse_server_port(server_port, default_port=443)
    cfg = get_runtime_config()
    if cfg.get('emoji'):
        name = (_get_country_emoji(server) or '') + (name or '')
    proxy: Dict[str, Any] = {
        'name': name,
        'type': 'trojan',
        'server': server,
        'port': port,
        'password': password,
        'client-fingerprint': 'chrome',
        'udp': cfg.get('udp', config_manager.Udp),
        'skip-cert-verify': cfg.get('skipcert', config_manager.SkipCert)
    }
    if query.get('fp'):
        proxy['client-fingerprint'] = query.get('fp')
    if query.get('sni'):
        proxy['sni'] = query.get('sni')
    if query.get('alpn'):
        proxy['alpn'] = [item for item in query.get('alpn').split(',') if item]
    if query.get('flow'):
        proxy['flow'] = query.get('flow')
    if query.get('type') in ('ws', 'grpc'):
        proxy['network'] = query.get('type')
    if query.get('type') == 'ws':
        proxy['ws-opts'] = {
            'path': query.get('path') or '/'
        }
        host = query.get('host')
        if host:
            proxy['ws-opts']['headers'] = {'Host': host}
    if query.get('type') == 'grpc':
        proxy['grpc-opts'] = {
            'grpc-service-name': query.get('serviceName') or query.get('service-name') or ''
        }
    if str(query.get('insecure') or query.get('allowInsecure') or '').lower() in ('1', 'true'):
        proxy['skip-cert-verify'] = True
    if query.get('cert'):
        proxy['skip-cert-verify'] = query.get('cert').lower() == 'true'
    return proxy


def parse_hysteria(proxy_test: str) -> Dict[str, Any]:
    """Parse Hysteria v1 node URI into proxy dictionary."""
    parse = urllib.parse.urlparse(proxy_test)
    auth_str, server_port = _extract_userinfo_host(parse)
    name = urllib.parse.unquote(parse.fragment)
    raw_query = urllib.parse.parse_qs(parse.query)
    query = {k: v[0] for k, v in raw_query.items()}
    server, port = parse_server_port(server_port, default_port=443)
    cfg = get_runtime_config()
    if cfg.get('emoji'):
        name = (_get_country_emoji(server) or '') + (name or '')
    proxy: Dict[str, Any] = {
        'name': name,
        'type': 'hysteria',
        'server': server,
        'port': port,
        'protocol': 'udp',
        'udp': cfg.get('udp', config_manager.Udp),
        'skip-cert-verify': cfg.get('skipcert', config_manager.SkipCert)
    }
    if auth_str:
        proxy['auth_str'] = auth_str
    if query.get('auth'):
        proxy['auth_str'] = query.get('auth')
    if query.get('upmbps'):
        proxy['up'] = query.get('upmbps')
    if query.get('downmbps'):
        proxy['down'] = query.get('downmbps')
    if query.get('alpn'):
        proxy['alpn'] = [item for item in query.get('alpn').split(',') if item]
    if query.get('peer') or query.get('sni'):
        proxy['sni'] = query.get('peer') or query.get('sni')
    if query.get('obfs'):
        proxy['obfs'] = query.get('obfs')
    if str(query.get('insecure') or '').lower() in ('1', 'true'):
        proxy['skip-cert-verify'] = True
    if query.get('cert'):
        proxy['skip-cert-verify'] = query.get('cert').lower() == 'true'
    return proxy


def _parse_positive_int(val: Any) -> Optional[int]:
    """Parse positive integer from string/int value, returning None if invalid."""
    if val in (None, ''):
        return None
    try:
        num = int(str(val).strip())
    except (ValueError, TypeError):
        return None
    return num if num > 0 else None


def _normalize_port_spec(spec: str) -> Tuple[Optional[int], str, bool]:
    """Normalize a Hysteria2 port/multi-port spec into (first_port, normalized_spec, is_multi_port)."""
    tokens = [t.strip() for t in re.split(r'[,;/]+', str(spec or '')) if t.strip()]
    normalized = []
    first_port: Optional[int] = None
    has_range = False
    for token in tokens:
        if '-' in token or ':' in token:
            sep = '-' if '-' in token else ':'
            start_str, _, end_str = token.partition(sep)
            try:
                start, end = int(start_str.strip()), int(end_str.strip())
            except (ValueError, TypeError):
                continue
            if not (1 <= start <= 65535 and 1 <= end <= 65535 and start <= end):
                continue
            if first_port is None:
                first_port = start
            if start == end:
                normalized.append(str(start))
            else:
                has_range = True
                normalized.append(f'{start}-{end}')
        else:
            try:
                port_num = int(token)
            except (ValueError, TypeError):
                continue
            if not (1 <= port_num <= 65535):
                continue
            if first_port is None:
                first_port = port_num
            normalized.append(str(port_num))
    is_multi = has_range or len(normalized) > 1
    return first_port, ','.join(normalized), is_multi


def _split_hysteria2_host_ports(server_port: str, default_port: int = 443) -> Tuple[str, int, str]:
    """Split Hysteria2 host and single/multi-port spec (supporting IPv6 brackets and inline port ranges)."""
    raw = str(server_port or '').strip()
    if not raw:
        return '', default_port, ''
    if raw.startswith('['):
        if ']:' in raw:
            host_part, _, port_spec = raw.rpartition(']:')
            host = if_ipv6_address(host_part + ']')
            first_port, norm, is_multi = _normalize_port_spec(port_spec)
            return host, (first_port or default_port), (norm if is_multi else '')
        return if_ipv6_address(raw), default_port, ''
    if ':' in raw:
        if raw.count(':') > 1:
            return raw, default_port, ''
        host, _, port_spec = raw.rpartition(':')
        first_port, norm, is_multi = _normalize_port_spec(port_spec)
        return host, (first_port or default_port), (norm if is_multi else '')
    return raw, default_port, ''


def _normalize_hop_interval(value: Any) -> Optional[str]:
    """Normalize hop-interval to integer seconds or 'min-max' seconds string (without 's' suffix)."""
    raw = str(value or '').strip().lower()
    if not raw:
        return None
    if '-' in raw:
        lo_str, _, hi_str = raw.partition('-')
        lo = _parse_positive_int(lo_str.strip().rstrip('s'))
        hi = _parse_positive_int(hi_str.strip().rstrip('s'))
        if lo is not None and hi is not None and lo <= hi:
            return f'{lo}-{hi}' if lo != hi else str(lo)
        return None
    sec = _parse_positive_int(raw.rstrip('s'))
    return str(sec) if sec is not None else None


_HY2_ALLOWED_OBFS = ('salamander', 'gecko')
_HY2_GECKO_DEFAULT_MIN_PKT = 512
_HY2_GECKO_DEFAULT_MAX_PKT = 1200
_HY2_GECKO_MAX_WIRE_SIZE = 2048
_HEX64_RE = re.compile(r'^[0-9a-f]{64}$')
_BANDWIDTH_RE = re.compile(r'^(\d+(?:\.\d+)?)\s*([kmgt]?)([b]?)(?:ps)?$', re.IGNORECASE)


def _normalize_pin_sha256(value: Any) -> str:
    """Normalize and validate 64-hex-char SHA256 certificate fingerprint; return '' if invalid."""
    raw = str(value or '').strip()
    if raw.lower().startswith('sha256:'):
        raw = raw[7:]
    cleaned = raw.replace(':', '').strip().lower()
    return cleaned if _HEX64_RE.match(cleaned) else ''


def _normalize_hysteria2_bandwidth(value: Any) -> Optional[str]:
    """Normalize bandwidth string for Mihomo (case-sensitive unit) and downstream parsers."""
    raw = str(value or '').strip()
    if not raw:
        return None
    m = _BANDWIDTH_RE.match(raw)
    if not m:
        return None
    num_val = float(m.group(1))
    if num_val <= 0:
        return None
    prefix = m.group(2).upper()
    bit_or_byte = m.group(3)  # preserve 'B' (bytes) vs 'b' (bits) when specified
    if not prefix and not bit_or_byte:
        mbps = int(round(num_val))
        return str(mbps) if mbps > 0 else None
    unit_b = 'B' if bit_or_byte == 'B' else 'b'
    int_num = int(round(num_val))
    if int_num <= 0:
        return None
    return f'{int_num} {prefix}{unit_b}ps'


def parse_hysteria2(proxy_test: str) -> Dict[str, Any]:
    """Parse Hysteria v2 node URI into proxy dictionary."""
    parse = urllib.parse.urlparse(proxy_test)
    urlpath = parse.netloc or (parse.path if parse.path != '/' else '')
    name = urllib.parse.unquote(parse.fragment)
    raw_query = urllib.parse.parse_qs(parse.query)
    query = {k.lower(): v[0] for k, v in raw_query.items() if v}
    if '@' in urlpath:
        password_raw, _, server_port = urlpath.rpartition('@')
        password = urllib.parse.unquote(password_raw)
    else:
        password = ''
        server_port = urlpath
    server, port, inline_ports = _split_hysteria2_host_ports(server_port, default_port=443)
    cfg = get_runtime_config()
    if cfg.get('emoji'):
        name = (_get_country_emoji(server) or '') + (name or '')
    proxy: Dict[str, Any] = {
        'name': name,
        'type': 'hysteria2',
        'server': server,
        'port': port,
        'password': password,
        'udp': cfg.get('udp', config_manager.Udp),
        'skip-cert-verify': cfg.get('skipcert', config_manager.SkipCert)
    }
    sni = query.get('sni') or query.get('peer')
    if sni:
        proxy['sni'] = sni
    if query.get('alpn'):
        alpn_list = [item.strip() for item in query['alpn'].split(',') if item.strip()]
        if alpn_list:
            proxy['alpn'] = alpn_list
    up = _normalize_hysteria2_bandwidth(query.get('upmbps') or query.get('up'))
    if up:
        proxy['up'] = up
    down = _normalize_hysteria2_bandwidth(query.get('downmbps') or query.get('down'))
    if down:
        proxy['down'] = down
    obfs = str(query.get('obfs') or '').strip().lower()
    obfs_password = query.get('obfs-password') or query.get('obfs_password')
    if obfs in _HY2_ALLOWED_OBFS and obfs_password:
        proxy['obfs'] = obfs
        proxy['obfs-password'] = obfs_password
        if obfs == 'gecko':
            min_pkt = _parse_positive_int(
                query.get('obfs-min-packet-size') or query.get('min_packet_size') or query.get('min-packet-size')
            )
            max_pkt = _parse_positive_int(
                query.get('obfs-max-packet-size') or query.get('max_packet_size') or query.get('max-packet-size')
            )
            eff_min = min_pkt if min_pkt is not None else _HY2_GECKO_DEFAULT_MIN_PKT
            eff_max = max_pkt if max_pkt is not None else _HY2_GECKO_DEFAULT_MAX_PKT
            if 1 <= eff_min <= eff_max <= _HY2_GECKO_MAX_WIRE_SIZE:
                if min_pkt is not None:
                    proxy['obfs-min-packet-size'] = min_pkt
                if max_pkt is not None:
                    proxy['obfs-max-packet-size'] = max_pkt
    mport = query.get('mport') or query.get('ports')
    if mport:
        _, norm_ports, _ = _normalize_port_spec(mport)
        if norm_ports:
            proxy['ports'] = norm_ports
    elif inline_ports:
        proxy['ports'] = inline_ports
    if proxy.get('ports'):
        hop_interval = _normalize_hop_interval(
            query.get('hop-interval') or query.get('hop_interval') or query.get('hopinterval')
        )
        if hop_interval:
            proxy['hop-interval'] = hop_interval
    pin = _normalize_pin_sha256(query.get('pinsha256') or query.get('fingerprint'))
    if pin:
        proxy['fingerprint'] = pin
    if str(query.get('insecure') or query.get('allowinsecure') or '').lower() in ('1', 'true'):
        proxy['skip-cert-verify'] = True
    if query.get('cert'):
        proxy['skip-cert-verify'] = query['cert'].lower() == 'true'
    return proxy


class NodeParse:
    """Backward-compatible NodeParse class for parsing URI nodes."""

    def __init__(self, proxy_test: str = ''):
        self.proxy_test = proxy_test

    def vless(self) -> Dict[str, Any]:
        return parse_vless(self.proxy_test)

    def vmess(self) -> Dict[str, Any]:
        return parse_vmess(self.proxy_test)

    def ss(self) -> Dict[str, Any]:
        return parse_ss(self.proxy_test)

    def ssr(self) -> Dict[str, Any]:
        return parse_ssr(self.proxy_test)

    def trojan(self) -> Dict[str, Any]:
        return parse_trojan(self.proxy_test)

    def hysteria(self) -> Dict[str, Any]:
        return parse_hysteria(self.proxy_test)

    def hysteria2(self) -> Dict[str, Any]:
        return parse_hysteria2(self.proxy_test)
