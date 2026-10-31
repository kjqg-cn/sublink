import base64
import os
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask
from flask_jwt_extended import create_access_token

from app import create_app, view
from app.core.generator import clash_encode, get_unique_proxy_name
from app.exts import db, jwtmanager
from app.model import User
from app.remote import get_country_emoji


class ReviewFixesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['JWT_SECRET_KEY'] = 'test-secret-review'
        db.init_app(self.app)
        jwtmanager.init_app(self.app)
        self.app.register_blueprint(view.blue)

        with self.app.app_context():
            db.create_all()
            # 预置两个用户以供越权测试
            admin_user = User(username='admin', password='password123', name='管理员')
            test_user = User(username='attacker', password='password456', name='攻击者')
            db.session.add(admin_user)
            db.session.add(test_user)
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # ================= 1. JWT 密钥环境变量读取 =================
    def test_jwt_secret_key_from_env_fallback(self):
        # 未设置环境变量时，默认回退到 'sub'
        with patch.dict(os.environ, {}, clear=True):
            app = create_app()
            self.assertEqual(app.config['JWT_SECRET_KEY'], 'sub')

    def test_jwt_secret_key_from_env_custom(self):
        # 设置环境变量时，读取配置值
        with patch.dict(os.environ, {'JWT_SECRET_KEY': 'custom-jwt-secret-xyz'}):
            app = create_app()
            self.assertEqual(app.config['JWT_SECRET_KEY'], 'custom-jwt-secret-xyz')

    def test_jwt_secret_key_from_env_empty_fallback(self):
        # 环境变量为空字符串时，回退到 'sub'
        with patch.dict(os.environ, {'JWT_SECRET_KEY': ''}):
            app = create_app()
            self.assertEqual(app.config['JWT_SECRET_KEY'], 'sub')

    # ================= 2. 国旗 Emoji LRU 缓存 =================
    def test_get_country_emoji_lru_cache(self):
        get_country_emoji.cache_clear()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'flag': {'emoji': '🇭🇰'}}

        with patch('requests.get', return_value=mock_resp) as mock_get:
            # 第一次调用，发起请求
            emoji1 = get_country_emoji('1.1.1.1')
            self.assertEqual(emoji1, '🇭🇰')
            self.assertEqual(mock_get.call_count, 1)

            # 第二次调用相同参数，命中 LRU 缓存，不应再发起网络请求
            emoji2 = get_country_emoji('1.1.1.1')
            self.assertEqual(emoji2, '🇭🇰')
            self.assertEqual(mock_get.call_count, 1)

            # 第三次调用不同参数，发起新请求
            get_country_emoji('8.8.8.8')
            self.assertEqual(mock_get.call_count, 2)

        info = get_country_emoji.cache_info()
        self.assertGreaterEqual(info.hits, 1)
        self.assertGreaterEqual(info.misses, 2)
        get_country_emoji.cache_clear()

    # ================= 3. Clash 配置生成同名节点去重 =================
    def test_get_unique_proxy_name_helper(self):
        used = set()
        n1 = get_unique_proxy_name('HK-Node', used, 1)
        self.assertEqual(n1, 'HK-Node')
        self.assertIn('HK-Node', used)

        n2 = get_unique_proxy_name('HK-Node', used, 2)
        self.assertEqual(n2, 'HK-Node (2)')
        self.assertIn('HK-Node (2)', used)

        n3 = get_unique_proxy_name('HK-Node', used, 3)
        self.assertEqual(n3, 'HK-Node (3)')
        self.assertIn('HK-Node (3)', used)

        # 预先占用 'HK-Node (4)'
        used.add('HK-Node (4)')
        n4 = get_unique_proxy_name('HK-Node', used, 4)
        self.assertEqual(n4, 'HK-Node (5)')

    def test_clash_encode_duplicate_names_deduplication(self):
        from types import SimpleNamespace
        import yaml

        # 模拟三个同名的 ss 节点
        sub1 = SimpleNamespace(node='ss://YWVzLTEyOC1nY206cGFzc0AxLjEuMS4xOjQ0Mw==#SameNode')
        sub2 = SimpleNamespace(node='ss://YWVzLTEyOC1nY206cGFzc0AyLjIuMi4yOjQ0Mw==#SameNode')
        sub3 = SimpleNamespace(node='ss://YWVzLTEyOC1nY206cGFzc0AzLjMuMy4zOjQ0Mw==#SameNode')

        yaml_str = clash_encode([sub1, sub2, sub3])
        parsed = yaml.safe_load(yaml_str)

        proxies = parsed.get('proxies', [])
        proxy_names = [p['name'] for p in proxies]
        self.assertEqual(proxy_names, ['SameNode', 'SameNode (2)', 'SameNode (3)'])

        # 验证包含 auto 占位符的 proxy-groups 同步更新为去重后的唯一名称，且无 auto 残留
        proxy_groups = parsed.get('proxy-groups', [])
        node_select_group = next(g for g in proxy_groups if g.get('name') == '🚀 节点选择')
        group_proxies = node_select_group.get('proxies', [])
        self.assertIn('SameNode', group_proxies)
        self.assertIn('SameNode (2)', group_proxies)
        self.assertIn('SameNode (3)', group_proxies)
        self.assertNotIn('auto', group_proxies)

    # ================= 4. /set_user 越权拦截 =================
    def test_set_user_unauthorized_cross_user_forbidden(self):
        with self.app.app_context():
            client = self.app.test_client()
            # 攻击者登录，生成 attacker 的 token
            attacker_token = create_access_token(identity='attacker')

            # 攻击者尝试修改 admin 的账号和密码
            payload = {
                'username': 'admin',
                'newUserName': 'hacked_admin',
                'password': 'hacked_password'
            }
            res = client.post(
                '/set_user',
                json=payload,
                headers={'Authorization': f'Bearer {attacker_token}'}
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data.get('code'), 403)
            self.assertIn('无权', data.get('msg', ''))

            # 验证 admin 用户名和密码未被篡改
            admin_in_db = User.query.filter_by(username='admin').first()
            self.assertIsNotNone(admin_in_db)
            self.assertEqual(admin_in_db.password, 'password123')

    def test_set_user_self_success(self):
        with self.app.app_context():
            client = self.app.test_client()
            admin_token = create_access_token(identity='admin')

            payload = {
                'username': 'admin',
                'newUserName': 'admin_renamed',
                'password': 'new_md5_hash_here'
            }
            res = client.post(
                '/set_user',
                json=payload,
                headers={'Authorization': f'Bearer {admin_token}'}
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data.get('code'), 200)

            # 验证修改成功生效
            user_in_db = User.query.filter_by(username='admin_renamed').first()
            self.assertIsNotNone(user_in_db)
            self.assertEqual(user_in_db.password, 'new_md5_hash_here')

    def test_set_user_requires_jwt(self):
        with self.app.app_context():
            client = self.app.test_client()
            res = client.post('/set_user', json={'username': 'admin'})
            self.assertEqual(res.status_code, 401)

    # ================= 5. /decode_sub 协议校验、超时与异常处理 =================
    def test_decode_sub_protocol_validation(self):
        with self.app.app_context():
            client = self.app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            # 阻止 file:// 协议
            res = client.post('/decode_sub', json={'urls': ['file:///etc/passwd']}, headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data.get('code'), 400)
            self.assertIn('仅支持 http 或 https', data.get('msg', ''))

            # 阻止 gopher:// 协议
            res = client.post('/decode_sub', json={'urls': ['gopher://127.0.0.1:6379/_test']}, headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data.get('code'), 400)
            self.assertIn('仅支持 http 或 https', data.get('msg', ''))

    def test_decode_sub_allows_loopback_and_internal_ip(self):
        # 严格验证：不能阻断 127.0.0.1 / 内网 IP
        with self.app.app_context():
            client = self.app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            node_plain = 'ss://YWVzLTEyOC1nY206cGFzc0AxLjEuMS4xOjQ0Mw==#LoopbackNode'
            mock_resp.text = base64.b64encode(node_plain.encode()).decode()

            with patch('requests.get', return_value=mock_resp) as mock_get:
                res = client.post('/decode_sub', json={'urls': ['http://127.0.0.1:8080/sub']}, headers=headers)
                self.assertEqual(res.status_code, 200)
                data = res.get_json()
                self.assertEqual(data.get('code'), 200)
                self.assertEqual(data.get('msg'), [node_plain])

                # 验证传递了正确的 timeout 参数
                mock_get.assert_called_once_with('http://127.0.0.1:8080/sub', timeout=(3, 10))

    def test_decode_sub_timeout_and_network_error(self):
        import requests.exceptions
        with self.app.app_context():
            client = self.app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            with patch('requests.get', side_effect=requests.exceptions.ConnectTimeout('Connection timed out')):
                res = client.post('/decode_sub', json={'urls': ['https://example.com/sub']}, headers=headers)
                self.assertEqual(res.status_code, 200)
                data = res.get_json()
                self.assertEqual(data.get('code'), 400)
                self.assertIn('拉取订阅失败', data.get('msg', ''))

    # ================= 6. app/xui.py 导入安全性 =================
    def test_xui_import_has_no_side_effects(self):
        with patch('requests.Session') as mock_session:
            import app.xui
            # 导入时不应实例化并调用网络请求
            mock_session.assert_not_called()

    # ================= 7. 深入边界与鲁棒性测试 =================
    def test_get_country_emoji_empty_input(self):
        get_country_emoji.cache_clear()
        with patch('requests.get') as mock_get:
            self.assertEqual(get_country_emoji(''), '')
            self.assertEqual(get_country_emoji('   '), '')
            self.assertEqual(get_country_emoji(None), '')
            mock_get.assert_not_called()

    def test_clash_encode_unnamed_node_fallback(self):
        from types import SimpleNamespace
        import yaml
        # 节点没有备注名（无 #fragment）
        sub = SimpleNamespace(node='ss://YWVzLTEyOC1nY206cGFzc0AxLjEuMS4xOjQ0Mw==')
        yaml_str = clash_encode([sub])
        parsed = yaml.safe_load(yaml_str)
        proxies = parsed.get('proxies', [])
        self.assertEqual(len(proxies), 1)
        self.assertEqual(proxies[0]['name'], 'node-1')

    def test_clash_encode_large_duplicate_performance(self):
        import time
        from types import SimpleNamespace
        import yaml
        # 验证 2500 个相同名称节点的去重耗时线性高效（纯去重 < 0.05s）
        used = set()
        counts = {}
        start = time.time()
        for i in range(1, 2501):
            get_unique_proxy_name('BatchNode', used, i, counts)
        duration = time.time() - start
        self.assertLess(duration, 0.05)
        self.assertEqual(len(used), 2500)
        self.assertIn('BatchNode', used)
        self.assertIn('BatchNode (2)', used)
        self.assertIn('BatchNode (2500)', used)

        # 验证 clash_encode 完整流程生成同名节点无异常且名称唯一
        subs = [SimpleNamespace(node='ss://YWVzLTEyOC1nY206cGFzc0AxLjEuMS4xOjQ0Mw==#BatchNode') for _ in range(50)]
        yaml_str = clash_encode(subs)
        parsed = yaml.safe_load(yaml_str)
        proxies = parsed.get('proxies', [])
        self.assertEqual(len(proxies), 50)
        self.assertEqual(proxies[0]['name'], 'BatchNode')
        self.assertEqual(proxies[49]['name'], 'BatchNode (50)')

    def test_set_user_empty_credentials_rejected(self):
        with self.app.app_context():
            client = self.app.test_client()
            admin_token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {admin_token}'}

            # 提交空白新用户名
            res = client.post('/set_user', json={'username': 'admin', 'newUserName': '', 'password': 'pwd'}, headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data.get('code'), 400)
            self.assertIn('不能为空', data.get('msg', ''))

            # 提交空白密码
            res = client.post('/set_user', json={'username': 'admin', 'newUserName': 'admin2', 'password': '  '}, headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data.get('code'), 400)
            self.assertIn('不能为空', data.get('msg', ''))

    def test_set_user_duplicate_username_rejected(self):
        with self.app.app_context():
            client = self.app.test_client()
            attacker_token = create_access_token(identity='attacker')
            headers = {'Authorization': f'Bearer {attacker_token}'}

            # attacker 尝试将自己的用户名重命名为已存在的 'admin'
            payload = {
                'username': 'attacker',
                'newUserName': 'admin',
                'password': 'attacker_new_password'
            }
            res = client.post('/set_user', json=payload, headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data.get('code'), 400)
            self.assertIn('用户名已存在', data.get('msg', ''))

            # 确保 admin 用户未被篡改
            admin = User.query.filter_by(username='admin').first()
            self.assertEqual(admin.password, 'password123')

    def test_decode_sub_empty_urls_rejected(self):
        with self.app.app_context():
            client = self.app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            res = client.post('/decode_sub', json={'urls': []}, headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data.get('code'), 400)
            self.assertIn('URL不能为空', data.get('msg', ''))

            res = client.post('/decode_sub', json={}, headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data.get('code'), 400)
            self.assertIn('URL不能为空', data.get('msg', ''))

    def test_decode_sub_ssl_error_fallback(self):
        import requests.exceptions
        with self.app.app_context():
            client = self.app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            node_plain = 'ss://YWVzLTEyOC1nY206cGFzc0AxLjEuMS4xOjQ0Mw==#SelfSignedNode'
            mock_success = MagicMock()
            mock_success.status_code = 200
            mock_success.text = base64.b64encode(node_plain.encode()).decode()

            def fake_get(url, timeout=None, verify=True):
                if verify is not False:
                    raise requests.exceptions.SSLError('certificate verify failed')
                return mock_success

            with patch('requests.get', side_effect=fake_get) as mock_get:
                res = client.post('/decode_sub', json={'urls': ['https://10.0.0.2:8443/sub']}, headers=headers)
                self.assertEqual(res.status_code, 200)
                data = res.get_json()
                self.assertEqual(data.get('code'), 200)
                self.assertEqual(data.get('msg'), [node_plain])
                self.assertEqual(mock_get.call_count, 2)


if __name__ == '__main__':
    unittest.main()
