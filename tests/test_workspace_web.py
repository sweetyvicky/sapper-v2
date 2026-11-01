"""Packaged UI boundary checks; interactive behavior is in browser journeys."""
import re
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from pentest.workspace_http import STATIC, WEB


class WorkspaceWebTests(unittest.TestCase):
    def test_packaged_entry_and_focused_modules_are_served(self):
        required = ('index.html', 'app.css', 'app.js', 'api.js', 'ui.js',
                    'task_editor.js', 'models_view.js', 'run_view.js',
                    'coverage_view.js', 'findings_view.js', 'report_view.js')
        self.assertEqual(set(required), {v[0] for v in STATIC.values()})
        for name in required:
            self.assertTrue((WEB / name).is_file(), name + ' is not packaged')
        html = (WEB / 'index.html').read_text(encoding='utf-8')
        self.assertIn('lang="zh-CN"', html)
        self.assertRegex(html, r'<script[^>]+type="module"[^>]+src="/app.js"')
        self.assertNotRegex(html, r'(?i)\bon\w+=|<style|<script(?![^>]+src=)')
        self.assertNotRegex(html, r'https?://')

    def test_browser_modules_do_not_persist_credentials_or_inject_markup(self):
        self.assertTrue(WEB.is_dir(), 'operator workspace is missing')
        for path in WEB.glob('*.js'):
            source = path.read_text(encoding='utf-8')
            self.assertNotRegex(source, r'\b(localStorage|sessionStorage|innerHTML|outerHTML|eval)\b', path.name)


if __name__ == '__main__':
    unittest.main()
