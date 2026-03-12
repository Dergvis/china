import json
from pathlib import Path
import unittest


class MiniappManifestTest(unittest.TestCase):
    def test_pages_exist(self):
        root = Path(__file__).resolve().parents[1] / 'miniapp'
        app_json = json.loads((root / 'app.json').read_text(encoding='utf-8'))
        pages = app_json.get('pages', [])
        self.assertTrue(pages, 'app.json.pages must not be empty')
        for page in pages:
            for ext in ('.wxml', '.js', '.wxss'):
                p = root / f'{page}{ext}'
                self.assertTrue(p.exists(), f'Missing page asset: {p}')


if __name__ == '__main__':
    unittest.main()
