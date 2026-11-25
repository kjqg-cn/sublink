"""Comprehensive tests verifying all P0/P1/P2/P3 global review fixes."""

import base64
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask
from flask_jwt_extended import create_access_token
from flask_migrate import upgrade as alembic_upgrade
import requests
import sqlalchemy as sa
import yaml

from app import create_app, view
import app.core.generator as generator
import app.core.rewrite as rewrite
import app.remote as remote
from app.core.parsers import (
    parse_hysteria,
    parse_ss,
    parse_ssr,
    parse_trojan,
    parse_vless,
    parse_vmess,
)
from app.core.utils import decode_base64_if, is_valid_node_uri
from app.exts import db, init_exts
from app.model import Config, Login, Sub, User, create_db, hash_password, is_password_hashed, verify_password
from upgrade_db import (
    CONFIG_SCHEMA_REVISION,
    MIGRATIONS_DIR,
    detect_schema_revision,
    read_schema_state,
    upgrade_database,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _make_test_app(db_uri='sqlite:///:memory:'):
    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    test_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    test_app.config['JWT_SECRET_KEY'] = 'test-global-review-secret-key-at-least-32-bytes'
    init_exts(test_app)
    test_app.register_blueprint(view.blue)
    return test_app


class P0SecurityAndStartupTest(unittest.TestCase):
    def setUp(self):
        view._login_rate_limiter.reset()
        self.app = _make_test_app()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        view._login_rate_limiter.reset()
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_salted_password_hashing_and_legacy_md5_auto_upgrade(self):
        h1 = hash_password('SuperSecret!23')
        h2 = hash_password('SuperSecret!23')
        self.assertNotEqual(h1, h2)
        self.assertTrue(is_password_hashed(h1))
        self.assertTrue(verify_password(h1, 'SuperSecret!23')[0])
        self.assertFalse(verify_password(h1, 'WrongPassword')[0])

        # Legacy unsalted MD5 row auto-upgrades to salted PBKDF2 on successful login
        legacy_md5 = hashlib.md5(b'MyOldPass123').hexdigest()
        with self.app.app_context():
            db.session.add(User(username='legacy_admin', password=legacy_md5, name='管理员'))
            db.session.commit()
            client = self.app.test_client()
            with patch('app.remote.requests.get'):
                res = client.post('/login', json={'username': 'legacy_admin', 'password': 'MyOldPass123'})
            self.assertEqual(res.status_code, 200)
            body = res.get_json()
            self.assertEqual(body['code'], 200)
            self.assertIn('token', body)
            self.assertIn('refresh', body)

            refreshed_user = User.query.filter_by(username='legacy_admin').first()
            self.assertTrue(is_password_hashed(refreshed_user.password))
            self.assertNotEqual(refreshed_user.password, legacy_md5)

    def test_login_rate_limiting_blocks_brute_force_and_resets_on_success(self):
        with self.app.app_context():
            db.session.add(User(username='admin', password=hash_password('Correct#Pass'), name='管理员'))
            db.session.commit()
            client = self.app.test_client()
            with patch.dict(os.environ, {'LOGIN_RATE_LIMIT_MAX_ATTEMPTS': '3', 'LOGIN_RATE_LIMIT_WINDOW': '60'}):
                for _ in range(3):
                    r = client.post('/login', json={'username': 'admin', 'password': 'wrong'})
                    self.assertEqual(r.status_code, 200)
                    self.assertEqual(r.get_json()['code'], 404)

                # 4th attempt should be rate-limited even with correct password
                blocked = client.post('/login', json={'username': 'admin', 'password': 'Correct#Pass'})
                self.assertEqual(blocked.status_code, 429)
                self.assertEqual(blocked.get_json()['code'], 429)
                self.assertIn('Retry-After', blocked.headers)

                # Reset limiter -> valid login succeeds and clears counter
                view._login_rate_limiter.reset()
                with patch('app.remote.requests.get'):
                    ok = client.post('/login', json={'username': 'admin', 'password': 'Correct#Pass'})
                self.assertEqual(ok.status_code, 200)
                self.assertEqual(ok.get_json()['code'], 200)

    def test_set_user_revokes_old_access_and_refresh_tokens_and_refresh_validates_user(self):
        with self.app.app_context():
            db.session.add(User(username='admin', password=hash_password('InitPass1'), name='管理员'))
            db.session.commit()
            client = self.app.test_client()

            with patch('app.remote.requests.get'):
                login_res = client.post('/login', json={'username': 'admin', 'password': 'InitPass1'}).get_json()
            old_access = login_res['token']
            old_refresh = login_res['refresh']

            # Valid refresh returns new access token string on 200
            r_ok = client.post('/refresh', headers={'Authorization': f'Bearer {old_refresh}'})
            self.assertEqual(r_ok.status_code, 200)
            self.assertEqual(len(r_ok.get_data(as_text=True).split('.')), 3)

            # Change password via /set_user -> old access & refresh tokens are immediately revoked
            set_res = client.post(
                '/set_user',
                json={'username': 'admin', 'oldPassword': 'InitPass1', 'newUserName': 'admin', 'password': 'NewStrongPass2!'},
                headers={'Authorization': f'Bearer {old_access}'},
            )
            self.assertEqual(set_res.get_json()['code'], 200)

            self.assertEqual(
                client.post('/get_config', headers={'Authorization': f'Bearer {old_access}'}).status_code,
                401,
            )
            self.assertEqual(
                client.post('/refresh', headers={'Authorization': f'Bearer {old_refresh}'}).status_code,
                401,
            )

            # Deleted user cannot refresh (no HTTP 200 '没获取到')
            with patch('app.remote.requests.get'):
                login2 = client.post('/login', json={'username': 'admin', 'password': 'NewStrongPass2!'}).get_json()
            new_refresh = login2['refresh']
            User.query.delete()
            db.session.commit()
            r_deleted = client.post('/refresh', headers={'Authorization': f'Bearer {new_refresh}'})
            self.assertEqual(r_deleted.status_code, 401)
            self.assertNotIn('没获取到', r_deleted.get_data(as_text=True))

    def test_run_py_no_hardcoded_debug_and_no_import_time_create_db(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(repo_root, 'run.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn('debug=True', content)
        self.assertNotIn('create_db()', content)

    def test_cold_start_and_concurrent_create_db_race_safe(self):
        with tempfile.TemporaryDirectory() as td:
            db_dir = os.path.join(td, 'db')
            db_file = os.path.join(db_dir, 'sub.db')
            # db_dir intentionally does NOT exist yet!
            self.assertFalse(os.path.exists(db_dir))

            test_app = _make_test_app(f'sqlite:///{db_file}')
            errors = []

            def worker():
                try:
                    with test_app.app_context():
                        with patch('app.model.ensure_db_dir', return_value=os.makedirs(db_dir, exist_ok=True) or db_dir):
                            # Patch app_dir via __file__? Instead call upgrade_database directly below
                            pass
                except Exception as exc:
                    errors.append(exc)

            # Run full cold-start upgrade_database + concurrent create_db
            with patch('app.model.ensure_db_dir', side_effect=lambda app_dir=None: (os.makedirs(db_dir, exist_ok=True), db_dir)[1]), \
                    patch('upgrade_db.ensure_db_dir', side_effect=lambda app_dir=None: (os.makedirs(db_dir, exist_ok=True), db_dir)[1]), \
                    patch.dict(os.environ, {'INIT_ADMIN_PASSWORD': 'ColdStart#Password1'}, clear=False):
                upgrade_database(test_app)
                self.assertTrue(os.path.exists(db_file))
                self.assertTrue(os.path.exists(os.path.join(db_dir, 'clash.yaml')))
                self.assertTrue(os.path.exists(os.path.join(db_dir, 'surge.conf')))
                self.assertTrue(os.path.exists(os.path.join(db_dir, 'sing-box.json')))

                # Concurrent create_db calls should be completely idempotent & race-free
                threads = []
                for _ in range(4):
                    def run_init():
                        try:
                            with test_app.app_context():
                                create_db()
                        except Exception as exc:
                            errors.append(exc)
                    t = threading.Thread(target=run_init)
                    threads.append(t)
                    t.start()
                for t in threads:
                    t.join()

                self.assertEqual(errors, [])
                with test_app.app_context():
                    users = User.query.all()
                    self.assertEqual(len(users), 1)
                    self.assertEqual(users[0].username, 'admin')
                    self.assertTrue(is_password_hashed(users[0].password))
                    self.assertTrue(verify_password(users[0].password, 'ColdStart#Password1')[0])
                    self.assertFalse(verify_password(users[0].password, 'admin')[0])
                    db.session.remove()
                    db.engine.dispose()

    def test_atomic_config_save_leaves_no_temp_files_and_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as td:
            db_dir = os.path.join(td, 'db')
            os.makedirs(db_dir)
            clash_path = os.path.join(db_dir, 'clash.yaml')
            with open(clash_path, 'w', encoding='utf-8') as f:
                f.write('port: 7890\nproxies: []\nproxy-groups:\n  - name: G1\n    type: select\n    proxies: [auto]\n')

            with self.app.app_context(), patch.object(view, 'path', td):
                # Prime clash cache
                out1 = view.clash_encode([])
                self.assertIn('G1', out1)

                token = create_access_token(identity='admin')
                new_yaml = 'port: 7899\nproxies: []\nproxy-groups:\n  - name: G2_UPDATED\n    type: select\n    proxies: [auto]\n'
                res = self.app.test_client().post(
                    '/clash_config',
                    json={'index': 'save', 'text': new_yaml},
                    headers={'Authorization': f'Bearer {token}'},
                )
                self.assertEqual(res.get_json()['code'], 200)
                # No leftover temp files in db_dir
                leftovers = [fn for fn in os.listdir(db_dir) if fn.startswith('.tmp_')]
                self.assertEqual(leftovers, [])
                # Cache invalidated -> clash_encode reads updated template
                out2 = view.clash_encode([])
                self.assertIn('G2_UPDATED', out2)

    def test_ssrf_blocks_private_metadata_obfuscated_dns_redirects_and_oversized(self):
        blocked_urls = [
            'http://127.0.0.1/sub',
            'http://localhost/sub',
            'http://sub.localhost/sub',
            'http://10.0.0.1/sub',
            'http://172.16.0.1/sub',
            'http://192.168.1.1/sub',
            'http://169.254.169.254/latest/meta-data/',
            'http://100.64.0.1/sub',
            'http://0.0.0.0/sub',
            'http://[::1]/sub',
            'http://[::ffff:127.0.0.1]/sub',
            'http://0x7f000001/sub',
            'http://2130706433/sub',
            'file:///etc/passwd',
        ]
        for bad_url in blocked_urls:
            with self.assertRaises(remote.SSRFError, msg=f'Should block {bad_url}'):
                remote.validate_remote_url(bad_url)

        # DNS resolving to cloud metadata IP must be blocked
        fake_addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('169.254.169.254', 80))]
        with patch('socket.getaddrinfo', return_value=fake_addrinfo):
            with self.assertRaises(remote.SSRFError):
                remote.validate_remote_url('http://rebind.example.com/sub')

        # 302 redirect from public host to metadata IP must be blocked
        redirect_resp = MagicMock()
        redirect_resp.status_code = 302
        redirect_resp.headers = {'Location': 'http://169.254.169.254/latest/meta-data/'}
        with patch('requests.get', return_value=redirect_resp) as mock_get:
            with self.assertRaises(remote.SSRFError):
                remote.safe_fetch_url('https://public.example.com/sub')
            self.assertEqual(mock_get.call_count, 1)

        # Oversized Content-Length must be rejected
        big_resp = MagicMock()
        big_resp.status_code = 200
        big_resp.headers = {'Content-Length': str(remote.MAX_REMOTE_SUB_BYTES + 1)}
        big_resp.text = 'x'
        with patch('requests.get', return_value=big_resp):
            with self.assertRaises(remote.ResponseTooLargeError):
                remote.safe_fetch_url('https://public.example.com/huge')

        # Oversized body without Content-Length must be rejected
        big_text_resp = MagicMock()
        big_text_resp.status_code = 200
        big_text_resp.headers = {}
        big_text_resp.text = 'a' * 1024
        with patch('requests.get', return_value=big_text_resp):
            with self.assertRaises(remote.ResponseTooLargeError):
                remote.safe_fetch_url('https://public.example.com/huge2', max_bytes=100)

        # Strict TLS: raw public IP HTTPS must NOT downgrade verify=False; SSLError must NOT retry verify=False
        with patch('requests.get', side_effect=requests.exceptions.SSLError('bad cert')) as mock_get:
            nodes = remote.fetch_remote_sub('https://1.1.1.1/sub', use_cache=False)
            self.assertEqual(nodes, [])
            self.assertEqual(mock_get.call_count, 1)
            self.assertTrue(mock_get.call_args.kwargs.get('verify'))
        self.assertFalse(hasattr(remote, '_insecure_ssl_hosts'))

    def test_get_country_emoji_uses_https(self):
        remote.get_country_emoji.cache_clear()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'flag': {'emoji': '🇺🇸'}}
        with patch('requests.get', return_value=mock_resp) as mock_get:
            flag = remote.get_country_emoji('8.8.8.8')
            self.assertEqual(flag, '🇺🇸')
            called_url = mock_get.call_args.args[0]
            self.assertTrue(called_url.startswith('https://ipwho.is/'))
        remote.get_country_emoji.cache_clear()

    def test_default_client_templates_hardened(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(repo_root, 'app', 'clash.yaml'), 'r', encoding='utf-8') as f:
            clash = yaml.safe_load(f)
        self.assertFalse(clash.get('allow-lan'))
        self.assertEqual(clash.get('external-controller'), '127.0.0.1:9090')

        with open(os.path.join(repo_root, 'app', 'surge.conf'), 'r', encoding='utf-8') as f:
            surge = f.read()
        self.assertNotIn('0.0.0.0:', surge)
        self.assertNotIn('external-controller-access', surge)
        self.assertNotIn('http-api =', surge)
        self.assertNotIn('password@', surge)
        self.assertNotIn('iqiyi.com', surge)
        self.assertNotIn('[Script]', surge)
        self.assertIn('allow-wifi-access = false', surge)
        self.assertIn('http-listen = 127.0.0.1:6152', surge)
        self.assertIn('socks5-listen = 127.0.0.1:6153', surge)
        self.assertIn('[Proxy]', surge)
        self.assertIn('[Proxy Group]', surge)


