import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import unquote

from scripts.query_config import load_source_queries
from scripts import daily_signals, weibo_render_urls


class SearchQueriesTests(unittest.TestCase):
    def test_defaults_and_config_validation(self):
        self.assertEqual(len(load_source_queries('xiaohongshu')), 6)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'queries.json'
            with patch.dict(os.environ, {'RADAR_SEARCH_CONFIG': str(path)}):
                path.write_text(json.dumps({'xiaohongshu': ['  自定义  ']}))
                self.assertEqual(load_source_queries('xiaohongshu'), ['自定义'])
                with self.assertRaises(ValueError): load_source_queries('weibo-reach')
                for value in ([], [''], ['a'] * 21, [3]):
                    path.write_text(json.dumps({'weibo-reach': value}))
                    with self.assertRaises(ValueError): load_source_queries('weibo-reach')
                path.write_text('{')
                with self.assertRaises(ValueError): load_source_queries('weibo-reach')

    def test_collectors_use_custom_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'queries.json'
            path.write_text(json.dumps({'xiaohongshu':['定向词一'], 'bilibili-reach':['定向词二'], 'weibo-reach':['定向词三']}))
            response = SimpleNamespace(stdout=json.dumps({'ok': True, 'items': []}))
            with patch.dict(os.environ, {'RADAR_SEARCH_CONFIG': str(path)}), \
                    patch.object(daily_signals.subprocess, 'run', return_value=response) as run, \
                    patch.object(daily_signals.time, 'sleep'):
                daily_signals.fetch_xiaohongshu_reach()
                daily_signals.fetch_bilibili_reach()
                self.assertEqual(run.call_args_list[0].args[0][3], '定向词一')
                self.assertEqual(run.call_args_list[1].args[0][3], '定向词二')
                self.assertIn('定向词三', unquote(weibo_render_urls.search_urls()[0]))

    def test_bad_config_skips_source(self):
        with patch.dict(os.environ, {'RADAR_SEARCH_CONFIG': '/not-present'}):
            self.assertEqual(daily_signals.fetch_weibo_reach(), [])
            self.assertEqual(daily_signals.fetch_xiaohongshu_reach(), [])
            self.assertEqual(daily_signals.fetch_bilibili_reach(), [])


if __name__ == '__main__':
    unittest.main()
