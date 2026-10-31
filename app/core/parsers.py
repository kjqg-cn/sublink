"""Node protocol parsers for Sublink."""

import json
import sys
import urllib.parse
from typing import Any, Dict

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


def parse_vless(proxy_test: str) -> Dict[str, Any]:
    """Parse VLESS node URI into proxy dictionary."""
    parse = urllib.parse.urlparse(proxy_test)
    raw_query = urllib.parse.parse_qs(parse.query)
    query = {k: v[0] for k, v in raw_query.items()}

    info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
    urlpath = decode_base64_if(info)
    if '@' in urlpath:
        uuid_part, _, server_port = urlpath.rpartition('@')
        uuid = decode_base64_if(uuid_part)
    else:
        uuid = ''
        server_port = urlpath

    proxy_name = urllib.parse.unquote(parse.fragment)
    server, port = parse_server_port(server_port, default_port=443)
    cfg = get_runtime_config()
    if cfg.get('emoji'):
        proxy_name = (_get_country_emoji(server) or '') + (proxy_name or '')

    proxy = {
        'name': proxy_name,
        'type': 'vless',
        'uuid': uuid,
        'server': server,
        'client-fingerprint': 'chrome',
        'port': int(port),
        'network': query.get('type'),
        'udp': cfg.get('udp', config_manager.Udp),
        'skip-cert-verify': cfg.get('skipcert', config_manager.SkipCert),
        'tfo': False,
        'tls': str(query.get('security') or '').lower() not in ('', 'none', 'false', '0'),
    }

    if query.get('fp'):
        proxy['client-fingerprint'] = query.get('fp')
    if query.get('sni'):
        proxy['servername'] = query.get('sni')
    if query.get('alpn'):
        proxy['alpn'] = [item for item in query.get('alpn').split(',') if item]
    if query.get('flow'):
        proxy['flow'] = query.get('flow')
    if query.get('security') == 'reality':
        proxy['reality-opts'] = {
            'public-key': query.get('pbk') or query.get('publicKey')
        }
        sid = query.get('sid') or query.get('shortId')
        if sid:
            proxy['reality-opts']['short-id'] = sid
    if query.get('type') == 'ws':
        proxy['ws-opts'] = {
            'path': query.get('path')
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


def parse_vmess(proxy_test: str) -> Dict[str, Any]:
    """Parse VMess node URI into proxy dictionary."""
    parse = urllib.parse.urlparse(proxy_test)
    cert = None
    cfg = get_runtime_config()

    if parse.query != '':
        raw_query = urllib.parse.parse_qs(parse.query)
        query = {k: v[0] for k, v in raw_query.items()}
        info = decode_base64_if(parse.netloc)
        name = query.get('remarks') or urllib.parse.unquote(parse.fragment) or ''
        if '@' in info:
            userinfo, _, server_port = info.rpartition('@')
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
        network = 'ws' if query.get('obfs') == 'websocket' else ''
        tls = query.get('tls')
        path_a = query.get('path')
        host = query.get('obfsParam')
        sni = query.get('sni') or query.get('peer')
        fingerprint = query.get('fp')
        alpn = query.get('alpn')
        grpc_service_name = query.get('serviceName') or query.get('service-name') or path_a
        if cfg.get('emoji'):
            name = (_get_country_emoji(server) or '') + (name or '')
        cert = query.get('cert')
    else:
        info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
        proxy = json.loads(decode_base64_if(info))
        name = proxy.get('ps')
        uuid = proxy.get('id')
        server = proxy.get('add')
        port = int(proxy.get('port') or 443)
        aid = int(proxy.get('aid') or 0)
        cipher = proxy.get('scy') if proxy.get('scy') else 'auto'
        network = proxy.get('net')
        tls = proxy.get('tls')
        path_a = proxy.get('path')
        host = proxy.get('host')
        sni = proxy.get('sni')
        fingerprint = proxy.get('fp')
        alpn = proxy.get('alpn')
        grpc_service_name = proxy.get('serviceName') or proxy.get('path')
        cert = proxy.get('cert')
        if cfg.get('emoji'):
            name = (_get_country_emoji(server) or '') + (name or '')

    proxys = {
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
        'network': network,
        'tls': str(tls or '').lower() not in ('', 'none', 'false', '0')
    }
    if sni:
        proxys['servername'] = sni
    if fingerprint:
        proxys['client-fingerprint'] = fingerprint
    if alpn:
        proxys['alpn'] = alpn if isinstance(alpn, list) else [item for item in alpn.split(',') if item]
    if cert:
        proxys['skip-cert-verify'] = str(cert).lower() == 'true'

    if network == 'ws':
        proxys['ws-opts'] = {
            'path': path_a,
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


def parse_ss(proxy_test: str) -> Dict[str, Any]:
    """Parse Shadowsocks node URI into proxy dictionary."""
    parse = urllib.parse.urlparse(proxy_test)
    info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
    urlpath = decode_base64_if(info)
    raw_query = urllib.parse.parse_qs(parse.query)
    query = {k: v[0] for k, v in raw_query.items()}
    name = urllib.parse.unquote(parse.fragment)
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
    proxy = {
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
    if plugin:
        plugin_name, separator, plugin_options = plugin.partition(';')
        proxy['plugin'] = plugin_name
        if separator:
            proxy['plugin-opts'] = plugin_options
    if query.get('plugin-opts'):
        proxy['plugin-opts'] = query.get('plugin-opts')
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
    password = decode_base64_if(parse2.path.replace('/', ''))
    query2 = urllib.parse.parse_qs(parse2.query)
    name = ''
    if query.get('remarks'):
        name = decode_base64_if(query.get('remarks')[0])
    if query2.get('remarks'):
        name = decode_base64_if(query2.get('remarks')[0])
    cfg = get_runtime_config()
    if cfg.get('emoji'):
        name = (_get_country_emoji(server) or '') + (name or '')
    proxy = {
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
    if query.get('cert'):
        proxy['skip-cert-verify'] = query.get('cert').lower() == 'true'
    return proxy


def parse_trojan(proxy_test: str) -> Dict[str, Any]:
    """Parse Trojan node URI into proxy dictionary."""
    parse = urllib.parse.urlparse(proxy_test)
    info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
    urlpath = decode_base64_if(info)
    name = urllib.parse.unquote(parse.fragment)
    raw_query = urllib.parse.parse_qs(parse.query)
    query = {k: v[0] for k, v in raw_query.items()}
    if '@' in urlpath:
        password, _, server_port = urlpath.rpartition('@')
    else:
        password = ''
        server_port = urlpath
    server, port = parse_server_port(server_port, default_port=443)
    cfg = get_runtime_config()
    if cfg.get('emoji'):
        name = (_get_country_emoji(server) or '') + (name or '')
    proxy = {
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
            'path': query.get('path')
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
    info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
    urlpath = decode_base64_if(info)
    name = urllib.parse.unquote(parse.fragment)
    raw_query = urllib.parse.parse_qs(parse.query)
    query = {k: v[0] for k, v in raw_query.items()}
    server, port = parse_server_port(urlpath, default_port=443)
    cfg = get_runtime_config()
    if cfg.get('emoji'):
        name = (_get_country_emoji(server) or '') + (name or '')
    proxy = {
        'name': name,
        'type': 'hysteria',
        'server': server,
        'port': port,
        'client-fingerprint': 'chrome',
        'protocol': 'udp',
        'udp': cfg.get('udp', config_manager.Udp),
        'skip-cert-verify': cfg.get('skipcert', config_manager.SkipCert)
    }
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


def parse_hysteria2(proxy_test: str) -> Dict[str, Any]:
    """Parse Hysteria v2 node URI into proxy dictionary."""
    parse = urllib.parse.urlparse(proxy_test)
    info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
    urlpath = decode_base64_if(info)
    name = urllib.parse.unquote(parse.fragment)
    raw_query = urllib.parse.parse_qs(parse.query)
    query = {k: v[0] for k, v in raw_query.items()}
    if '@' in urlpath:
        password, _, server_port = urlpath.rpartition('@')
    else:
        password = ''
        server_port = urlpath
    server, port = parse_server_port(server_port, default_port=443)
    cfg = get_runtime_config()
    if cfg.get('emoji'):
        name = (_get_country_emoji(server) or '') + (name or '')
    proxy = {
        'name': name,
        'type': 'hysteria2',
        'server': server,
        'port': port,
        'password': password,
        'auth': password,
        'client-fingerprint': 'chrome',
        'udp': cfg.get('udp', config_manager.Udp),
        'skip-cert-verify': cfg.get('skipcert', config_manager.SkipCert)
    }
    if query.get('sni'):
        proxy['sni'] = query.get('sni')
    if query.get('alpn'):
        proxy['alpn'] = [item for item in query.get('alpn').split(',') if item]
    if query.get('upmbps'):
        proxy['up'] = query.get('upmbps')
    if query.get('downmbps'):
        proxy['down'] = query.get('downmbps')
    if query.get('obfs') not in (None, 'none'):
        proxy['obfs'] = query.get('obfs')
    if query.get('obfs-password'):
        proxy['obfs-password'] = query.get('obfs-password')
    if str(query.get('insecure') or '').lower() in ('1', 'true'):
        proxy['skip-cert-verify'] = True
    if query.get('cert'):
        proxy['skip-cert-verify'] = query.get('cert').lower() == 'true'
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
