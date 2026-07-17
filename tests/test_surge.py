import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import view


SURGE_TEMPLATE = """[Proxy]
DIRECT = direct

[Proxy Group]
manual = select,auto
region = select,auto
"""


class SurgeEncodeTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_dir = os.path.join(self.temp_dir.name, 'db')
        os.mkdir(db_dir)
        with open(os.path.join(db_dir, 'surge.conf'), 'w', encoding='utf-8') as file:
            file.write(SURGE_TEMPLATE)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empty_proxy_list_uses_direct_fallback(self):
        with patch.object(view, 'path', self.temp_dir.name):
            config = view.surge_encode([])

        self.assertNotIn('select,\n', config)
        self.assertEqual(config.count('select,DIRECT'), 2)

    def test_proxy_names_replace_auto_placeholder(self):
        proxy = {
            'name': 'test-node',
            'server': 'example.com',
            'port': 443,
            'cipher': 'aes-128-gcm',
            'password': 'password',
            'tfo': False,
            'udp': False,
        }
        sub = SimpleNamespace(node='ss://test')

        with patch.object(view, 'path', self.temp_dir.name), \
                patch.object(view.NodeParse, 'ss', return_value=proxy):
            config = view.surge_encode([sub])

        self.assertEqual(config.count('select,test-node'), 2)
        self.assertIn('test-node = ss, example.com, 443', config)


if __name__ == '__main__':
    unittest.main()
