import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import app


class QuoteTests(unittest.TestCase):
    def test_api_returns_original_quote_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = {'date':'2026-01-01', 'modules':{'quoteBank':[{'quote':'原话','author':'说话者','url':'https://example.org/a'}]}}
            Path(tmp,'2026-01-01.json').write_text(json.dumps(report,ensure_ascii=False))
            with patch('app.REPORTS_DIR',Path(tmp)), app.test_client() as c:
                r=c.get('/api/modules/quotes')
                self.assertEqual(r.status_code,200)
                self.assertEqual(r.json[0]['quote'],'原话')
                self.assertEqual(r.json[0]['author'],'说话者')
    def test_browser_render_functions(self):
        subprocess.run(['node','tests/test_quote_render.js'],check=True,timeout=15)


if __name__ == '__main__': unittest.main()