class P1ProtocolAndLogicFixesTest(unittest.TestCase):
    def setUp(self):
        self.orig_custom = view.CustomFeature
        self.orig_loopback = view.CustomLoopback
        self.orig_node_name = view.CustomNodeName
        self.orig_emoji = view.Emoji
        self.orig_skipcert = view.SkipCert
        self.orig_udp = view.Udp

    def tearDown(self):
        view.CustomFeature = self.orig_custom
        view.CustomLoopback = self.orig_loopback
        view.CustomNodeName = self.orig_node_name
        view.Emoji = self.orig_emoji
        view.SkipCert = self.orig_skipcert
        view.Udp = self.orig_udp
        remote.clear_remote_sub_cache()

    def test_decode_base64_if_urlsafe_and_plaintext_preservation(self):
        # URL-safe base64 containing '-' and '_' (e.g. '?>?' -> 'Pz4_' in urlsafe)
        raw_text = 'aes-256-gcm:a?>?b>>c'
        urlsafe = base64.urlsafe_b64encode(raw_text.encode()).decode().rstrip('=')
        self.assertTrue('-' in urlsafe or '_' in urlsafe)
        self.assertEqual(decode_base64_if(urlsafe), raw_text)

        # Plaintext credentials & base64-like tokens must not be corrupted
        self.assertEqual(decode_base64_if('AAAA'), 'AAAA')
        self.assertEqual(decode_base64_if('my_pass:word-123'), 'my_pass:word-123')

        # Trojan/VLESS/Hysteria preserve base64-like passwords & unquote URL-encoded credentials
        tr = parse_trojan('trojan://AAAA@tr.example.com:443#Tr1')
        self.assertEqual(tr['password'], 'AAAA')
        tr_enc = parse_trojan('trojan://user%3Apass%401%2F2@tr.example.com:443#Tr2')
        self.assertEqual(tr_enc['password'], 'user:pass@1/2')

        vl = parse_vless('vless://Q0ND@vl.example.com:443?security=tls#Vl1')
        self.assertEqual(vl['uuid'], 'Q0ND')
        vl_enc = parse_vless('vless://11111111-2222-3333-4444-555555555555@vl.example.com:443#Vl2')
        self.assertEqual(vl_enc['uuid'], '11111111-2222-3333-4444-555555555555')

        hy1 = parse_hysteria('hysteria://user%3Apass@hy1.example.com:443?upmbps=10&downmbps=20#Hy1')
        self.assertEqual(hy1['auth_str'], 'user:pass')

        # Loopback rewrite preserves plaintext & encoded passwords on Hysteria2 / Trojan
        view.CustomFeature = True
        view.CustomLoopback = True
        view.CustomNodeName = False
        hy2_loop = 'hysteria2://AAAA@127.0.0.1:443?sni=test.com#LoopHy2'
        rewritten = rewrite.rewrite_remote_node(hy2_loop, 'edge.example.com')
        self.assertEqual(rewritten, 'hysteria2://AAAA@edge.example.com:443?sni=test.com#LoopHy2')

        tr_loop = 'trojan://user%3Apass@127.0.0.1:8443?sni=test.com#LoopTr'
        rewritten_tr = rewrite.rewrite_remote_node(tr_loop, 'edge.example.com')
        self.assertEqual(rewritten_tr, 'trojan://user%3Apass@edge.example.com:443?sni=test.com#LoopTr')

    def test_parse_ssr_with_cert_param_does_not_crash(self):
        plain = '1.2.3.4:443:origin:aes-256-cfb:plain:cGFzcw==/?remarks=U1NSVGVzdA=='
        b64 = base64.urlsafe_b64encode(plain.encode()).decode().rstrip('=')
        p_true = parse_ssr(f'ssr://{b64}?cert=true')
        p_false = parse_ssr(f'ssr://{b64}?cert=false')
        self.assertTrue(p_true['skip-cert-verify'])
        self.assertFalse(p_false['skip-cert-verify'])

    def test_clash_surge_singbox_protocol_fields(self):
        # 1. SS plugin-opts dict for Clash, SIP003 string for Sing-Box
        ss_v2 = parse_ss(
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            '?plugin=v2ray-plugin%3Btls%3Bhost%3Dcdn.example.com#SSV2'
        )
        self.assertEqual(ss_v2['plugin'], 'v2ray-plugin')
        self.assertIsInstance(ss_v2['plugin-opts'], dict)
        self.assertEqual(ss_v2['plugin-opts'], {'mode': 'websocket', 'tls': True, 'host': 'cdn.example.com'})
        sb_v2 = generator.get_singbox_outbound('ss', ss_v2, 'SSV2')
        self.assertEqual(sb_v2['plugin'], 'v2ray-plugin')
        self.assertEqual(sb_v2['plugin_opts'], 'tls;host=cdn.example.com')

        ss_obfs = parse_ss(
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            '?plugin=obfs-local%3Bobfs%3Dhttp%3Bobfs-host%3Dexample.com#SSObfs'
        )
        self.assertEqual(ss_obfs['plugin'], 'obfs')
        self.assertEqual(ss_obfs['plugin-opts'], {'mode': 'http', 'host': 'example.com'})
        sb_obfs = generator.get_singbox_outbound('ss', ss_obfs, 'SSObfs')
        self.assertEqual(sb_obfs['plugin'], 'obfs-local')
        self.assertEqual(sb_obfs['plugin_opts'], 'obfs=http;obfs-host=example.com')

        # 2. No null network or null ws-opts.path; VMess insecure/allowInsecure supported
        vl_min = parse_vless('vless://uuid@vl.example.com:443?type=ws#VLMin')
        self.assertEqual(vl_min['ws-opts']['path'], '/')
        vl_no_net = parse_vless('vless://uuid@vl.example.com:443#VLNoNet')
        self.assertNotIn('network', vl_no_net)

        tr_ws = parse_trojan('trojan://pw@tr.example.com:443?type=ws#TrWS')
        self.assertEqual(tr_ws['ws-opts']['path'], '/')

        vm_json = base64.b64encode(json.dumps({
            'v': '2', 'ps': 'VM1', 'add': '1.2.3.4', 'port': 443,
            'id': 'u-1', 'net': 'ws', 'tls': 'tls', 'sni': 'sni.example.com',
            'allowInsecure': True,
        }).encode()).decode()
        vm = parse_vmess(f'vmess://{vm_json}')
        self.assertTrue(vm['skip-cert-verify'])
        self.assertEqual(vm['ws-opts']['path'], '/')
        self.assertEqual(vm['servername'], 'sni.example.com')

        vm_no_net = parse_vmess('vmess://' + base64.b64encode(json.dumps({
            'v': '2', 'ps': 'VM2', 'add': '1.2.3.4', 'port': 443, 'id': 'u-2',
        }).encode()).decode())
        self.assertNotIn('network', vm_no_net)

        vm_q = parse_vmess('vmess://u-3@1.2.3.4:443?remarks=VMQ&insecure=1')
        self.assertTrue(vm_q['skip-cert-verify'])

        # 3. Surge lowercase booleans and VMess servername SNI
        ss_line, _ = generator.parse_surge_node('ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:8388#SS1')
        self.assertIn('tfo=false', ss_line)
        self.assertIn('udp-relay=false', ss_line)
        self.assertNotIn('False', ss_line)
        self.assertNotIn('True', ss_line)

        vm_line, _ = generator.parse_surge_node(f'vmess://{vm_json}')
        self.assertIn('tls=true', vm_line)
        self.assertIn('skip-cert-verify=true', vm_line)
        self.assertIn('tfo=false', vm_line)
        self.assertIn('sni=sni.example.com', vm_line)
        self.assertNotIn('sni=1.2.3.4', vm_line)
        self.assertNotIn('False', vm_line)
        self.assertNotIn('True', vm_line)

        tr_line, _ = generator.parse_surge_node('trojan://pw@1.2.3.4:443?sni=tr.example.com&type=ws#Tr1')
        self.assertIn('skip-cert-verify=false', tr_line)
        self.assertIn('tfo=false', tr_line)
        self.assertIn('udp-relay=false', tr_line)
        self.assertIn('ws-path=/', tr_line)
        self.assertNotIn('False', tr_line)

    def test_strict_protocol_validation_blocks_substring_bypass(self):
        self.assertTrue(is_valid_node_uri('ss://abc@1.2.3.4:443'))
        self.assertTrue(is_valid_node_uri('https://sub.example.com/list'))
        self.assertFalse(is_valid_node_uri('evil://foo?x=ss'))
        self.assertFalse(is_valid_node_uri('javascript:alert("http")'))
        self.assertFalse(is_valid_node_uri('random-ss-text'))
        self.assertFalse(is_valid_node_uri('ss://   '))
        self.assertFalse(is_valid_node_uri(12345))

        app = _make_test_app()
        with app.app_context():
            db.create_all()
            client = app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            res = client.post('/create_node', json={'name': 'Sub1', 'node': 'evil://foo?x=ss'}, headers=headers)
            self.assertEqual(res.get_json()['code'], 400)

            res2 = client.post('/create_sub', json={'name': 'Sub1', 'node': ['evil://foo?x=http']}, headers=headers)
            self.assertEqual(res2.get_json()['code'], 400)

            # Non-string node element rejected with 400 (no 500 AttributeError)
            res3 = client.post('/create_sub', json={'name': 'Sub2', 'node': [123, None]}, headers=headers)
            self.assertEqual(res3.get_json()['code'], 400)

            # Subscription name stripped on create_sub
            res4 = client.post(
                '/create_sub',
                json={'name': '  MySub  ', 'node': ['ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:443#N1']},
                headers=headers,
            )
            self.assertEqual(res4.get_json()['code'], 200)
            saved = Sub.query.first()
            self.assertEqual(saved.name, 'MySub')

    def test_remote_sub_cache_raw_nodes_reflect_config_changes_and_thread_context(self):
        remote.clear_remote_sub_cache()
        test_url = 'https://cache-cfg.test/sub'
        raw_node = 'vless://uuid@127.0.0.1:8080?type=ws#' + '🇭🇰【香港-01-SG'
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.text = base64.b64encode(raw_node.encode('utf-8')).decode('utf-8')

        view.CustomFeature = False
        view.CustomLoopback = False
        view.CustomNodeName = False

        with patch.object(remote, '_ORIGINAL_REQUESTS_GET', requests.get), \
                patch('app.remote._http_get', return_value=mock_resp) as mock_http:
            # First fetch with custom OFF -> un-rewritten
            nodes1 = remote.fetch_remote_sub(test_url, use_cache=True)
            self.assertEqual(mock_http.call_count, 1)
            self.assertIn('@127.0.0.1:8080', nodes1[0])

            # Enable custom rewrite -> MUST immediately reflect on cached entry without re-fetching
            view.CustomFeature = True
            view.CustomLoopback = True
            view.CustomNodeName = True
            nodes2 = remote.fetch_remote_sub(test_url, use_cache=True)
            self.assertEqual(mock_http.call_count, 1)
            self.assertIn('@cache-cfg.test:443', nodes2[0])
            self.assertIn('%F0%9F%87%B8%F0%9F%87%AC', nodes2[0])  # Singapore flag

        # Verify bounded LRU cache eviction
        with patch.object(remote, 'REMOTE_SUB_CACHE_MAXSIZE', 3):
            remote.clear_remote_sub_cache()
            for i in range(5):
                remote._cache_put(f'https://u{i}.test/sub', [f'ss://n{i}'])
            self.assertEqual(len(remote._remote_sub_cache), 3)
            self.assertNotIn('https://u0.test/sub', remote._remote_sub_cache)
            self.assertIn('https://u4.test/sub', remote._remote_sub_cache)

        # Verify ThreadPoolExecutor in expand_node_list propagates Flask request DB config
        app = _make_test_app()
        with app.app_context():
            db.create_all()
            db.session.add_all([
                Config(key='custom', value='1'),
                Config(key='custom_loopback', value='1'),
                Config(key='custom_node_name', value='0'),
            ])
            db.session.commit()
            # Intentionally set stale module globals opposite to DB config
            view.CustomFeature = False
            view.CustomLoopback = False
            seen_configs = []

            def fake_fetch(url):
                seen_configs.append(dict(view.get_runtime_config()))
                return [f'ss://node-from-{url}']

            with app.test_request_context('/sub/clash/tok'):
                with patch('app.core.generator._fetch_remote_sub', side_effect=fake_fetch):
                    generator.expand_node_list([
                        SimpleNamespace(node='https://a.example.com/sub'),
                        SimpleNamespace(node='https://b.example.com/sub'),
                    ])
            self.assertEqual(len(seen_configs), 2)
            for cfg in seen_configs:
                self.assertTrue(cfg['custom'])
                self.assertTrue(cfg['custom_loopback'])
                self.assertFalse(cfg['custom_node_name'])

    def test_alembic_full_migration_chain_from_empty_and_legacy_db(self):
        # 1. Pure Alembic upgrade head on an empty SQLite database
        with tempfile.TemporaryDirectory() as td:
            db_file = os.path.join(td, 'empty_alembic.db')
            app = _make_test_app(f'sqlite:///{db_file}')
            with app.app_context():
                alembic_upgrade(directory=MIGRATIONS_DIR, revision='head')
                tables, schema_items, rev = read_schema_state(db_file)
                self.assertEqual(rev, CONFIG_SCHEMA_REVISION)
                self.assertTrue({'user', 'sub', 'login', 'config'}.issubset(tables))
                self.assertEqual(detect_schema_revision(schema_items), CONFIG_SCHEMA_REVISION)
                db.session.remove()
                db.engine.dispose()

        # 2. Legacy DB with old schema + duplicate usernames upgraded cleanly via upgrade_database()
        with tempfile.TemporaryDirectory() as td:
            db_dir = os.path.join(td, 'db')
            os.makedirs(db_dir)
            db_file = os.path.join(db_dir, 'legacy.db')
            conn = sqlite3.connect(db_file)
            conn.execute('CREATE TABLE user (id INTEGER PRIMARY KEY, username VARCHAR(40), password VARCHAR(40), name VARCHAR(40))')
            conn.execute("INSERT INTO user (username, password, name) VALUES ('admin', '21232f297a57a5a743894a0e4a801fc3', 'A1')")
            conn.execute("INSERT INTO user (username, password, name) VALUES ('admin', '21232f297a57a5a743894a0e4a801fc3', 'A2')")
            conn.execute('CREATE TABLE sub (id INTEGER PRIMARY KEY, name VARCHAR(40), node TEXT)')
            conn.execute("INSERT INTO sub (name, node) VALUES ('OldSub', 'ss://abc')")
            conn.commit()
            conn.close()

            app = _make_test_app(f'sqlite:///{db_file}')
            with patch('app.model.ensure_db_dir', return_value=db_dir), \
                    patch('upgrade_db.ensure_db_dir', return_value=db_dir):
                upgrade_database(app)
                tables, schema_items, rev = read_schema_state(db_file)
                self.assertEqual(rev, CONFIG_SCHEMA_REVISION)
                self.assertEqual(detect_schema_revision(schema_items), CONFIG_SCHEMA_REVISION)
                with app.app_context():
                    self.assertEqual(User.query.count(), 1)
                    sub = Sub.query.filter_by(name='OldSub').first()
                    self.assertIsNotNone(sub.access_token)
                    db.session.remove()
                    db.engine.dispose()


