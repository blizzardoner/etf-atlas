"""Independent black-box audit of generated artifacts (no upstream mocks)."""
import calendar
import json
import math
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('root',nargs='?',default='public/data')
parser.add_argument('--portable-recovery',action='store_true',help='Validate public recovery witnesses only; does NOT verify unavailable private raw bytes')
args = parser.parse_args()
root = Path(args.root)
repo = Path(__file__).resolve().parents[1]
market = json.loads((root / 'market.json').read_text(encoding='utf-8'))
items = market['instruments']
assert market.get('failures') == [], 'source refresh failures prohibit publication'
assert all(item['status'] == 'fresh' for item in items), 'stale/unavailable snapshots prohibit publication'
assert len(items) == len({x['id'] for x in items}), 'duplicate instruments'
universe_path = Path(__file__).resolve().parents[1] / 'data' / 'universe.json'
configs = {}
if universe_path.exists():
    universe = json.loads(universe_path.read_text(encoding='utf-8'))
    universe = universe['instruments'] if isinstance(universe, dict) else universe
    assert {x['id'] for x in items} == {x['id'] for x in universe}, 'universe/snapshot coverage mismatch'
    configs = {x['id']:x for x in universe}
    for item in items:
        for field in ('symbol','name','country','kind','currency','benchmark','issuerUrl','frequency'):
            assert item.get(field) == configs[item['id']].get(field), (item['id'], 'universe metadata mismatch', field)
counts = Counter()
# Independent freshness check: do not trust a producer's 'fresh' label.
import exchange_calendars as xc
import pandas as pd
instant = pd.Timestamp(market['generatedAt'])
calendar_expectations = {}
for country in {item['country'] for item in items}:
    name = {'CN':'XSHG','US':'XNYS','AU':'XASX'}[country]
    try:
        bound = xc.get_calendar(name).bound_max()
        end = pd.Timestamp(f'{instant.year+1}-12-31')
        if bound is not None:
            end = min(end, bound)
        schedule = xc.get_calendar(name,start=f'{instant.year-1}-01-01',end=end).schedule
        closes = schedule['close'] + pd.Timedelta(minutes=5)
        completed, future = closes[closes <= instant], closes[closes > instant]
        assert not completed.empty and not future.empty, 'calendar coverage unavailable'
        calendar_expectations[country] = (name,completed.index[-1].date().isoformat(),future.iloc[0])
    except Exception as exc:
        raise AssertionError(f'{name} calendar coverage unavailable: {exc}') from exc
