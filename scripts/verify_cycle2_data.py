"""Read-only actual-source and nominal-price receipt; never repairs public data."""
from collections import Counter
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
market = json.loads((ROOT/'public/data/market.json').read_text(encoding='utf-8'))
universe = {c['id']:c for c in json.loads((ROOT/'data/universe.json').read_text(encoding='utf-8'))['instruments']}
before_hashes = json.loads((ROOT/'artifacts/fix-cycle2-before-bars.json').read_text())
cache = {}
for path in (ROOT/'.cache').glob('*.meta.json'):
    meta = json.loads(path.read_text())
    url = urlparse(meta['url'])
    params = parse_qs(url.query)
    if '/chart/' in url.path or 'secid' in params:
        key = ('Yahoo', url.path) if '/chart/' in url.path else ('Eastmoney', params['secid'][0])
        cache.setdefault(key, []).append((meta, path.with_name(path.name.replace('.meta.json','.raw'))))
rows = []
changes = Counter()
for item in market['instruments']:
    config = universe[item['id']]
    for field in ('symbol','name','country','kind','currency','benchmark','issuerUrl','frequency'):
        assert item.get(field) == config.get(field), (item['id'],field)
    filename = f"{item['id']}.json"
    history = json.loads((ROOT/'public/data/history'/filename).read_text(encoding='utf-8'))
    bars = history['bars']
    baseline = json.loads((ROOT/'dist/data/history'/filename).read_text(encoding='utf-8'))['bars']
    assert len(baseline) == len(bars)
    for old,new in zip(baseline,bars):
        for field in old.keys() | new.keys():
            if old.get(field) != new.get(field):
                changes[field] += 1
                assert field == 'adjustedClose', (item['id'],field,'nominal/OHLC/volume changed')
    digest = hashlib.sha256(json.dumps(bars,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    parsed_source = urlparse(history['sourceUrl'])
    key = ('Yahoo',parsed_source.path) if config['provider']=='yahoo' else ('Eastmoney',config['secid'])
    source_params = parse_qs(parsed_source.query)
    candidates = [(meta,path) for meta,path in cache[key] if parse_qs(urlparse(meta['url']).query) == source_params]
    exact_request = bool(candidates)
    meta,path = max(candidates or cache[key],key=lambda pair:pair[0]['retrievedAt'])
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == meta['sha256'], (item['id'], 'raw source hash')
    payload = json.loads(raw)
    first_trade = None
    if config['provider']=='yahoo':
        result = payload['chart']['result'][0]
        provider_meta = result['meta']
        assert provider_meta['symbol']==config['symbol'] and provider_meta['currency']==config['currency'] and provider_meta['dataGranularity']=='1d'
        zone = ZoneInfo(provider_meta['exchangeTimezoneName'])
        epoch = dt.datetime(1970,1,1,tzinfo=dt.timezone.utc)
        first_trade = (epoch+dt.timedelta(seconds=provider_meta['firstTradeDate'])).astimezone(zone).date().isoformat()
        assert first_trade == history['providerEvidence']['firstTradeDate']
        raw_count = len(result['timestamp'])
        source_prices = {}
        for stamp,close in zip(result['timestamp'],result['indicators']['quote'][0]['close']):
            date = (epoch+dt.timedelta(seconds=stamp)).astimezone(zone).date().isoformat()
            if date <= item['lastDate'] and close is not None and math.isfinite(close) and close > 0:
                source_prices[date] = close
        assert 0 <= (dt.date.fromisoformat(bars[0]['date'])-dt.date.fromisoformat(first_trade)).days <= 10
    else:
        data = payload['data']
        assert data['code']==config['secid'].split('.')[1]
        raw_count = len(data['klines'])
        assert raw_count == data['dktotal'] == history['providerEvidence']['declaredCount']
        source_prices = {row.split(',')[0]:float(row.split(',')[2]) for row in data['klines'] if row.split(',')[0] <= item['lastDate']}
    assert raw_count == history['providerEvidence']['rawCount']
    assert min(source_prices) == bars[0]['date'], (item['id'], 'actual first date')
    missing = [b['date'] for b in bars if b['date'] not in source_prices]
    assert not missing or missing == [item['expectedLastDate']], (item['id'],'unexpected source gap',missing)
    for bar in bars:
        if bar['date'] in source_prices:
            assert math.isclose(source_prices[bar['date']],bar.get('rawClose',bar['close']),rel_tol=1e-12), (item['id'],bar['date'],'actual nominal price')
    rows.append({'id':item['id'],'status':item['status'],'firstDate':bars[0]['date'],'lastDate':bars[-1]['date'],'count':len(bars),
                 'sourceFirstTradeDate':first_trade,'rawCount':raw_count,'sourceValidCompletedCount':len(source_prices),
                 'missingSourceCloseDates':missing,'exactSnapshotSourceRequest':exact_request,
                 'rawCache':str(path.relative_to(ROOT)),'sourceUrl':meta['url'],'sourceRetrievedAt':meta['retrievedAt'],
                 'sourceSha256':meta['sha256'],'barsUnchangedSinceCycle2':digest==before_hashes[item['id']],
                 'barsSha256':digest})
assert len(rows)==42 and sum(row['count'] for row in rows)==198033
print(json.dumps({'receipt':'BLOCKED' if market['failures'] else 'PASS','generatedAt':market['generatedAt'],'instruments':len(rows),
                  'dailyBars':sum(row['count'] for row in rows),'all42NominalPriceOHLCVolumeDatesUnchangedAgainstActualDist':True,
                  'all42ActualFirstDatesAndProviderIdentityCurrencyVerified':True,
                  'actualDistFieldChanges':dict(changes),'failures':market['failures'],'rows':rows},indent=2))
