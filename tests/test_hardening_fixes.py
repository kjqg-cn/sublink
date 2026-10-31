import base64
import json
import os
import unittest
import urllib.parse
from unittest.mock import MagicMock, patch

from flask import Flask, g
from flask_jwt_extended import create_access_token

from app import view
from app.exts import db, jwtmanager
from app.model import Config, Login, Sub, User


class HardeningFixesTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['JWT_SECRET_KEY'] = 'test-secret-key-hardening'
        db.init_app(self.app)
        jwtmanager.init_app(self.app)
        self.app.register_blueprint(view.blue)

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

    # ================= 1. Shadowsocks SIP002 规范与 IPv6 重写 =================
    def test_ss_sip002_loopback_rewrite(self):
        view.CustomFeature = True
        view.CustomLoopback = True
        view.CustomNodeName = False

        # 原始节点：密码与加密方式经 Base64 编码符合 SIP002 规范
        userinfo_raw = 'aes-256-gcm:MySecretPassword123'
        encoded_userinfo = view.encode_base64(userinfo_raw, urlsafe=True)
        node = f'ss://{encoded_userinfo}@127.0.0.1:8388#TestNode'

        rewritten = view.rewrite_remote_node(node, 'proxy.myserver.com')

        # 1. 结构断言
        self.assertTrue(rewritten.startswith('ss://'))
        self.assertIn('@proxy.myserver.com:443#TestNode', rewritten)

        # 2. 绝对不能在 URL 中泄露明文密码和加密方式
        self.assertNotIn('MySecretPassword123', rewritten)
        self.assertNotIn('aes-256-gcm', rewritten)

        # 3. 提取 UserInfo，必须可正确 Base64 解码回原始 method:password
        netloc = rewritten.split('://')[1].split('#')[0]
        userinfo_part, host_port_part = netloc.split('@')
        self.assertEqual(host_port_part, 'proxy.myserver.com:443')
        self.assertEqual(view.decode_base64_if(userinfo_part), userinfo_raw)

    def test_ss_sip002_with_plugin_and_fragment(self):
        view.CustomFeature = True
        view.CustomLoopback = True
        view.CustomNodeName = True

        userinfo_raw = 'chacha20-ietf-poly1305:p@ss:word'
        encoded_userinfo = view.encode_base64(userinfo_raw, urlsafe=True)
        node = f'ss://{encoded_userinfo}@127.0.0.1:8388/?plugin=obfs-local%3Bobfs%3Dhttp#%F0%9F%87%AD%F0%9F%87%B0%E3%80%90%E9%A6%99%E6%B8%AF-01-SG'

        rewritten = view.rewrite_remote_node(node, 'edge.domain.org')

        self.assertTrue(rewritten.startswith('ss://'))
        self.assertIn('@edge.domain.org:443', rewritten)
        self.assertIn('plugin=obfs-local', rewritten)
        # 节点名称也被重写为新加坡
        self.assertIn('🇸🇬【新加坡-01-SG', urllib.parse.unquote(rewritten))
        # 密码未泄露
        self.assertNotIn('p@ss:word', rewritten)

    def test_ss_non_loopback_remains_intact(self):
        view.CustomFeature = True
        view.CustomLoopback = True

        userinfo = view.encode_base64('aes-128-gcm:pass', urlsafe=True)
        external_node = f'ss://{userinfo}@192.168.1.1:8388#External'
        res = view.rewrite_remote_node(external_node, 'sub.domain.com')
        self.assertEqual(res, external_node)

    def test_ssr_loopback_ipv6_bracketed(self):
        view.CustomFeature = True
        view.CustomLoopback = True

        ssr_plain = '127.0.0.1:8388:origin:none:plain:' + base64.urlsafe_b64encode(b'pass').decode().rstrip('=') + '/?remarks=' + base64.b64encode('SSRTest'.encode()).decode()
        ssr_node = 'ssr://' + base64.urlsafe_b64encode(ssr_plain.encode()).decode().rstrip('=')

        # host 为 IPv6 地址
        ipv6_host = '2001:db8::ff00:42'
        rewritten = view.rewrite_remote_node(ssr_node, ipv6_host)
        self.assertTrue(rewritten.startswith('ssr://'))

        ssr_decoded = view.decode_base64_if(rewritten.split('://')[1].replace('-', '+').replace('_', '/'))
        # 必须包裹方括号 [2001:db8::ff00:42]:443
        self.assertTrue(ssr_decoded.startswith(f'[{ipv6_host}]:443:'), f'Decoded SSR: {ssr_decoded}')

    # ================= 2. 离线登录静默降级 =================
    def test_login_offline_whois_timeout_graceful_degrade(self):
        with self.app.app_context():
            db.create_all()
            user = User(username='admin', password='password123')
            db.session.add(user)
            db.session.commit()

            client = self.app.test_client()

            # 模拟 whois.pconline.com.cn 超时异常
            import requests.exceptions
            with patch('requests.get', side_effect=requests.exceptions.ConnectTimeout('Connection timed out')):
                res = client.post('/login', json={'username': 'admin', 'password': 'password123'})

            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data['code'], 200)
            self.assertIn('token', data)
            self.assertIn('refresh', data)

            # 验证 Login 记录依然被安全写入，未因超时而中断
            login_record = Login.query.first()
            self.assertIsNotNone(login_record)
            self.assertEqual(login_record.address, '')

    def test_login_offline_whois_connection_error_graceful_degrade(self):
        with self.app.app_context():
            db.create_all()
            user = User(username='tester', password='secret')
            db.session.add(user)
            db.session.commit()

            client = self.app.test_client()

            # 模拟断网/域名解析失败
            import requests.exceptions
            with patch('requests.get', side_effect=requests.exceptions.ConnectionError('Network unreachable')):
                res = client.post('/login', json={'username': 'tester', 'password': 'secret'})

            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.get_json()['code'], 200)

    # ================= 3. 节点协议防御性边界防护 =================
    def test_hysteria2_without_at_symbol(self):
        # 节点缺少 @ 符号，不应抛出 IndexError
        node = 'hysteria2://server.example.com:443?sni=server.example.com#Hy2Node'
        parser = view.NodeParse()
        parser.proxy_test = node
        proxy = parser.hysteria2()

        self.assertEqual(proxy['type'], 'hysteria2')
        self.assertEqual(proxy['server'], 'server.example.com')
        self.assertEqual(proxy['port'], 443)
        self.assertEqual(proxy['password'], '')
        self.assertEqual(proxy['name'], 'Hy2Node')

    def test_hysteria2_without_port_defaults_to_443(self):
        node = 'hysteria2://mypass@server.example.com#Hy2Node'
        parser = view.NodeParse()
        parser.proxy_test = node
        proxy = parser.hysteria2()

        self.assertEqual(proxy['server'], 'server.example.com')
        self.assertEqual(proxy['port'], 443)
        self.assertEqual(proxy['password'], 'mypass')

    def test_trojan_without_at_symbol(self):
        node = 'trojan://trojan-server.com:443#TrojanNode'
        parser = view.NodeParse()
        parser.proxy_test = node
        proxy = parser.trojan()

        self.assertEqual(proxy['type'], 'trojan')
        self.assertEqual(proxy['server'], 'trojan-server.com')
        self.assertEqual(proxy['port'], 443)
        self.assertEqual(proxy['password'], '')

    def test_vmess_query_without_cipher_prefix(self):
        # query 格式且无 cipher: 前缀（仅有 uuid@server:port）
        node = 'vmess://11111111-2222-3333-4444-555555555555@vmess.org:8443?remarks=NonCipherVMess&alterId=0'
        parser = view.NodeParse()
        parser.proxy_test = node
        proxy = parser.vmess()

        self.assertEqual(proxy['type'], 'vmess')
        self.assertEqual(proxy['uuid'], '11111111-2222-3333-4444-555555555555')
        self.assertEqual(proxy['cipher'], 'auto')
        self.assertEqual(proxy['server'], 'vmess.org')
        self.assertEqual(proxy['port'], 8443)
        self.assertEqual(proxy['name'], 'NonCipherVMess')

    def test_ssr_ipv6_parsing(self):
        # SSR 节点中包含 IPv6 地址 [2001:db8::1]
        plain = '[2001:db8::1]:443:auth_aes128_md5:aes-128-cfb:tls1.2_ticket_auth:cGFzc3dvcmQ=/?remarks=SVB2NlNTUg=='
        encoded = base64.urlsafe_b64encode(plain.encode()).decode().rstrip('=')
        node = f'ssr://{encoded}'

        parser = view.NodeParse()
        parser.proxy_test = node
        proxy = parser.ssr()

        self.assertEqual(proxy['type'], 'ssr')
        self.assertEqual(proxy['server'], '2001:db8::1')
        self.assertEqual(proxy['port'], 443)
        self.assertEqual(proxy['cipher'], 'aes-128-cfb')

    # ================= 4. Gunicorn 多 Worker 运行时配置读取 =================
    def test_get_runtime_config_reads_db_and_caches_in_g(self):
        with self.app.app_context():
            db.create_all()
            # 数据库预先插入配置
            db.session.add(Config(key='custom', value='1'))
            db.session.add(Config(key='custom_loopback', value='1'))
            db.session.commit()

            # 模拟在请求周期内
            with self.app.test_request_context('/sub/clash/test'):
                # 初始未缓存时，读取数据库
                cfg1 = view.get_runtime_config()
                self.assertTrue(cfg1['custom'])
                self.assertTrue(cfg1['custom_loopback'])
                self.assertFalse(cfg1['custom_node_name'])
                self.assertIs(g.runtime_config, cfg1)

                # 修改数据库内容
                Config.query.filter_by(key='custom').update({'value': '0'})
                db.session.commit()

                # 在同一请求周期内，应命中 g 缓存
                cfg2 = view.get_runtime_config()
                self.assertTrue(cfg2['custom'])

            # 模拟另一个 Worker 或下一个请求周期（清空 g）
            with self.app.test_request_context('/sub/clash/test'):
                cfg3 = view.get_runtime_config()
                # 此时实时读取数据库最新值，已变成 False
                self.assertFalse(cfg3['custom'])

    # ================= 5. 语法笔误与细节加固 =================
    def test_del_sub_node_nonexistent_returns_400(self):
        with self.app.app_context():
            db.create_all()
            client = self.app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            res = client.post('/del_sub_node/999999', headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data['code'], 400)
            self.assertEqual(data['msg'], '不存在')

    def test_get_country_emoji_failure_gracefully_returns_empty_string(self):
        import requests.exceptions
        with patch('requests.get', side_effect=requests.exceptions.Timeout('Timeout')):
            emoji = view.get_country_emoji('1.1.1.1')
            self.assertEqual(emoji, '')

        # 验证在 NodeParse 开启 Emoji 时，查询失败不会将 hostname 拼入节点名称
        view.Emoji = True
        with patch.object(view, 'get_country_emoji', return_value=''):
            node = 'vless://uuid@1.1.1.1:443?type=tcp#NodeOriginalName'
            parser = view.NodeParse()
            parser.proxy_test = node
            proxy = parser.vless()
            self.assertEqual(proxy['name'], 'NodeOriginalName')
            self.assertNotIn('1.1.1.1', proxy['name'])

    def test_clash_config_validation(self):
        with self.app.app_context():
            db.create_all()
            client = self.app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            # 1. 空文本拒绝
            res_empty = client.post('/clash_config', json={'index': 'save', 'text': ''}, headers=headers)
            self.assertEqual(res_empty.get_json()['code'], 400)
            self.assertIn('不能为空', res_empty.get_json()['msg'])

            # 2. 语法错误的 YAML 拒绝
            res_bad_yaml = client.post('/clash_config', json={'index': 'save', 'text': 'proxies: [unclosed'}, headers=headers)
            self.assertEqual(res_bad_yaml.get_json()['code'], 400)
            self.assertIn('配置格式错误', res_bad_yaml.get_json()['msg'])

            # 3. 非字典结构的 YAML 拒绝
            res_list_yaml = client.post('/clash_config', json={'index': 'save', 'text': '- item1\n- item2'}, headers=headers)
            self.assertEqual(res_list_yaml.get_json()['code'], 400)
            self.assertIn('字典结构', res_list_yaml.get_json()['msg'])

            # 4. 合法字典 YAML 接受保存
            valid_yaml = "port: 7890\nsocks-port: 7891\nallow-lan: false\n"
            with patch('builtins.open', unittest.mock.mock_open()):
                res_ok = client.post('/clash_config', json={'index': 'save', 'text': valid_yaml}, headers=headers)
            self.assertEqual(res_ok.get_json()['code'], 200)
            self.assertEqual(res_ok.get_json()['msg'], '保存成功')

    # ================= 6. 补充协议与边界防御测试 =================
    def test_ss_sip002_with_ipv6_host(self):
        view.CustomFeature = True
        view.CustomLoopback = True

        userinfo_raw = 'aes-256-gcm:pass123'
        encoded_userinfo = view.encode_base64(userinfo_raw, urlsafe=True)
        node = f'ss://{encoded_userinfo}@127.0.0.1:8388#IPv6HostTest'

        ipv6_host = '2001:db8::1'
        rewritten = view.rewrite_remote_node(node, ipv6_host)

        self.assertTrue(rewritten.startswith('ss://'))
        self.assertIn(f'@[{ipv6_host}]:443#IPv6HostTest', rewritten)
        self.assertNotIn('pass123', rewritten)

    def test_ss_malformed_without_at_returns_original(self):
        view.CustomFeature = True
        view.CustomLoopback = True

        malformed_ss = 'ss://some-invalid-data-without-at#Tag'
        res = view.rewrite_remote_node(malformed_ss, 'example.com')
        self.assertEqual(res, malformed_ss)

    def test_vless_without_at_symbol(self):
        node = 'vless://server.example.com:443?type=tcp#VlessNode'
        parser = view.NodeParse()
        parser.proxy_test = node
        proxy = parser.vless()

        self.assertEqual(proxy['type'], 'vless')
        self.assertEqual(proxy['server'], 'server.example.com')
        self.assertEqual(proxy['port'], 443)
        self.assertEqual(proxy['uuid'], '')
        self.assertEqual(proxy['name'], 'VlessNode')

    def test_hysteria_without_port_defaults_to_443(self):
        node = 'hysteria://server.example.com?auth=pass#Hy1Node'
        parser = view.NodeParse()
        parser.proxy_test = node
        proxy = parser.hysteria()

        self.assertEqual(proxy['server'], 'server.example.com')
        self.assertEqual(proxy['port'], 443)
        self.assertEqual(proxy['name'], 'Hy1Node')

    def test_node_parse_ss_preserves_hyphenated_ciphers_and_complex_passwords(self):
        # 验证常见标准加密方式中的连字符及密码中的下划线/连字符不会被错误替换为 + 或 /
        test_cases = [
            ('aes-256-gcm', 'my_pass-word_123'),
            ('chacha20-ietf-poly1305', 'p@ss:word-test_456'),
            ('aes-128-gcm', 'simplepass'),
        ]
        for cipher, password in test_cases:
            userinfo = view.encode_base64(f'{cipher}:{password}', urlsafe=True)
            node = f'ss://{userinfo}@server.example.com:8388#TestNode'
            parser = view.NodeParse()
            parser.proxy_test = node
            proxy = parser.ss()

            self.assertEqual(proxy['cipher'], cipher, f"Cipher {cipher} must not be corrupted")
            self.assertEqual(proxy['password'], password, f"Password {password} must not be corrupted")
            self.assertEqual(proxy['server'], 'server.example.com')
            self.assertEqual(proxy['port'], 8388)

    def test_ss_loopback_rewrite_unencoded_with_hyphens_preserves_cipher(self):
        view.CustomFeature = True
        view.CustomLoopback = True
        view.CustomNodeName = False

        # 未编码明文形式的 Shadowsocks 节点
        unencoded_node = 'ss://aes-256-gcm:my_pass-word@127.0.0.1:8388#UnencodedSS'
        rewritten = view.rewrite_remote_node(unencoded_node, 'gateway.example.com')

        self.assertTrue(rewritten.startswith('ss://'))
        self.assertIn('@gateway.example.com:443#UnencodedSS', rewritten)

        # 解码 userinfo 必须保留原始连字符与下划线
        netloc = rewritten.split('://')[1].split('#')[0]
        userinfo_encoded, _ = netloc.split('@')
        userinfo_decoded = view.decode_base64_if(userinfo_encoded)
        self.assertEqual(userinfo_decoded, 'aes-256-gcm:my_pass-word')

    def test_decode_base64_if_multiple_at_and_hash_symbols(self):
        # 测试多个 @ 符号与多个 # 符号时不会丢弃后续文本
        # 1. 多个 # 符号
        text_with_hash = 'YWVzLTEyOC1nY206cGFzcw==#tag1#subtag2'
        decoded_hash = view.decode_base64_if(text_with_hash)
        self.assertEqual(decoded_hash, 'aes-128-gcm:pass#tag1#subtag2')

        # 2. 包含 @ 的合法 Base64 UserInfo
        encoded_userinfo = view.encode_base64('aes-128-gcm:pass', urlsafe=True)
        text_with_at = f'{encoded_userinfo}@cluster.node1.org:443'
        decoded_at = view.decode_base64_if(text_with_at)
        self.assertEqual(decoded_at, 'aes-128-gcm:pass@cluster.node1.org:443')

    def test_parse_server_port_ipv6_bracketed_and_unbracketed(self):
        # 1. 带方括号无端口的 IPv6
        s1, p1 = view.parse_server_port('[2001:db8::1]', default_port=443)
        self.assertEqual(s1, '2001:db8::1')
        self.assertEqual(p1, 443)

        # 2. 带方括号带端口的 IPv6
        s2, p2 = view.parse_server_port('[2001:db8::1]:8443', default_port=443)
        self.assertEqual(s2, '2001:db8::1')
        self.assertEqual(p2, 8443)

        # 3. 不带方括号无端口的 IPv6
        s3, p3 = view.parse_server_port('2001:db8::1', default_port=443)
        self.assertEqual(s3, '2001:db8::1')
        self.assertEqual(p3, 443)

        # 4. 非法非数字端口回退默认端口
        s4, p4 = view.parse_server_port('myhost.com:abc', default_port=443)
        self.assertEqual(s4, 'myhost.com')
        self.assertEqual(p4, 443)

    def test_trojan_ipv6_without_port(self):
        node = 'trojan://mypass@[2001:db8::1]#TrojanIPv6'
        parser = view.NodeParse()
        parser.proxy_test = node
        proxy = parser.trojan()

        self.assertEqual(proxy['server'], '2001:db8::1')
        self.assertEqual(proxy['port'], 443)
        self.assertEqual(proxy['password'], 'mypass')

    def test_surge_config_save_validation(self):
        with self.app.app_context():
            db.create_all()
            client = self.app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            # 1. 空文本拒绝
            res1 = client.post('/surge_config', json={'index': 'save', 'text': ''}, headers=headers)
            self.assertEqual(res1.get_json()['code'], 400)
            self.assertIn('不能为空', res1.get_json()['msg'])

            # 2. 缺少 text 字段拒绝
            res2 = client.post('/surge_config', json={'index': 'save'}, headers=headers)
            self.assertEqual(res2.get_json()['code'], 400)
            self.assertIn('不能为空', res2.get_json()['msg'])


if __name__ == '__main__':
    unittest.main()


