import asyncio
import json
import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from contextlib import asynccontextmanager
from scripts import daily_signals as radar


class TavilyTests(unittest.TestCase):
    def test_queries_base_override_and_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'base.json'
            override = Path(tmp) / 'agent.json'
            base.write_text(json.dumps({'max_queries': 2, 'queries': [{'facet':'基础','query':'默认关键词'}]}))
            override.write_text(json.dumps({'queries': [{'facet':'动态','query':'最新话题'}]}))
            with patch.dict(os.environ, {'TAVILY_BASE_CONFIG': str(base), 'TAVILY_QUERY_FILE': ''}):
                self.assertEqual(radar.load_tavily_queries(), [('基础', '默认关键词')])
                os.environ['TAVILY_QUERY_FILE'] = str(override)
                self.assertEqual(radar.load_tavily_queries(), [('动态', '最新话题')])
                override.write_text(json.dumps({'queries':[{'facet':'x','query':'q'}] * 3}))
                with self.assertRaises(ValueError): radar.load_tavily_queries()
                override.write_text('{broken')
                with self.assertRaises(ValueError): radar.load_tavily_queries()
                override.write_text(json.dumps({'queries': []}))
                with self.assertRaises(ValueError): radar.load_tavily_queries()
                os.environ['TAVILY_QUERY_FILE'] = str(Path(tmp) / 'missing')
                with self.assertRaises(ValueError): radar.load_tavily_queries()

    def test_normalize_and_deduplicate(self):
        data = {'results': [{'title': '标题', 'url': 'https://example.org/a', 'content': '摘要', 'published_date': '2026-10-30'},
                            {'title': '重复', 'url': 'https://example.org/a'},
                            {'title': '不安全', 'url': 'javascript:alert(1)'}]}
        seen = set()
        items = radar._tavily_results(data, '健康与身体', seen)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['source'], 'tavily')
        self.assertEqual(items[0]['extra_tags'], ['健康与身体'])
        self.assertEqual(radar._tavily_results(data, '生活方式', seen), [])
        with self.assertRaises(ValueError):
            radar._tavily_results({'message': 'invalid key'}, '生活方式', seen)

    def test_no_key(self):
        with patch.dict(os.environ, {'TAVILY_API_KEY': ''}):
            self.assertEqual(radar.fetch_tavily(), [])

    def test_mcp_search(self):
        class Session:
            def __init__(self, *_): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def initialize(self): pass
            async def call_tool(self, name, params):
                self.assert_name = name
                return SimpleNamespace(isError=False, structuredContent={'results': [
                    {'title': params['query'], 'url': 'https://example.org/' + str(len(params['query']))}
                ]}, content=[])
        @asynccontextmanager
        async def transport(*args, **kwargs):
            yield None, None
        with patch.dict(os.environ, {'TAVILY_API_KEY': 'dummy'}), \
             patch('mcp.ClientSession', Session), \
             patch('mcp.client.stdio.stdio_client', transport):
            result = radar.fetch_tavily()
            self.assertTrue(result)
            self.assertTrue(all(x['source'] == 'tavily' for x in result))

    def test_local_text_response(self):
        text = 'Request ID: abc\nDetailed Results:\n\nTitle: 测试\nID: 1\nURL: https://example.com/a\nContent: 第一行\n第二行'
        result = radar._parse_tavily_text(text)
        self.assertEqual(result['results'][0]['title'], '测试')
        self.assertEqual(result['results'][0]['content'], '第一行\n第二行')
        self.assertEqual(len(radar._tavily_results(result, '健康与身体', set())), 1)
        with self.assertRaises(ValueError): radar._parse_tavily_text('Error: invalid key')

    def test_error_payload_not_accepted(self):
        with self.assertRaises(ValueError):
            radar._tavily_results({'code': 'monthly_cap_reached'}, '生活方式', set())


if __name__ == '__main__':
    unittest.main()