class P2AndP3FixesTest(unittest.TestCase):
    def test_reverse_proxy_ip_spoofing_and_proxyfix_https(self):
        # Default (no trusted proxy): X-Real-IP and X-Forwarded-Proto MUST be ignored
        with tempfile.TemporaryDirectory() as td:
            with patch('app.ensure_db_dir', return_value=td), \
                    patch.dict(os.environ, {'JWT_SECRET_KEY': 'test-proxy-secret-key-at-least-32-bytes'}, clear=True):
                app_direct = create_app()
                app_direct.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
                with app_direct.app_context():
                    db.create_all()
                    db.session.add(Sub(
                        name='S1', node='ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:443#N1',
                        sort_order=0, access_token='tok-direct', legacy_enabled=False
                    ))
                    db.session.commit()
                    client = app_direct.test_client()
                    # Spoofed X-Forwarded-Proto ignored
                    res_surge = client.get('/sub/surge/tok-direct', headers={'X-Forwarded-Proto': 'https'})
                    self.assertIn('#!MANAGED-CONFIG http://', res_surge.get_data(as_text=True))

                    # Spoofed X-Real-IP ignored by get_client_ip
                    with app_direct.test_request_context(
                        '/login',
                        environ_base={'REMOTE_ADDR': '198.51.100.10'},
                        headers={'X-Real-IP': '1.2.3.4'},
                    ):
                        self.assertEqual(remote.get_client_ip(), '198.51.100.10')
                    db.session.remove()
                    db.engine.dispose()

        # With TRUSTED_PROXIES=127.0.0.1: ProxyFix honors X-Forwarded-Proto & X-Forwarded-For
        with tempfile.TemporaryDirectory() as td:
            with patch('app.ensure_db_dir', return_value=td), \
                    patch.dict(os.environ, {
                        'JWT_SECRET_KEY': 'test-proxy-secret-key-at-least-32-bytes',
                        'TRUSTED_PROXIES': '127.0.0.1',
                    }, clear=True):
                app_proxied = create_app()
                with app_proxied.app_context():
                    db.create_all()
                    db.session.add(Sub(
                        name='S1', node='ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:443#N1',
                        sort_order=0, access_token='tok-proxy', legacy_enabled=False
                    ))
                    db.session.commit()
                    client = app_proxied.test_client()
                    res_surge = client.get(
                        '/sub/surge/tok-proxy',
                        environ_base={'REMOTE_ADDR': '127.0.0.1'},
                        headers={'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'sub.mydomain.com'},
                    )
                    self.assertIn('#!MANAGED-CONFIG https://sub.mydomain.com/sub/surge/tok-proxy', res_surge.get_data(as_text=True))
                    db.session.remove()
                    db.engine.dispose()

    def test_v2ray_mimetype_plain_and_500_hides_internal_error(self):
        app = _make_test_app()
        with app.app_context():
            db.create_all()
            db.session.add(Sub(
                name='V2', node='ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:443#N1',
                sort_order=0, access_token='tok-v2', legacy_enabled=False
            ))
            db.session.commit()
            client = app.test_client()

            res_v2 = client.get('/sub/v2ray/tok-v2')
            self.assertEqual(res_v2.status_code, 200)
            self.assertEqual(res_v2.mimetype, 'text/plain')

            with patch('app.view.clash_encode', side_effect=RuntimeError('SECRET_INTERNAL_FILE_PATH')):
                res_err = client.get('/sub/clash/tok-v2')
                self.assertEqual(res_err.status_code, 500)
                msg = res_err.get_json()['msg']
                self.assertEqual(msg, 'clash 配置生成失败')
                self.assertNotIn('SECRET_INTERNAL_FILE_PATH', msg)

    def test_get_subs_eliminates_n_plus_one_and_config_route_aliases(self):
        app = _make_test_app()
        with app.app_context():
            db.create_all()
            for i in range(10):
                db.session.add(Sub(name=f'Sub{i}', node='ss://abc@1.2.3.4:443#N', sort_order=i, access_token=None))
            db.session.commit()

            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}
            client = app.test_client()

            select_count = 0

            def count_queries(conn, cursor, statement, parameters, context, executemany):
                nonlocal select_count
                if statement.strip().upper().startswith('SELECT') and 'FROM SUB' in statement.upper():
                    select_count += 1

            sa.event.listen(db.engine, 'before_cursor_execute', count_queries)
            try:
                res = client.post('/get_subs', headers=headers)
            finally:
                sa.event.remove(db.engine, 'before_cursor_execute', count_queries)

            self.assertEqual(res.status_code, 200)
            items = res.get_json()
            self.assertEqual(len(items), 10)
            self.assertTrue(all(item['access_token'] for item in items))
            # Backfill path uses constant 2 SELECTs (initial check + locked re-query, NOT N+1 = 12!)
            self.assertEqual(select_count, 2)

            # Steady-state call after backfill uses only 1 SELECT
            select_count = 0
            sa.event.listen(db.engine, 'before_cursor_execute', count_queries)
            try:
                res2 = client.post('/get_subs', headers=headers)
            finally:
                sa.event.remove(db.engine, 'before_cursor_execute', count_queries)
            self.assertEqual(res2.status_code, 200)
            self.assertEqual(select_count, 1)

            # Both new spelling (/set_config, /get_config) and legacy aliases (/set_conifg, /get_conifg) work
            r_set = client.post('/set_config', json={'udp': True}, headers=headers)
            self.assertEqual(r_set.get_json()['code'], 200)
            r_get_new = client.post('/get_config', headers=headers).get_json()
            r_get_old = client.post('/get_conifg', headers=headers).get_json()
            self.assertTrue(r_get_new['udp'])
            self.assertTrue(r_get_old['udp'])

    def test_clash_template_cache_avoids_repeated_yaml_parsing_and_dead_code_removed(self):
        self.assertFalse(hasattr(rewrite, 'rewrite_node_ipv6'))
        generator.clear_template_cache()
        with patch('yaml.safe_load', wraps=yaml.safe_load) as spy_load:
            out1 = generator.clash_encode([])
            out2 = generator.clash_encode([])
            self.assertEqual(spy_load.call_count, 1)
            self.assertIn('DIRECT', out1)
            self.assertIn('DIRECT', out2)

    def test_round1_self_review_regressions(self):
        from app import _load_or_create_jwt_secret
        from app.model import init_user_pass

        # 1. Concurrent _load_or_create_jwt_secret returns identical secret across threads (no 0-byte race)
        with tempfile.TemporaryDirectory() as td:
            secrets_seen = []
            errors = []

            def grab_secret():
                try:
                    secrets_seen.append(_load_or_create_jwt_secret(td))
                except Exception as exc:
                    errors.append(exc)

            with patch.dict(os.environ, {}, clear=True):
                threads = [threading.Thread(target=grab_secret) for _ in range(8)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
            self.assertEqual(errors, [])
            self.assertEqual(len(set(secrets_seen)), 1)
            self.assertGreaterEqual(len(secrets_seen[0]), 64)

        # 2. init_user_pass() revokes pre-reset JWTs even if SQLite reuses id=1
        app = _make_test_app()
        with app.app_context():
            db.create_all()
            db.session.add(User(id=1, username='admin', password=hash_password('OldPass!'), name='管理员', token_version=1))
            db.session.commit()
            client = app.test_client()
            with patch('app.remote.requests.get'):
                old_token = client.post('/login', json={'username': 'admin', 'password': 'OldPass!'}).get_json()['token']
            self.assertEqual(client.post('/get_config', headers={'Authorization': f'Bearer {old_token}'}).status_code, 200)

            with patch.dict(os.environ, {'INIT_ADMIN_PASSWORD': 'ResetStrongPass!'}):
                init_user_pass()
            self.assertEqual(client.post('/get_config', headers={'Authorization': f'Bearer {old_token}'}).status_code, 401)

            # 3. Non-dict JSON payloads & bad types return clean 400/404 instead of 500
            with patch('app.remote.requests.get'):
                new_token = client.post('/login', json={'username': 'admin', 'password': 'ResetStrongPass!'}).get_json()['token']
            headers = {'Authorization': f'Bearer {new_token}'}
            r_list_login = client.post('/login', json=['not', 'a', 'dict'])
            self.assertEqual(r_list_login.status_code, 200)
            self.assertEqual(r_list_login.get_json()['code'], 404)

            r_bad_sort = client.post('/sort_subs', json={'names': [{'unhashable': 1}]}, headers=headers)
            self.assertEqual(r_bad_sort.status_code, 200)
            self.assertEqual(r_bad_sort.get_json()['code'], 400)

            r_bad_node_id = client.post(
                '/set_node',
                json={'id': {'bad': 1}, 'node': 'ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:443#N'},
                headers=headers,
            )
            self.assertEqual(r_bad_node_id.status_code, 200)
            self.assertEqual(r_bad_node_id.get_json()['code'], 404)

        # 4. Lowercase 'location' redirect header to private IP is blocked
        low_redir = MagicMock()
        low_redir.status_code = 302
        low_redir.headers = {'location': 'http://127.0.0.1/secret'}
        with patch('requests.get', return_value=low_redir):
            with self.assertRaises(remote.SSRFError):
                remote.safe_fetch_url('https://public.example.com/redir')

        # 5. Space-separated plaintext is NOT collapsed into fake Base64
        self.assertEqual(decode_base64_if('TWF u'), 'TWF u')

        # 6. get_country_emoji handles long TLDs (.network) and IPv6-only domains over HTTPS
        remote.get_country_emoji.cache_clear()
        mock_geo = MagicMock()
        mock_geo.status_code = 200
        mock_geo.json.return_value = {'flag': {'emoji': '🇯🇵'}}
        v4_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.1.1.1', 0))]
        with patch('socket.getaddrinfo', return_value=v4_info), \
                patch('requests.get', return_value=mock_geo) as mock_get:
            self.assertEqual(remote.get_country_emoji('edge.example.network'), '🇯🇵')
            self.assertEqual(mock_get.call_args.args[0], 'https://ipwho.is/1.1.1.1')
        remote.get_country_emoji.cache_clear()
        v6_info = [(socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('2606:4700:4700::1111', 0, 0, 0))]
        with patch('socket.getaddrinfo', return_value=v6_info), \
                patch('requests.get', return_value=mock_geo) as mock_get:
            self.assertEqual(remote.get_country_emoji('v6only.example.network'), '🇯🇵')
            self.assertIn('2606%3A4700%3A4700%3A%3A1111', mock_get.call_args.args[0])
        remote.get_country_emoji.cache_clear()

    def test_round2_deep_review_regressions(self):
        from flask_migrate import downgrade as alembic_downgrade

        # 1. Legacy MD5 DB row rejects pass-the-hash (raw MD5 hex) so DB is never corrupted to PBKDF2(MD5)
        legacy_md5 = hashlib.md5(b'AdminPass!23').hexdigest()
        ok_pth, rehash_pth = verify_password(legacy_md5, legacy_md5)
        self.assertFalse(ok_pth)
        self.assertFalse(rehash_pth)
        ok_plain, rehash_plain = verify_password(legacy_md5, 'AdminPass!23')
        self.assertTrue(ok_plain)
        self.assertTrue(rehash_plain)

        # 2. Invalid/re-keyed JWT returns 401 (not 422), and prod revocation check is fail-closed
        with tempfile.TemporaryDirectory() as td:
            old_app = Flask(__name__)
            old_app.config.update(JWT_SECRET_KEY='sub', SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
            init_exts(old_app)
            with old_app.app_context():
                old_key_token = create_access_token(identity='admin')

            db_file = os.path.join(td, 'prod.db')
            prod_app = Flask(__name__)
            prod_app.config['TESTING'] = False
            prod_app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_file}'
            prod_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
            prod_app.config['JWT_SECRET_KEY'] = 'new-strong-secret-key-at-least-32-bytes-long'
            init_exts(prod_app)
            prod_app.register_blueprint(view.blue)
            with prod_app.app_context():
                db.create_all()
                client = prod_app.test_client()
                # Old-secret JWT gets 401 (triggers frontend redirect instead of hanging on 422)
                r_old = client.post('/get_config', headers={'Authorization': f'Bearer {old_key_token}'})
                self.assertEqual(r_old.status_code, 401)
                # Bare token with empty User table in production MUST be rejected (fail-closed)
                bare_token = create_access_token(identity='ghost')
                r_empty = client.post('/get_config', headers={'Authorization': f'Bearer {bare_token}'})
                self.assertEqual(r_empty.status_code, 401)
                # DB error during revocation check in production MUST fail-closed (401)
                db.session.add(User(username='admin', password=hash_password('Strong!1'), name='管理员', token_version=1))
                db.session.commit()
                with patch('app.remote.requests.get'):
                    real_tok = client.post('/login', json={'username': 'admin', 'password': 'Strong!1'}).get_json()['token']
                with patch.object(db.session, 'get', side_effect=RuntimeError('db locked')):
                    r_err = client.post('/get_config', headers={'Authorization': f'Bearer {real_tok}'})
                    self.assertEqual(r_err.status_code, 401)
                db.session.remove()
                db.engine.dispose()

        # 3. SS v2ray-plugin mux=0 / mux=4 / tls=false / simple-obfs Sing-Box compatibility
        ss_mux0 = parse_ss(
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            '?plugin=v2ray-plugin%3Bmode%3Dwebsocket%3Btls%3Bmux%3D0%3Bhost%3Dcdn.example.com#SS0'
        )
        self.assertIs(ss_mux0['plugin-opts']['mux'], False)
        sb_mux0 = generator.get_singbox_outbound('ss', ss_mux0, 'SS0')
        self.assertIn('mux=0', sb_mux0['plugin_opts'])
        self.assertNotIn('mux=false', sb_mux0['plugin_opts'])

        ss_mux4 = parse_ss(
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            '?plugin=v2ray-plugin%3Btls%3Dfalse%3Bmux%3D4%3Bhost%3Dcdn.example.com#SS4'
        )
        self.assertIs(ss_mux4['plugin-opts']['mux'], True)
        self.assertIs(ss_mux4['plugin-opts']['tls'], False)
        sb_mux4 = generator.get_singbox_outbound('ss', ss_mux4, 'SS4')
        self.assertIn('mux=1', sb_mux4['plugin_opts'])
        self.assertNotIn('tls', sb_mux4['plugin_opts'])

        sb_simple = generator.get_singbox_outbound('ss', {
            'server': '1.2.3.4', 'port': 8388, 'cipher': 'aes-128-gcm', 'password': 'p',
            'plugin': 'simple-obfs', 'plugin-opts': {'mode': 'http', 'host': 'example.com'},
        }, 'SSSimple')
        self.assertEqual(sb_simple['plugin'], 'obfs-local')

        # 4. Plaintext query-style VMess UUID is not corrupted by loopback rewrite
        view.CustomFeature = True
        view.CustomLoopback = True
        view.CustomNodeName = False
        vm_plain = 'vmess://Q0ND@127.0.0.1:8080?remarks=Test'
        self.assertEqual(rewrite.get_node_server(vm_plain), '127.0.0.1')
        rewritten_vm = rewrite.rewrite_loopback_node(vm_plain, 'edge.example.com')
        self.assertEqual(rewritten_vm, 'vmess://Q0ND@edge.example.com:443?remarks=Test')

        # 5. SSRF edge cases: invalid port, IPv6 6to4/NAT64, uppercase LOCATION, UTF-8 streamed body,
        #    proxy-only filtering in fetch_remote_sub, and socket-level DNS rebinding guard
        with self.assertRaises(remote.SSRFError):
            remote.validate_remote_url('http://example.com:99999/sub')
        with self.assertRaises(remote.SSRFError):
            remote.validate_remote_url('http://[2002:7f00:0001::1]/sub')
        with self.assertRaises(remote.SSRFError):
            remote.validate_remote_url('http://[64:ff9b::169.254.169.254]/sub')

        upper_redir = MagicMock()
        upper_redir.status_code = 302
        upper_redir.headers = {'LOCATION': 'http://127.0.0.1/secret'}
        with patch('requests.get', return_value=upper_redir):
            with self.assertRaises(remote.SSRFError):
                remote.safe_fetch_url('https://public.example.com/r')

        # Streamed UTF-8 body with ISO-8859-1 default (no charset in Content-Type) preserves Chinese/emoji
        utf8_node = 'vless://u@1.2.3.4:443#🇭🇰香港节点'
        streamed_resp = MagicMock()
        streamed_resp.headers = {'Content-Type': 'text/plain'}
        streamed_resp.encoding = 'ISO-8859-1'
        streamed_resp.iter_content.return_value = [utf8_node.encode('utf-8')]
        decoded_body = remote._read_bounded_response(streamed_resp, max_bytes=1024, is_streamed=True)
        self.assertEqual(decoded_body, utf8_node)

        # fetch_remote_sub strips http(s) promo links from remote subscription body
        mixed_resp = MagicMock()
        mixed_resp.status_code = 200
        mixed_resp.headers = {}
        mixed_resp.text = 'https://provider.example.com/promo\nvless://u@1.2.3.4:443#RealNode\n'
        with patch('requests.get', return_value=mixed_resp):
            fetched = remote.fetch_remote_sub('https://sub.example.com/list', use_cache=False)
            self.assertEqual(fetched, ['vless://u@1.2.3.4:443#RealNode'])

        # Socket-level _SafeHTTPConnection._new_conn rejects DNS rebinding to metadata IP
        rebind_conn = remote._SafeHTTPConnection('rebind.example.com', port=80)
        rebind_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('169.254.169.254', 80))]
        with patch('socket.getaddrinfo', return_value=rebind_info):
            with self.assertRaises(remote.SSRFError):
                rebind_conn._new_conn()

        # 6. Dual-stack IPv4-mapped IPv6 REMOTE_ADDR matches IPv4 TRUSTED_PROXIES
        with tempfile.TemporaryDirectory() as td:
            with patch('app.ensure_db_dir', return_value=td), \
                    patch.dict(os.environ, {
                        'JWT_SECRET_KEY': 'test-proxy-secret-key-at-least-32-bytes',
                        'TRUSTED_PROXIES': '127.0.0.1',
                    }, clear=True):
                app_v6proxy = create_app()
                with app_v6proxy.test_request_context(
                    '/login',
                    environ_base={'REMOTE_ADDR': '::ffff:127.0.0.1'},
                    headers={'X-Real-IP': '203.0.113.42'},
                ):
                    self.assertEqual(remote.get_client_ip(), '203.0.113.42')

        # 7. Partial legacy DB (user table only, missing sub table) upgrades cleanly + full downgrade/upgrade cycle
        with tempfile.TemporaryDirectory() as td:
            db_dir = os.path.join(td, 'db')
            os.makedirs(db_dir)
            db_file = os.path.join(db_dir, 'partial_legacy.db')
            conn = sqlite3.connect(db_file)
            conn.execute('CREATE TABLE user (id INTEGER PRIMARY KEY, username VARCHAR(40), password VARCHAR(40), name VARCHAR(40))')
            conn.execute("INSERT INTO user (username, password, name) VALUES ('admin', '21232f297a57a5a743894a0e4a801fc3', 'Old')")
            conn.commit()
            conn.close()

            app_partial = _make_test_app(f'sqlite:///{db_file}')
            with patch('app.model.ensure_db_dir', return_value=db_dir), \
                    patch('upgrade_db.ensure_db_dir', return_value=db_dir):
                upgrade_database(app_partial)
                with app_partial.app_context():
                    u = User.query.filter_by(username='admin').first()
                    self.assertIsNotNone(u)
                    self.assertEqual(u.token_version, 1)
                    # Full downgrade -> base -> upgrade -> head roundtrip
                    alembic_downgrade(directory=MIGRATIONS_DIR, revision='base')
                    alembic_upgrade(directory=MIGRATIONS_DIR, revision='head')
                    tables, _, rev = read_schema_state(db_file)
                    self.assertEqual(rev, CONFIG_SCHEMA_REVISION)
                    self.assertTrue({'user', 'sub', 'login', 'config'}.issubset(tables))
                    db.session.remove()
                    db.engine.dispose()

    def test_sqlite_wal_busy_timeout_and_non_sqlite_isolation(self):
        from app.exts import (
            SQLITE_BUSY_TIMEOUT_MS,
            SQLITE_CONNECT_TIMEOUT_SECONDS,
            _configure_sqlite_connection,
            _is_file_backed_sqlite_uri,
            _prepare_sqlite_engine_options,
        )

        # 1. URI detection cleanly distinguishes file-backed SQLite vs :memory: vs non-SQLite
        self.assertTrue(_is_file_backed_sqlite_uri('sqlite:///app/db/sub.db'))
        self.assertTrue(_is_file_backed_sqlite_uri('sqlite+pysqlite:///tmp/sub.db'))
        self.assertFalse(_is_file_backed_sqlite_uri('sqlite:///:memory:'))
        self.assertFalse(_is_file_backed_sqlite_uri('sqlite://'))
        self.assertFalse(_is_file_backed_sqlite_uri('sqlite:///'))
        self.assertFalse(_is_file_backed_sqlite_uri('sqlite:///file::memory:?cache=shared'))
        self.assertFalse(_is_file_backed_sqlite_uri('sqlite:///file:mem1?mode=memory&cache=shared'))
        self.assertFalse(_is_file_backed_sqlite_uri('sqlite:///file:mem1?MODE=memory&cache=shared'))
        self.assertFalse(_is_file_backed_sqlite_uri('postgresql://user:pass@localhost:5432/sublink'))
        self.assertFalse(_is_file_backed_sqlite_uri('mysql+pymysql://user:pass@localhost/sublink'))
        self.assertFalse(_is_file_backed_sqlite_uri(''))
        self.assertFalse(_is_file_backed_sqlite_uri(None))

        # 2. Non-SQLite and :memory: apps do NOT receive SQLite connect_args
        pg_app = Flask(__name__)
        pg_app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@localhost/sublink'
        self.assertFalse(_prepare_sqlite_engine_options(pg_app))
        self.assertNotIn('SQLALCHEMY_ENGINE_OPTIONS', pg_app.config)

        mem_app = _make_test_app('sqlite:///:memory:')
        self.assertEqual(mem_app.config.get('SQLALCHEMY_ENGINE_OPTIONS'), {})
        with mem_app.app_context():
            db.create_all()
            with db.engine.connect() as conn:
                self.assertEqual(str(conn.execute(sa.text('PRAGMA journal_mode')).scalar()).lower(), 'memory')
                self.assertNotEqual(int(conn.execute(sa.text('PRAGMA busy_timeout')).scalar()), SQLITE_BUSY_TIMEOUT_MS)
            db.session.remove()
            db.engine.dispose()

        # Defense-in-depth: _configure_sqlite_connection skips non-sqlite3 objects and :memory: connections
        _configure_sqlite_connection(object(), None)
        mem_conn = sqlite3.connect(':memory:')
        try:
            initial_bt = mem_conn.execute('PRAGMA busy_timeout').fetchone()[0]
            _configure_sqlite_connection(mem_conn, None)
            self.assertEqual(mem_conn.execute('PRAGMA journal_mode').fetchone()[0].lower(), 'memory')
            self.assertEqual(mem_conn.execute('PRAGMA busy_timeout').fetchone()[0], initial_bt)
        finally:
            mem_conn.close()

        # 3. File-backed SQLite via create_app() enables WAL, NORMAL sync, busy_timeout=15000, connect timeout=15
        with tempfile.TemporaryDirectory() as td:
            with patch('app.ensure_db_dir', return_value=td), \
                    patch.dict(os.environ, {'JWT_SECRET_KEY': 'test-wal-secret-key-at-least-32-bytes-long'}, clear=True):
                prod_app = create_app()
                engine_opts = prod_app.config.get('SQLALCHEMY_ENGINE_OPTIONS') or {}
                self.assertEqual(engine_opts.get('connect_args', {}).get('timeout'), SQLITE_CONNECT_TIMEOUT_SECONDS)

                with prod_app.app_context():
                    db.create_all()
                    with db.engine.connect() as conn:
                        jm = str(conn.execute(sa.text('PRAGMA journal_mode')).scalar()).lower()
                        bt = int(conn.execute(sa.text('PRAGMA busy_timeout')).scalar())
                        sy = int(conn.execute(sa.text('PRAGMA synchronous')).scalar())
                    self.assertEqual(jm, 'wal')
                    self.assertEqual(bt, SQLITE_BUSY_TIMEOUT_MS)
                    self.assertEqual(sy, 1)  # NORMAL

                    # Concurrent multi-thread writes under WAL + busy_timeout complete cleanly
                    errors = []

                    def write_worker(idx):
                        try:
                            with prod_app.app_context():
                                db.session.add(Config(key=f'k_{idx}', value=f'v_{idx}'))
                                db.session.commit()
                                db.session.remove()
                        except Exception as exc:
                            errors.append(exc)

                    threads = [threading.Thread(target=write_worker, args=(i,)) for i in range(6)]
                    for t in threads:
                        t.start()
                    for t in threads:
                        t.join()
                    self.assertEqual(errors, [])
                    self.assertEqual(Config.query.count(), 6)
                    db.session.remove()
                    db.engine.dispose()

        # 4. Existing custom SQLALCHEMY_ENGINE_OPTIONS timeout is preserved in BOTH connect_args and PRAGMA busy_timeout,
        #    and explicit timeout=None falls back safely to default 15s / 15000ms.
        with tempfile.TemporaryDirectory() as td:
            custom_db = os.path.join(td, 'custom.db')
            custom_app = Flask(__name__)
            custom_app.config['TESTING'] = True
            custom_app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{custom_db}'
            custom_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
            custom_app.config['JWT_SECRET_KEY'] = 'test-custom-opts-secret-key-at-least-32-bytes'
            custom_app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
                'pool_pre_ping': True,
                'connect_args': {'timeout': 30},
            }
            init_exts(custom_app)
            self.assertEqual(custom_app.config['SQLALCHEMY_ENGINE_OPTIONS']['connect_args']['timeout'], 30)
            self.assertTrue(custom_app.config['SQLALCHEMY_ENGINE_OPTIONS']['pool_pre_ping'])
            with custom_app.app_context():
                db.create_all()
                with db.engine.connect() as conn:
                    self.assertEqual(str(conn.execute(sa.text('PRAGMA journal_mode')).scalar()).lower(), 'wal')
                    self.assertEqual(int(conn.execute(sa.text('PRAGMA busy_timeout')).scalar()), 30000)
                db.session.remove()
                db.engine.dispose()

            none_timeout_db = os.path.join(td, 'none_timeout.db')
            none_app = Flask(__name__)
            none_app.config['TESTING'] = True
            none_app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{none_timeout_db}'
            none_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
            none_app.config['JWT_SECRET_KEY'] = 'test-none-timeout-secret-key-at-least-32-bytes'
            none_app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'timeout': None}}
            init_exts(none_app)
            self.assertEqual(
                none_app.config['SQLALCHEMY_ENGINE_OPTIONS']['connect_args']['timeout'],
                SQLITE_CONNECT_TIMEOUT_SECONDS,
            )
            with none_app.app_context():
                db.create_all()
                with db.engine.connect() as conn:
                    self.assertEqual(int(conn.execute(sa.text('PRAGMA busy_timeout')).scalar()), SQLITE_BUSY_TIMEOUT_MS)
                db.session.remove()
                db.engine.dispose()

            # 5. Real multi-process concurrent writes (simulating gunicorn -w 4) succeed without database is locked
            mp_dir = os.path.join(td, 'mp_db')
            os.makedirs(mp_dir, exist_ok=True)
            with patch('app.ensure_db_dir', return_value=mp_dir), \
                    patch.dict(os.environ, {'JWT_SECRET_KEY': 'test-mp-wal-secret-key-at-least-32-bytes-long'}, clear=True):
                mp_app = create_app()
                with mp_app.app_context():
                    db.create_all()
                    db.session.remove()
                    db.engine.dispose()

            worker_code = (
                'import os, sys\n'
                'from unittest.mock import patch\n'
                'from app import create_app\n'
                'from app.exts import db\n'
                'from app.model import Config\n'
                'mp_dir, wid = sys.argv[1], sys.argv[2]\n'
                'with patch("app.ensure_db_dir", return_value=mp_dir):\n'
                '    app = create_app()\n'
                'with app.app_context():\n'
                '    for i in range(10):\n'
                '        db.session.add(Config(key=f"mp_{wid}_{i}", value=f"v_{i}"))\n'
                '        db.session.commit()\n'
                '    db.session.remove()\n'
                '    db.engine.dispose()\n'
            )
            env = dict(os.environ)
            env['JWT_SECRET_KEY'] = 'test-mp-wal-secret-key-at-least-32-bytes-long'
            env['PYTHONUTF8'] = '1'
            procs = [
                subprocess.Popen(
                    [sys.executable, '-c', worker_code, mp_dir, str(w)],
                    cwd=REPO_ROOT,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for w in range(4)
            ]
            for p in procs:
                out_b, err_b = p.communicate(timeout=30)
                out = out_b.decode('utf-8', errors='replace')
                err = err_b.decode('utf-8', errors='replace')
                self.assertEqual(p.returncode, 0, msg=f'worker failed: stdout={out} stderr={err}')

            mp_conn = sqlite3.connect(os.path.join(mp_dir, 'sub.db'))
            try:
                self.assertEqual(mp_conn.execute('PRAGMA journal_mode').fetchone()[0].lower(), 'wal')
                self.assertEqual(mp_conn.execute('SELECT COUNT(*) FROM config').fetchone()[0], 40)
            finally:
                mp_conn.close()

    def test_vless_reality_missing_pbk_and_ss_plugin_opts_json_normalization(self):
        from urllib.parse import quote

        # 1. VLESS security=reality without pbk/publicKey must NOT emit reality-opts or public-key: null
        uri_no_pbk = 'vless://11111111-2222-3333-4444-555555555555@vl.example.com:443?security=reality#NoPbk'
        parsed_no_pbk = parse_vless(uri_no_pbk)
        self.assertTrue(parsed_no_pbk['tls'])
        self.assertNotIn('reality-opts', parsed_no_pbk)

        clash_no_pbk = generator.clash_encode([uri_no_pbk])
        self.assertNotIn('public-key: null', clash_no_pbk)
        self.assertNotIn('reality-opts', clash_no_pbk)
        clash_doc = yaml.safe_load(clash_no_pbk)
        self.assertNotIn('reality-opts', clash_doc['proxies'][0])

        sb_no_pbk = json.loads(generator.singbox_encode([uri_no_pbk]))
        vless_ob = next(o for o in sb_no_pbk['outbounds'] if o.get('type') == 'vless')
        self.assertTrue(vless_ob['tls']['enabled'])
        self.assertNotIn('reality', vless_ob['tls'])

        # Missing pbk with sid present must still omit reality-opts (no orphan short-id without public-key)
        uri_empty_pbk = (
            'vless://11111111-2222-3333-4444-555555555555@vl.example.com:443'
            '?security=reality&pbk=&sid=deadbeef#EmptyPbk'
        )
        parsed_empty_pbk = parse_vless(uri_empty_pbk)
        self.assertNotIn('reality-opts', parsed_empty_pbk)

        # Valid uppercase security=REALITY with publicKey/shortId works cleanly
        uri_valid_reality = (
            'vless://11111111-2222-3333-4444-555555555555@vl.example.com:443'
            '?security=REALITY&publicKey=pubkey123&shortId=01ab#ValidReality'
        )
        parsed_valid = parse_vless(uri_valid_reality)
        self.assertEqual(parsed_valid['reality-opts'], {'public-key': 'pubkey123', 'short-id': '01ab'})
        sb_valid = generator.get_singbox_outbound('vless', parsed_valid, 'ValidReality')
        self.assertEqual(
            sb_valid['tls']['reality'],
            {'enabled': True, 'public_key': 'pubkey123', 'short_id': '01ab'},
        )

        # 2. SS JSON plugin-opts applies exact same boolean normalization as semicolon branch
        json_opts = json.dumps({
            'mux': 0,
            'tls': 'true',
            'skip-cert-verify': '1',
            'fast-open': 'false',
            'v2ray-http-upgrade': 'yes',
            'host': 'cdn.example.com',
            'ignored_null': None,
        })
        uri_ss_json = (
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            f'?plugin=v2ray-plugin&plugin-opts={quote(json_opts)}#SSJson'
        )
        uri_ss_semi = (
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            '?plugin=v2ray-plugin%3Bmode%3Dwebsocket%3Bmux%3D0%3Btls%3Dtrue'
            '%3Bskip-cert-verify%3D1%3Bfast-open%3Dfalse%3Bv2ray-http-upgrade%3Dyes'
            '%3Bhost%3Dcdn.example.com#SSSemi'
        )
        ss_json = parse_ss(uri_ss_json)
        ss_semi = parse_ss(uri_ss_semi)
        self.assertEqual(ss_json['plugin-opts'], ss_semi['plugin-opts'])
        self.assertIs(ss_json['plugin-opts']['mux'], False)
        self.assertIs(ss_json['plugin-opts']['tls'], True)
        self.assertIs(ss_json['plugin-opts']['skip-cert-verify'], True)
        self.assertIs(ss_json['plugin-opts']['fast-open'], False)
        self.assertIs(ss_json['plugin-opts']['v2ray-http-upgrade'], True)
        self.assertNotIn('ignored_null', ss_json['plugin-opts'])

        # Clash YAML roundtrip preserves genuine YAML booleans (not strings/ints)
        clash_ss = yaml.safe_load(generator.clash_encode([uri_ss_json]))
        clash_opts = clash_ss['proxies'][0]['plugin-opts']
        self.assertIs(clash_opts['mux'], False)
        self.assertIs(clash_opts['tls'], True)
        self.assertIs(clash_opts['skip-cert-verify'], True)
        self.assertIs(clash_opts['fast-open'], False)
        self.assertIs(clash_opts['v2ray-http-upgrade'], True)

        # Sing-Box outbound renders normalized flags + integer mux=0 cleanly
        sb_ss_json = generator.get_singbox_outbound('ss', ss_json, 'SSJson')
        sb_parts = set(sb_ss_json['plugin_opts'].split(';'))
        self.assertIn('mux=0', sb_parts)
        self.assertIn('tls', sb_parts)
        self.assertIn('skip-cert-verify', sb_parts)
        self.assertIn('v2ray-http-upgrade', sb_parts)
        self.assertIn('host=cdn.example.com', sb_parts)
        self.assertNotIn('fast-open', sb_parts)
        self.assertNotIn('fast-open=false', sb_parts)
        self.assertNotIn('tls=true', sb_parts)

        # Additional JSON edge cases: string "0", int 4, malformed "--1", tls=0, empty JSON "{}"
        uri_ss_mux_str0 = (
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            f'?plugin=v2ray-plugin&plugin-opts={quote(json.dumps({"mux": "0", "tls": 0}))}#SSStr0'
        )
        p_str0 = parse_ss(uri_ss_mux_str0)
        self.assertIs(p_str0['plugin-opts']['mux'], False)
        self.assertIs(p_str0['plugin-opts']['tls'], False)
        sb_str0 = generator.get_singbox_outbound('ss', p_str0, 'SSStr0')
        self.assertEqual(sb_str0['plugin_opts'], 'mux=0')

        uri_ss_mux_int4 = (
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            f'?plugin=v2ray-plugin&plugin-opts={quote(json.dumps({"mux": 4, "tls": 1}))}#SSInt4'
        )
        p_int4 = parse_ss(uri_ss_mux_int4)
        self.assertIs(p_int4['plugin-opts']['mux'], True)
        self.assertIs(p_int4['plugin-opts']['tls'], True)
        sb_int4 = generator.get_singbox_outbound('ss', p_int4, 'SSInt4')
        self.assertEqual(set(sb_int4['plugin_opts'].split(';')), {'mux=1', 'tls'})

        uri_ss_bad_mux = (
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            f'?plugin=v2ray-plugin&plugin-opts={quote(json.dumps({"mux": "--1"}))}#SSBadMux'
        )
        self.assertIs(parse_ss(uri_ss_bad_mux)['plugin-opts']['mux'], False)

        uri_ss_empty_json_obfs = (
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            f'?plugin=obfs-local&plugin-opts={quote("{}")}#SSEmptyObfs'
        )
        p_empty_obfs = parse_ss(uri_ss_empty_json_obfs)
        self.assertEqual(p_empty_obfs['plugin'], 'obfs')
        self.assertNotIn('plugin-opts', p_empty_obfs)

        uri_ss_empty_json_v2 = (
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            f'?plugin=v2ray-plugin&plugin-opts={quote("{}")}#SSEmptyV2'
        )
        p_empty_v2 = parse_ss(uri_ss_empty_json_v2)
        self.assertEqual(p_empty_v2['plugin-opts'], {'mode': 'websocket'})

        # Whitespace-padded VLESS security=none must not enable TLS
        p_ws_none = parse_vless(
            'vless://11111111-2222-3333-4444-555555555555@vl.example.com:443?security=%20none%20#WSNone'
        )
        self.assertFalse(p_ws_none['tls'])
        self.assertNotIn('reality-opts', p_ws_none)

        # v2ray-http-upgrade-fast-open normalized in both JSON and semicolon branches + omitted when false in Sing-Box
        uri_ss_upgrade_fo = (
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            f'?plugin=v2ray-plugin&plugin-opts={quote(json.dumps({"v2ray-http-upgrade": "true", "v2ray-http-upgrade-fast-open": "false"}))}#SSUpFO'
        )
        p_up_fo = parse_ss(uri_ss_upgrade_fo)
        self.assertIs(p_up_fo['plugin-opts']['v2ray-http-upgrade'], True)
        self.assertIs(p_up_fo['plugin-opts']['v2ray-http-upgrade-fast-open'], False)
        sb_up_fo = generator.get_singbox_outbound('ss', p_up_fo, 'SSUpFO')
        self.assertEqual(sb_up_fo['plugin_opts'], 'v2ray-http-upgrade')

        # Uppercase plugin name and option keys normalized cleanly; empty mode defaults to websocket
        uri_ss_upper = (
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            f'?plugin=V2RAY-PLUGIN&plugin-opts={quote(json.dumps({"MODE": "", "TLS": "true", "Mux": 0}))}#SSUpper'
        )
        p_upper = parse_ss(uri_ss_upper)
        self.assertEqual(p_upper['plugin'], 'v2ray-plugin')
        self.assertEqual(p_upper['plugin-opts'], {'mode': 'websocket', 'tls': True, 'mux': False})

        # JSON headers dict preserved in Clash YAML, converted safely to host= (never dict repr) in Sing-Box
        uri_ss_headers = (
            'ss://YWVzLTEyOC1nY206cGFzcw==@ss.example.com:8388'
            f'?plugin=v2ray-plugin&plugin-opts={quote(json.dumps({"mode": "websocket", "headers": {"Host": "cdn.example.com"}}))}#SSHeaders'
        )
        p_headers = parse_ss(uri_ss_headers)
        self.assertEqual(p_headers['plugin-opts']['headers'], {'Host': 'cdn.example.com'})
        sb_headers = generator.get_singbox_outbound('ss', p_headers, 'SSHeaders')
        self.assertEqual(sb_headers['plugin_opts'], 'host=cdn.example.com')
        self.assertNotIn('{', sb_headers['plugin_opts'])


class Round3GlobalAudit24ItemsTest(unittest.TestCase):
    """Regression suite covering all 24 deep global review findings (P0-1..2, P1-1..8, P2-1..9, P3-1..5)."""

    def setUp(self):
        import app.config_manager as cm
        self._orig_cfg = cm._snapshot_globals()
        cm.sync_config_globals({
            'udp': False, 'skipcert': False, 'emoji': False,
            'custom': False, 'custom_loopback': False, 'custom_node_name': False,
        })
        view._login_rate_limiter.reset()
        remote.get_country_emoji.cache_clear()
        remote.clear_remote_sub_cache()
        generator.clear_template_cache()

    def tearDown(self):
        import app.config_manager as cm
        cm.sync_config_globals(self._orig_cfg)
        view._login_rate_limiter.reset()
        remote.get_country_emoji.cache_clear()
        remote.clear_remote_sub_cache()
        generator.clear_template_cache()

    def test_p0_1_surge_crlf_section_injection_and_syntax_sanitization(self):
        # CRLF + [Script] section injection in node name, password, and SNI must be collapsed to one safe line
        malicious_uri = (
            'trojan://pass%2Ccomma%0D%0A%5BScript%5D%0Aevil%3Dtype%3Dhttp-request'
            '@1.2.3.4:443?sni=good.example.com%0A%5BRule%5D%0AFINAL%2CDIRECT'
            '#Bad%2CName%3D1%0D%0A%5BScript%5D%0Apwn%3D1'
        )
        line, _ = generator.parse_surge_node(malicious_uri)
        self.assertIsNotNone(line)
        self.assertNotIn('\n', line)
        self.assertNotIn('\r', line)
        self.assertEqual(len(line.splitlines()), 1)
        # Name commas & equals replaced with '-' so Surge INI parser never splits key/value
        name_part, _, rest = line.partition(' = ')
        self.assertNotIn(',', name_part)
        self.assertNotIn('=', name_part)
        # Password containing comma is safely quoted
        self.assertIn('password="', rest)

        # Full surge_encode must contain ZERO injected [Script] section headers
        surge_out = generator.surge_encode([SimpleNamespace(node=malicious_uri, remarks='')])
        self.assertFalse(any(l.strip().startswith('[Script]') for l in surge_out.splitlines()))

        # Invalid host with whitespace/comma raises ValueError in parse_surge_node and is skipped by surge_encode
        with self.assertRaises(ValueError):
            generator.parse_surge_node('trojan://pw@bad,host:443#BadHost')
        surge_bad = generator.surge_encode([SimpleNamespace(node='trojan://pw@bad,host:443#BadHost', remarks='')])
        self.assertNotIn('bad,host', surge_bad)

    def test_p0_2_and_p1_8_docker_entrypoint_compose_and_docs(self):
        with open(os.path.join(REPO_ROOT, 'docker-entrypoint.sh'), 'r', encoding='utf-8') as f:
            ep = f.read()
        self.assertIn('chown -R sublink:sublink /app/app/db', ep)
        self.assertIn('exec gosu sublink "$@"', ep)
        self.assertIn('mkdir -p /app/app/db', ep)

        with open(os.path.join(REPO_ROOT, 'Dockerfile'), 'r', encoding='utf-8') as f:
            df = f.read()
        self.assertIn('gosu', df)
        self.assertIn('npm ci', df)
        self.assertIn('npm run build', df)
        self.assertIn('app/static/dist', df)
        self.assertNotIn('yarn', df)
        self.assertNotIn('app/templates', df)
        self.assertIn('ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]', df)

        with open(os.path.join(REPO_ROOT, 'docker-compose.yml'), 'r', encoding='utf-8') as f:
            dc = f.read()
        for key in ('WORKERS', 'TRUSTED_PROXIES', 'TRUSTED_PROXY_COUNT', 'INIT_ADMIN_PASSWORD', 'ENABLE_LOGIN_GEOIP'):
            self.assertIn(key, dc)

        with open(os.path.join(REPO_ROOT, 'README.md'), 'r', encoding='utf-8') as f:
            readme = f.read()
        self.assertNotIn('--network host', readme)
        self.assertIn('127.0.0.1:8000:8000', readme)
        self.assertIn('TRUSTED_PROXIES', readme)
        self.assertIn('INIT_ADMIN_PASSWORD', readme)
        self.assertIn('?legacy=1', readme)

    def test_p1_1_surge_template_clean_and_reserved_name_collision_guard(self):
        with open(os.path.join(REPO_ROOT, 'app', 'surge.conf'), 'r', encoding='utf-8') as f:
            surge_tpl = f.read()
        for fake_node in ('日本节点 = direct', '美国节点 = direct', '新加坡节点 = direct', '台湾节点 = direct'):
            self.assertNotIn(fake_node, surge_tpl)
        self.assertIn('DIRECT = direct', surge_tpl)

        # Nodes named DIRECT / REJECT / template group name must be renamed in both Clash and Surge
        colliding = [
            SimpleNamespace(node='ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:443#DIRECT', remarks=''),
            SimpleNamespace(node='ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.5:443#REJECT', remarks=''),
            SimpleNamespace(node='ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.6:443#%F0%9F%9A%80%20%E8%8A%82%E7%82%B9%E9%80%89%E6%8B%A9', remarks=''),
        ]
        clash_doc = yaml.safe_load(generator.clash_encode(colliding))
        clash_names = [p['name'] for p in clash_doc['proxies']]
        self.assertNotIn('DIRECT', clash_names)
        self.assertNotIn('REJECT', clash_names)
        self.assertNotIn('🚀 节点选择', clash_names)
        self.assertEqual(len(set(clash_names)), 3)

        surge_out = generator.surge_encode(colliding)
        self.assertIn('DIRECT (2) = ss,', surge_out)
        self.assertIn('REJECT (2) = ss,', surge_out)
        self.assertIn('🚀 节点选择 (2) = ss,', surge_out)

    def test_p1_2_split_node_and_remarks_and_remarks_fallback_naming(self):
        from app.core.utils import split_node_and_remarks

        # Unescaped '|' inside balanced brackets in #fragment must NOT truncate node URI
        uri_pipe = 'vless://11111111-2222-3333-4444-555555555555@1.2.3.4:443#🇭🇰【香港 | BGP】'
        self.assertEqual(split_node_and_remarks(uri_pipe), (uri_pipe, ''))

        # Explicit trailing '|备注' splits cleanly while preserving inner '|'
        self.assertEqual(split_node_and_remarks(f'{uri_pipe}|我的备注'), (uri_pipe, '我的备注'))

        # Escaped '\|' from batch editor round-trips losslessly with or without remarks
        escaped = uri_pipe.replace('|', r'\|')
        self.assertEqual(split_node_and_remarks(f'{escaped}|备注A'), (uri_pipe, '备注A'))
        self.assertEqual(split_node_and_remarks(escaped), (uri_pipe, ''))

        # Unnamed node uses Sub.remarks as fallback node name on Clash / Surge / Sing-Box export
        unnamed = SimpleNamespace(
            node='ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:443',
            remarks='我的自建香港节点',
        )
        clash_doc = yaml.safe_load(generator.clash_encode([unnamed]))
        self.assertEqual(clash_doc['proxies'][0]['name'], '我的自建香港节点')
        surge_out = generator.surge_encode([unnamed])
        self.assertIn('我的自建香港节点 = ss,', surge_out)
        sb_doc = json.loads(generator.singbox_encode([unnamed]))
        self.assertTrue(any(o.get('tag') == '我的自建香港节点' for o in sb_doc['outbounds']))

    def test_p1_4_last_node_deletion_guard_and_steady_state_get_subs_readonly(self):
        app = _make_test_app()
        with app.app_context():
            db.create_all()
            db.session.add(Sub(
                name='OnlyOne',
                node='ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:443#N1',
                remarks='',
                sort_order=0,
                access_token='keep-this-token-safe-123456789012345678901234567',
                legacy_enabled=False,
            ))
            db.session.commit()
            sub_id = Sub.query.first().id

            client = app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            # Deleting the last remaining node must be rejected to protect access_token
            res = client.post(f'/del_sub_node/{sub_id}', headers=headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.get_json()['code'], 400)
            self.assertIn('最后一个节点', res.get_json()['msg'])
            self.assertEqual(Sub.query.count(), 1)

            # Steady-state /get_subs with populated tokens executes zero UPDATE/INSERT/COMMIT writes
            writes = []

            def spy_write(conn, cursor, statement, parameters, context, executemany):
                upper = statement.strip().upper()
                if upper.startswith(('INSERT', 'UPDATE', 'DELETE')):
                    writes.append(upper)

            sa.event.listen(db.engine, 'before_cursor_execute', spy_write)
            try:
                res_subs = client.post('/get_subs', headers=headers)
            finally:
                sa.event.remove(db.engine, 'before_cursor_execute', spy_write)
            self.assertEqual(res_subs.status_code, 200)
            self.assertEqual(writes, [])

    def test_p1_5_set_user_requires_old_password_and_validates_format(self):
        app = _make_test_app()
        with app.app_context():
            db.create_all()
            db.session.add(User(username='admin', password=hash_password('OldPass#123'), name='管理员', token_version=1))
            db.session.commit()
            client = app.test_client()
            with patch('app.remote.requests.get'):
                tok = client.post('/login', json={'username': 'admin', 'password': 'OldPass#123'}).get_json()['token']
            headers = {'Authorization': f'Bearer {tok}'}

            # Missing oldPassword rejected
            r1 = client.post('/set_user', json={'username': 'admin', 'newUserName': 'admin2', 'password': 'NewPass#123'}, headers=headers)
            self.assertEqual(r1.get_json()['code'], 400)
            self.assertIn('当前密码', r1.get_json()['msg'])

            # Wrong oldPassword rejected
            r2 = client.post('/set_user', json={
                'username': 'admin', 'oldPassword': 'WrongOldPassword', 'newUserName': 'admin2', 'password': 'NewPass#123'
            }, headers=headers)
            self.assertEqual(r2.get_json()['code'], 400)
            self.assertIn('当前密码', r2.get_json()['msg'])

            # Invalid username format rejected
            r3 = client.post('/set_user', json={
                'username': 'admin', 'oldPassword': 'OldPass#123', 'newUserName': 'ab', 'password': 'NewPass#123'
            }, headers=headers)
            self.assertEqual(r3.get_json()['code'], 400)

            # Invalid short password rejected
            r4 = client.post('/set_user', json={
                'username': 'admin', 'oldPassword': 'OldPass#123', 'newUserName': 'admin2', 'password': '123'
            }, headers=headers)
            self.assertEqual(r4.get_json()['code'], 400)

            # Valid oldPassword + format succeeds
            r5 = client.post('/set_user', json={
                'username': 'admin', 'oldPassword': 'OldPass#123', 'newUserName': 'admin_new', 'password': 'NewPass#123'
            }, headers=headers)
            self.assertEqual(r5.get_json()['code'], 200)

    def test_p1_6_max_content_length_yaml_bomb_and_decode_sub_limit(self):
        from app.core.utils import check_yaml_safe_aliases

        # 1. YAML Billion Laughs alias bomb blocked in milliseconds
        bomb = (
            "a: &a ['lol','lol','lol','lol','lol','lol','lol','lol','lol','lol']\n"
            "b: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a,*a]\n"
            "c: &c [*b,*b,*b,*b,*b,*b,*b,*b,*b,*b]\n"
            "d: &d [*c,*c,*c,*c,*c,*c,*c,*c,*c,*c]\n"
            "e: &e [*d,*d,*d,*d,*d,*d,*d,*d,*d,*d]\n"
            "proxies: []\n"
            "proxy-groups:\n"
            "  - name: G\n"
            "    type: select\n"
            "    proxies: [auto]\n"
        )
        with self.assertRaises(yaml.YAMLError):
            check_yaml_safe_aliases(bomb)

        err = view._validate_clash_yaml(bomb)
        self.assertIsNotNone(err)
        self.assertIn('格式错误', err)

        # 2. MAX_CONTENT_LENGTH returns JSON 413 on create_app()
        with tempfile.TemporaryDirectory() as td:
            with patch('app.ensure_db_dir', return_value=td), \
                    patch.dict(os.environ, {
                        'JWT_SECRET_KEY': 'test-413-secret-key-at-least-32-bytes-long',
                        'MAX_CONTENT_LENGTH': '128',
                    }, clear=True):
                small_app = create_app()
                small_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
                with small_app.app_context():
                    db.create_all()
                    r413 = small_app.test_client().post('/login', data='x' * 512, content_type='application/json')
                    self.assertEqual(r413.status_code, 413)
                    self.assertEqual(r413.get_json()['code'], 413)
                    db.session.remove()
                    db.engine.dispose()

        # 3. /decode_sub enforces MAX_DECODE_SUB_URLS (20)
        app = _make_test_app()
        with app.app_context():
            db.create_all()
            tok = create_access_token(identity='admin')
            r_many = app.test_client().post(
                '/decode_sub',
                json={'urls': [f'https://example.com/{i}' for i in range(25)]},
                headers={'Authorization': f'Bearer {tok}'},
            )
            self.assertEqual(r_many.get_json()['code'], 400)
            self.assertIn('20', r_many.get_json()['msg'])

    def test_p1_7_ssr_obfs_proto_params_and_surge_ss_obfs_hy2_pin(self):
        # 1. SSR obfsparam & protoparam decoded properly
        obfs_b64 = base64.urlsafe_b64encode(b'cdn.example.com').decode().rstrip('=')
        proto_b64 = base64.urlsafe_b64encode(b'12345:secret').decode().rstrip('=')
        rem_b64 = base64.urlsafe_b64encode(b'SSRParam').decode().rstrip('=')
        inner = (
            f'1.2.3.4:443:auth_aes128_md5:aes-128-ctr:tls1.2_ticket_auth:cGFzcw=='
            f'/?obfsparam={obfs_b64}&protoparam={proto_b64}&remarks={rem_b64}'
        )
        ssr_uri = 'ssr://' + base64.urlsafe_b64encode(inner.encode()).decode().rstrip('=')
        ssr_parsed = parse_ssr(ssr_uri)
        self.assertEqual(ssr_parsed['obfs-param'], 'cdn.example.com')
        self.assertEqual(ssr_parsed['protocol-param'], '12345:secret')

        # 2. Surge SS obfs & obfs-host emitted for simple-obfs
        ss_obfs_uri = (
            'ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:8388'
            '?plugin=obfs-local%3Bobfs%3Dtls%3Bobfs-host%3Dcdn.example.com#SSObfsSurge'
        )
        ss_line, _ = generator.parse_surge_node(ss_obfs_uri)
        self.assertIn('obfs=tls', ss_line)
        self.assertIn('obfs-host=cdn.example.com', ss_line)

        # 3. Surge Hy2 pinSHA256 emitted as server-cert-fingerprint-sha256 (valid 64-hex SHA256 fingerprint)
        sha256_hex = 'ab' * 32
        hy2_uri = f'hysteria2://secret@1.2.3.4:443?sni=hy2.example.com&pinSHA256={sha256_hex}#Hy2Pin'
        hy2_line, _ = generator.parse_surge_node(hy2_uri)
        self.assertIn(f'server-cert-fingerprint-sha256={sha256_hex}', hy2_line)

    def test_p2_1_rate_limiter_ip_bucket_isolated_from_username_flood(self):
        limiter = view._LoginRateLimiter(max_user_entries=5, max_ip_entries=10)
        with patch.dict(os.environ, {'LOGIN_RATE_LIMIT_MAX_ATTEMPTS': '3', 'LOGIN_RATE_LIMIT_IP_MAX_ATTEMPTS': '10', 'LOGIN_RATE_LIMIT_WINDOW': '60'}):
            # Attacker sprays 20 random usernames from same IP — IP bucket must NOT be evicted!
            for i in range(20):
                limiter.record_failure('203.0.113.9', f'rand_user_{i}')
            blocked, retry_after = limiter.check_blocked('203.0.113.9', 'victim_admin')
            self.assertTrue(blocked)
            self.assertGreaterEqual(retry_after, 1)

    def test_p2_3_remote_trust_env_emoji_short_fail_ttl_and_login_log_pruning(self):
        # 1. Hardened HTTP session disables environment proxies by default
        sess = remote._get_remote_session()
        self.assertFalse(sess.trust_env)

        # 2. get_country_emoji failure is NOT permanently cached; recovers after short TTL
        remote.get_country_emoji.cache_clear()
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {'flag': {'emoji': '🇸🇬'}}
        with patch.object(remote, 'EMOJI_FAIL_CACHE_TTL', 0.05):
            with patch('requests.get', side_effect=requests.RequestException('temp fail')) as m_fail:
                self.assertEqual(remote.get_country_emoji('9.9.9.9'), '')
                # Within failure TTL, does not hammer upstream
                self.assertEqual(remote.get_country_emoji('9.9.9.9'), '')
                self.assertEqual(m_fail.call_count, 1)
            import time
            time.sleep(0.08)
            with patch('requests.get', return_value=ok_resp) as m_ok:
                self.assertEqual(remote.get_country_emoji('9.9.9.9'), '🇸🇬')
                self.assertEqual(m_ok.call_count, 1)

        # 3. save_ip_address records seconds, respects ENABLE_LOGIN_GEOIP=0, and prunes old rows
        app = _make_test_app()
        with app.app_context():
            db.create_all()
            with patch.dict(os.environ, {'ENABLE_LOGIN_GEOIP': '0', 'MAX_LOGIN_LOG_ROWS': '3'}), \
                    patch('requests.get') as mock_get:
                for i in range(5):
                    with app.test_request_context('/login', environ_base={'REMOTE_ADDR': f'198.51.100.{i}'}):
                        remote.save_ip_address()
                mock_get.assert_not_called()
            rows = Login.query.order_by(Login.id.asc()).all()
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[-1].ip, '198.51.100.4')
            # Timestamp format includes seconds: YYYY-MM-DD HH:MM:SS
            self.assertRegex(rows[-1].time, r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')

    def test_p2_4_jwt_unified_401_json_loaders(self):
        from datetime import timedelta

        app = _make_test_app()
        with app.app_context():
            db.create_all()
            client = app.test_client()
            # Missing Authorization header -> 401 JSON
            r_unauth = client.post('/get_config')
            self.assertEqual(r_unauth.status_code, 401)
            self.assertEqual(r_unauth.get_json()['code'], 401)

            # Expired token -> 401 JSON
            expired_tok = create_access_token(identity='admin', expires_delta=timedelta(seconds=-10))
            r_exp = client.post('/get_config', headers={'Authorization': f'Bearer {expired_tok}'})
            self.assertEqual(r_exp.status_code, 401)
            self.assertEqual(r_exp.get_json()['code'], 401)

    def test_p2_5_config_manager_no_global_clobber_and_unique_config_upsert(self):
        import app.config_manager as cm

        app = _make_test_app()
        with app.app_context():
            db.create_all()
            db.session.add(Config(key='udp', value='1'))
            db.session.commit()

            orig_udp = cm.Udp
            try:
                cm.sync_config_globals({'udp': False})
                with app.test_request_context('/get_config'):
                    cfg = cm.get_runtime_config()
                    self.assertTrue(cfg['udp'])
                    # Regular request read must NOT mutate shared module globals
                    self.assertFalse(cm.Udp)
            finally:
                cm.sync_config_globals({'udp': orig_udp})

            # Repeated /set_config upserts stay unique per key
            tok = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {tok}'}
            client = app.test_client()
            for val in (True, False, True):
                res = client.post('/set_config', json={'udp': val, 'emoji': val}, headers=headers)
                self.assertEqual(res.get_json()['code'], 200)
            self.assertEqual(Config.query.filter_by(key='udp').count(), 1)
            self.assertEqual(Config.query.filter_by(key='emoji').count(), 1)

    def test_p2_6_singbox_legacy_query_param_and_version_compat(self):
        app = _make_test_app()
        with app.app_context():
            db.create_all()
            db.session.add(Sub(
                name='SBSub',
                node='ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:443#N1',
                remarks='',
                sort_order=0,
                access_token='tok-sb-compat-123456789012345678901234567890123',
                legacy_enabled=False,
            ))
            db.session.commit()
            client = app.test_client()

            # Default output uses sing-box 1.14+ http_clients (no deprecated download_detour)
            r_modern = client.get('/sub/sing-box/tok-sb-compat-123456789012345678901234567890123')
            self.assertEqual(r_modern.status_code, 200)
            doc_modern = json.loads(r_modern.get_data(as_text=True))
            self.assertIn('http_clients', doc_modern)
            for rs in doc_modern.get('route', {}).get('rule_set', []):
                self.assertNotIn('download_detour', rs)

            # ?legacy=1 emits legacy download_detour without http_clients
            r_legacy = client.get('/sub/sing-box/tok-sb-compat-123456789012345678901234567890123?legacy=1')
            self.assertEqual(r_legacy.status_code, 200)
            doc_legacy = json.loads(r_legacy.get_data(as_text=True))
            self.assertNotIn('http_clients', doc_legacy)
            remote_sets = [rs for rs in doc_legacy.get('route', {}).get('rule_set', []) if rs.get('type') == 'remote']
            self.assertTrue(len(remote_sets) > 0)
            for rs in remote_sets:
                self.assertIn('download_detour', rs)
                self.assertNotIn('http_client', rs)

            # ?version=1.12 also switches to legacy format; ?version=1.14 keeps modern format
            r_v112 = client.get('/sub/sing-box/tok-sb-compat-123456789012345678901234567890123?version=1.12.9')
            doc_v112 = json.loads(r_v112.get_data(as_text=True))
            self.assertNotIn('http_clients', doc_v112)
            r_v114 = client.get('/sub/sing-box/tok-sb-compat-123456789012345678901234567890123?version=1.14.0')
            doc_v114 = json.loads(r_v114.get_data(as_text=True))
            self.assertIn('http_clients', doc_v114)

    def test_p2_8_and_p2_9_field_length_validation_and_xui_cookie_fix(self):
        app = _make_test_app()
        with app.app_context():
            db.create_all()
            client = app.test_client()
            tok = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {tok}'}

            r_long_name = client.post(
                '/create_sub',
                json={'name': 'A' * 41, 'node': ['ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:443#N1']},
                headers=headers,
            )
            self.assertEqual(r_long_name.get_json()['code'], 400)
            self.assertIn('40', r_long_name.get_json()['msg'])

            r_long_rem = client.post(
                '/create_sub',
                json={'name': 'OkSub', 'node': ['ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:443#N1|' + 'R' * 41]},
                headers=headers,
            )
            self.assertEqual(r_long_rem.get_json()['code'], 400)
            self.assertIn('备注', r_long_rem.get_json()['msg'])

            # Login.ip accepts full 45-char IPv6 address
            ipv6_addr = '2001:0db8:85a3:0000:0000:8a2e:0370:7334'
            db.session.add(Login(ip=ipv6_addr, address='Test', time='2026-01-01 00:00:00'))
            db.session.commit()
            self.assertEqual(Login.query.first().ip, ipv6_addr)

    def test_p3_3_p3_4_p3_5_redaction_rewrite_env_and_prod_pbkdf2_default(self):
        from app.core.utils import redact_uri_credentials
        import tests.conftest as test_conftest

        # P3-3: credential redaction masks passwords/tokens/opaque proxy payloads
        r_hy2 = redact_uri_credentials('hysteria2://supersecret@1.2.3.4:443?obfs-password=obfspw&sni=a.com#MyNode')
        self.assertNotIn('supersecret', r_hy2)
        self.assertNotIn('obfspw', r_hy2)
        self.assertIn('1.2.3.4:443', r_hy2)
        self.assertEqual(redact_uri_credentials('vmess://eyJwcyI6InNlY3JldCJ9'), 'vmess://<redacted>')
        r_http = redact_uri_credentials('https://sub.example.com/sub/clash/abcdefghijklmnopqrstuvwxyz123456?token=mysecret')
        self.assertNotIn('abcdefghijklmnopqrstuvwxyz123456', r_http)
        self.assertNotIn('mysecret', r_http)

        # P3-4: rewrite rules configurable via env vars
        orig_custom = view.CustomFeature
        orig_loopback = view.CustomLoopback
        orig_nodename = view.CustomNodeName
        try:
            view.CustomFeature = True
            view.CustomLoopback = True
            view.CustomNodeName = True
            with patch.dict(os.environ, {
                'CUSTOM_LOOPBACK_PORT': '8443',
                'CUSTOM_HK_PREFIX': '🇭🇰【自定义',
                'CUSTOM_NAME_REWRITE_RULES': json.dumps([[['-CUSTOM'], '🇩🇪【法兰克福']]),
            }):
                out = rewrite.rewrite_remote_node(
                    'vless://uuid@127.0.0.1:10086#🇭🇰【自定义-01-CUSTOM',
                    'edge.example.com',
                )
                self.assertIn('@edge.example.com:8443', out)
                self.assertIn('%F0%9F%87%A9%F0%9F%87%AA', out)
        finally:
            view.CustomFeature = orig_custom
            view.CustomLoopback = orig_loopback
            view.CustomNodeName = orig_nodename

        # P3-5: production PBKDF2 default remains 260,000 iterations even though pytest fixture speeds up tests
        import app.model as app_model
        self.assertEqual(app_model.DEFAULT_PASSWORD_HASH_METHOD, 'pbkdf2:sha256:260000')
        self.assertEqual(test_conftest.PRODUCTION_PASSWORD_HASH_METHOD, 'pbkdf2:sha256:260000')

    def test_round4_empty_effective_nodes_no_duplicate_direct_in_clash_and_surge(self):
        # 1. Empty node list -> Clash proxy-groups must have NO duplicate DIRECT or duplicate entries
        clash_doc = yaml.safe_load(generator.clash_encode([]))
        self.assertEqual(clash_doc['proxies'], [])
        for group in clash_doc.get('proxy-groups', []):
            proxies = group.get('proxies', [])
            self.assertGreater(len(proxies), 0)
            self.assertEqual(len(proxies), len(set(proxies)), msg=f"Duplicate entries in Clash group {group['name']}: {proxies}")
            self.assertLessEqual(proxies.count('DIRECT'), 1, msg=f"Duplicate DIRECT in Clash group {group['name']}: {proxies}")

        # 2. Pure VLESS subscription exported to Surge (0 supported Surge nodes) -> NO duplicate DIRECT in any [Proxy Group]
        vless_only = [SimpleNamespace(
            node='vless://11111111-1111-1111-1111-111111111111@1.2.3.4:443?security=tls#OnlyVless',
            remarks='',
        )]
        surge_out = generator.surge_encode(vless_only)
        self.assertNotIn('DIRECT,DIRECT', surge_out)
        in_group_section = False
        checked_groups = 0
        for line in surge_out.splitlines():
            stripped = line.strip()
            if stripped.startswith('['):
                in_group_section = (stripped == '[Proxy Group]')
                continue
            if not in_group_section or not stripped or stripped.startswith('#') or '=' not in line:
                continue
            checked_groups += 1
            _, _, rhs = line.partition('=')
            parts = [p.strip() for p in rhs.split(',')[1:] if p.strip() and '=' not in p]
            self.assertEqual(len(parts), len(set(parts)), msg=f'Duplicate entries in Surge group line: {line}')
            self.assertLessEqual(parts.count('DIRECT'), 1, msg=f'Duplicate DIRECT in Surge group line: {line}')
        self.assertGreater(checked_groups, 0)

    def test_round4_batch_escape_roundtrip_and_unbracketed_pipe_fragment(self):
        from app.core.utils import split_node_and_remarks

        def frontend_format_line(node: str, remarks: str = '') -> str:
            escaped = node.replace('\\', '\\\\').replace('|', '\\|')
            return f'{escaped}|{remarks}' if remarks else escaped

        # 1. Raw pasted unbracketed airport node name '#HK | IEPL | 01' is NOT truncated
        uri_spaces = 'vless://11111111-1111-1111-1111-111111111111@1.2.3.4:443#HK | IEPL | 01'
        self.assertEqual(split_node_and_remarks(uri_spaces), (uri_spaces, ''))
        # Explicit trailing compact '|我的备注' still splits cleanly
        self.assertEqual(split_node_and_remarks(f'{uri_spaces}|我的备注'), (uri_spaces, '我的备注'))

        # 2. Strict symmetrical batch editor round-trip for trailing backslash, literal '\|', and multi-pipe fragments
        roundtrip_cases = [
            ('trojan://pw@1.2.3.4:443#Node\\', 'MyRemark'),
            ('trojan://pw@1.2.3.4:443#Node\\', ''),
            ('trojan://pw@1.2.3.4:443#Node\\|A', ''),
            ('trojan://pw@1.2.3.4:443#Node\\|A', 'MyRemark'),
            (uri_spaces, ''),
            (uri_spaces, '线路备注'),
            ('vless://11111111-2222-3333-4444-555555555555@1.2.3.4:443#🇭🇰【香港 | BGP】', 'BGP备注'),
        ]
        for node, remarks in roundtrip_cases:
            serialized = frontend_format_line(node, remarks)
            parsed_node, parsed_remarks = split_node_and_remarks(serialized)
            self.assertEqual(
                (parsed_node, parsed_remarks),
                (node, remarks),
                msg=f'Batch roundtrip mismatch for ({node!r}, {remarks!r}) via {serialized!r}',
            )

    def test_round4_get_subs_locked_requery_singbox_compat_docs_and_web_noclean(self):
        # 1. /get_subs re-queries inside _sub_write_lock() so concurrent backfill isn't overwritten
        app = _make_test_app()
        with app.app_context():
            db.create_all()
            db.session.add(Sub(
                name='RaceSub',
                node='ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:443#N1',
                remarks='',
                sort_order=0,
                access_token=None,
                legacy_enabled=False,
            ))
            db.session.commit()

            orig_lock = view._sub_write_lock
            concurrent_token = 'concurrent-writer-token-123456789012345678901234'

            from contextlib import contextmanager

            @contextmanager
            def lock_with_concurrent_writer():
                # Simulate another worker committing access_token right before this worker acquires lock
                with orig_lock():
                    db.session.execute(
                        sa.text('UPDATE sub SET access_token = :tok WHERE name = :name'),
                        {'tok': concurrent_token, 'name': 'RaceSub'},
                    )
                    db.session.commit()
                    yield

            token = create_access_token(identity='admin')
            with patch.object(view, '_sub_write_lock', lock_with_concurrent_writer):
                res = app.test_client().post('/get_subs', headers={'Authorization': f'Bearer {token}'})
            self.assertEqual(res.status_code, 200)
            items = res.get_json()
            self.assertEqual(items[0]['access_token'], concurrent_token)
            self.assertEqual(Sub.query.filter_by(name='RaceSub').first().access_token, concurrent_token)

        # 2. README.md and generator docstring align on sing-box 1.12 - 1.13 legacy range
        with open(os.path.join(REPO_ROOT, 'README.md'), 'r', encoding='utf-8') as f:
            readme = f.read()
        self.assertIn('sing-box 1.12 ～ 1.13', readme)
        self.assertNotIn('sing-box 1.11', readme)
        self.assertIn('1.12 - 1.13', generator.convert_singbox_to_legacy_options.__doc__ or '')

        # 3. Unified Vue 3 frontend in web/ builds to app/static/dist, Flask serves / and redirects /next -> /
        with open(os.path.join(REPO_ROOT, 'web', 'package.json'), 'r', encoding='utf-8') as f:
            web_pkg = json.load(f)
        self.assertIn('vite build', web_pkg['scripts']['build'])
        self.assertIn('vue-tsc --noEmit', web_pkg['scripts']['build'])
        self.assertFalse(os.path.exists(os.path.join(REPO_ROOT, 'web', 'next')))

        with open(os.path.join(REPO_ROOT, 'web', 'vite.config.ts'), 'r', encoding='utf-8') as f:
            vite_cfg = f.read()
        self.assertIn("base: '/static/dist/'", vite_cfg)
        self.assertIn('../app/static/dist', vite_cfg)

        app_ui = _make_test_app()
        with app_ui.app_context():
            client_ui = app_ui.test_client()
            for next_path in ('/next', '/next/'):
                res_next = client_ui.get(next_path)
                self.assertEqual(res_next.status_code, 302)
                self.assertTrue(res_next.headers['Location'].endswith('/'))

            with tempfile.TemporaryDirectory() as tmp_app_dir:
                with patch.object(view, 'path', tmp_app_dir):
                    res_missing = client_ui.get('/')
                    self.assertEqual(res_missing.status_code, 503)
                    self.assertIn('npm run build', res_missing.get_data(as_text=True))

                    dist_dir = os.path.join(tmp_app_dir, 'static', 'dist')
                    os.makedirs(dist_dir, exist_ok=True)
                    with open(os.path.join(dist_dir, 'index.html'), 'w', encoding='utf-8') as f:
                        f.write('<!DOCTYPE html><html><body>sublink-vue3</body></html>')

                    with client_ui.get('/') as res_ok:
                        self.assertEqual(res_ok.status_code, 200)
                        self.assertIn('sublink-vue3', res_ok.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
