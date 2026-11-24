"""Pure utility functions for Sublink."""

import base64
import re
import secrets
import string
import urllib.parse
from typing import Any, Dict, List, Set, Tuple

import yaml

TOKEN_ALPHABET = string.ascii_lowercase + string.digits
SUBSCRIPTION_DOWNLOAD_NAME = 'v3订阅'
subname_list = ['vless', 'vmess', 'ss', 'ssr', 'trojan', 'hysteria', 'hy2', 'hysteria2', 'http', 'https']
remote_sub_types = ('http', 'https')
rewritable_node_types = ('vless', 'vmess', 'ss', 'ssr', 'trojan', 'hysteria', 'hy2', 'hysteria2')

_BRACKET_PAIRS = (
    ('【', '】'),
    ('[', ']'),
    ('(', ')'),
    ('（', '）'),
    ('{', '}'),
    ('《', '》'),
    ('<', '>'),
)
_SENSITIVE_QUERY_KEYS = frozenset({
    'password', 'pass', 'pwd', 'auth', 'obfs-password', 'obfs_password',
    'token', 'access_token', 'pbk', 'publickey', 'key', 'secret', 'uuid',
})
_OPAQUE_CRED_SCHEMES = frozenset({'vmess', 'ssr', 'ss'})


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


_STD_B64_RE = re.compile(r'^[A-Za-z0-9+/]+={0,2}$')
_URLSAFE_B64_RE = re.compile(r'^[A-Za-z0-9\-_]+={0,2}$')
_DISALLOWED_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def decode_base64_if(text: str) -> str:
    """
    Attempt to strictly base64-decode a text string (standard or URL-safe).
    Preserves fragments (#) and userinfo (@) markers if present.
    Never silently drops non-base64 characters; falls back to original text if invalid.
    """
    if not isinstance(text, str) or not text:
        return text
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

        candidate = decoded_text.strip()
        if not at and not name:
            # Allow MIME line-wrapped base64 bodies without collapsing spaces between plaintext words
            candidate = re.sub(r'[\r\n]+', '', candidate)
        if not candidate or (len(candidate) % 4 == 1):
            return text

        has_urlsafe_chars = ('-' in candidate or '_' in candidate)
        has_std_chars = ('+' in candidate or '/' in candidate)
        if has_urlsafe_chars and has_std_chars:
            return text

        padded = candidate + ('=' * ((4 - (len(candidate) % 4)) % 4))
        if has_urlsafe_chars:
            if not _URLSAFE_B64_RE.match(padded):
                return text
            decoded_bytes = base64.urlsafe_b64decode(padded.encode('ascii'))
        else:
            if not _STD_B64_RE.match(padded):
                return text
            decoded_bytes = base64.b64decode(padded.encode('ascii'), validate=True)

        decoded_str = decoded_bytes.decode('utf-8')
        if _DISALLOWED_CTRL_RE.search(decoded_str):
            return text
        return decoded_str + at + name
    except Exception:
        return text


def _unescape_batch_node(text: str) -> str:
    """Single-pass symmetrical unescape for batch-encoded node URIs ('\\\\' -> '\\', '\\|' -> '|')."""
    if '\\' not in text:
        return text
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '\\' and i + 1 < n and text[i + 1] in ('\\', '|'):
            out.append(text[i + 1])
            i += 2
        else:
            out.append(ch)
            i += 1
    return ''.join(out)


def split_node_and_remarks(item: str) -> Tuple[str, str]:
    """
    Split a batch line '<node>|<remarks>' without truncating '|' inside node URIs.
    - Symmetrical escaping for batch round-trips: '\\\\' -> '\\', '\\|' -> '|'.
    - Single-pass scan finds the last unescaped '|'.
    - Inside URI '#fragment', protects both balanced-bracket pipes ('#🇭🇰【香港 | BGP】')
      and space-padded visual separators ('#HK | IEPL | 01') when no trailing '|remarks' is appended.
    """
    if not isinstance(item, str):
        return '', ''
    raw = item.strip()
    if not raw:
        return '', ''

    # Single-pass scan: skip escaped '\\' / '\|' pairs and record the last unescaped '|'
    split_idx = -1
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch == '\\' and i + 1 < n and raw[i + 1] in ('\\', '|'):
            i += 2
            continue
        if ch == '|':
            split_idx = i
        i += 1

    if split_idx == -1:
        return _unescape_batch_node(raw).strip(), ''

    left = raw[:split_idx]
    right = raw[split_idx + 1:]

    # Protect literal '|' inside URI '#fragment' (balanced brackets or space-padded ' | ' separators)
    if '#' in left:
        frag_prefix = left.split('#', 1)[1]
        for open_br, close_br in _BRACKET_PAIRS:
            if frag_prefix.count(open_br) > frag_prefix.count(close_br) and close_br in right:
                return _unescape_batch_node(raw).strip(), ''
        if left.endswith((' ', '\t')) and right.startswith((' ', '\t')):
            return _unescape_batch_node(raw).strip(), ''

    node = _unescape_batch_node(left).strip()
    remarks = right.strip()
    return node, remarks


