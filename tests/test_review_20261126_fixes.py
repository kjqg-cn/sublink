import base64
import json
import os
import sqlite3
import tempfile
import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml
from flask import Flask
from flask_jwt_extended import create_access_token, create_refresh_token
from sqlalchemy.exc import SAWarning

from app import config_manager, remote, view
from app.core import generator, parsers
from app.exts import db, init_exts, jwtmanager
from app.model import Sub, User, hash_password
from upgrade_db import (
    CONFIG_SCHEMA_REVISION,
    USER_AUTH_REVISION,
    detect_schema_revision,
    read_schema_state,
    upgrade_database,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
VALID_SHA256 = '9A63E05CCED113283D090B274A08AE4F817F962F7DE8456F3B1013844F2065E6'


class Review20261126FixesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_dir = os.path.join(self.temp_dir.name, 'db')
        os.mkdir(db_dir)
        for fname in ('clash.yaml', 'surge.conf', 'sing-box.json'):
            src = os.path.join(REPO_ROOT, 'app', fname)
            with open(src, 'r', encoding='utf-8') as f_src:
                with open(os.path.join(db_dir, fname), 'w', encoding='utf-8') as f_dst:
                    f_dst.write(f_src.read())

        self._orig_cfg = config_manager._snapshot_globals()
        config_manager.sync_config_globals({
            'udp': False, 'skipcert': False, 'emoji': False, 'hy2_pin_fallback': False,
            'custom': False, 'custom_loopback': False, 'custom_node_name': False,
        })
        view._login_rate_limiter.reset()
        remote.get_country_emoji.cache_clear()
        remote.clear_remote_sub_cache()
        generator.clear_template_cache()

    def tearDown(self):
        config_manager.sync_config_globals(self._orig_cfg)
        view._login_rate_limiter.reset()
        remote.get_country_emoji.cache_clear()
        remote.clear_remote_sub_cache()
        generator.clear_template_cache()
        self.temp_dir.cleanup()

    def _make_memory_app(self) -> Flask:
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['JWT_SECRET_KEY'] = 'review-20261126-secret-key-32-bytes'
        db.init_app(app)
        jwtmanager.init_app(app)
        app.register_blueprint(view.blue)
        app.after_request(view.apply_security_headers)
        return app

    # ---- P1-1 & P1-3: sing-box Hy2 explicit pinSHA256 switch + server_ports + ?legacy=1 ----
    def test_p1_1_and_p1_3_singbox_hy2_server_ports_legacy_and_pin_switch(self):
        hy2_gecko = (
            'hysteria2://pw@hy2.example.com:443?sni=hy2.example.com'
            '&obfs=gecko&obfs-password=gpass&mport=20000-20010&hop-interval=10-20'
            f'&pinSHA256={VALID_SHA256}#Hy2Gecko'
        )
        hy2_sal = (
            'hysteria2://pw@hy2.example.com:443?sni=hy2.example.com'
            '&obfs=salamander&obfs-password=spass&mport=20000-20010&hop-interval=10-20#Hy2Sal'
        )
        subs = [SimpleNamespace(node=hy2_gecko), SimpleNamespace(node=hy2_sal)]

        with patch.object(view, 'path', self.temp_dir.name):
            # Default: hy2_pin_fallback=False -> secure by default (insecure=False)
            cfg_default = json.loads(generator.singbox_encode(subs, legacy_format=False))
            # Explicit switch enabled: pinned node falls back to insecure=True with warning log
            with self.assertLogs('app.core.generator', level='WARNING') as cm:
                cfg_114 = json.loads(generator.singbox_encode(subs, legacy_format=False, hy2_pin_fallback=True))
            cfg_legacy = json.loads(generator.singbox_encode(subs, legacy_format=True))

        self.assertTrue(any('pinSHA256' in msg for msg in cm.output))

        ob_default = {o['tag']: o for o in cfg_default['outbounds']}
        self.assertFalse(ob_default['Hy2Gecko']['tls']['insecure'])
        self.assertFalse(ob_default['Hy2Sal']['tls']['insecure'])

        ob_114 = {o['tag']: o for o in cfg_114['outbounds']}
        # server_ports must drop conflicting server_port
        self.assertNotIn('server_port', ob_114['Hy2Gecko'])
        self.assertEqual(ob_114['Hy2Gecko']['server_ports'], ['20000:20010'])
        self.assertEqual(ob_114['Hy2Gecko']['hop_interval'], '10s')
        self.assertEqual(ob_114['Hy2Gecko']['hop_interval_max'], '20s')
        self.assertEqual(ob_114['Hy2Gecko']['obfs']['type'], 'gecko')
        self.assertTrue(ob_114['Hy2Gecko']['tls']['insecure'])
        self.assertFalse(ob_114['Hy2Sal']['tls']['insecure'])

        ob_legacy = {o['tag']: o for o in cfg_legacy['outbounds']}
        # legacy 1.12-1.13 must skip gecko node and omit hop_interval_max
        self.assertNotIn('Hy2Gecko', ob_legacy)
        self.assertIn('Hy2Sal', ob_legacy)
        self.assertNotIn('server_port', ob_legacy['Hy2Sal'])
        self.assertEqual(ob_legacy['Hy2Sal']['hop_interval'], '10s')
        self.assertNotIn('hop_interval_max', ob_legacy['Hy2Sal'])

        # HTTP endpoint: global config switch & per-URL ?hy2_pin_fallback=1|0 override
        app = self._make_memory_app()
        with app.app_context(), patch.object(view, 'path', self.temp_dir.name):
            db.create_all()
            user = User(username='admin', password=hash_password('Pass#123'), name='管理员', token_version=1)
            db.session.add(user)
            db.session.add(Sub(
                name='Hy2Sub', node=hy2_gecko, remarks='', sort_order=0,
                access_token='hy2tok1234567890', legacy_enabled=False,
            ))
            db.session.commit()
            client = app.test_client()
            jwt_tok = create_access_token(identity='admin', additional_claims={'tv': 1, 'uid': user.id})
            auth_h = {'Authorization': f'Bearer {jwt_tok}'}

            # Default off -> insecure=False
            r_off = client.get('/sub/sing-box/hy2tok1234567890')
            ob = next(o for o in json.loads(r_off.data)['outbounds'] if o['tag'] == 'Hy2Gecko')
            self.assertFalse(ob['tls']['insecure'])

            # Per-URL ?hy2_pin_fallback=1 -> insecure=True
            r_q1 = client.get('/sub/sing-box/hy2tok1234567890?hy2_pin_fallback=1')
            ob = next(o for o in json.loads(r_q1.data)['outbounds'] if o['tag'] == 'Hy2Gecko')
            self.assertTrue(ob['tls']['insecure'])

            # Global switch on via /set_config -> insecure=True by default, ?hy2_pin_fallback=0 overrides to False
            r_cfg = client.post('/set_config', json={'hy2_pin_fallback': True}, headers=auth_h)
            self.assertEqual(r_cfg.get_json()['code'], 200)
            r_on = client.get('/sub/sing-box/hy2tok1234567890')
            ob = next(o for o in json.loads(r_on.data)['outbounds'] if o['tag'] == 'Hy2Gecko')
            self.assertTrue(ob['tls']['insecure'])
            r_q0 = client.get('/sub/sing-box/hy2tok1234567890?hy2_pin_fallback=0')
            ob = next(o for o in json.loads(r_q0.data)['outbounds'] if o['tag'] == 'Hy2Gecko')
            self.assertFalse(ob['tls']['insecure'])

    # ---- P1-2: accurate bandwidth normalization & Mbps conversion ----
    def test_p1_2_bandwidth_conversion_accuracy(self):
        cases = [
            ('0.5 Gbps', '500 Mbps', 500),
            ('1.5 Gbps', '1500 Mbps', 1500),
            ('2.5 Gbps', '2500 Mbps', 2500),
            ('0.5 Mbps', '500 Kbps', None),
            ('100 bps', '100 bps', None),
            ('100 Bps', '100 Bps', None),
            ('100 MB/s', '100 MBps', 800),
            ('1.5 MB/s', '1500 KBps', 12),
            ('500 Kbps', '500 Kbps', None),
            ('2000 Kbps', '2000 Kbps', 2),
            ('100', '100 Mbps', 100),
            ('0', None, None),
        ]
        for raw, expected_mihomo, expected_sb in cases:
            with self.subTest(raw=raw):
                self.assertEqual(parsers._normalize_hysteria2_bandwidth(raw), expected_mihomo)
                self.assertEqual(generator.get_singbox_bandwidth(raw), expected_sb)

    # ---- P1-5: cross-worker file-backed rate limiter ----
    def test_p1_5_cross_worker_file_backed_rate_limiter(self):
        db_file = os.path.join(self.temp_dir.name, 'db', 'rl.db')
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_file}'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['JWT_SECRET_KEY'] = 'test-secret-key-for-rl-32-bytes-len'

        worker1 = view._LoginRateLimiter()
        worker2 = view._LoginRateLimiter()

        with app.app_context(), patch.dict(os.environ, {'LOGIN_RATE_LIMIT_MAX_ATTEMPTS': '3'}):
            worker1.reset()
            worker1.record_failure('203.0.113.10', 'admin')
            worker2.record_failure('203.0.113.10', 'admin')
            blocked_before, _ = worker1.check_blocked('203.0.113.10', 'admin')
            self.assertFalse(blocked_before)

            worker1.record_failure('203.0.113.10', 'admin')
            blocked_after, retry_after = worker2.check_blocked('203.0.113.10', 'admin')
            self.assertTrue(blocked_after)
            self.assertGreaterEqual(retry_after, 1)

            worker2.clear_success('203.0.113.10', 'admin')
            blocked_cleared, _ = worker1.check_blocked('203.0.113.10', 'admin')
            self.assertFalse(blocked_cleared)

    # ---- P2-1: bad port & missing credentials skipped cleanly across all formats ----
    def test_p2_1_invalid_ports_and_missing_credentials_are_skipped(self):
        bad_nodes = [
            'vless://@1.2.3.4:99999#BadVless',
            'vless://@1.2.3.4:443#NoUuidVless',
            'ss://1.2.3.4:0#ZeroPortSS',
            'trojan://@1.2.3.4:-1#NegTrojan',
            'trojan://@1.2.3.4:443#EmptyPwdTrojan',
            'hysteria2://1.2.3.4:443?sni=hy2.example.com#EmptyPwdHy2',
        ]
        good_node = 'trojan://goodpass@1.2.3.4:443?sni=good.example.com#GoodNode'
        subs = [SimpleNamespace(node=n, remarks='') for n in bad_nodes + [good_node]]

        with patch.object(view, 'path', self.temp_dir.name):
            clash_data = yaml.safe_load(generator.clash_encode(subs))
            surge_text = generator.surge_encode(subs)
            sb_data = json.loads(generator.singbox_encode(subs))

        self.assertEqual([p['name'] for p in clash_data['proxies']], ['GoodNode'])
        self.assertIn('GoodNode = trojan,1.2.3.4,443', surge_text)
        self.assertNotIn('NegTrojan', surge_text)
        self.assertNotIn('ZeroPortSS', surge_text)
        sb_proxy_tags = [o['tag'] for o in sb_data['outbounds'] if o['type'] not in ('selector', 'urltest', 'direct')]
        self.assertEqual(sb_proxy_tags, ['GoodNode'])

    # ---- P2-2: YAML 1.2 scalar quoting, Reality skip-cert-verify, multi-protocol case-insensitive query ----
    def test_p2_2_yaml_scientific_quoting_reality_skip_cert_and_case_insensitive_queries(self):
        trojan_sci = 'trojan://1e234567@tr.example.com:443?SNI=sni.example.com&Type=ws&Path=/ws&Host=h.example.com&AllowInsecure=1#1.0e5'
        hy1_upper = 'hysteria://hy1.example.com:443?Auth=pw&UpMbps=50&DownMbps=100&SNI=hy1.example.com&allowInsecure=1#Hy1Upper'
        reality_insec = (
            'vless://00000000-0000-0000-0000-000000000001@1.2.3.4:443'
            '?security=reality&pbk=pub123&sid=0123&insecure=1&type=tcp#RealInsec'
        )
        p_tr = parsers.parse_trojan(trojan_sci)
        self.assertEqual(p_tr['sni'], 'sni.example.com')
        self.assertEqual(p_tr['network'], 'ws')
        self.assertEqual(p_tr['ws-opts']['path'], '/ws')
        self.assertEqual(p_tr['ws-opts']['headers'], {'Host': 'h.example.com'})
        self.assertTrue(p_tr['skip-cert-verify'])

        p_hy1 = parsers.parse_hysteria(hy1_upper)
        self.assertEqual(p_hy1['sni'], 'hy1.example.com')
        self.assertTrue(p_hy1['skip-cert-verify'])
        self.assertEqual(p_hy1['up'], '50')

        p_real = parsers.parse_vless(reality_insec)
        self.assertFalse(p_real['skip-cert-verify'])

        with patch.object(view, 'path', self.temp_dir.name):
            clash_raw = generator.clash_encode([
                SimpleNamespace(node=trojan_sci),
                SimpleNamespace(node=reality_insec),
            ])
        self.assertIn("password: '1e234567'", clash_raw)
        self.assertIn("name: '1.0e5'", clash_raw)
        self.assertIn("short-id: '0123'", clash_raw)

    # ---- P2-3: Surge comment-safe [Proxy] injection & unsupported transport/plugin filtering ----
    def test_p2_3_surge_comment_safe_injection_and_unsupported_transports_skipped(self):
        tmpl = (
            '# Notice: put proxies under [Proxy] and groups under [Proxy Group]\n'
            '[General]\n'
            'loglevel = notify\n\n'
            '[Proxy]\n'
            'DIRECT = direct\n\n'
            '[Proxy Group]\n'
            'manual = select,auto\n'
        )
        injected = generator.inject_surge_proxies(tmpl, ['NodeA = trojan,1.2.3.4,443,password=pw'])
        self.assertLess(injected.index('[General]'), injected.index('NodeA = trojan'))
        self.assertGreater(injected.index('NodeA = trojan'), injected.index('\n[Proxy]\n'))

        # Comment-only template must fail _validate_surge_conf
        comment_only = '# [Proxy]\n# [Proxy Group]\n[General]\n'
        self.assertIsNotNone(view._validate_surge_conf(comment_only))
        self.assertIsNone(view._validate_surge_conf(tmpl))

        # Unsupported transports / plugins return None in parse_surge_node
        vmess_grpc_b64 = base64.b64encode(json.dumps({
            'v': '2', 'ps': 'VmGrpc', 'add': '1.2.3.4', 'port': 443,
            'id': '11111111-1111-1111-1111-111111111111', 'net': 'grpc', 'tls': 'tls',
        }).encode()).decode()
        self.assertIsNone(generator.parse_surge_node(f'vmess://{vmess_grpc_b64}'))
        self.assertIsNone(generator.parse_surge_node(
            'trojan://pw@1.2.3.4:443?type=grpc&serviceName=svc#TrGrpc'
        ))
        self.assertIsNone(generator.parse_surge_node(
            'ss://YWVzLTEyOC1nY206cGFzcw==@1.2.3.4:8388?plugin=v2ray-plugin%3Btls#SSV2'
        ))

    # ---- P2-4, P2-5, P2-6, P2-8, P3-3, P3-5: API validation, SAWarning, headers, /set_user limit, summaries, healthz ----
    def test_p2_4_to_p3_5_api_hardening_and_summaries(self):
        app = self._make_memory_app()
        with app.app_context():
            db.create_all()
            user = User(username='admin', password=hash_password('OldPass#123'), name='管理员', token_version=1)
            db.session.add(user)
            # Legacy subscription row with access_token=None
            db.session.add(Sub(
                name='LegacySub',
                node='trojan://pw@1.2.3.4:443#N1',
                remarks='',
                sort_order=0,
                access_token=None,
                legacy_enabled=False,
            ))
            db.session.commit()

            client = app.test_client()
            token = create_access_token(identity='admin', additional_claims={'tv': 1, 'uid': user.id})
            refresh = create_refresh_token(identity='admin', additional_claims={'tv': 1, 'uid': user.id})
            headers = {'Authorization': f'Bearer {token}'}

            # P3-5: /healthz
            r_health = client.get('/healthz')
            self.assertEqual(r_health.status_code, 200)
            self.assertEqual(r_health.get_json(), {'status': 'ok'})
            self.assertEqual(r_health.headers.get('X-Content-Type-Options'), 'nosniff')
            self.assertEqual(r_health.headers.get('X-Frame-Options'), 'DENY')
            self.assertEqual(r_health.headers.get('Referrer-Policy'), 'no-referrer')
            self.assertEqual(r_health.headers.get('Cache-Control'), 'no-store')

            # P2-6: /refresh returns text/plain + security headers
            r_ref = client.post('/refresh', headers={'Authorization': f'Bearer {refresh}'})
            self.assertEqual(r_ref.status_code, 200)
            self.assertEqual(r_ref.mimetype, 'text/plain')
            self.assertEqual(r_ref.headers.get('Cache-Control'), 'no-store')

            # P2-4: reject dangerous subscription names
            for bad_name in ('.', '..', 'foo/bar', 'a\\b', 'a?b', 'a#b'):
                res_c = client.post('/create_sub', json={'name': bad_name, 'node': ['trojan://pw@1.2.3.4:443#A']}, headers=headers)
                self.assertEqual(res_c.get_json()['code'], 400, msg=f'expected reject for {bad_name}')
                res_r = client.post('/rename_sub/LegacySub', json={'newName': bad_name}, headers=headers)
                self.assertEqual(res_r.get_json()['code'], 400, msg=f'expected rename reject for {bad_name}')

            # P2-5: /create_node & /set_sub must backfill non-empty access_token and emit zero SAWarning
            res_cn = client.post(
                '/create_node',
                json={'name': 'LegacySub', 'node': 'trojan://pw@1.2.3.4:443#N2', 'remarks': ''},
                headers=headers,
            )
            self.assertEqual(res_cn.get_json()['code'], 200)
            rows_after_cn = Sub.query.filter_by(name='LegacySub').all()
            self.assertTrue(all(r.access_token for r in rows_after_cn))
            self.assertEqual(len({r.access_token for r in rows_after_cn}), 1)

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always', SAWarning)
                res_set = client.post(
                    '/set_sub',
                    json={'name': 'LegacySub', 'newNode': ['trojan://pw@1.2.3.4:443#N3']},
                    headers=headers,
                )
            self.assertEqual(res_set.get_json()['code'], 200)
            sa_warnings = [w for w in caught if issubclass(w.category, SAWarning)]
            self.assertEqual(sa_warnings, [])

            # P3-3: /get_sub_summaries returns lightweight summary
            r_sum = client.post('/get_sub_summaries', headers=headers)
            self.assertEqual(r_sum.status_code, 200)
            self.assertEqual(r_sum.get_json(), [{'name': 'LegacySub', 'count': 1, 'sort_order': 0}])
            self.assertEqual(r_sum.headers.get('Cache-Control'), 'no-store')

            # P2-6: /sub/v2ray/<token> returns Cache-Control: no-store
            sub_token = Sub.query.filter_by(name='LegacySub').first().access_token
            r_sub = client.get(f'/sub/v2ray/{sub_token}')
            self.assertEqual(r_sub.status_code, 200)
            self.assertEqual(r_sub.headers.get('Cache-Control'), 'no-store')

            # P2-8: /set_user oldPassword rate limiting
            with patch.dict(os.environ, {'LOGIN_RATE_LIMIT_MAX_ATTEMPTS': '2'}):
                for _ in range(2):
                    r_bad = client.post(
                        '/set_user',
                        json={
                            'username': 'admin',
                            'oldPassword': 'WrongPassword',
                            'newUserName': 'admin',
                            'password': 'NewPass#123',
                        },
                        headers=headers,
                    )
                    self.assertEqual(r_bad.status_code, 200)
                    self.assertEqual(r_bad.get_json()['code'], 400)
                r_429 = client.post(
                    '/set_user',
                    json={
                        'username': 'admin',
                        'oldPassword': 'OldPass#123',
                        'newUserName': 'admin',
                        'password': 'NewPass#123',
                    },
                    headers=headers,
                )
                self.assertEqual(r_429.status_code, 429)
                self.assertIn('Retry-After', r_429.headers)

    # ---- P3-1: upgrade_db detects missing login table & narrow login.ip ----
    def test_p3_1_upgrade_db_detects_missing_login_and_narrow_ip(self):
        db_file = os.path.join(self.temp_dir.name, 'db', 'missing_login.db')
        conn = sqlite3.connect(db_file)
        try:
            conn.executescript("""
                CREATE TABLE user (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(40) NOT NULL UNIQUE,
                    password VARCHAR(255) NOT NULL,
                    name VARCHAR(40),
                    token_version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE sub (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(40),
                    node TEXT,
                    remarks VARCHAR(40),
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    access_token VARCHAR(48),
                    legacy_enabled BOOLEAN NOT NULL DEFAULT 0
                );
                CREATE INDEX ix_sub_access_token ON sub (access_token);
                CREATE TABLE config (
                    id INTEGER PRIMARY KEY,
                    key VARCHAR(64) NOT NULL UNIQUE,
                    value TEXT
                );
            """)
            conn.commit()
        finally:
            conn.close()

        _, schema_items, _ = read_schema_state(db_file)
        self.assertEqual(detect_schema_revision(schema_items), USER_AUTH_REVISION)

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_file}'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['JWT_SECRET_KEY'] = 'upgrade-test-secret-key-32-bytes'
        init_exts(app)
        try:
            upgrade_database(app)
            tables, schema_after, _ = read_schema_state(db_file)
            self.assertIn('login', tables)
            self.assertEqual(detect_schema_revision(schema_after), CONFIG_SCHEMA_REVISION)
        finally:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()

    # ---- P3-4: httpupgrade/h2 transport, emoji negative cache, non-URI remote sub warning ----
    def test_p3_4_transports_emoji_negative_cache_and_remote_yaml_warning(self):
        vless_hu = 'vless://11111111-1111-1111-1111-111111111111@1.2.3.4:443?security=tls&sni=s.com&type=httpupgrade&path=/hu&host=h.com#VHu'
        vless_h2 = 'vless://11111111-1111-1111-1111-111111111111@1.2.3.4:443?security=tls&sni=s.com&type=h2&path=/h2&host=h1.com,h2.com#VH2'

        p_hu = parsers.parse_vless(vless_hu)
        self.assertEqual(p_hu['network'], 'ws')
        self.assertTrue(p_hu['ws-opts']['v2ray-http-upgrade'])
        sb_hu = generator.get_singbox_outbound('vless', p_hu, 'VHu')
        self.assertEqual(sb_hu['transport'], {'type': 'httpupgrade', 'path': '/hu', 'host': 'h.com'})

        p_h2 = parsers.parse_vless(vless_h2)
        self.assertEqual(p_h2['network'], 'h2')
        self.assertEqual(p_h2['h2-opts'], {'path': '/h2', 'host': ['h1.com', 'h2.com']})
        sb_h2 = generator.get_singbox_outbound('vless', p_h2, 'VH2')
        self.assertEqual(sb_h2['transport'], {'type': 'http', 'path': '/h2', 'host': ['h1.com', 'h2.com']})

        # Private DNS result must be negatively cached so getaddrinfo is only called once
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('10.0.0.1', 0))]) as mock_dns:
            self.assertEqual(remote.get_country_emoji('internal.corp.example'), '')
            self.assertEqual(remote.get_country_emoji('internal.corp.example'), '')
            self.assertEqual(mock_dns.call_count, 1)

        # Remote Clash YAML logs explicit warning
        mock_resp = MagicMock(status_code=200, text='proxies:\n  - name: a\n    type: ss\n', headers={})
        with patch('requests.get', return_value=mock_resp), \
             patch('app.remote.validate_remote_url', side_effect=lambda u, **kw: u), \
             self.assertLogs('app.remote', level='WARNING') as cm:
            nodes = remote.fetch_remote_sub('https://sub.example.com/clash.yaml', use_cache=False)
        self.assertEqual(nodes, [])
        self.assertTrue(any('Clash YAML' in msg for msg in cm.output))

    def test_p3_5_dockerfile_has_healthcheck_and_timeout(self):
        with open(os.path.join(REPO_ROOT, 'Dockerfile'), 'r', encoding='utf-8') as f:
            df = f.read()
        self.assertIn('HEALTHCHECK', df)
        self.assertIn('/healthz', df)
        self.assertIn('ProxyHandler({})', df)
        self.assertIn('--timeout', df)
        with open(os.path.join(REPO_ROOT, '.dockerignore'), 'r', encoding='utf-8') as f:
            di = f.read().splitlines()
        self.assertIn('review', [line.strip() for line in di])

    # ---- R2-1: skipped sing-box node must not pollute used_tags ----
    def test_r2_1_singbox_skipped_node_does_not_pollute_used_tags(self):
        gecko_hk = 'hysteria2://pw@1.2.3.4:443?obfs=gecko&obfs-password=gp#HK'
        bad_port_hk = 'trojan://pw@1.2.3.4:99999#HK'
        good_hk = 'trojan://pw@1.2.3.4:443?sni=good.example.com#HK'
        subs = [
            SimpleNamespace(node=gecko_hk, remarks=''),
            SimpleNamespace(node=bad_port_hk, remarks=''),
            SimpleNamespace(node=good_hk, remarks=''),
        ]
        with patch.object(view, 'path', self.temp_dir.name):
            cfg = json.loads(generator.singbox_encode(subs, legacy_format=True))
        proxy_tags = [o['tag'] for o in cfg['outbounds'] if o['type'] not in ('selector', 'urltest', 'direct')]
        self.assertEqual(proxy_tags, ['HK'])

    # ---- R2-2: /set_user rejects invalid new params before verify_password / write lock ----
    def test_r2_2_set_user_fast_reject_before_pbkdf2_and_lock(self):
        app = self._make_memory_app()
        with app.app_context():
            db.create_all()
            user = User(username='admin', password=hash_password('OldPass#123'), name='管理员', token_version=1)
            db.session.add(user)
            db.session.commit()
            client = app.test_client()
            token = create_access_token(identity='admin', additional_claims={'tv': 1, 'uid': user.id})
            headers = {'Authorization': f'Bearer {token}'}

            with patch('app.view.verify_password') as mock_verify:
                res = client.post(
                    '/set_user',
                    json={
                        'username': 'admin',
                        'oldPassword': 'OldPass#123',
                        'newUserName': 'ab',
                        'password': 'NewPass#123',
                    },
                    headers=headers,
                )
            self.assertEqual(res.get_json()['code'], 400)
            mock_verify.assert_not_called()

    # ---- R2-3: GeoIP async rollback inside app_context, semaphore released, skipped in TESTING ----
    def test_r2_3_geoip_async_rollback_context_and_testing_guard(self):
        app = self._make_memory_app()
        app.config['TESTING'] = True
        with app.app_context():
            db.create_all()
            # TESTING=True must not spawn background threads even for file-backed URI
            with patch('app.remote.threading.Thread') as mock_thread, \
                 patch('app.remote._lookup_login_geoip', return_value='') as mock_lookup, \
                 patch('app.remote._is_file_backed_sqlite_uri', return_value=True), \
                 app.test_request_context('/login', environ_base={'REMOTE_ADDR': '8.8.8.8'}):
                remote.save_ip_address()
            mock_thread.assert_not_called()
            mock_lookup.assert_called_once()

            # Simulate commit error in _backfill_login_geoip_async: rollback inside app_context & semaphore released
            acquired = remote._geoip_backfill_sem.acquire(blocking=False)
            self.assertTrue(acquired)
            with patch('app.remote._lookup_login_geoip', return_value='TestCity'), \
                 patch.object(db.session, 'commit', side_effect=RuntimeError('boom')), \
                 patch.object(db.session, 'rollback', wraps=db.session.rollback) as mock_rb:
                row = remote.Login(ip='8.8.8.8', address='', time='2026-11-26 00:00:00')
                db.session.add(row)
                db.session.flush()
                remote._backfill_login_geoip_async(app, row.id, '8.8.8.8')
            mock_rb.assert_called()
            # Semaphore must be released back to full capacity
            re_acq = remote._geoip_backfill_sem.acquire(blocking=False)
            self.assertTrue(re_acq)
            remote._geoip_backfill_sem.release()

    # ---- R2-4: clock-backwards future timestamps discarded and retry_after clamped ----
    def test_r2_4_rate_limiter_guards_against_future_clock_skew(self):
        import time as _time

        db_file = os.path.join(self.temp_dir.name, 'db', 'rl_clock.db')
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_file}'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['JWT_SECRET_KEY'] = 'clock-skew-test-secret-32-bytes-ok'

        state_path = os.path.join(self.temp_dir.name, 'db', '.login_rate_limit.json')
        future_ts = _time.time() + 3600.0
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump({
                'u': {'u:203.0.113.9:admin': [future_ts] * 10},
                'ip': {'ip:203.0.113.9': [future_ts] * 25},
            }, f)

        limiter = view._LoginRateLimiter()
        with app.app_context(), patch.dict(os.environ, {'LOGIN_RATE_LIMIT_WINDOW': '300'}):
            blocked, retry_after = limiter.check_blocked('203.0.113.9', 'admin')
            self.assertFalse(blocked)
            self.assertEqual(retry_after, 0)

    # ---- R2-5: Trojan httpupgrade/h2, h2 empty host omitted, VMess bool port rejected ----
    def test_r2_5_trojan_transports_empty_h2_host_and_vmess_bool_port(self):
        tr_hu = 'trojan://pw@1.2.3.4:443?sni=a.com&type=httpupgrade&path=/hu&host=h.com#TrHu'
        tr_h2 = 'trojan://pw@1.2.3.4:443?sni=a.com&type=h2&path=/h2&host=%20,%20#TrH2'
        vless_h2_empty = 'vless://11111111-1111-1111-1111-111111111111@1.2.3.4:443?security=tls&type=h2&host=%20,%20#VH2Empty'
        vmess_bool_port = 'vmess://' + base64.b64encode(json.dumps({
            'v': '2', 'ps': 'BoolPort', 'add': '1.2.3.4', 'port': True,
            'id': '11111111-1111-1111-1111-111111111111', 'net': 'tcp',
        }).encode()).decode()

        p_tr_hu = parsers.parse_trojan(tr_hu)
        self.assertEqual(p_tr_hu['network'], 'ws')
        self.assertTrue(p_tr_hu['ws-opts']['v2ray-http-upgrade'])
        self.assertEqual(
            generator.get_singbox_outbound('trojan', p_tr_hu, 'TrHu')['transport'],
            {'type': 'httpupgrade', 'path': '/hu', 'host': 'h.com'},
        )
        self.assertIsNone(generator.parse_surge_node(tr_hu))

        p_tr_h2 = parsers.parse_trojan(tr_h2)
        self.assertEqual(p_tr_h2['network'], 'h2')
        self.assertEqual(p_tr_h2['h2-opts'], {'path': '/h2'})
        self.assertIsNone(generator.parse_surge_node(tr_h2))

        p_vl_h2 = parsers.parse_vless(vless_h2_empty)
        self.assertEqual(p_vl_h2['h2-opts'], {'path': '/'})

        with patch.object(view, 'path', self.temp_dir.name):
            clash_data = yaml.safe_load(generator.clash_encode([SimpleNamespace(node=vmess_bool_port, remarks='')]))
            sb_data = json.loads(generator.singbox_encode([SimpleNamespace(node=vmess_bool_port, remarks='')]))
        self.assertEqual(clash_data['proxies'], [])
        self.assertEqual(
            [o for o in sb_data['outbounds'] if o['type'] not in ('selector', 'urltest', 'direct')],
            [],
        )
        with self.assertRaises(ValueError):
            generator.parse_surge_node(vmess_bool_port)


if __name__ == '__main__':
    unittest.main()