def audit_closing_recovery(history, config, expected, closing, instant):
    """Re-derive every recovery assertion from hash-verified original responses."""
    import hashlib
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from urllib.parse import urlparse, parse_qs, unquote
    evidence = history['providerEvidence']
    proof = evidence['latestClosingRecovery']
    assert proof['date'] == expected and proof['sessionCloseTimestamp'] == closing, 'recovery session evidence'
    # This witness-only boundary is explicit, never an automatic missing-cache
    # fallback. It cannot authenticate original response bytes or historical
    # raw-field equality; the default mode below always does both.
    import re
    from urllib.parse import urlparse, parse_qs, unquote
    p = proof['primary']
    zone = ZoneInfo(p['exchangeTimezoneName'])
    def witness_date(stamp):
        return (datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(seconds=stamp)).astimezone(zone).date().isoformat()
    assert p['sourceUrl'] == history['sourceUrl'], 'recovery primary URL witness'
    for key,interval,range_ in [('primary','1d',None),('minute','15m','5d'),('snapshot','1wk','1mo')]:
        record = proof[key]
        receipt = record['rawSource']
        assert receipt and re.fullmatch(r'[0-9a-f]{64}',receipt['sha256']), 'recovery source hash shape'
        assert receipt['url'] == record['sourceUrl'], 'recovery URL witness'
        retrieved = pd.Timestamp(receipt['retrievedAt'])
        assert retrieved.tzinfo is not None and retrieved.timestamp() >= closing, 'recovery retrieval witness'
        parsed = urlparse(record['sourceUrl'])
        params = parse_qs(parsed.query)
        assert parsed.scheme == 'https' and parsed.hostname in ('query1.finance.yahoo.com','query2.finance.yahoo.com'), 'recovery URL host witness'
        assert unquote(parsed.path).endswith('/chart/'+config['symbol']), 'recovery URL symbol witness'
        assert record['symbol'] == config['symbol'] and record['currency'] == config['currency'], 'recovery identity/currency witness'
        assert record['dataGranularity'] == record['requestedInterval'] == interval and params.get('interval') == [interval], 'recovery interval witness'
        if range_:
            assert params.get('range') == [range_] and params.get('includePrePost') == ['false'], 'recovery range witness'
            if interval == '1wk': assert params.get('includeAdjustedClose') == ['true'], 'recovery adjusted witness'
        else:
            assert params.get('period1') == [str(-2208988800 if config['kind']=='index' else 0)], 'recovery lifetime request witness'
    assert witness_date(proof['primaryTimestamp']) == expected, 'recovery primary date witness'
    assert p['rowIndex'] == evidence['rawCount']-1, 'recovery terminal row witness'
    if p['firstTradeTimestamp']:
        assert witness_date(p['firstTradeTimestamp']) == evidence['firstTradeDate'], 'recovery primary first anchor witness'
    else: assert config.get('expectedFirstDate') == evidence.get('expectedFirstDate') and config.get('expectedFirstDate'), 'recovery primary missing anchor witness'
    original = proof['primaryValues']
    missing = [k for k in ('close','adjustedClose') if original[k] is None]
    assert missing and missing == proof['primaryMissingFields'], 'recovery missing witness'
    minute,snapshot = proof['minute'],proof['snapshot']
    assert minute['timestamp'] == closing, 'recovery exact closing minute witness'
    assert snapshot['timestamp'] == snapshot['regularMarketTime'] and closing <= snapshot['timestamp'] <= closing+60, 'recovery snapshot closing time witness'
    assert witness_date(snapshot['timestamp']) == expected, 'recovery snapshot date witness'
    assert snapshot['close'] is not None and math.isfinite(snapshot['close']) and snapshot['close'] > 0 and snapshot['close'] == minute['close'], 'recovery close agreement witness'
    for field in ('open','high','low','close'):
        if original[field] is not None: assert original[field] == snapshot[field], 'recovery primary OHLC witness'
    assert original['high'] is None or snapshot['close'] <= original['high'], 'recovery primary high witness'
    assert original['low'] is None or snapshot['close'] >= original['low'], 'recovery primary low witness'
    assert snapshot['adjustedClose'] is None or math.isfinite(snapshot['adjustedClose']) and snapshot['adjustedClose'] > 0, 'recovery explicit adjusted witness'
    assert evidence['rawCount'] == evidence['completedRawCount']+evidence['excludedIncompleteCount'], 'recovery raw count witness'
    assert evidence['completedRawCount'] == evidence['primaryValidCloseCount']+evidence['primaryMissingCloseCount'], 'recovery completed count witness'
    assert evidence['primaryMissingCloseCount'] == evidence['recoveredCloseCount'] == int('close' in missing), 'recovery null/recovered count witness'
    assert evidence['primaryValidCloseCount']+evidence['recoveredCloseCount'] == len(history['bars']), 'recovery output count witness'
    assert evidence['recoveredAdjustedCloseCount'] == int(config['kind'] != 'index' and 'adjustedClose' in missing and snapshot['adjustedClose'] is not None), 'recovery adjusted count witness'
    last = history['bars'][-1]
    assert last['date'] == expected and last['close'] == (snapshot['close'] if 'close' in missing else original['close']), 'recovery output close witness'
    adjusted = snapshot['adjustedClose'] if 'adjustedClose' in missing else original['adjustedClose']
    assert last['adjustedClose'] == (None if config['kind']=='index' else adjusted), 'recovery output adjusted witness'
    assert all(last.get(k) == original[k] for k in ('open','high','low')), 'recovery output primary OHLC witness'
    if args.portable_recovery:
        return
    def source(key, interval, range_=None):
        record = proof[key]
        receipt = record['rawSource']
        assert receipt and receipt['url'] == record['sourceUrl'], 'recovery raw source URL'
        assert pd.Timestamp(receipt['retrievedAt']).tzinfo is not None, 'recovery retrieval timestamp'
        requested = Path(receipt.get('path',''))
        assert not requested.is_absolute() and '..' not in requested.parts, 'recovery raw path must be relative and contained'
        resolved = (repo/requested).resolve()
        assert any(resolved.is_relative_to(base.resolve()) for base in (repo/'.cache',repo/'scripts/fixtures')), 'recovery raw path outside allowed roots'
        raw = resolved.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == receipt['sha256'], 'recovery raw source hash'
        payload = json.loads(raw)
        if receipt['format'] == 'captured-wrapper':
            assert payload['url'] == receipt['url'], 'recovery captured URL'
            payload = payload['payload']
        else:
            assert receipt['format'] == 'raw-json', 'recovery raw format'
        parsed = urlparse(receipt['url'])
        params = parse_qs(parsed.query)
        assert parsed.hostname in ('query1.finance.yahoo.com','query2.finance.yahoo.com'), 'recovery source host'
        assert unquote(parsed.path).endswith('/chart/'+config['symbol']), 'recovery source symbol'
        assert params.get('interval') == [interval], 'recovery source interval'
        if range_:
            assert params.get('range') == [range_] and params.get('includePrePost') == ['false'], 'recovery regular-hours range'
            if interval == '1wk': assert params.get('includeAdjustedClose') == ['true'], 'recovery adjusted request'
        result = payload['chart']['result'][0]
        meta = result['meta']
        assert meta['symbol'] == config['symbol'] and meta['currency'] == config['currency'], 'recovery raw identity/currency'
        assert meta['dataGranularity'] == interval, 'recovery raw granularity'
        assert result['timestamp'] == sorted(set(result['timestamp'])), 'recovery raw timestamps'
        return result
    primary = source('primary','1d')
    assert p['firstTradeTimestamp'] == primary['meta'].get('firstTradeDate') and p['exchangeTimezoneName'] == primary['meta']['exchangeTimezoneName'], 'recovery raw anchor/timezone proof'
    assert proof['primary']['sourceUrl'] == history['sourceUrl'], 'recovery primary source'
    zone = ZoneInfo(primary['meta']['exchangeTimezoneName'])
    def trade_date(stamp):
        return (datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(seconds=stamp)).astimezone(zone).date().isoformat()
    def fields(result,index):
        q = result['indicators']['quote'][0]
        a = result['indicators'].get('adjclose',[{}])[0].get('adjclose',[])
        def value(values):
            v = values[index] if index < len(values) else None
            return float(v) if v is not None and math.isfinite(float(v)) else None
        return {**{k:value(q.get(k,[])) for k in ('open','high','low','close','volume')},'adjustedClose':value(a)}
    i = len(primary['timestamp'])-1
    assert primary['timestamp'][i] == proof['primaryTimestamp'] and trade_date(primary['timestamp'][i]) == expected, 'recovery existing primary last row'
    original = fields(primary,i)
    assert proof['primaryValues'] == {k:original[k] for k in ('open','high','low','close','adjustedClose')}, 'recovery primary values'
    missing = [k for k in ('close','adjustedClose') if original[k] is None]
    assert missing and proof['primaryMissingFields'] == missing, 'recovery missing fields evidence'
    verified = {}
    for key, interval, range_ in [('minute','15m','5d'),('snapshot','1wk','1mo')]:
        result = source(key,interval,range_)
        record = proof[key]
        meta = result['meta']
        assert meta['exchangeTimezoneName'] == primary['meta']['exchangeTimezoneName'], 'recovery timezone'
        for field in ('symbol','currency','dataGranularity','regularMarketTime'):
            assert record[field] == meta[field], 'recovery raw metadata proof'
        assert record['requestedInterval'] == interval, 'recovery requested interval proof'
        stamp = closing if key == 'minute' else result['timestamp'][-1]
        assert record['timestamp'] == stamp, 'recovery raw timestamp proof'
        if key == 'snapshot':
            assert stamp == meta['regularMarketTime'] and closing <= stamp <= closing+60, 'recovery closing snapshot not weekly candle'
            assert trade_date(stamp) == expected, 'recovery snapshot trade date'
        index = result['timestamp'].index(stamp)
        values = fields(result,index)
        for field in ('open','high','low','close','adjustedClose'):
            assert record[field] == values[field], 'recovery raw value proof'
        assert values['close'] is not None and values['close'] > 0, 'recovery positive closing quote'
        verified[key] = values
    snapshot = verified['snapshot']
    assert snapshot['close'] == verified['minute']['close'], 'recovery independent close agreement'
    for field in ('open','high','low','close'):
        if original[field] is not None: assert original[field] == snapshot[field], 'recovery primary OHLC constraints'
    assert original['high'] is None or snapshot['close'] <= original['high'], 'recovery primary high'
    assert original['low'] is None or snapshot['close'] >= original['low'], 'recovery primary low'
    assert snapshot['adjustedClose'] is None or snapshot['adjustedClose'] > 0, 'recovery explicit adjusted value'
    # All lifetime rows remain daily-source rows. Only the two missing terminal
    # fields can differ; no arbitrary dates, valid-price replacement or fill.
    today = instant.tz_convert(zone).date().isoformat()
    regular_end = primary['meta']['currentTradingPeriod']['regular']['end']
    completed = [j for j,s in enumerate(primary['timestamp']) if trade_date(s) < today or
                 (trade_date(s) == today and instant.timestamp() >= regular_end+300)]
    assert len(completed) == len(history['bars']), 'recovery lifetime daily count'
    nulls = sum(fields(primary,j)['close'] is None for j in completed)
    assert evidence['rawCount'] == len(primary['timestamp']), 'recovery raw count'
    assert evidence['completedRawCount'] == len(completed), 'recovery completed raw count'
    assert evidence['primaryMissingCloseCount'] == nulls == int('close' in missing), 'recovery primary null count'
    assert evidence['primaryValidCloseCount'] == len(completed)-nulls, 'recovery valid primary count'
    assert evidence['excludedIncompleteCount'] == len(primary['timestamp'])-len(completed), 'recovery incomplete count'
    assert evidence['recoveredCloseCount'] == int('close' in missing), 'recovery recovered close count'
    assert evidence['recoveredAdjustedCloseCount'] == int(config['kind'] != 'index' and 'adjustedClose' in missing and snapshot['adjustedClose'] is not None), 'recovery recovered adjusted count'
    for bar,j in zip(history['bars'],completed):
        assert bar['date'] == trade_date(primary['timestamp'][j]), 'recovery daily dates'
        values = fields(primary,j)
        if j == i:
            for field in missing: values[field] = snapshot[field]
        if config['kind'] == 'index': values['adjustedClose'] = None
        assert all(bar.get(k) == v for k,v in values.items()), 'recovery unchanged daily values'
    anchor = primary['meta'].get('firstTradeDate')
    if anchor: assert evidence['firstTradeDate'] == trade_date(anchor), 'recovery primary first-trade anchor'
    else: assert config.get('expectedFirstDate'), 'recovery missing primary beginning anchor'


