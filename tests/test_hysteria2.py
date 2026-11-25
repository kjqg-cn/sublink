import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from app import view
from app.core.generator import get_singbox_bandwidth, get_singbox_outbound, parse_surge_node
from app.core.parsers import parse_hysteria, parse_hysteria2


VALID_SHA256_UPPER = '9A63E05CCED113283D090B274A08AE4F817F962F7DE8456F3B1013844F2065E6'
VALID_SHA256_COLON = ':'.join(VALID_SHA256_UPPER[i:i + 2] for i in range(0, 64, 2))
VALID_SHA256_LOWER = VALID_SHA256_UPPER.lower()

SURGE_TEMPLATE = """[Proxy]
DIRECT = direct

[Proxy Group]
manual = select,auto
"""

CLASH_TEMPLATE = """proxies:

proxy-groups:
  - name: select
    type: select
    proxies:
      - auto
"""


class Hysteria2HandlingTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_dir = os.path.join(self.temp_dir.name, 'db')
        os.mkdir(db_dir)

        sb_template_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'app', 'sing-box.json')
        )
        with open(sb_template_path, 'r', encoding='utf-8') as src:
            with open(os.path.join(db_dir, 'sing-box.json'), 'w', encoding='utf-8') as dst:
                dst.write(src.read())
        with open(os.path.join(db_dir, 'clash.yaml'), 'w', encoding='utf-8') as dst:
            dst.write(CLASH_TEMPLATE)
        with open(os.path.join(db_dir, 'surge.conf'), 'w', encoding='utf-8') as dst:
            dst.write(SURGE_TEMPLATE)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_hysteria_and_hysteria2_no_utls_fingerprint_or_redundant_auth(self):
        hy1 = parse_hysteria('hysteria://hy1.example.com:443?auth=pw&upmbps=50&downmbps=100#Hy1')
        hy2 = parse_hysteria2('hysteria2://pw@hy2.example.com:443?sni=hy2.example.com#Hy2')

        self.assertNotIn('client-fingerprint', hy1)
        self.assertNotIn('client-fingerprint', hy2)
        self.assertNotIn('auth', hy2)
        self.assertEqual(hy2['password'], 'pw')

    def test_parse_hysteria2_password_unquote_base64_like_and_extra_path(self):
        encoded_pwd = parse_hysteria2('hysteria2://user%3Apass%401%2F2@hy2.example.com:443#Encoded')
        b64_like_pwd = parse_hysteria2('hysteria2://AAAA@hy2.example.com:443#Base64Like')
        with_path = parse_hysteria2('hysteria2://pw@hy2.example.com/extra/path?sni=hy2.example.com#WithPath')

        self.assertEqual(encoded_pwd['password'], 'user:pass@1/2')
        self.assertEqual(b64_like_pwd['password'], 'AAAA')
        self.assertEqual(with_path['server'], 'hy2.example.com')
        self.assertEqual(with_path['port'], 443)

    def test_parse_hysteria2_aliases_pin_ports_hop_bandwidth_and_gecko(self):
        node = (
            'hy2://secret@hy2.example.com:443'
            '?peer=tls.example.com&allowInsecure=1&up=50mbps&down=1gbps'
            '&obfs=Gecko&obfs-password=geckopass&min_packet_size=512&max_packet_size=1200'
            '&mport=20000-50000,8080&hop-interval=10s-20s'
            f'&pinSHA256=SHA256:{VALID_SHA256_COLON}#FullHy2'
        )
        proxy = parse_hysteria2(node)

        self.assertEqual(proxy['sni'], 'tls.example.com')
        self.assertTrue(proxy['skip-cert-verify'])
        self.assertEqual(proxy['up'], '50 Mbps')
        self.assertEqual(proxy['down'], '1 Gbps')
        self.assertEqual(proxy['obfs'], 'gecko')
        self.assertEqual(proxy['obfs-password'], 'geckopass')
        self.assertEqual(proxy['obfs-min-packet-size'], 512)
        self.assertEqual(proxy['obfs-max-packet-size'], 1200)
        self.assertEqual(proxy['ports'], '20000-50000,8080')
        self.assertEqual(proxy['hop-interval'], '10-20')
        self.assertEqual(proxy['fingerprint'], VALID_SHA256_LOWER)

    def test_parse_hysteria2_drops_invalid_obfs_gecko_range_and_malformed_pin(self):
        # Missing obfs-password -> omit obfs entirely (prevents Mihomo rejection)
        no_pwd = parse_hysteria2('hysteria2://pw@hy2.example.com:443?obfs=salamander#NoObfsPwd')
        self.assertNotIn('obfs', no_pwd)
        self.assertNotIn('obfs-password', no_pwd)

        # Unknown obfs type -> omit (prevents Mihomo & sing-box rejection)
        bad_obfs = parse_hysteria2('hysteria2://pw@hy2.example.com:443?obfs=plain&obfs-password=abc#BadObfs')
        self.assertNotIn('obfs', bad_obfs)
        self.assertNotIn('obfs-password', bad_obfs)

        # Malformed/short pinSHA256 -> omit fingerprint (prevents Mihomo rejection)
        bad_pin = parse_hysteria2('hysteria2://pw@hy2.example.com:443?pinSHA256=deadbeef#BadPin')
        self.assertNotIn('fingerprint', bad_pin)

        # Invalid Gecko packet size ranges (min > default max 1200; max < default min 512; max > 2048)
        g_min_too_big = parse_hysteria2(
            'hysteria2://pw@hy2.example.com:443?obfs=gecko&obfs-password=abc&min_packet_size=1500#G1'
        )
        g_max_too_small = parse_hysteria2(
            'hysteria2://pw@hy2.example.com:443?obfs=gecko&obfs-password=abc&max_packet_size=400#G2'
        )
        g_over_wire = parse_hysteria2(
            'hysteria2://pw@hy2.example.com:443?obfs=gecko&obfs-password=abc&min_packet_size=512&max_packet_size=3000#G3'
        )
        for p in (g_min_too_big, g_max_too_small, g_over_wire):
            self.assertEqual(p['obfs'], 'gecko')
            self.assertNotIn('obfs-min-packet-size', p)
            self.assertNotIn('obfs-max-packet-size', p)

    def test_parse_hysteria2_inline_multiport_ipv4_and_ipv6(self):
        v4_range = parse_hysteria2('hysteria2://pwd@hy2.example.com:20000-20050/?sni=hy2.example.com#Range')
        v4_list = parse_hysteria2('hysteria2://pwd@hy2.example.com:443,20000-20050#List')
        v6_list = parse_hysteria2('hysteria2://pwd@[2001:db8::1]:443,20000-20050#IPv6')

        self.assertEqual(v4_range['server'], 'hy2.example.com')
        self.assertEqual(v4_range['port'], 20000)
        self.assertEqual(v4_range['ports'], '20000-20050')

        self.assertEqual(v4_list['port'], 443)
        self.assertEqual(v4_list['ports'], '443,20000-20050')

        self.assertEqual(v6_list['server'], '2001:db8::1')
        self.assertEqual(v6_list['port'], 443)
        self.assertEqual(v6_list['ports'], '443,20000-20050')

    def test_bandwidth_unit_conversion(self):
        self.assertEqual(get_singbox_bandwidth('100'), 100)
        self.assertEqual(get_singbox_bandwidth('50 Mbps'), 50)
        self.assertEqual(get_singbox_bandwidth('1 Gbps'), 1000)
        self.assertEqual(get_singbox_bandwidth('2000 Kbps'), 2)
        self.assertEqual(get_singbox_bandwidth('10 MBps'), 80)
        self.assertIsNone(get_singbox_bandwidth('0'))
        self.assertIsNone(get_singbox_bandwidth('500 Kbps'))

    def test_singbox_encode_hy2_omits_utls_and_maps_ports_hop_and_gecko(self):
        nodes = [
            'hysteria://hy1.example.com:443?auth=pw1&upmbps=50&downmbps=100&peer=hy1.example.com#Hy1',
            'hysteria2://pw2@hy2.example.com:443?sni=hy2.example.com&alpn=h3'
            '&obfs=gecko&obfs-password=geckopwd&obfs-min-packet-size=512&obfs-max-packet-size=1200'
            f'&mport=20000-20010,8080&hop-interval=10-20&pinSHA256={VALID_SHA256_UPPER}&up=50mbps&down=1gbps#Hy2',
            'vless://00000000-0000-0000-0000-000000000000@vless.example.com:443?security=tls&sni=vless.example.com#VLESS',
        ]
        subs = [SimpleNamespace(node=n) for n in nodes]
        with patch.object(view, 'path', self.temp_dir.name):
            config = json.loads(view.singbox_encode(subs))

        outbounds = {o['tag']: o for o in config['outbounds']}

        self.assertNotIn('utls', outbounds['Hy1']['tls'])
        self.assertNotIn('utls', outbounds['Hy2']['tls'])
        self.assertNotIn('certificate_public_key_sha256', outbounds['Hy2']['tls'])
        self.assertNotIn('certificate_sha256', outbounds['Hy2']['tls'])
        self.assertFalse(outbounds['Hy2']['tls']['insecure'])
        self.assertEqual(outbounds['Hy2']['server_ports'], ['20000:20010', '8080:8080'])
        self.assertEqual(outbounds['Hy2']['hop_interval'], '10s')
        self.assertEqual(outbounds['Hy2']['hop_interval_max'], '20s')
        self.assertEqual(outbounds['Hy2']['obfs'], {
            'type': 'gecko',
            'password': 'geckopwd',
            'min_packet_size': 512,
            'max_packet_size': 1200,
        })
        self.assertEqual(outbounds['Hy2']['up_mbps'], 50)
        self.assertEqual(outbounds['Hy2']['down_mbps'], 1000)
        # Non-QUIC VLESS should still keep uTLS
        self.assertTrue(outbounds['VLESS']['tls']['utls']['enabled'])

    def test_singbox_outbound_strips_utls_and_invalid_obfs_even_if_injected(self):
        outbound = get_singbox_outbound('hysteria2', {
            'server': 'hy2.example.com',
            'port': 443,
            'password': 'pwd',
            'sni': 'hy2.example.com',
            'client-fingerprint': 'chrome',
            'ports': '20000-20010',
            'hop-interval': '2',
            'obfs': 'plain',
            'obfs-password': 'abc',
        }, 'Hy2Manual')

        self.assertNotIn('utls', outbound['tls'])
        self.assertEqual(outbound['hop_interval'], '5s')
        self.assertNotIn('obfs', outbound)

    def test_clash_encode_hysteria2_maps_mihomo_fields(self):
        node = (
            'hysteria2://pw@hy2.example.com:443?sni=hy2.example.com&mport=20000-20010'
            f'&hop-interval=30s&obfs=salamander&obfs-password=obfspw&pinSHA256={VALID_SHA256_COLON}#Hy2Clash'
        )
        with patch.object(view, 'path', self.temp_dir.name):
            data = yaml.safe_load(view.clash_encode([SimpleNamespace(node=node)]))

        proxy = data['proxies'][0]
        self.assertEqual(proxy['type'], 'hysteria2')
        self.assertNotIn('client-fingerprint', proxy)
        self.assertNotIn('auth', proxy)
        self.assertEqual(proxy['ports'], '20000-20010')
        self.assertEqual(proxy['hop-interval'], '30')
        self.assertEqual(proxy['fingerprint'], VALID_SHA256_LOWER)
        self.assertEqual(proxy['obfs'], 'salamander')
        self.assertEqual(proxy['obfs-password'], 'obfspw')

    def test_surge_encode_hysteria2_lowercase_bools_and_extended_fields(self):
        sal_node = (
            'hysteria2://pw@hy2.example.com:443?sni=hy2.example.com&insecure=1'
            '&downmbps=150&obfs=salamander&obfs-password=salpw&mport=20000-20010,8080&hop-interval=30s#Hy2Sal'
        )
        gecko_node = 'hy2://pw@hy2.example.com:443?obfs=gecko&obfs-password=geckopw&down=1gbps#Hy2Gecko'

        line_sal, _ = parse_surge_node(sal_node)
        line_gecko, _ = parse_surge_node(gecko_node)

        self.assertIn('skip-cert-verify=true', line_sal)
        self.assertIn('udp-relay=false', line_sal)
        self.assertIn('sni=hy2.example.com', line_sal)
        self.assertIn('download-bandwidth=150', line_sal)
        self.assertIn('salamander-password=salpw', line_sal)
        self.assertIn('port-hopping=20000-20010;8080', line_sal)
        self.assertIn('port-hopping-interval=30', line_sal)
        self.assertIn('gecko-password=geckopw', line_gecko)
        self.assertIn('download-bandwidth=1000', line_gecko)

    def test_hysteria2_unitless_bandwidth_normalizes_to_mbps_and_pin_fallback(self):
        unitless_node = 'hysteria2://pw@hy2.example.com:443?sni=hy2.example.com&upmbps=100&down=200#Hy2Plain'
        pinned_node = (
            f'hysteria2://pw@hy2.example.com:443?sni=hy2.example.com'
            f'&up=100&down=200&pinSHA256={VALID_SHA256_UPPER}#Hy2Pinned'
        )
        parsed = parse_hysteria2(unitless_node)
        self.assertEqual(parsed['up'], '100 Mbps')
        self.assertEqual(parsed['down'], '200 Mbps')

        with patch.object(view, 'path', self.temp_dir.name):
            clash_raw = view.clash_encode([SimpleNamespace(node=unitless_node)])
            clash_data = yaml.safe_load(clash_raw)
            sb_default = json.loads(view.singbox_encode([
                SimpleNamespace(node=unitless_node),
                SimpleNamespace(node=pinned_node),
            ]))
            sb_fallback = json.loads(view.singbox_encode([
                SimpleNamespace(node=unitless_node),
                SimpleNamespace(node=pinned_node),
            ], hy2_pin_fallback=True))

        self.assertIn('up: 100 Mbps', clash_raw)
        self.assertIn('down: 200 Mbps', clash_raw)
        self.assertEqual(clash_data['proxies'][0]['up'], '100 Mbps')
        self.assertEqual(clash_data['proxies'][0]['down'], '200 Mbps')

        ob_default = {o['tag']: o for o in sb_default['outbounds']}
        self.assertEqual(ob_default['Hy2Plain']['up_mbps'], 100)
        self.assertEqual(ob_default['Hy2Plain']['down_mbps'], 200)
        self.assertFalse(ob_default['Hy2Plain']['tls']['insecure'])
        self.assertFalse(ob_default['Hy2Pinned']['tls']['insecure'])

        ob_fallback = {o['tag']: o for o in sb_fallback['outbounds']}
        self.assertFalse(ob_fallback['Hy2Plain']['tls']['insecure'])
        self.assertEqual(ob_fallback['Hy2Pinned']['up_mbps'], 100)
        self.assertEqual(ob_fallback['Hy2Pinned']['down_mbps'], 200)
        self.assertTrue(ob_fallback['Hy2Pinned']['tls']['insecure'])
        self.assertNotIn('certificate_sha256', ob_fallback['Hy2Pinned']['tls'])
        self.assertNotIn('certificate_public_key_sha256', ob_fallback['Hy2Pinned']['tls'])

        surge_line, _ = parse_surge_node(unitless_node)
        self.assertIn('download-bandwidth=200', surge_line)


if __name__ == '__main__':
    unittest.main()
