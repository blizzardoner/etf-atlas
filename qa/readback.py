"""Read back every published history artifact, then use qa/audit.py on it."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin
import requests

base = sys.argv[1].rstrip('/') + '/'
assert base.startswith('https://'), 'production verification requires HTTPS'
root = Path('artifacts/remote-data')
(root / 'history').mkdir(parents=True, exist_ok=True)
response = requests.get(urljoin(base, 'data/market.json'), timeout=60, headers={'Cache-Control': 'no-cache'})
response.raise_for_status()
market = response.json()
(root / 'market.json').write_text(json.dumps(market, ensure_ascii=False, allow_nan=False), encoding='utf-8')

def fetch(item):
    identity = item['id']
    assert all(c.isalnum() or c in '-_' for c in identity), 'unsafe artifact id'
    url = urljoin(base, item['historyUrl'])
    assert url.startswith(base + 'data/history/'), 'unexpected history origin/path'
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    history = r.json()
    assert history['id'] == identity
    assert len(history['bars']) == item['count']
    (root / 'history' / f'{identity}.json').write_text(json.dumps(history, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    return identity

ids = list(ThreadPoolExecutor(max_workers=4).map(fetch, market['instruments']))
assert len(ids) == len(set(ids)) == len(market['instruments'])
print(json.dumps({'readback':'PASS','base':base,'generatedAt':market['generatedAt'],'histories':len(ids),'output':str(root)}, ensure_ascii=False))
