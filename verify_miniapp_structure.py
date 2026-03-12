#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
miniapp = ROOT / 'miniapp'
required = [
    'app.json',
    'app.js',
    'app.wxss',
    'sitemap.json',
    'project.config.json',
    'index.wxml',
    'index.js',
    'index.wxss',
]
missing = [p for p in required if not (miniapp / p).exists()]
if missing:
    print('Missing miniapp files:')
    for p in missing:
        print('-', p)
    sys.exit(1)
print('Miniapp structure OK')
