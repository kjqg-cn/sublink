import base64
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import create_access_token

from app import view
from app.exts import db, jwtmanager
from app.model import Sub


class SingBoxEncodeTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_dir = os.path.join(self.temp_dir.name, 'db')
        os.mkdir(db_dir)
        template_path = os.path.join(os.path.dirname(view.path), 'app', 'sing-box.json')
        with open(template_path, 'r', encoding='utf-8') as source:
            template = source.read()
        with open(os.path.join(db_dir, 'sing-box.json'), 'w', encoding='utf-8') as target:
            target.write(template)

    def tearDown(self):
        self.temp_dir.cleanup()

    def encode(self, nodes):
        subs = [SimpleNamespace(node=node) for node in nodes]
        with patch.object(view, 'path', self.temp_dir.name):
            return json.loads(view.singbox_encode(subs))

    def test_empty_subscription_uses_direct_fallback(self):
        config = self.encode([])
        groups = {
            outbound['tag']: outbound
            for outbound in config['outbounds']
            if outbound['type'] in ('selector', 'urltest')
        }

        self.assertEqual(groups['auto-select']['outbounds'], ['direct'])
        self.assertIn('direct', groups['proxy']['outbounds'])

    def test_supported_nodes_are_converted_to_native_outbounds(self):
        vmess_data = {
            'v': '2',
            'ps': 'VMess',
            'add': 'vmess.example.com',
            'port': '443',
            'id': '11111111-1111-1111-1111-111111111111',
            'aid': '0',
            'scy': 'auto',
            'net': 'ws',
            'type': 'none',
            'host': 'cdn.example.com',
            'path': '/vmess',
            'tls': 'tls',
        }
        vmess = base64.b64encode(json.dumps(vmess_data).encode()).decode()
        nodes = [
            'vless://00000000-0000-0000-0000-000000000000@vless.example.com:443'
            '?security=reality&sni=www.example.com&fp=chrome'
            '&pbk=f7efia-jZY36DI77N2nGUIPtdCvI_bVD2qhJxPzmrzg&sid=0123'
            '&type=ws&path=%2Fvless&host=cdn.example.com#VLESS',
            f'vmess://{vmess}',
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388#SS',
            'trojan://password@trojan.example.com:443?sni=trojan.example.com'
            '&type=ws&path=%2Ftrojan&host=cdn.example.com#Trojan',
            'hysteria://hy.example.com:443?auth=password&upmbps=100&downmbps=200'
            '&peer=hy.example.com#Hysteria',
            'hysteria2://password@hy2.example.com:443?sni=hy2.example.com'
            '&obfs=salamander&obfs-password=secret#Hysteria2',
        ]

        config = self.encode(nodes)
        outbounds = {outbound['tag']: outbound for outbound in config['outbounds']}

        self.assertEqual(outbounds['VLESS']['server_port'], 443)
        self.assertEqual(outbounds['VLESS']['transport']['type'], 'ws')
        self.assertTrue(outbounds['VLESS']['tls']['reality']['enabled'])
        self.assertEqual(outbounds['VMess']['type'], 'vmess')
        self.assertEqual(outbounds['VMess']['transport']['path'], '/vmess')
        self.assertEqual(outbounds['SS']['type'], 'shadowsocks')
        self.assertEqual(outbounds['Trojan']['tls']['server_name'], 'trojan.example.com')
        self.assertEqual(outbounds['Hysteria']['up_mbps'], 100)
        self.assertEqual(outbounds['Hysteria2']['obfs']['type'], 'salamander')

    def test_duplicate_names_are_made_unique_and_ssr_is_skipped(self):
        proxy = {
            'name': 'duplicate',
            'server': 'example.com',
            'port': 443,
            'uuid': '00000000-0000-0000-0000-000000000000',
            'tls': False,
        }
        nodes = [
            'vless://first',
            'vless://second',
            'ssr://unsupported',
        ]

        with patch.object(view, 'parse_singbox_node', return_value=proxy):
            config = self.encode(nodes)

        tags = [outbound['tag'] for outbound in config['outbounds']]
        self.assertIn('duplicate', tags)
        self.assertIn('duplicate (2)', tags)
        self.assertFalse(any(outbound['type'] == 'ssr' for outbound in config['outbounds']))

    def test_hysteria_without_bandwidth_is_skipped(self):
        node = 'hysteria://hy.example.com:443?auth=password&peer=hy.example.com#Hysteria'

        config = self.encode([node])

        self.assertFalse(any(outbound['type'] == 'hysteria' for outbound in config['outbounds']))
        groups = {outbound['tag']: outbound for outbound in config['outbounds']}
        self.assertEqual(groups['auto-select']['outbounds'], ['direct'])

    def test_grpc_plugin_and_tls_options_are_mapped(self):
        nodes = [
            'vless://00000000-0000-0000-0000-000000000000@vless.example.com:443'
            '?security=tls&sni=vless.example.com&type=grpc&serviceName=vless-grpc'
            '&alpn=h2&insecure=1#VLESS-gRPC',
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            '?plugin=v2ray-plugin%3Btls%3Bhost%3Dcdn.example.com#SS-plugin',
            'trojan://password@trojan.example.com:443?sni=trojan.example.com'
            '&type=grpc&serviceName=trojan-grpc#Trojan-gRPC',
        ]

        config = self.encode(nodes)
        outbounds = {outbound['tag']: outbound for outbound in config['outbounds']}

        self.assertEqual(outbounds['VLESS-gRPC']['transport']['service_name'], 'vless-grpc')
        self.assertEqual(outbounds['VLESS-gRPC']['tls']['alpn'], ['h2'])
        self.assertTrue(outbounds['VLESS-gRPC']['tls']['insecure'])
        self.assertEqual(outbounds['SS-plugin']['plugin'], 'v2ray-plugin')
        self.assertEqual(outbounds['SS-plugin']['plugin_opts'], 'tls;host=cdn.example.com')
        self.assertEqual(outbounds['Trojan-gRPC']['transport']['service_name'], 'trojan-grpc')

    def test_query_vmess_without_alter_id_defaults_to_zero(self):
        credentials = base64.b64encode(
            b'auto:11111111-1111-1111-1111-111111111111@vmess.example.com:443'
        ).decode()
        node = f'vmess://{credentials}?remarks=VMess-query&tls=tls'

        config = self.encode([node])
        outbound = next(item for item in config['outbounds'] if item.get('tag') == 'VMess-query')

        self.assertEqual(outbound['alter_id'], 0)

    def test_template_validation_rejects_invalid_outbounds(self):
        with self.assertRaisesRegex(ValueError, '只能包含 JSON 对象'):
            view.validate_singbox_template({'outbounds': [None]})

        with self.assertRaisesRegex(ValueError, '不能重复'):
            view.validate_singbox_template({
                'outbounds': [
                    {'type': 'direct', 'tag': 'direct'},
                    {'type': 'selector', 'tag': 'direct', 'outbounds': ['auto']},
                ]
            })

    def test_remote_subscription_is_expanded(self):
        remote_node = 'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388#Remote'
        with patch.object(view, 'fetch_remote_sub', return_value=[remote_node]):
            config = self.encode(['https://subscription.example.com/list'])

        tags = [outbound['tag'] for outbound in config['outbounds']]
        self.assertIn('Remote', tags)

    def test_subscription_endpoint_returns_json_profile(self):
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['JWT_SECRET_KEY'] = 'test-secret'
        db.init_app(app)
        jwtmanager.init_app(app)
        app.register_blueprint(view.blue)

        with app.app_context():
            db.create_all()
            db.session.add(Sub(
                name='sing-box-test',
                node='ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388#Endpoint',
                remarks='',
                sort_order=0,
                access_token='test-token',
                legacy_enabled=False,
            ))
            db.session.commit()

            with patch.object(view, 'path', self.temp_dir.name):
                client = app.test_client()
                response = client.get('/sub/sing-box/test-token')
                token = create_access_token(identity='test-user')
                headers = {'Authorization': f'Bearer {token}'}
                read_response = client.post('/singbox_config', json={'index': 'read'}, headers=headers)
                invalid_response = client.post(
                    '/singbox_config',
                    json={'index': 'save', 'text': '{"outbounds":[null]}'},
                    headers=headers,
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/json')
        config = json.loads(response.data)
        self.assertTrue(any(outbound.get('tag') == 'Endpoint' for outbound in config['outbounds']))
        self.assertEqual(read_response.get_json()['code'], 200)
        self.assertEqual(invalid_response.status_code, 200)
        self.assertEqual(invalid_response.get_json()['code'], 400)

    def test_legacy_download_detour_uniform_migrated_to_default_http_client(self):
        legacy_template = {
            'outbounds': [
                {'type': 'selector', 'tag': 'proxy', 'outbounds': ['auto', 'direct']},
                {'type': 'direct', 'tag': 'direct'},
            ],
            'route': {
                'final': 'proxy',
                'rule_set': [
                    {
                        'type': 'remote',
                        'tag': 'geosite-cn',
                        'format': 'binary',
                        'url': 'https://example.com/geosite-cn.srs',
                        'download_detour': 'proxy',
                    },
                    {
                        'type': 'remote',
                        'tag': 'geoip-cn',
                        'format': 'binary',
                        'url': 'https://example.com/geoip-cn.srs',
                        'download_detour': 'proxy',
                    },
                ],
            },
        }
        with open(os.path.join(self.temp_dir.name, 'db', 'sing-box.json'), 'w', encoding='utf-8') as f:
            json.dump(legacy_template, f)

        config = self.encode([])
        self.assertEqual(config['http_clients'], [{'tag': 'remote-client', 'detour': 'proxy'}])
        self.assertEqual(config['route']['default_http_client'], 'remote-client')
        for rs in config['route']['rule_set']:
            self.assertNotIn('download_detour', rs)
            self.assertNotIn('http_client', rs)

    def test_legacy_download_detour_mixed_and_implicit_default_migrated(self):
        mixed_template = {
            'outbounds': [
                {'type': 'selector', 'tag': 'proxy', 'outbounds': ['auto', 'direct']},
                {'type': 'direct', 'tag': 'direct'},
            ],
            'route': {
                'final': 'proxy',
                'rule_set': [
                    {
                        'type': 'remote',
                        'tag': 'rs-proxy',
                        'format': 'binary',
                        'url': 'https://example.com/a.srs',
                        'download_detour': 'proxy',
                    },
                    {
                        'type': 'remote',
                        'tag': 'rs-direct',
                        'format': 'binary',
                        'url': 'https://example.com/b.srs',
                        'download_detour': 'direct',
                    },
                    {
                        'type': 'remote',
                        'tag': 'rs-implicit',
                        'format': 'binary',
                        'url': 'https://example.com/c.srs',
                    },
                ],
            },
        }
        with open(os.path.join(self.temp_dir.name, 'db', 'sing-box.json'), 'w', encoding='utf-8') as f:
            json.dump(mixed_template, f)

        config = self.encode([])
        clients = {c['tag']: c['detour'] for c in config['http_clients']}
        self.assertEqual(clients, {'remote-client': 'proxy', 'remote-client-direct': 'direct'})
        self.assertEqual(config['route']['default_http_client'], 'remote-client')
        by_tag = {rs['tag']: rs for rs in config['route']['rule_set']}
        for rs in by_tag.values():
            self.assertNotIn('download_detour', rs)
        self.assertEqual(by_tag['rs-proxy']['http_client'], 'remote-client')
        self.assertEqual(by_tag['rs-direct']['http_client'], 'remote-client-direct')
        self.assertNotIn('http_client', by_tag['rs-implicit'])

    def test_vless_reality_normalization_flow_fp_short_id_and_insecure(self):
        import yaml

        # 1. Mixed-case query keys, type=raw -> tcp, flow udp443 -> vision, fp=none -> firefox, scientific short-id
        raw_reality = (
            'vless://00000000-0000-0000-0000-000000000001@1.2.3.4:443'
            '?Encryption=none&Flow=xtls-rprx-vision-udp443&Security=REALITY'
            '&SNI=www.example.com&FP=none&PBK=pubkey123&SID=1e234567'
            '&Type=raw&insecure=1#RealityRaw'
        )
        # 2. User-like standard TCP Reality with fp=firefox & flow=xtls-rprx-vision
        std_reality = (
            'vless://00000000-0000-0000-0000-000000000002@1.2.3.4:443'
            '?encryption=none&flow=xtls-rprx-vision&security=reality'
            '&sni=www.domain.com&fp=firefox&pbk=pubkey456&sid=0123'
            '&spx=%2Fxxx&type=tcp&headerType=none#RealityStd'
        )
        # 3. Non-TCP (gRPC) Reality with stray flow must strip flow
        grpc_reality = (
            'vless://00000000-0000-0000-0000-000000000003@1.2.3.4:443'
            '?flow=xtls-rprx-vision&security=reality&sni=www.example.com'
            '&pbk=pubkey789&type=grpc&serviceName=svc#RealityGrpc'
        )
        # 4. Plain TLS VLESS with fp=none must omit uTLS rather than forcing firefox
        tls_no_fp = (
            'vless://00000000-0000-0000-0000-000000000004@1.2.3.4:443'
            '?security=tls&sni=tls.example.com&fp=none&type=tcp#TlsNoFp'
        )

        # Prepare minimal Clash template in temp db dir
        clash_tpl = (
            'proxies:\n\nproxy-groups:\n  - name: select\n    type: select\n    proxies:\n      - auto\n'
        )
        with open(os.path.join(self.temp_dir.name, 'db', 'clash.yaml'), 'w', encoding='utf-8') as f:
            f.write(clash_tpl)

        subs = [SimpleNamespace(node=n) for n in (raw_reality, std_reality, grpc_reality, tls_no_fp)]
        with patch.object(view, 'path', self.temp_dir.name):
            clash_text = view.clash_encode(subs)
            clash_data = yaml.safe_load(clash_text)
            sb_data = json.loads(view.singbox_encode(subs))

        # Raw YAML must explicitly quote short-id so Go yaml.v3 never parses 1e234567 as float or 0123 as int
        self.assertIn("short-id: '1e234567'", clash_text)
        self.assertIn("short-id: '0123'", clash_text)

        clash_by_name = {p['name']: p for p in clash_data['proxies']}
        self.assertEqual(clash_by_name['RealityRaw']['network'], 'tcp')
        self.assertEqual(clash_by_name['RealityRaw']['flow'], 'xtls-rprx-vision')
        self.assertEqual(clash_by_name['RealityRaw']['client-fingerprint'], 'firefox')
        self.assertEqual(clash_by_name['RealityRaw']['servername'], 'www.example.com')
        self.assertEqual(clash_by_name['RealityRaw']['reality-opts'], {
            'public-key': 'pubkey123',
            'short-id': '1e234567',
        })
        self.assertEqual(clash_by_name['RealityStd']['flow'], 'xtls-rprx-vision')
        self.assertEqual(clash_by_name['RealityStd']['client-fingerprint'], 'firefox')
        self.assertNotIn('flow', clash_by_name['RealityGrpc'])
        self.assertEqual(clash_by_name['RealityGrpc']['client-fingerprint'], 'firefox')
        self.assertNotIn('client-fingerprint', clash_by_name['TlsNoFp'])

        sb_by_tag = {o['tag']: o for o in sb_data['outbounds']}
        self.assertEqual(sb_by_tag['RealityRaw']['flow'], 'xtls-rprx-vision')
        self.assertFalse(sb_by_tag['RealityRaw']['tls']['insecure'])
        self.assertEqual(sb_by_tag['RealityRaw']['tls']['utls'], {'enabled': True, 'fingerprint': 'firefox'})
        self.assertEqual(sb_by_tag['RealityRaw']['tls']['reality'], {
            'enabled': True,
            'public_key': 'pubkey123',
            'short_id': '1e234567',
        })
        self.assertEqual(sb_by_tag['RealityStd']['flow'], 'xtls-rprx-vision')
        self.assertEqual(sb_by_tag['RealityStd']['tls']['utls']['fingerprint'], 'firefox')
        self.assertNotIn('flow', sb_by_tag['RealityGrpc'])
        self.assertEqual(sb_by_tag['RealityGrpc']['tls']['utls'], {'enabled': True, 'fingerprint': 'firefox'})
        self.assertNotIn('utls', sb_by_tag['TlsNoFp']['tls'])


if __name__ == '__main__':
    unittest.main()