rows = []
for item in items:
    name, expected, expiry = calendar_expectations[item['country']]
    assert item.get('calendar') == name, (item['id'], 'calendar identity')
    assert item.get('expectedLastDate') == item['lastDate'] == expected, (item['id'], 'missing latest completed session')
    assert pd.Timestamp(item.get('freshUntil')).tzinfo is not None, (item['id'], 'expiry must have timezone')
    assert pd.Timestamp(item['freshUntil']) == expiry, (item['id'], 'incorrect next session expiry')
    import time
    assert pd.Timestamp(time.time(),unit='s',tz='UTC') < expiry, (item['id'], 'snapshot expired before publication')
    if item['status'] == 'unavailable':
        raise AssertionError(f"missing initial history: {item['id']}: {item.get('error')}")
    history = json.loads((root / 'history' / f"{item['id']}.json").read_text(encoding='utf-8'))
    bars = history['bars']
    if item['kind'] == 'index':
        assert all(b.get('adjustedClose') is None for b in bars), (item['id'], 'price index adjustedClose must be null')
        assert all(v is None for v in item['returns']['total'].values()), (item['id'], 'price index total returns must be null')
        assert item['cashYield'] is None, (item['id'], 'price index cashYield must be null')
        assert history['dividends'] is None, (item['id'], 'price index dividends must be null')
        assert item['dividendStatus'] == 'unavailable', (item['id'], 'price index distribution status')
    assert not history.get('priceComparisonUnavailable'), (item['id'], 'unverified split basis prevents valid rankings')
    assert len(bars) == item['count'] > 0
    assert history['id'] == item['id']
    dates = [b['date'] for b in bars]
    assert dates == sorted(set(dates)), item['id']
    assert (dates[0], dates[-1]) == (item['firstDate'], item['lastDate'])
    assert history['coverage']['count'] == len(bars)
    assert history['coverage']['complete'], (item['id'], 'incomplete full-history coverage', history['coverage'])
    assert (history['coverage']['firstDate'],history['coverage']['lastDate']) == (dates[0],dates[-1]), (item['id'], 'coverage date evidence')
    if item['id'] in configs:
        from urllib.parse import urlparse, parse_qs, unquote
        config = configs[item['id']]
        evidence = history.get('providerEvidence', {})
        assert evidence.get('uniqueCompletedCount') == len(bars), (item['id'], 'completed provider count evidence')
        assert isinstance(evidence.get('rawCount'), int) and evidence['rawCount'] >= len(bars), (item['id'], 'raw provider count evidence')
        source = urlparse(history['sourceUrl'])
        assert item['sourceUrl'] == history['sourceUrl'], (item['id'], 'source URL evidence')
        params = parse_qs(source.query)
        anchor = config.get('expectedFirstDate')
        if config['provider'] == 'yahoo':
            assert evidence.get('provider') == 'Yahoo Finance', (item['id'], 'provider evidence')
            assert evidence.get('symbol') == config['symbol'] and evidence.get('currency') == config['currency'], (item['id'], 'identity/currency evidence')
            assert evidence.get('dataGranularity') == evidence.get('requestedInterval') == '1d', (item['id'], 'daily granularity evidence')
            assert source.hostname in ('query1.finance.yahoo.com','query2.finance.yahoo.com') and unquote(source.path).endswith('/chart/'+config['symbol']), (item['id'], 'source identity evidence')
            assert params.get('interval') == ['1d'] and params.get('period1') == [str(-2208988800 if config['kind']=='index' else 0)], (item['id'], 'full daily request evidence')
            if anchor:
                assert evidence.get('expectedFirstDate') == anchor and evidence.get('firstDateBasis') == 'universe.expectedFirstDate', (item['id'], 'configured beginning evidence')
            else:
                anchor = evidence.get('firstTradeDate')
                assert anchor and evidence.get('firstDateBasis') == 'Yahoo meta.firstTradeDate', (item['id'], 'missing beginning-of-history evidence')
            if evidence.get('latestClosingRecovery'):
                closing = int(xc.get_calendar(name).session_close(pd.Timestamp(expected)).timestamp())
                audit_closing_recovery(history,config,expected,closing,instant)
            else:
                assert not evidence.get('recoveredCloseCount') and not evidence.get('recoveredAdjustedCloseCount'), (item['id'], 'recovery proof missing')
        elif evidence.get('provider') == 'Eastmoney':
            assert evidence.get('declaredCount') == evidence['rawCount'], (item['id'], 'declared provider count evidence')
            assert source.hostname == 'push2his.eastmoney.com' and params.get('secid') == [config['secid']] and params.get('klt') == ['101'] and params.get('fqt') == ['0'], (item['id'], 'daily nominal source evidence')
        else:
            assert evidence.get('provider') == 'Tencent', (item['id'], 'provider evidence')
            pages = evidence.get('annualPages', [])
            assert [p['year'] for p in pages] == list(range(1990,instant.year+1)), (item['id'], 'annual lifetime evidence')
            assert sum(p['count'] for p in pages) == evidence['rawCount'], (item['id'], 'annual provider count evidence')
        if anchor:
            assert 0 <= (date.fromisoformat(dates[0])-date.fromisoformat(anchor)).days <= 10, (item['id'], 'truncated beginning', anchor, dates[0])
    assert all(math.isfinite(b['close']) and b['close'] > 0 for b in bars)
    if history['adjustment'] == 'split-normalized-price':
        for bar in bars:
            factor = math.prod(s['ratio'] for s in history['splits'] if s['effectiveDate'] > bar['date'])
            assert math.isclose(bar['close'], bar['rawClose'] / factor, rel_tol=1e-8), (item['id'], 'split normalization', bar['date'])
        for event in history['dividends'] or []:
            factor = math.prod(s['ratio'] for s in history['splits'] if s['effectiveDate'] > event['date'])
            assert math.isclose(event['amount'], event.get('rawAmount', event['amount']) / factor, rel_tol=1e-8), (item['id'], 'distribution share basis')
    assert math.isclose(item['close'], bars[-1]['close'], rel_tol=1e-8)
    counts[item['country']] += 1
    last = date.fromisoformat(dates[-1])
    for mode, field in [('price', 'close'), ('total', 'adjustedClose')]:
        for period, months in [('1m', 1), ('3m', 3), ('6m', 6), ('1y', 12), ('3y', 36), ('5y', 60), ('10y', 120)]:
            n = last.year * 12 + last.month - 1 - months
            y, m = divmod(n, 12)
            target = date(y, m + 1, min(last.day, calendar.monthrange(y, m + 1)[1]))
            eligible = [b for b in bars if target - timedelta(days=10) <= date.fromisoformat(b['date']) <= target]
            actual = item['returns'][mode][period]
            start = eligible[-1].get(field) if eligible else None
            end = bars[-1].get(field)
            expected = end / start - 1 if start and end else None
            assert (actual is None) == (expected is None), (item['id'], mode, period, actual, expected)
            if expected is not None:
                assert math.isclose(actual, expected, rel_tol=1e-5, abs_tol=1e-6), (item['id'], mode, period, actual, expected)
    assert item['frankingRate'] is None or 0 <= item['frankingRate'] <= 1
    if item['cashYield'] is not None:
        n = last.year * 12 + last.month - 1 - 12
        y, m = divmod(n, 12)
        cutoff = date(y, m + 1, min(last.day, calendar.monthrange(y, m + 1)[1]))
        amount = sum(d['amount'] for d in history['dividends'] if cutoff < date.fromisoformat(d['date']) <= last)
        assert math.isclose(item['cashYield'], amount / item['close'], rel_tol=1e-5, abs_tol=1e-6), item['id']
    rows.append({'id': item['id'], 'symbol': item['symbol'], 'country': item['country'], 'kind': item['kind'], 'bars':len(bars), 'first':dates[0], 'last':dates[-1], 'dividends':len(history['dividends']) if history['dividends'] is not None else None, 'coverage':history['coverage'], 'status':item['status']})
print(json.dumps({'audit':'PASS','auditMode':'portable-recovery-witness' if args.portable_recovery else 'strict-local-raw','rawBytesVerified':not args.portable_recovery,'verificationBoundary':'Public witnesses and downloaded histories only; unavailable original raw bytes NOT authenticated' if args.portable_recovery else 'Local recovery original bytes hash-verified; full daily values reconciled','generatedAt':market['generatedAt'],'count':len(items),'countries':dict(counts),'dailyBars':sum(r['bars'] for r in rows),'failures':market.get('failures'), 'instruments': rows}, ensure_ascii=False, indent=2))