def redact_uri_credentials(text: Any) -> str:
    """Redact credentials, tokens, and opaque proxy payloads before writing URIs to logs."""
    raw = str(text or '').strip()
    if not raw:
        return ''
    if '://' not in raw:
        return raw[:48] + ('...' if len(raw) > 48 else '')

    try:
        parsed = urllib.parse.urlsplit(raw)
        scheme = (parsed.scheme or '').lower()
        netloc = parsed.netloc
        path = parsed.path
        query = parsed.query

        if scheme in _OPAQUE_CRED_SCHEMES and '@' not in netloc:
            return f'{scheme}://<redacted>'

        if '@' in netloc:
            _, _, host_port = netloc.rpartition('@')
            safe_netloc = f'***@{host_port}'
        else:
            safe_netloc = netloc

        safe_path = path
        if scheme in ('http', 'https') and path:
            segments = path.split('/')
            safe_segments = ['***' if len(seg) >= 20 else seg for seg in segments]
            safe_path = '/'.join(safe_segments)

        safe_query = ''
        if query:
            pairs = urllib.parse.parse_qsl(query, keep_blank_values=True)
            redacted_pairs = []
            for k, v in pairs:
                if k.lower() in _SENSITIVE_QUERY_KEYS or scheme in ('http', 'https'):
                    redacted_pairs.append((k, '***'))
                else:
                    redacted_pairs.append((k, v))
            safe_query = urllib.parse.urlencode(redacted_pairs)

        return urllib.parse.urlunsplit((scheme, safe_netloc, safe_path, safe_query, ''))
    except Exception:
        scheme = raw.split('://', 1)[0].lower()
        return f'{scheme}://<redacted>'


def check_yaml_safe_aliases(
    text: str,
    max_aliases: int = 100,
    max_expanded_nodes: int = 50000,
) -> None:
    """
    Guard against YAML Billion Laughs / anchor-alias expansion DoS before yaml.safe_load().
    Uses streaming yaml.parse() without expanding aliases to compute exact expanded node weight.
    """
    anchor_direct_nodes: Dict[str, int] = {}
    anchor_alias_refs: Dict[str, List[str]] = {}
    # Stack entries: (anchor_name_or_None, direct_node_count, referenced_alias_names)
    container_stack: List[Tuple[Any, int, List[str]]] = []
    root_direct_nodes = 0
    root_alias_refs: List[str] = []
    total_alias_events = 0

    for event in yaml.parse(text):
        if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
            container_stack.append((event.anchor, 1, []))
        elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
            if not container_stack:
                continue
            anchor, node_count, alias_refs = container_stack.pop()
            if anchor:
                anchor_direct_nodes[anchor] = node_count
                anchor_alias_refs[anchor] = list(alias_refs)
            if container_stack:
                p_anchor, p_count, p_refs = container_stack[-1]
                container_stack[-1] = (p_anchor, p_count + node_count, p_refs + alias_refs)
            else:
                root_direct_nodes += node_count
                root_alias_refs.extend(alias_refs)
        elif isinstance(event, yaml.ScalarEvent):
            if event.anchor:
                anchor_direct_nodes[event.anchor] = 1
                anchor_alias_refs[event.anchor] = []
            if container_stack:
                p_anchor, p_count, p_refs = container_stack[-1]
                container_stack[-1] = (p_anchor, p_count + 1, p_refs)
            else:
                root_direct_nodes += 1
        elif isinstance(event, yaml.AliasEvent):
            total_alias_events += 1
            if total_alias_events > max_aliases:
                raise yaml.YAMLError(f'YAML 锚点引用次数超过安全限制 ({max_aliases})')
            if container_stack:
                p_anchor, p_count, p_refs = container_stack[-1]
                p_refs.append(event.anchor)
                container_stack[-1] = (p_anchor, p_count, p_refs)
            else:
                root_alias_refs.append(event.anchor)

    if total_alias_events == 0:
        return

    memo: Dict[str, int] = {}
    visiting: Set[str] = set()

    def expanded_weight(anchor_name: str) -> int:
        if anchor_name in memo:
            return memo[anchor_name]
        if anchor_name in visiting:
            raise yaml.YAMLError('YAML 存在循环锚点引用')
        if anchor_name not in anchor_direct_nodes:
            return 1
        visiting.add(anchor_name)
        weight = anchor_direct_nodes[anchor_name]
        for ref in anchor_alias_refs.get(anchor_name, ()):
            weight += expanded_weight(ref)
            if weight > max_expanded_nodes:
                raise yaml.YAMLError('YAML 锚点展开规模超过安全限制')
        visiting.remove(anchor_name)
        memo[anchor_name] = weight
        return weight

    total_weight = root_direct_nodes
    for ref in root_alias_refs:
        total_weight += expanded_weight(ref)
        if total_weight > max_expanded_nodes:
            raise yaml.YAMLError('YAML 锚点展开规模超过安全限制')


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


def is_valid_node_uri(node: Any) -> bool:
    """Validate that node is a URI string with an allowed protocol scheme."""
    if not isinstance(node, str):
        return False
    stripped = node.strip()
    if '://' not in stripped:
        return False
    scheme, _, rest = stripped.partition('://')
    return scheme.lower() in subname_list and bool(rest.strip())


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
