"""Pure utility functions for Sublink."""

import base64
import re
import secrets
import string
import urllib.parse
from typing import Any, Tuple

TOKEN_ALPHABET = string.ascii_lowercase + string.digits
SUBSCRIPTION_DOWNLOAD_NAME = 'v3订阅'
subname_list = ['vless', 'vmess', 'ss', 'ssr', 'trojan', 'hysteria', 'hy2', 'hysteria2', 'http', 'https']
remote_sub_types = ('http', 'https')
rewritable_node_types = ('vless', 'vmess', 'ss', 'ssr', 'trojan', 'hysteria', 'hy2', 'hysteria2')


def new_access_token() -> str:
    """Generate a random 48-character access token."""
    return ''.join(secrets.choice(TOKEN_ALPHABET) for _ in range(48))


def decode_base64_if_emoji(encoded_text: str) -> str:
    """Decode base64 text that may contain emojis and URL-encoding."""
    encoded_text = urllib.parse.unquote(encoded_text)
    byte_text = encoded_text.encode('utf-8')
    decoded_bytes = base64.b64decode(byte_text)
    return decoded_bytes.decode('utf-8')


def if_ipv6_address(string_val: str) -> str:
    """Extract IPv6 address enclosed in brackets if matched."""
    pattern = r'\[([0-9a-fA-F:]+)\]'
    match = re.search(pattern, string_val)
    if match:
        return match.group(1)
    return string_val


def decode_base64_if(text: str) -> str:
    """
    Attempt to base64 decode a text string.
    Preserves fragments (#) and userinfo (@) markers if present.
    Falls back to returning original text if decoding fails.
    """
    try:
        name = ''
        decoded_text = text
        at = ''
        if '#' in decoded_text:
            decoded_text, _, fragment = decoded_text.partition('#')
            name = '#' + fragment
        if '@' in decoded_text:
            decoded_text, _, at_part = decoded_text.rpartition('@')
            at = '@' + at_part
        padding = 4 - (len(decoded_text) % 4)
        if 0 < padding < 4:
            decoded_text += '=' * padding

        try:
            decoded_bytes = base64.b64decode(decoded_text)
        except Exception:
            decoded_bytes = base64.urlsafe_b64decode(decoded_text)
        decoded_text = decoded_bytes.decode('utf-8')
        return decoded_text + at + name
    except Exception:
        return text


def parse_server_port(server_port: Any, default_port: int = 443) -> Tuple[str, int]:
    """Parse server host and port, handling IPv6 bracket notation and defaults."""
    server_port_str = str(server_port or '').strip()
    if not server_port_str:
        return '', default_port
    if server_port_str.startswith('['):
        if ']:' in server_port_str:
            server_part, _, port_part = server_port_str.rpartition(']:')
            server = if_ipv6_address(server_part + ']')
            try:
                port = int(port_part)
            except (ValueError, TypeError):
                port = default_port
            return server, port
        return if_ipv6_address(server_port_str), default_port
    if ':' in server_port_str:
        if server_port_str.count(':') > 1:
            return server_port_str, default_port
        server_str, _, port_str = server_port_str.rpartition(':')
        try:
            port = int(port_str)
        except (ValueError, TypeError):
            port = default_port
        return server_str, port
    return server_port_str, default_port


def get_proxy_type(node: str) -> str:
    """Extract protocol scheme from node URI."""
    return node.strip().split('://', 1)[0].lower()


def get_remote_sub_host(url: str) -> str:
    """Extract hostname from subscription URL."""
    return urllib.parse.urlparse(url).hostname or ''


def encode_base64(text: str, urlsafe: bool = False) -> str:
    """Encode string to base64 (standard or URL-safe without padding)."""
    if urlsafe:
        return base64.urlsafe_b64encode(text.encode('utf-8')).decode('utf-8').rstrip('=')
    return base64.b64encode(text.encode('utf-8')).decode('utf-8')


def get_host_port(host: str, port: Any) -> str:
    """Format host and port, wrapping bare IPv6 with brackets."""
    if ':' in host and not host.startswith('['):
        host = f'[{host}]'
    return f'{host}:{port}'


def is_truthy(val: Any) -> bool:
    """Determine whether a value represents boolean True."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        return val.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(val)
