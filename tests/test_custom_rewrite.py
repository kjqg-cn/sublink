import base64
import json
import unittest
import urllib.parse
from unittest.mock import MagicMock, patch

from flask import Flask
from flask_jwt_extended import create_access_token

from app import view
from app.exts import db, jwtmanager


class CustomRewriteLogicTest(unittest.TestCase):
    def setUp(self):
        # 保存全局状态
        self.orig_custom = view.CustomFeature
        self.orig_loopback = view.CustomLoopback
        self.orig_node_name = view.CustomNodeName
        self.orig_emoji = view.Emoji
        self.orig_skipcert = view.SkipCert
        self.orig_udp = view.Udp

    def tearDown(self):
        # 恢复全局状态
        view.CustomFeature = self.orig_custom
        view.CustomLoopback = self.orig_loopback
        view.CustomNodeName = self.orig_node_name
        view.Emoji = self.orig_emoji
        view.SkipCert = self.orig_skipcert
        view.Udp = self.orig_udp

    def test_custom_disabled_does_not_modify_node(self):
        view.CustomFeature = False
        view.CustomLoopback = True
        view.CustomNodeName = True

        vless = 'vless://uuid@127.0.0.1:8080?type=ws#' + urllib.parse.quote('🇭🇰【香港-01-SG')
        res = view.rewrite_remote_node(vless, 'sub.domain.com')
        self.assertEqual(res, vless)

        vmess_dict = {
            'v': '2', 'ps': '🇭🇰【香港-01-TYO', 'add': '127.0.0.1', 'port': '8080',
            'id': 'uuid', 'aid': '0', 'net': 'ws', 'type': 'none', 'tls': ''
        }
        vmess = 'vmess://' + base64.b64encode(json.dumps(vmess_dict).encode()).decode()
        res_vmess = view.rewrite_remote_node(vmess, 'sub.domain.com')
        self.assertEqual(res_vmess, vmess)

    def test_custom_loopback_only(self):
        view.CustomFeature = True
        view.CustomLoopback = True
        view.CustomNodeName = False

        vless = 'vless://uuid@127.0.0.1:8080?type=ws#' + urllib.parse.quote('🇭🇰【香港-01-SG')
        res = view.rewrite_remote_node(vless, 'sub.domain.com')

        # 检查地址和端口被重写为 sub.domain.com:443
        self.assertIn('@sub.domain.com:443', res)
        # 检查节点名称保持未重写
        parsed = urllib.parse.urlparse(res)
        self.assertEqual(urllib.parse.unquote(parsed.fragment), '🇭🇰【香港-01-SG')

    def test_custom_node_name_only(self):
        view.CustomFeature = True
        view.CustomLoopback = False
        view.CustomNodeName = True

        vless = 'vless://uuid@127.0.0.1:8080?type=ws#' + urllib.parse.quote('🇭🇰【香港-01-SG')
        res = view.rewrite_remote_node(vless, 'sub.domain.com')

        # 检查地址和端口保持未重写
        self.assertIn('@127.0.0.1:8080', res)
        # 检查节点名称被重写为新加坡
        parsed = urllib.parse.urlparse(res)
        self.assertEqual(urllib.parse.unquote(parsed.fragment), '🇸🇬【新加坡-01-SG')

    def test_custom_both_loopback_and_node_name(self):
        view.CustomFeature = True
        view.CustomLoopback = True
        view.CustomNodeName = True

        vless = 'vless://uuid@127.0.0.1:8080?type=ws#' + urllib.parse.quote('🇭🇰【香港-01-SG')
        res = view.rewrite_remote_node(vless, 'sub.domain.com')

        self.assertIn('@sub.domain.com:443', res)
        parsed = urllib.parse.urlparse(res)
        self.assertEqual(urllib.parse.unquote(parsed.fragment), '🇸🇬【新加坡-01-SG')

        # 测试 vmess 节点
        vmess_dict = {
            'v': '2', 'ps': '🇭🇰【香港-02-TYO', 'add': '127.0.0.1', 'port': '8080',
            'id': 'uuid', 'aid': '0', 'net': 'ws', 'type': 'none', 'tls': ''
        }
        vmess = 'vmess://' + base64.b64encode(json.dumps(vmess_dict).encode()).decode()
        res_vmess = view.rewrite_remote_node(vmess, 'sub.domain.com')
        payload = json.loads(view.decode_base64_if(res_vmess.split('://')[1]))
        self.assertEqual(payload['add'], 'sub.domain.com')
        self.assertEqual(payload['port'], '443')
        self.assertEqual(payload['ps'], '🇯🇵【东京-02-TYO')

    def test_custom_both_disabled_under_custom_feature(self):
        view.CustomFeature = True
        view.CustomLoopback = False
        view.CustomNodeName = False

        vless = 'vless://uuid@127.0.0.1:8080?type=ws#' + urllib.parse.quote('🇭🇰【香港-01-SG')
        res = view.rewrite_remote_node(vless, 'sub.domain.com')
        self.assertEqual(res, vless)

    def test_fetch_remote_sub_integration(self):
        view.CustomFeature = True
        view.CustomLoopback = True
        view.CustomNodeName = True

        mock_response = MagicMock()
        mock_response.status_code = 200
        raw_nodes = [
            'vless://uuid@127.0.0.1:8080?type=ws#' + urllib.parse.quote('🇭🇰【香港-01-SG'),
            'ss://YWVzLTEyOC1nY206cGFzcw==@127.0.0.1:8388#' + urllib.parse.quote('🇭🇰【香港-03-LAX')
        ]
        mock_response.text = base64.b64encode('\n'.join(raw_nodes).encode()).decode()
        mock_response.raise_for_status = MagicMock()

        with patch('requests.get', return_value=mock_response):
            nodes = view.fetch_remote_sub('https://my-sub.example.com/api/v1')

        self.assertEqual(len(nodes), 2)
        self.assertIn('@my-sub.example.com:443', nodes[0])
        self.assertIn('🇸🇬【新加坡-01-SG', urllib.parse.unquote(nodes[0]))
        self.assertIn('@my-sub.example.com:443', nodes[1])
        self.assertIn('🇺🇸【洛杉矶-03-LAX', urllib.parse.unquote(nodes[1]))
        # 严格断言 SIP002 规范：禁止明文暴露密码，UserInfo 必须被重新 Base64 编码
        self.assertNotIn('aes-128-gcm', nodes[1])
        self.assertNotIn('pass', nodes[1].split('@')[0])
        ss_userinfo = nodes[1].split('://')[1].split('@')[0]
        self.assertEqual(view.decode_base64_if(ss_userinfo), 'aes-128-gcm:pass')

    def test_edge_cases(self):
        view.CustomFeature = True
        view.CustomLoopback = True
        view.CustomNodeName = True

        # 空节点与 None
        self.assertEqual(view.rewrite_remote_node('', 'sub.example.com'), '')
        self.assertIsNone(view.rewrite_remote_node(None, 'sub.example.com'))

        # host 为空或 None
        node = 'vless://uuid@127.0.0.1:8080?type=ws#' + urllib.parse.quote('🇭🇰【香港-01-SG')
        self.assertEqual(view.rewrite_remote_node(node, None), 'vless://uuid@127.0.0.1:8080?type=ws#' + urllib.parse.quote('🇸🇬【新加坡-01-SG'))
        self.assertEqual(view.rewrite_remote_node(node, ''), 'vless://uuid@127.0.0.1:8080?type=ws#' + urllib.parse.quote('🇸🇬【新加坡-01-SG'))

        # 非 127.0.0.1 节点，地址不应被替换
        normal_vless = 'vless://uuid@8.8.8.8:8080?type=ws#' + urllib.parse.quote('🇭🇰【香港-01-SG')
        res = view.rewrite_remote_node(normal_vless, 'sub.example.com')
        self.assertIn('@8.8.8.8:8080', res)
        self.assertIn('🇸🇬【新加坡-01-SG', urllib.parse.unquote(res))

        # 不含 🇭🇰【香港 的节点名称不被重写
        other_vless = 'vless://uuid@127.0.0.1:8080?type=ws#' + urllib.parse.quote('专线-01-SG')
        res2 = view.rewrite_remote_node(other_vless, 'sub.example.com')
        self.assertIn('@sub.example.com:443', res2)
        self.assertIn('专线-01-SG', urllib.parse.unquote(res2))

        # SSR 节点回环重写与名称重写
        ssr_plain = '127.0.0.1:8388:origin:none:plain:' + base64.urlsafe_b64encode(b'pass').decode().rstrip('=') + '/?remarks=' + base64.b64encode('🇭🇰【香港-01-SG'.encode()).decode()
        ssr_node = 'ssr://' + base64.urlsafe_b64encode(ssr_plain.encode()).decode().rstrip('=')
        res_ssr = view.rewrite_remote_node(ssr_node, 'sub.example.com')
        self.assertTrue(res_ssr.startswith('ssr://'))
        ssr_decoded = view.decode_base64_if(res_ssr.split('://')[1].replace('-', '+').replace('_', '/'))
        self.assertTrue(ssr_decoded.startswith('sub.example.com:443:'))
        self.assertIn(urllib.parse.quote(base64.b64encode('🇸🇬【新加坡-01-SG'.encode()).decode()), ssr_decoded)


class CustomConfigApiTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['JWT_SECRET_KEY'] = 'test-secret-key'
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

    def test_get_config_defaults(self):
        with self.app.app_context():
            db.create_all()
            client = self.app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            res = client.post('/get_conifg', headers=headers)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertIn('custom', data)
            self.assertIn('custom_loopback', data)
            self.assertIn('custom_node_name', data)
            self.assertFalse(data['custom'])
            self.assertFalse(data['custom_loopback'])
            self.assertFalse(data['custom_node_name'])

    def test_set_and_get_config_and_memory_sync(self):
        with self.app.app_context():
            db.create_all()
            client = self.app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            # 设置自定义开关全部开启
            payload = {
                'udp': True,
                'skipcert': False,
                'emoji': True,
                'custom': True,
                'custom_loopback': True,
                'custom_node_name': True
            }
            res_set = client.post('/set_conifg', json=payload, headers=headers)
            self.assertEqual(res_set.status_code, 200)
            self.assertEqual(res_set.get_json()['code'], 200)

            # 验证内存中全局变量已同步
            self.assertTrue(view.CustomFeature)
            self.assertTrue(view.CustomLoopback)
            self.assertTrue(view.CustomNodeName)
            self.assertTrue(view.Udp)
            self.assertFalse(view.SkipCert)
            self.assertTrue(view.Emoji)

            # 验证 get_conifg 接口读取到正确配置
            res_get = client.post('/get_conifg', headers=headers)
            self.assertEqual(res_get.status_code, 200)
            data = res_get.get_json()
            self.assertTrue(data['custom'])
            self.assertTrue(data['custom_loopback'])
            self.assertTrue(data['custom_node_name'])
            self.assertTrue(data['udp'])
            self.assertFalse(data['skipcert'])

            # 验证 load_config 函数从数据库重新加载
            view.CustomFeature = False
            view.CustomLoopback = False
            view.CustomNodeName = False
            view.load_config()
            self.assertTrue(view.CustomFeature)
            self.assertTrue(view.CustomLoopback)
            self.assertTrue(view.CustomNodeName)

    def test_partial_set_config_and_truthy_values(self):
        with self.app.app_context():
            db.create_all()
            client = self.app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            client.post('/set_conifg', json={'custom': True, 'custom_loopback': True, 'custom_node_name': False}, headers=headers)
            self.assertTrue(view.CustomFeature)
            self.assertTrue(view.CustomLoopback)
            self.assertFalse(view.CustomNodeName)

            # 局部更新并测试字符串形式 "1"
            res_partial = client.post('/set_conifg', json={'custom_node_name': '1'}, headers=headers)
            self.assertEqual(res_partial.status_code, 200)
            self.assertTrue(view.CustomNodeName)
            self.assertTrue(view.CustomFeature)
            self.assertTrue(view.CustomLoopback)

    def test_empty_db_resets_stale_memory_globals(self):
        with self.app.app_context():
            db.create_all()
            client = self.app.test_client()
            token = create_access_token(identity='admin')
            headers = {'Authorization': f'Bearer {token}'}

            # 模拟内存变量原本为 True，但数据库为空的情形
            view.CustomFeature = True
            view.CustomLoopback = True
            view.CustomNodeName = True
            view.Udp = True
            view.SkipCert = True
            view.Emoji = True

            # get_conifg 应返回默认 False，并同步重置内存变量
            res = client.post('/get_conifg', headers=headers)
            data = res.get_json()
            self.assertFalse(data['custom'])
            self.assertFalse(data['custom_loopback'])
            self.assertFalse(data['custom_node_name'])
            self.assertFalse(view.CustomFeature)
            self.assertFalse(view.CustomLoopback)
            self.assertFalse(view.CustomNodeName)

            # load_config 同样应重置内存变量
            view.CustomFeature = True
            view.CustomLoopback = True
            view.CustomNodeName = True
            view.load_config()
            self.assertFalse(view.CustomFeature)
            self.assertFalse(view.CustomLoopback)
            self.assertFalse(view.CustomNodeName)

    def test_is_truthy_helper(self):
        self.assertTrue(view.is_truthy(True))
        self.assertTrue(view.is_truthy(1))
        self.assertTrue(view.is_truthy('1'))
        self.assertTrue(view.is_truthy('true'))
        self.assertTrue(view.is_truthy('TRUE'))
        self.assertTrue(view.is_truthy('yes'))
        self.assertTrue(view.is_truthy('on'))

        self.assertFalse(view.is_truthy(False))
        self.assertFalse(view.is_truthy(0))
        self.assertFalse(view.is_truthy('0'))
        self.assertFalse(view.is_truthy('false'))
        self.assertFalse(view.is_truthy('FALSE'))
        self.assertFalse(view.is_truthy('no'))
        self.assertFalse(view.is_truthy('off'))
        self.assertFalse(view.is_truthy(None))
        self.assertFalse(view.is_truthy(''))

    def test_ipv6_node_server_detection(self):
        # IPv6 字面量
        self.assertTrue(view.is_ipv6_node_server('2400:3200::1'))
        self.assertTrue(view.is_ipv6_node_server('[2400:3200::1]'))
        self.assertTrue(view.is_ipv6_node_server('::1'))
        # 显式 IPv6 域名特征
        self.assertTrue(view.is_ipv6_node_server('jp-v6.example.com'))
        self.assertTrue(view.is_ipv6_node_server('node.v6.example.com'))
        self.assertTrue(view.is_ipv6_node_server('server-ipv6.test.net'))
        # 普通 IPv4 或域名
        self.assertFalse(view.is_ipv6_node_server('127.0.0.1'))
        self.assertFalse(view.is_ipv6_node_server('8.8.8.8'))
        self.assertFalse(view.is_ipv6_node_server('jp.example.com'))
        self.assertFalse(view.is_ipv6_node_server(''))

    def test_rewrite_node_name_ipv6_text(self):
        # 模式1: 【城市 | 线路】 -> 【城市 | IPv6】
        self.assertEqual(
            view.rewrite_node_name_ipv6_text('🇯🇵【东京 | SoftBank】01'),
            '🇯🇵【东京 | IPv6】01'
        )
        self.assertEqual(
            view.rewrite_node_name_ipv6_text('🇭🇰【香港 | BGP】高速-01'),
            '🇭🇰【香港 | IPv6】高速-01'
        )
        # 模式2: 【城市】 -> 【城市 | IPv6】
        self.assertEqual(
            view.rewrite_node_name_ipv6_text('🇸🇬【新加坡】02'),
            '🇸🇬【新加坡 | IPv6】02'
        )
        # 模式3: 普通文本未包含 IPv6
        self.assertEqual(
            view.rewrite_node_name_ipv6_text('US-Node-1'),
            'US-Node-1 [IPv6]'
        )
        # 已有 IPv6 标识不重复追加
        self.assertEqual(
            view.rewrite_node_name_ipv6_text('US-Node-1 [IPv6]'),
            'US-Node-1 [IPv6]'
        )

    def test_rewrite_remote_node_ipv6_e2e(self):
        view.CustomFeature = True
        view.CustomLoopback = True
        view.CustomNodeName = True

        # 测试场景：节点原为 127.0.0.1 回环隧道，名称为 🇭🇰【香港 | SoftBank】01-TYO
        # 远程订阅 host 为 IPv6 地址：2400:3200::1
        vless_127 = 'vless://uuid@127.0.0.1:8080?type=ws#' + urllib.parse.quote('🇭🇰【香港 | SoftBank】01-TYO')
        res = view.rewrite_remote_node(vless_127, '2400:3200::1')

        # 1. 回环地址与端口重写生效：127.0.0.1:8080 -> [2400:3200::1]:443
        self.assertIn('@[2400:3200::1]:443', res)
        # 2. 节点名称与国旗重写生效：🇭🇰【香港 改为 🇯🇵【东京
        # 3. 订阅域名为 IPv6 的延续生效：【东京 | SoftBank】延续改写为 【东京 | IPv6】
        expected_name = '🇯🇵【东京 | IPv6】01-TYO'
        self.assertIn(urllib.parse.quote(expected_name), res)

        # 对照场景：订阅 host 为普通 IPv4 时，保留原有 SoftBank 线路名
        res_ipv4 = view.rewrite_remote_node(vless_127, '1.2.3.4')
        self.assertIn('@1.2.3.4:443', res_ipv4)
        expected_ipv4_name = '🇯🇵【东京 | SoftBank】01-TYO'
        self.assertIn(urllib.parse.quote(expected_ipv4_name), res_ipv4)
        self.assertNotIn('IPv6', res_ipv4)


if __name__ == '__main__':
    unittest.main()
