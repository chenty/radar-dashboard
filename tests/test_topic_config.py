import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
from scripts.query_config import load_topic_facets, load_source_queries
from scripts.daily_signals import load_tavily_queries, _tavily_results


class TopicConfigTests(unittest.TestCase):
    def test_config_integrates_collection_and_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'topics.json'
            path.write_text(json.dumps({'theme':'测试', 'facets':[
                {'name':'职业转变','types':['观点争议型'],'keywords':{'zh':['中文查询','另一个词'], 'en':['english query']}}
            ]}, ensure_ascii=False))
            with patch.dict(os.environ, {'RADAR_TOPIC_CONFIG':str(path), 'RADAR_QUERY_LANGUAGE':'zh', 'RADAR_SEARCH_CONFIG':'', 'TAVILY_QUERY_FILE':''}):
                self.assertEqual(load_source_queries('xiaohongshu'), ['中文查询'])
                self.assertEqual(load_tavily_queries(), [('职业转变','中文查询')])
                with app.test_client() as client:
                    response = client.get('/api/topic-config')
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json['facets'][0]['name'], '职业转变')
                os.environ['RADAR_QUERY_LANGUAGE'] = 'en'
                self.assertEqual(load_source_queries('bilibili-reach'), ['english query'])
                self.assertEqual(load_tavily_queries(), [('职业转变','english query')])
                item = _tavily_results({'results':[{'title':'结果','url':'https://example.org'}]},'职业转变',set())[0]
                self.assertEqual(item['extra_tags'], ['职业转变'])
                path.write_text('{}')
                with self.assertRaises(ValueError): load_source_queries('xiaohongshu')
                with app.test_client() as client:
                    self.assertEqual(client.get('/api/topic-config').status_code, 503)

    def test_existing_report_without_subfacet_still_served(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = {'date':'2026-01-01','modules':{'publicAccountTopics':[{'title':'旧选题','facet':'生活方式'}]}}
            Path(tmp,'2026-01-01.json').write_text(json.dumps(report,ensure_ascii=False))
            with patch('app.REPORTS_DIR', Path(tmp)):
                with app.test_client() as c:
                    result = c.get('/api/modules/topics')
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.json[0]['title'], '旧选题')
                    self.assertNotIn('subfacet', result.json[0])


if __name__ == '__main__':
    unittest.main()
