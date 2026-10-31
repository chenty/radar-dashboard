import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import app
from scripts.source_config import load_signal_sources
from scripts.daily_signals import source_label


class SourceLabelTests(unittest.TestCase):
    def test_supported_sources_have_implementations(self):
        tree = ast.parse(Path('scripts/daily_signals.py').read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        assignment = next(node for node in ast.walk(main) if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'available_collectors' for t in node.targets))
        implementations = {key.value for key in assignment.value.keys}
        sources = load_signal_sources()
        self.assertEqual({s['key'] for s in sources}, implementations)
        labels = {s['key']: s['name'] for s in sources}
        self.assertEqual(source_label('weibo-hot', labels), '微博热搜')
        self.assertEqual(source_label('unknown-source', labels), 'unknown-source')

    def test_config_is_used_by_dashboard_and_rejects_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sources.json'
            path.write_text(json.dumps({'sources':[{'key':'tavily','name':'自定义名称','enabled':False, 'category':'定向搜索'}]},ensure_ascii=False))
            with patch.dict(os.environ, {'RADAR_SOURCES_CONFIG': str(path)}):
                with app.test_client() as c:
                    result=c.get('/api/sources')
                    self.assertEqual(result.status_code,200)
                    self.assertEqual(result.json['sources'][0]['name'],'自定义名称')
                    self.assertEqual(result.json['sources'][0]['status'],'disabled')
                path.write_text(json.dumps({'sources':[{'key':'a','name':'A','enabled':'yes'}]}))
                with self.assertRaises(ValueError): load_signal_sources()
                with app.test_client() as c: self.assertEqual(c.get('/api/sources').status_code,503)

if __name__ == '__main__': unittest.main()
