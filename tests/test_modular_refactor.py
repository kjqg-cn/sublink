"""Tests for modular architecture refactoring."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import config_manager, view
from app.config_manager import (
    APP_DIR,
    CustomFeature,
    CustomLoopback,
    CustomNodeName,
    Emoji,
    SkipCert,
    Udp,
    get_runtime_config,
    load_config,
    sync_config_globals,
)
from app.core import generator, parsers, rewrite, utils
from app.core.generator import (
    clash_encode,
    expand_node_list,
    inject_surge_proxies,
    parse_clash_node,
    parse_surge_node,
    singbox_encode,
    surge_encode,
    v2ray_encode,
)
from app.core.parsers import (
    NodeParse,
    parse_hysteria,
    parse_hysteria2,
    parse_ss,
    parse_ssr,
    parse_trojan,
    parse_vless,
    parse_vmess,
)
from app.core.rewrite import (
    node_name_rewrite_rules,
    rewrite_loopback_node,
    rewrite_node_name,
    rewrite_remote_node,
)
from app.core.utils import (
    decode_base64_if,
    decode_base64_if_emoji,
    encode_base64,
    get_host_port,
    get_proxy_type,
    if_ipv6_address,
    is_truthy,
    new_access_token,
    parse_server_port,
)


class ModularArchitectureTest(unittest.TestCase):
    def test_utils_functions(self):
        self.assertEqual(if_ipv6_address('[2001:db8::1]'), '2001:db8::1')
        self.assertEqual(if_ipv6_address('192.168.1.1'), '192.168.1.1')

        host, port = parse_server_port('[2001:db8::1]:8443')
        self.assertEqual(host, '2001:db8::1')
        self.assertEqual(port, 8443)

        host, port = parse_server_port('example.com:443')
        self.assertEqual(host, 'example.com')
        self.assertEqual(port, 443)

        self.assertEqual(get_host_port('2001:db8::1', 443), '[2001:db8::1]:443')
        self.assertEqual(get_host_port('1.1.1.1', 80), '1.1.1.1:80')

        self.assertEqual(get_proxy_type('vless://uuid@host:443'), 'vless')
        self.assertEqual(get_proxy_type('HY2://pass@host:443'), 'hy2')

        token = new_access_token()
        self.assertEqual(len(token), 48)

        self.assertTrue(is_truthy('yes'))
        self.assertTrue(is_truthy(1))
        self.assertFalse(is_truthy('0'))
        self.assertFalse(is_truthy('false'))

    def test_rewrite_rules_preserve_hyphen_prefixes(self):
        for keywords, _ in node_name_rewrite_rules:
            for kw in keywords:
                self.assertTrue(kw.startswith('-'), f"Rule keyword '{kw}' must retain '-' prefix")

    def test_module_proxy_synchronization(self):
        orig = config_manager.CustomFeature
        orig_path = config_manager.path
        try:
            # 1. view -> config_manager sync
            view.CustomFeature = True
            self.assertTrue(config_manager.CustomFeature)
            self.assertTrue(view.CustomFeature)

            view.CustomFeature = False
            self.assertFalse(config_manager.CustomFeature)
            self.assertFalse(view.CustomFeature)

            # 2. config_manager -> view reverse sync
            config_manager.CustomFeature = True
            self.assertTrue(view.CustomFeature)

            config_manager.CustomFeature = False
            self.assertFalse(view.CustomFeature)

            # 3. path synchronization
            config_manager.path = '/temp/sync_test_path'
            self.assertEqual(view.path, '/temp/sync_test_path')

            view.path = orig_path
            self.assertEqual(config_manager.path, orig_path)
            self.assertEqual(view.path, orig_path)
        finally:
            config_manager.CustomFeature = orig
            view.CustomFeature = orig
            config_manager.path = orig_path
            view.path = orig_path

    def test_generator_module_level_pure_functions(self):
        # Empty/unsupported returns None without crashing
        self.assertIsNone(parse_clash_node(''))
        self.assertIsNone(parse_clash_node('unknown://test'))
        self.assertIsNone(parse_surge_node(''))
        self.assertIsNone(parse_surge_node('vless://unsupported-in-surge'))

        # Valid nodes return proper structures
        ss_node = 'ss://' + utils.encode_base64('aes-128-gcm:pass', urlsafe=True) + '@1.2.3.4:8388#MySS'
        clash_proxy = parse_clash_node(ss_node)
        self.assertIsNotNone(clash_proxy)
        self.assertEqual(clash_proxy['name'], 'MySS')
        self.assertEqual(clash_proxy['type'], 'ss')

        surge_result = parse_surge_node(ss_node)
        self.assertIsNotNone(surge_result)
        line, name = surge_result
        self.assertEqual(name, 'MySS')
        self.assertTrue(line.startswith('MySS = ss,'))

    def test_inject_surge_proxies(self):
        tmpl = "[General]\nloglevel = notify\n[Proxy]\nDIRECT = direct\n[Proxy Group]\n"
        res = inject_surge_proxies(tmpl, ['Node1 = ss, 1.1.1.1, 443'])
        self.assertIn('[Proxy]\nNode1 = ss, 1.1.1.1, 443\nDIRECT = direct', res)

        # Missing [Proxy] section returns template gracefully
        no_proxy_tmpl = "[General]\nloglevel = notify"
        self.assertEqual(inject_surge_proxies(no_proxy_tmpl, ['Node1']), no_proxy_tmpl)

    def test_v2ray_encode(self):
        subs = [
            SimpleNamespace(node='vless://uuid@1.1.1.1:443#node1'),
            SimpleNamespace(node='vmess://uuid@1.1.1.2:443#node2'),
        ]
        b64_output = v2ray_encode(subs)
        decoded = utils.decode_base64_if(b64_output)
        self.assertIn('vless://uuid@1.1.1.1:443#node1', decoded)
        self.assertIn('vmess://uuid@1.1.1.2:443#node2', decoded)

    def test_parsers_direct_invocation(self):
        vless_node = 'vless://uuid123@myserver.com:443?type=ws&security=reality&pbk=pubkey123#MyVless'
        proxy = parse_vless(vless_node)
        self.assertEqual(proxy['name'], 'MyVless')
        self.assertEqual(proxy['uuid'], 'uuid123')
        self.assertEqual(proxy['server'], 'myserver.com')
        self.assertEqual(proxy['port'], 443)
        self.assertEqual(proxy['reality-opts']['public-key'], 'pubkey123')

        parser = NodeParse(vless_node)
        proxy_via_class = parser.vless()
        self.assertEqual(proxy_via_class, proxy)

    def test_mocking_view_node_parse_propagates(self):
        mock_parser = MagicMock()
        mock_parser.return_value.ss.return_value = {
            'name': 'MockSSNode', 'type': 'ss', 'server': '1.2.3.4', 'port': 443,
            'cipher': 'aes-128-gcm', 'password': 'pass', 'tfo': False, 'udp': False,
        }
        sub = SimpleNamespace(node='ss://test')
        with patch.object(view, 'NodeParse', mock_parser):
            clash_out = view.clash_encode([sub])
            self.assertTrue(mock_parser.called)
            self.assertIn('MockSSNode', clash_out)

    def test_mocking_view_rewrite_remote_node_propagates(self):
        mock_rewrite = MagicMock(return_value='vless://rewritten-by-mock')
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = 'vless://original-node'
        with patch('requests.get', return_value=mock_resp), \
                patch.object(view, 'rewrite_remote_node', mock_rewrite):
            nodes = view.fetch_remote_sub('https://example.com/sub')
            self.assertTrue(mock_rewrite.called)
            self.assertEqual(nodes, ['vless://rewritten-by-mock'])


if __name__ == '__main__':
    unittest.main()
