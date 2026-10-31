"""Tests verifying the latest review fixes (Surge auto, Clash empty fallback, etc.)."""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask
from flask_jwt_extended import create_access_token

from app import view
from app.core.generator import clash_encode, replace_surge_group_auto, surge_encode
from app.core.parsers import parse_hysteria, parse_ssr
from app.exts import db, jwtmanager
from app.model import Sub, User
from app.remote import is_private_or_loopback_ip, save_ip_address


class Review2FixesTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['JWT_SECRET_KEY'] = 'test-secret-review2'
        db.init_app(self.app)
        jwtmanager.init_app(self.app)
        self.app.register_blueprint(view.blue)
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # 1. Surge auto regex replacement
    def test_surge_auto_replacement_preserves_node_names_and_passwords(self):
        sample_config = (
            "[Proxy]\n"
            "SG-auto-01 = ss, 1.2.3.4, 443, encrypt-method=aes-128-gcm, password=autolink123\n"
            "\n"
            "[Proxy Group]\n"
            "🚀 手动切换 = select,auto\n"
            "Auto-Select = url-test, auto, DIRECT\n"
            "\n"
            "[Rule]\n"
            "DOMAIN-SUFFIX,auto.example.com,DIRECT\n"
        )
        autos = "SG-auto-01,HK-01"
        res = replace_surge_group_auto(sample_config, autos)

        # [Proxy] 段中的 auto 不应被替换
        self.assertIn("SG-auto-01 = ss, 1.2.3.4, 443, encrypt-method=aes-128-gcm, password=autolink123", res)
        # [Rule] 中的 auto 不应被替换
        self.assertIn("DOMAIN-SUFFIX,auto.example.com,DIRECT", res)
        # [Proxy Group] 中的策略组名不应被替换
        self.assertIn("Auto-Select =", res)
        # 仅策略组参数中的 auto token 被替换
        self.assertIn("🚀 手动切换 = select,SG-auto-01,HK-01", res)
        self.assertIn("Auto-Select = url-test, SG-auto-01,HK-01, DIRECT", res)

    # 2. Clash 空订阅导致策略组空列表崩溃
    def test_clash_empty_subscription_fallback_to_direct(self):
        # 传入空订阅列表
        yaml_text = clash_encode([])
        import yaml
        data = yaml.safe_load(yaml_text)
        self.assertEqual(data.get('proxies'), [])
        proxy_groups = data.get('proxy-groups', [])
        for group in proxy_groups:
            # 必须保证至少包含一个 proxy，不能成为空列表 []
            self.assertGreater(len(group['proxies']), 0)
            self.assertIn('DIRECT', group['proxies'])

    # 3. Surge 导出同名节点去重
    def test_surge_duplicate_node_name_deduplication(self):
        sub1 = Sub(
            name='TestSub',
            node='ss://YWVzLTEyOC1nY206cGFzc3dvcmQ=@1.2.3.4:443#%E4%B8%9C%E4%BA%AC%E8%8A%82%E7%82%B9',
            sort_order=1,
            access_token='surge-dup-token',
        )
        sub2 = Sub(
            name='TestSub',
            node='ss://YWVzLTEyOC1nY206cGFzc3dvcmQ=@1.2.3.5:443#%E4%B8%9C%E4%BA%AC%E8%8A%82%E7%82%B9',
            sort_order=1,
            access_token='surge-dup-token',
        )
        surge_conf = surge_encode([sub1, sub2])
        # [Proxy] 中两个节点名称应去重
        self.assertIn('东京节点 =', surge_conf)
        self.assertIn('东京节点 (2) =', surge_conf)
        # [Proxy Group] 中也应包含去重后的名称
        self.assertIn('东京节点,东京节点 (2)', surge_conf)

    # 4. Hysteria v1 剥离 @ 前缀
    def test_hysteria_auth_prefix_stripping(self):
        uri = 'hysteria://my_secret_token@1.2.3.4:443?upmbps=100&downmbps=100#HysteriaNode'
        proxy = parse_hysteria(uri)
        self.assertEqual(proxy['server'], '1.2.3.4')
        self.assertEqual(proxy['port'], 443)
        self.assertEqual(proxy['auth_str'], 'my_secret_token')

    # 5. SSR remarks 解码空格保留与还原
    def test_ssr_remarks_with_plus_decoding(self):
        # Base64 编码的 "Japan+Tokyo": "SmFwYW4rVG9reW8="
        # 其中包含 '+' 字符
        raw_ssr = 'ssr://MS4yLjMuNDo0NDM6b3JpZ2luOm5vbmU6cGxhaW46YUdWc2JHOD0vP3JlbWFya3M9U21Gd1lXNHJWRzlyZVc4PQ=='
        proxy = parse_ssr(raw_ssr)
        self.assertEqual(proxy['name'], 'Japan+Tokyo')

    # 6. /sub 接口对不存在订阅返回 404
    def test_sub_non_existent_token_returns_404(self):
        with self.app.app_context():
            db.create_all()
            res = self.client.get('/sub/clash/non_existent_random_token_123456789012345678901234')
            self.assertEqual(res.status_code, 404)
            data = res.get_json()
            self.assertEqual(data['code'], 404)
            self.assertEqual(data['msg'], '订阅不存在')

    # 7. create_node 判空校验前置
    def test_create_node_empty_returns_correct_message(self):
        with self.app.app_context():
            db.create_all()
            user = User(username='admin', password='password123')
            db.session.add(user)
            db.session.commit()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            res = self.client.post('/create_node', json={'name': 'test', 'node': ''}, headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data['code'], 400)
            self.assertEqual(data['msg'], '节点内容不能为空')

    # 8. Surge 配置校验与 /sub 异常保护
    def test_surge_config_validation(self):
        with self.app.app_context():
            db.create_all()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            # 缺少必要段落
            res_invalid = self.client.post('/surge_config', json={'index': 'save', 'text': 'invalid text'}, headers=headers)
            self.assertEqual(res_invalid.get_json()['code'], 400)
            self.assertIn('配置格式错误', res_invalid.get_json()['msg'])

            # 空内容
            res_empty = self.client.post('/surge_config', json={'index': 'save', 'text': '   '}, headers=headers)
            self.assertEqual(res_empty.get_json()['code'], 400)
            self.assertIn('不能为空', res_empty.get_json()['msg'])

    def test_sub_export_generator_exception_returns_500_json(self):
        with self.app.app_context():
            db.create_all()
            sub = Sub(name='TestSub', node='ss://YWVzLTEyOC1nY206cGFzc3dvcmQ=@1.2.3.4:443#Node1', sort_order=1, access_token='token-crash')
            db.session.add(sub)
            db.session.commit()

            with patch('app.view.clash_encode', side_effect=RuntimeError('Template corrupted')):
                res = self.client.get('/sub/clash/token-crash')
                self.assertEqual(res.status_code, 500)
                self.assertEqual(res.get_json()['code'], 500)
                self.assertIn('clash 配置生成失败', res.get_json()['msg'])

    # 9. /login 内网 IP 判断短路
    def test_private_and_loopback_ip_detection(self):
        self.assertTrue(is_private_or_loopback_ip('127.0.0.1'))
        self.assertTrue(is_private_or_loopback_ip('::1'))
        self.assertTrue(is_private_or_loopback_ip('192.168.1.1'))
        self.assertTrue(is_private_or_loopback_ip('10.0.0.1'))
        self.assertTrue(is_private_or_loopback_ip('172.16.0.1'))
        self.assertFalse(is_private_or_loopback_ip('1.1.1.1'))
        self.assertFalse(is_private_or_loopback_ip('8.8.8.8'))
        self.assertFalse(is_private_or_loopback_ip('invalid-ip'))

    # 10. docker-compose.yml 内容一致性校验
    def test_docker_compose_configuration(self):
        compose_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'docker-compose.yml')
        with open(compose_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('sublink:v3', content)
        self.assertIn('sublink-v3', content)
        self.assertIn('network_mode: host', content)
        self.assertIn('PORT=8000', content)
        self.assertIn('JWT_SECRET_KEY', content)

    # 11. Surge auto 占位符反斜杠安全测试
    def test_surge_auto_replacement_with_backslash_no_regex_crash(self):
        sample_config = (
            "[Proxy Group]\n"
            "Group1 = select,auto\n"
        )
        autos_with_backslash = r"HK \1,US \ "
        res = replace_surge_group_auto(sample_config, autos_with_backslash)
        self.assertIn(r"Group1 = select,HK \1,US \ ", res)

    # 12. Surge 节点名称含等号切分去重测试
    def test_surge_deduplication_with_equals_sign_in_node_name(self):
        sub1 = Sub(
            name='TestSub',
            node='ss://YWVzLTEyOC1nY206cGFzc3dvcmQ=@1.2.3.4:443#%E4%B8%9C%E4%BA%AC%3D01',
            sort_order=1,
            access_token='surge-eq-token',
        )
        sub2 = Sub(
            name='TestSub',
            node='ss://YWVzLTEyOC1nY206cGFzc3dvcmQ=@1.2.3.5:443#%E4%B8%9C%E4%BA%AC%3D01',
            sort_order=1,
            access_token='surge-eq-token',
        )
        surge_conf = surge_encode([sub1, sub2])
        self.assertIn('东京=01 =', surge_conf)
        self.assertIn('东京=01 (2) =', surge_conf)
        self.assertNotIn('东京=01 (2) =01 =', surge_conf)

    # 13. Clash 策略组缺少 proxies 或为 None
    def test_clash_group_proxies_none_or_missing(self):
        import yaml
        from unittest.mock import mock_open
        fake_yaml = (
            "proxies: []\n"
            "proxy-groups:\n"
            "  - name: GroupA\n"
            "    type: select\n"
            "  - name: GroupB\n"
            "    type: select\n"
            "    proxies: null\n"
        )
        with patch('builtins.open', mock_open(read_data=fake_yaml)):
            out = clash_encode([])
            data = yaml.safe_load(out)
            self.assertEqual(data['proxy-groups'][0]['proxies'], ['DIRECT'])
            self.assertEqual(data['proxy-groups'][1]['proxies'], ['DIRECT'])

    # 14. _validate_surge_conf 必须同时包含 [Proxy] 与 [Proxy Group]
    def test_surge_conf_validation_demorgan(self):
        from app.view import _validate_surge_conf
        self.assertIsNotNone(_validate_surge_conf("[Proxy]\nDIRECT=direct\n"))
        self.assertIsNotNone(_validate_surge_conf("[Proxy Group]\nauto=select,DIRECT\n"))
        self.assertIsNone(_validate_surge_conf("[Proxy]\nDIRECT=direct\n[Proxy Group]\nauto=select,DIRECT\n"))

    # 15. create_node 与 create_sub 名称非空校验
    def test_create_node_and_create_sub_name_validation(self):
        with self.app.app_context():
            db.create_all()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            res = self.client.post('/create_node', json={'name': '   ', 'node': 'ss://YWVzLTEyOC1nY206cGFzc3dvcmQ=@1.2.3.4:443#Node'}, headers=headers)
            self.assertEqual(res.get_json()['code'], 400)
            self.assertEqual(res.get_json()['msg'], '订阅名称不能为空')

            res2 = self.client.post('/create_sub', json={'name': '', 'node': ['ss://YWVzLTEyOC1nY206cGFzc3dvcmQ=@1.2.3.4:443#Node|remark']}, headers=headers)
            self.assertEqual(res2.get_json()['code'], 400)
            self.assertEqual(res2.get_json()['msg'], '订阅名称不能为空')

    # 16. rename_sub 查无订阅返回 404 及空新名称校验
    def test_rename_sub_not_found_and_empty_check(self):
        with self.app.app_context():
            db.create_all()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            res = self.client.post('/rename_sub/not_exist', json={'newName': 'newName'}, headers=headers)
            self.assertEqual(res.status_code, 404)
            self.assertEqual(res.get_json()['code'], 404)

            res2 = self.client.post('/rename_sub/not_exist', json={'newName': '  '}, headers=headers)
            self.assertEqual(res2.status_code, 200)
            self.assertEqual(res2.get_json()['code'], 400)
            self.assertEqual(res2.get_json()['msg'], '新名称不能为空')

    # 17. IPv6 SSR 解析与重写
    def test_ipv6_ssr_rewrite_and_get_server(self):
        import base64
        import urllib.parse
        from app.core.rewrite import get_node_server, rewrite_ssr_name
        inner = '[2001:db8::1]:443:origin:none:plain:aGVsbG8=/?remarks=' + base64.b64encode(b'OldName').decode()
        ssr_node = 'ssr://' + base64.urlsafe_b64encode(inner.encode()).decode()

        server = get_node_server(ssr_node)
        self.assertEqual(server, '2001:db8::1')

        parse = urllib.parse.urlparse(ssr_node)
        rewritten = rewrite_ssr_name(ssr_node, parse, transformer=lambda n: f"{n}_New")
        self.assertIn('ssr://', rewritten)
        raw_b64 = rewritten.replace('ssr://', '')
        decoded_inner = base64.urlsafe_b64decode(raw_b64 + '=' * (4 - len(raw_b64) % 4)).decode('utf-8', errors='ignore')
        self.assertIn('[2001:db8::1]:443', decoded_inner)
        self.assertIn('remarks=', decoded_inner)

    # 18. get_country_emoji 对本地/私网 IP 短路
    def test_get_country_emoji_short_circuit_private_ip(self):
        from app.remote import get_country_emoji
        with patch('requests.get') as mock_get:
            res1 = get_country_emoji('127.0.0.1')
            self.assertEqual(res1, '')
            res2 = get_country_emoji('192.168.1.1')
            self.assertEqual(res2, '')
            res3 = get_country_emoji('localhost')
            self.assertEqual(res3, '')
            mock_get.assert_not_called()

    # 19. /set_sub 订阅名称非空校验
    def test_set_sub_name_validation(self):
        with self.app.app_context():
            db.create_all()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            res = self.client.post('/set_sub', json={'name': '', 'newNode': []}, headers=headers)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.get_json()['code'], 400)
            self.assertEqual(res.get_json()['msg'], '订阅名称不能为空')

            res2 = self.client.post('/set_sub', json={'name': '   ', 'newNode': []}, headers=headers)
            self.assertEqual(res2.get_json()['code'], 400)
            self.assertEqual(res2.get_json()['msg'], '订阅名称不能为空')

    # 20. sort_subs 防御历史空名与脏数据
    def test_sort_subs_ignores_empty_or_none_names(self):
        with self.app.app_context():
            db.create_all()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            # 插入正常订阅与脏空名订阅
            db.session.add(Sub(name='SubA', node='ss://node1', sort_order=0))
            db.session.add(Sub(name='SubB', node='ss://node2', sort_order=1))
            db.session.add(Sub(name='', node='ss://dirty1', sort_order=2))
            db.session.add(Sub(name=None, node='ss://dirty2', sort_order=3))
            db.session.commit()

            # 前端仅对合法订阅排序：['SubB', 'SubA']
            res = self.client.post('/sort_subs', json={'names': ['SubB', 'SubA']}, headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data['code'], 200)
            self.assertEqual(data['msg'], '订阅排序已保存')

            # 验证排序确实生效
            sub_b = Sub.query.filter_by(name='SubB').first()
            sub_a = Sub.query.filter_by(name='SubA').first()
            self.assertEqual(sub_b.sort_order, 0)
            self.assertEqual(sub_a.sort_order, 1)

    # 21. expand_node_list 并发拉取远程订阅与顺序保持
    def test_expand_node_list_parallel_order(self):
        from app.core.generator import expand_node_list
        from collections import namedtuple

        SubItem = namedtuple('SubItem', ['node'])
        subs = [
            SubItem(node='ss://local-node-1'),
            SubItem(node='https://sub1.example.com/sub'),
            SubItem(node='vmess://local-node-2'),
            SubItem(node='https://sub2.example.com/sub'),
        ]

        def fake_fetch(url):
            if 'sub1' in url:
                return ['ss://remote1-a', 'ss://remote1-b']
            if 'sub2' in url:
                return ['trojan://remote2-a']
            return []

        with patch('app.core.generator._fetch_remote_sub', side_effect=fake_fetch) as mock_fetch:
            nodes = expand_node_list(subs)
            self.assertEqual(nodes, [
                'ss://local-node-1',
                'ss://remote1-a',
                'ss://remote1-b',
                'vmess://local-node-2',
                'trojan://remote2-a'
            ])
            self.assertEqual(mock_fetch.call_count, 2)

    # 22. 远程订阅内存缓存与异常兜底 (Stale-While-Revalidate)
    def test_remote_sub_cache_and_stale_fallback(self):
        import time
        import requests
        import app.remote
        from app.remote import (
            _remote_sub_cache,
            clear_remote_sub_cache,
            fetch_remote_sub,
            _ORIGINAL_REQUESTS_GET
        )

        clear_remote_sub_cache()
        test_url = 'https://mock-cache.test/sub'

        # 构造成功响应对象
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "ss://Y2FjaGVkLW5vZGUtMQo=\nss://Y2FjaGVkLW5vZGUtMgo="  # 2 个节点

        with patch.object(app.remote, '_ORIGINAL_REQUESTS_GET', requests.get):
            with patch('app.remote._http_get', return_value=mock_resp) as mock_http:
                nodes1 = fetch_remote_sub(test_url, use_cache=True)
                self.assertEqual(len(nodes1), 2)
                self.assertEqual(mock_http.call_count, 1)

                # 第二次在 TTL 内调用，直接命中缓存，不发起网络请求
                nodes2 = fetch_remote_sub(test_url, use_cache=True)
                self.assertEqual(nodes1, nodes2)
                self.assertEqual(mock_http.call_count, 1)

            # 模拟网络异常时，验证使用过期缓存兜底返回
            with patch('app.remote._http_get', side_effect=requests.RequestException("Network down")):
                nodes3 = fetch_remote_sub(test_url, use_cache=True)
                self.assertEqual(nodes3, nodes1)

        clear_remote_sub_cache()

    # 23. 纯 IP 与自签名主机识别
    def test_is_raw_ip_identification(self):
        from app.remote import is_raw_ip
        self.assertTrue(is_raw_ip('1.2.3.4'))
        self.assertTrue(is_raw_ip('192.168.1.1'))
        self.assertTrue(is_raw_ip('2001:db8::1'))
        self.assertTrue(is_raw_ip('[2400:8902::f03c:93ff:feb8:68c4]'))
        self.assertFalse(is_raw_ip('example.com'))
        self.assertFalse(is_raw_ip('my.domain.cn'))
        self.assertFalse(is_raw_ip(''))
        self.assertFalse(is_raw_ip(None))

