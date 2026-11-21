"""ETF Atlas: audited daily market data, never synthetic histories."""
import calendar
import datetime as dt
import math
import time
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
PERIODS = {'1m':1,'3m':3,'6m':6,'1y':12,'3y':36,'5y':60,'10y':120}

def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None

def timestamp_datetime(stamp, zone=UTC):
    # Arithmetic epoch conversion supports negative UNIX timestamps on Windows.
    return (dt.datetime(1970,1,1,tzinfo=UTC)+dt.timedelta(seconds=stamp)).astimezone(zone)

def iso_time(now=None):
    return dt.datetime.fromtimestamp(now if now is not None else time.time(), UTC).isoformat().replace('+00:00','Z')

def parse_cn_dividends(html):
    import re
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html,'html.parser')
    for table in soup.select('table'):
        text = table.get_text(' ',strip=True)
        if not all(label in text for label in ('权益登记日','除息日','每10份分红')):
            continue
        if '暂无分红' in text:
            return []
        events = {}
        for row in table.select('tr'):
            cells = [cell.get_text(' ',strip=True) for cell in row.select('td')]
            if not cells or not re.fullmatch(r'\d{4}年?',cells[0]):
                continue
            if len(cells) != 5:
                raise ValueError('Unrecognized distribution table row')
            date = dt.date.fromisoformat(cells[2]).isoformat()
            match = re.search(r'每10份派现金\s*([\d.]+)\s*元',cells[3])
            if not match:
                raise ValueError(f'Unrecognized distribution amount: {cells[3]}')
            amount = number(match.group(1))
            if amount is None or amount < 0:
                raise ValueError('Invalid distribution amount')
            if date in events:
                raise ValueError('Duplicate ex-date distribution')
            events[date] = {'date':date,'amount':round(amount/10,10)}
        if not events:
            raise ValueError('Distribution table found without validated rows or explicit no-dividends statement')
        return sorted(events.values(),key=lambda e:e['date'])
    raise ValueError('Distribution table missing')

def parse_cn_splits(html):
    import re
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html,'html.parser')
    for table in soup.select('table'):
        text = table.get_text(' ',strip=True)
        if '拆分折算日' not in text or '拆分折算比例' not in text:
            continue
        if '暂无拆分' in text: return []
        events = []
        for row in table.select('tr'):
            cells = [c.get_text(' ',strip=True) for c in row.select('td')]
            if not cells or not re.fullmatch(r'\d{4}年?',cells[0]): continue
            if len(cells) != 4: raise ValueError('Unrecognized split row')
            date = dt.date.fromisoformat(cells[1]).isoformat()
            match = re.fullmatch(r'([\d.]+)\s*[:：]\s*([\d.]+)',cells[3])
            if not match: raise ValueError('Unrecognized split ratio')
            denominator,numerator = [number(v) for v in match.groups()]
            if not denominator or not numerator or numerator <= 0 or denominator <= 0:
                raise ValueError('Invalid split ratio')
            events.append({'date':date,'ratio':numerator/denominator})
        if not events: raise ValueError('Split table empty without explicit statement')
        if len({e['date'] for e in events}) != len(events): raise ValueError('Duplicate splits')
        return sorted(events,key=lambda e:e['date'])
    raise ValueError('Split table missing')


def normalize_cn_splits(history, splits):
    bars = history['bars']
    active = []
    for split in splits:
        if not bars[0]['date'] < split['date'] <= bars[-1]['date']: continue
        # F10 fold dates can be after that day's close. Match the share-ratio
        # discontinuity at the listed session or immediately following session.
        candidate_indices = [i for i,b in enumerate(bars) if b['date'] >= split['date']][:2]
        candidates = []
        for i in candidate_indices:
            if i == 0: continue
            ratio_return = bars[i]['close']/bars[i-1]['close']*split['ratio']
            candidates.append((abs(math.log(ratio_return)),i))
        if not candidates: raise ValueError('Split effective session cannot be established')
        residual,index = min(candidates)
        raw_residual = abs(math.log(bars[index]['close']/bars[index-1]['close']))
        # A normal terminal session is not evidence of a small after-close
        # fold. Require normalization to explain the discontinuity materially
        # better than leaving the nominal prices alone. Defer without mutation.
        if residual >= raw_residual / 2:
            history.update(splits=[],adjustment='none',priceAdjustment='none',
                           priceComparisonUnavailable=True,
                           splitError='Ambiguous fold: awaiting effective-session discontinuity')
            for bar in bars:
                for key in ('open','high','low','close'):
                    if bar.get(key) is not None:
                        bar['raw'+key.capitalize()] = bar[key]
            return history
        if residual > math.log(1.20):
            raise ValueError('Split ratio inconsistent with trading-price discontinuity')
        active.append({**split,'effectiveDate':bars[index]['date'],
                       'effectiveDateBasis':'ratio-matched provider daily discontinuity'})
    history['splits'] = active
    history['priceAdjustment'] = 'split-normalized' if active else 'none'
    history['adjustment'] = 'split-normalized-price' if active else 'none'
    for bar in bars:
        factor = math.prod(s['ratio'] for s in active if s['effectiveDate'] > bar['date'])
        for key in ('open','high','low','close'):
            if bar.get(key) is not None:
                bar['raw'+key.capitalize()] = bar[key]
                bar[key] /= factor
    for event in history.get('dividends') or []:
        factor = math.prod(s['ratio'] for s in active if s['effectiveDate'] > event['date'])
        if factor != 1:
            event['rawAmount'] = event['amount']
            event['amount'] /= factor
    # This normalizes share counts only; it never reinvests distributions.
    return history


def parse_cn_rows(rows, instrument_id, url, now=None):
    now = time.time() if now is None else now
    local = dt.datetime.fromtimestamp(now,ZoneInfo('Asia/Shanghai'))
    today = local.date().isoformat()
    bars = {}
    for row in rows:
        if row[0] > today or (row[0] == today and (local.hour,local.minute) < (15,5)):
            continue
        values = [number(v) for v in row[1:6]]
        if values[1] is None or values[1] <= 0:
            raise ValueError('Invalid CN close')
        bars[row[0]] = dict(zip(('open','close','high','low','volume'),values),date=row[0],adjustedClose=None)
    return {'id':instrument_id,'sourceUrl':url,'retrievedAt':iso_time(now),'adjustment':'none','bars':sorted(bars.values(),key=lambda b:b['date']),'dividends':None,'splits':[]}

def parse_eastmoney(payload, instrument_id, url, now=None):
    data = payload.get('data')
    if not data or not data.get('klines'):
        raise ValueError('Eastmoney returned no data')
    rows = data['klines']
    if data.get('dktotal') and len(rows) != int(data['dktotal']):
        raise ValueError(f"Eastmoney truncated: {len(rows)}/{data['dktotal']}")
    return parse_cn_rows([r.split(',') for r in rows],instrument_id,url,now)

def parse_tencent(payload, symbol, instrument_id, url, now=None):
    if payload.get('code') != 0:
        raise ValueError('Tencent error')
    rows = payload.get('data',{}).get(symbol,{}).get('day')
    if rows is None:
        raise ValueError('Tencent missing unadjusted day series')
    return parse_cn_rows(rows,instrument_id,url,now)

def validate_history(history, config, expected_count=None, first_trade=None):
    bars = history['bars']
    if not bars:
        raise ValueError('Empty history')
    dates = [dt.date.fromisoformat(bar['date']) for bar in bars]
    if dates != sorted(set(dates)):
        raise ValueError('Daily dates must be ascending and unique')
    for bar in bars:
        if number(bar['close']) is None or bar['close'] <= 0:
            raise ValueError('Nonfinite/nonpositive close')
        for key in ('open','high','low','adjustedClose','volume'):
            if bar.get(key) is not None and number(bar[key]) is None:
                raise ValueError(f'Nonfinite {key}')
        if bar.get('adjustedClose') is not None and bar['adjustedClose'] <= 0:
            raise ValueError('Nonpositive adjusted close')
    span = (dates[-1]-dates[0]).days
    if span > 365 and len(bars)/span*365.25 < 180:
        raise ValueError('Not a full daily series (weekly/monthly or missing years)')
    gaps = [(b-a).days for a,b in zip(dates,dates[1:])]
    if gaps and max(gaps) > config.get('maxGapDays',30):
        raise ValueError(f'Unexpected daily gap: {max(gaps)} days')
    expected_first = config.get('expectedFirstDate') or first_trade or history.get('providerEvidence',{}).get('firstTradeDate')
    if config.get('provider') == 'yahoo' and not expected_first:
        raise ValueError('Yahoo missing beginning-of-history evidence')
    if expected_first and (dates[0]-dt.date.fromisoformat(expected_first)).days > 10:
        raise ValueError(f"Truncated beginning {dates[0]}, expected {expected_first}")
    if expected_count is not None and len(bars) != expected_count:
        raise ValueError(f'Provider count mismatch: {len(bars)}/{expected_count}')
    if config['kind'] == 'index':
        # A price index adjclose often equals close; this is NOT total return.
        history['adjustment'] = 'none'
        history['dividends'] = None
        for bar in bars:
            bar['adjustedClose'] = None
    events = history.get('dividends')
    if events is not None:
        event_dates = [e['date'] for e in events]
        if event_dates != sorted(set(event_dates)):
            raise ValueError('Dividend ex-dates must be unique and ascending')
        for event in events:
            dt.date.fromisoformat(event['date'])
            if number(event['amount']) is None or event['amount'] < 0:
                raise ValueError('Invalid dividend')
    history['coverage'] = {'firstDate':dates[0].isoformat(),'lastDate':dates[-1].isoformat(),'count':len(bars),'complete':True,
        'reason':'Complete available provider daily history; inception/backtest dates may differ from provider first availability.'}
    return history

def shift_months(date, months):
    index = date.year * 12 + date.month - 1 - months
    year, month = divmod(index,12)
    month += 1
    return dt.date(year,month,min(date.day,calendar.monthrange(year,month)[1]))

def session_freshness(country, now=None):
    """Actual exchange closes plus five minutes; no weekday/age fallback.

    XNYS is the US equity-market calendar proxy, including Nasdaq listings.
    XSHG's published holiday coverage is bounded by exchange-calendars; a
    missing next session or unsupported year fails closed rather than guessing.
    """
    import exchange_calendars as xc
    import pandas as pd
    instant = pd.Timestamp(iso_time(now))
    name = {'CN':'XSHG','US':'XNYS','AU':'XASX'}[country]
    try:
        bound = xc.get_calendar(name).bound_max()
        end = pd.Timestamp(f'{instant.year+1}-12-31')
        if bound is not None:
            end = min(end, bound)
        cal = xc.get_calendar(name, start=f'{instant.year-1}-01-01', end=end)
        boundaries = cal.schedule['close'] + pd.Timedelta(minutes=5)
        completed = boundaries[boundaries <= instant]
        future = boundaries[boundaries > instant]
        if completed.empty or future.empty:
            raise ValueError('Calendar lacks completed/next session coverage')
        return {'calendar':name,'expectedLastDate':completed.index[-1].date().isoformat(),
                'freshUntil':future.iloc[0].isoformat().replace('+00:00','Z')}
    except Exception as exc:
        raise ValueError(f'{name} exchange calendar unavailable: {exc}') from exc


def summarize(config, history, now=None):
    bars = history['bars']
    if not bars:
        raise ValueError('No completed daily prices')
    first,last = bars[0]['date'],bars[-1]['date']
    end = dt.date.fromisoformat(last)
    returns = {'price':{},'total':{}}
    for period,months in PERIODS.items():
        target = shift_months(end,months)
        candidates = [b for b in bars if b['date'] <= target.isoformat()]
        base = candidates[-1] if candidates else None
        if base and (target-dt.date.fromisoformat(base['date'])).days > 10:
            base = None
        for label,column in [('price','close'),('total','adjustedClose')]:
            start = base.get(column) if base else None
            finish = bars[-1].get(column)
            returns[label][period] = finish/start - 1 if start and finish else None
    unverified_actions = history.get('priceComparisonUnavailable',False)
    if unverified_actions:
        returns['price'] = {period:None for period in PERIODS}
    dividends = history.get('dividends')
    enough = first <= shift_months(end,12).isoformat()
    cash = None
    if dividends is not None and enough and config['kind'] == 'etf' and not unverified_actions:
        cash = sum(e['amount'] for e in dividends if shift_months(end,12).isoformat() < e['date'] <= last)/bars[-1]['close']
    freshness = session_freshness(config['country'],now)
    status = 'fresh' if last == freshness['expectedLastDate'] else 'stale'
    if status != 'fresh' and 'coverage' in history:
        history['coverage'].update(complete=False,reason=f"Missing latest completed session {freshness['expectedLastDate']}")
    return {**{key:config[key] for key in ('id','symbol','name','country','kind','benchmark','currency')},
            **{key:config[key] for key in ('issuerUrl','frequency') if key in config},
            'sourceUrl':history['sourceUrl'],'historyUrl':f"data/history/{config['id']}.json",
            'firstDate':first,'lastDate':last,'count':len(bars),'status':status,**freshness,
            'close':bars[-1]['close'],'dailyChange':bars[-1]['close']/bars[-2]['close']-1 if len(bars)>1 and not unverified_actions else None,
            'priceComparisonUnavailable':unverified_actions,
            **{key:history[key] for key in ('dividendSourceUrl','splitSourceUrl','dividendError','splitError') if key in history},
            'cashYield':cash,'dividendStatus':'unavailable' if dividends is None else ('available' if dividends else 'no-distributions'),
            'frankingRate':None,'returns':returns}

def parse_yahoo(payload, instrument_id, url, now=None):
    now = time.time() if now is None else now
    results = payload.get('chart',{}).get('result')
    if not results:
        raise ValueError(f"Yahoo chart error: {payload.get('chart',{}).get('error')}")
    result = results[0]
    meta = result['meta']
    zone = ZoneInfo(meta.get('exchangeTimezoneName','UTC'))
    today = dt.datetime.fromtimestamp(now,zone).date()
    session_end = meta.get('currentTradingPeriod',{}).get('regular',{}).get('end',math.inf)
    quote = result['indicators']['quote'][0]
    adj = result['indicators'].get('adjclose',[{}])[0].get('adjclose',[])
    bars = {}
    for i, stamp in enumerate(result.get('timestamp',[])):
        date = timestamp_datetime(stamp,zone).date()
        if date > today or (date == today and now < session_end + 300):
            continue
        close = number(quote.get('close',[])[i])
        if close is None or close <= 0:
            continue
        bar = {'date':date.isoformat(),'close':close}
        for key in ('open','high','low','volume'):
            values = quote.get(key,[])
            bar[key] = number(values[i]) if i < len(values) else None
        bar['adjustedClose'] = number(adj[i]) if i < len(adj) else None
        bars[bar['date']] = bar
    events = result.get('events',{})
    dividends = []
    splits = []
    for event in events.get('dividends',{}).values():
        date = timestamp_datetime(event['date'],zone).date()
        amount = number(event.get('amount'))
        if date <= today and amount is not None:
            dividends.append({'date':date.isoformat(),'amount':amount})
    for event in events.get('splits',{}).values():
        date = timestamp_datetime(event['date'],zone).date()
        denominator = number(event.get('denominator'))
        numerator = number(event.get('numerator'))
        if date <= today and numerator and denominator:
            splits.append({'date':date.isoformat(),'ratio':numerator/denominator})
    return {'id':instrument_id,'sourceUrl':url,'retrievedAt':iso_time(now),'adjustment':'provider-adjusted-close' if adj else 'none','bars':sorted(bars.values(),key=lambda b:b['date']),'dividends':sorted(dividends,key=lambda b:b['date']),'splits':sorted(splits,key=lambda b:b['date'])}


def atomic_json(path, value):
    import json
    import os
    import tempfile
    from pathlib import Path
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    body = json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')) + '\n'
    fd,name = tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


class HTTPClient:
    """Bounded retries, raw evidence cache; failed fetches never masquerade as live."""
    def __init__(self, cache, retries=2, timeout=25, session=None, max_entries=2000):
        import requests
        from pathlib import Path
        self.cache = Path(cache)
        self.cache.mkdir(parents=True,exist_ok=True)
        self.max_entries = max_entries
        self.retries = retries
        self.timeout = timeout
        self.session = session or requests.Session()
        self.last_request = 0
        self.session.headers.update({'User-Agent':'Mozilla/5.0','Accept':'application/json,text/html,*/*'})

    def cache_key(self,url,params=None):
        import hashlib
        import json
        stable = {k:v for k,v in (params or {}).items() if k!='period2'}
        return hashlib.sha256((url+'?'+json.dumps(stable,sort_keys=True)).encode()).hexdigest()

    def get_json_cached(self,url,params=None):
        import hashlib
        import json
        key = self.cache_key(url,params)
        try:
            raw = (self.cache/(key+'.raw')).read_bytes()
            meta = json.loads((self.cache/(key+'.meta.json')).read_text(encoding='utf-8'))
            if hashlib.sha256(raw).hexdigest() != meta['sha256']: raise ValueError('Corrupt raw cache')
            return json.loads(raw)
        except (OSError,ValueError,KeyError):
            return self.get_json(url,params)

    def prune(self):
        files = sorted(self.cache.glob('*.raw'),key=lambda p:p.stat().st_mtime,reverse=True)
        for path in files[self.max_entries:]:
            path.unlink(missing_ok=True)
            path.with_suffix('.meta.json').unlink(missing_ok=True)

    def _get(self,url,params=None):
        import hashlib
        import json
        import random
        import requests
        error = None
        for attempt in range(self.retries):
            delay = 0.12 - (time.monotonic()-self.last_request)
            if delay > 0: time.sleep(delay)
            self.last_request = time.monotonic()
            try:
                response = self.session.get(url,params=params,timeout=self.timeout)
                response.raise_for_status()
                digest = hashlib.sha256(response.content).hexdigest()
                key = self.cache_key(url,params)
                # Save exact bytes and fetch evidence for reproducibility, not generated fixtures.
                (self.cache/(key+'.raw')).write_bytes(response.content)
                atomic_json(self.cache/(key+'.meta.json'),{'url':response.url,'retrievedAt':iso_time(),'sha256':digest})
                raw_path = (self.cache/(key+'.raw')).resolve()
                repo = __import__('pathlib').Path(__file__).resolve().parents[1]
                self.last_receipt = {'path':raw_path.relative_to(repo).as_posix() if raw_path.is_relative_to(repo) else None,'sha256':digest,
                    'url':response.url,'retrievedAt':iso_time(),'format':'raw-json'}
                self.prune()
                return response
            except (requests.RequestException,ValueError) as exc:
                error = exc
                if attempt+1 < self.retries: time.sleep(0.4*2**attempt+random.random()*0.2)
        raise ValueError(f'{url}: {error}')

    def get_json(self,url,params=None):
        return self._get(url,params).json()

    def get_text(self,url):
        return self._get(url).content


def fetch_tencent(config, client, now=None):
    now = time.time() if now is None else now
    url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
    rows = {}
    pages = []
    for year in range(1990,dt.datetime.fromtimestamp(now,UTC).year+1):
        params = {'param':f"{config['tencent']},day,{year}-01-01,{year}-12-31,640,"}
        get = client.get_json_cached if year < dt.datetime.fromtimestamp(now,UTC).year and hasattr(client,'get_json_cached') else client.get_json
        payload = get(url,params)
        data = payload.get('data',{}).get(config['tencent'],{})
        if payload.get('code') != 0 or 'day' not in data:
            raise ValueError(f'Tencent missing annual series {year}')
        page = data['day']
        if len(page) >= 640:
            raise ValueError('Tencent annual cap reached unexpectedly')
        for row in page:
            if not row[0].startswith(str(year)):
                raise ValueError('Tencent ignored annual range')
            if row[0] in rows:
                raise ValueError('Tencent duplicate daily row')
            rows[row[0]] = row
        pages.append({'year':year,'count':len(page)})
    history = parse_cn_rows(sorted(rows.values()),config['id'],url+'?param='+config['tencent']+',day,1990-01-01,,640,',now)
    history['providerEvidence'] = {'provider':'Tencent','annualPages':pages,'rawCount':len(rows),'uniqueCompletedCount':len(history['bars'])}
    return validate_history(history,config)


def recover_yahoo_closing(payload, history, config, client, url, now, primary_receipt=None):
    """Recover only an existing last daily row, never resample weekly history."""
    import copy
    from urllib.parse import urlencode
    result = payload['chart']['result'][0]
    zone = ZoneInfo(result['meta'].get('exchangeTimezoneName','UTC'))
    expected = session_freshness(config['country'],now)['expectedLastDate']
    stamps = result.get('timestamp',[])
    if not stamps or timestamp_datetime(stamps[-1],zone).date().isoformat() != expected:
        return history
    i = len(stamps)-1
    quote = result['indicators']['quote'][0]
    adj = result['indicators'].get('adjclose',[{}])[0].get('adjclose',[])
    primary = {k:number(quote.get(k,[])[i]) if i < len(quote.get(k,[])) else None for k in ('open','high','low','close')}
    primary['adjustedClose'] = number(adj[i]) if i < len(adj) else None
    missing = [k for k in ('close','adjustedClose') if primary[k] is None]
    if not missing:
        return history
    if sum(timestamp_datetime(s,zone).date().isoformat() == expected for s in stamps) != 1:
        raise ValueError('Closing recovery ambiguous duplicate primary date; never replace valid daily price')
    import exchange_calendars as xc
    import pandas as pd
    cal = xc.get_calendar({'US':'XNYS','AU':'XASX','CN':'XSHG'}[config['country']])
    closing = int(cal.session_close(pd.Timestamp(expected)).timestamp())
    sources = {}
    for kind, interval, range_ in [('minute','15m','5d'),('snapshot','1wk','1mo')]:
        params = {'range':range_,'interval':interval,'includePrePost':'false'}
        if interval == '1wk': params.update(events='div,splits',includeAdjustedClose='true')
        secondary = client.get_json(url,params)['chart']['result'][0]
        meta = secondary['meta']
        if meta.get('symbol') != config['symbol'] or meta.get('currency') != config['currency']:
            raise ValueError('Closing recovery identity/currency mismatch')
        if meta.get('dataGranularity') != interval:
            raise ValueError('Closing recovery granularity mismatch')
        if meta.get('exchangeTimezoneName') != result['meta'].get('exchangeTimezoneName'):
            raise ValueError('Closing recovery exchange timezone mismatch')
        secondary_stamps = secondary['timestamp']
        if secondary_stamps != sorted(set(secondary_stamps)):
            raise ValueError('Closing recovery duplicate/unordered timestamps')
        if kind == 'snapshot':
            stamp = secondary_stamps[-1]
            if stamp != meta.get('regularMarketTime') or not closing <= stamp <= closing+60:
                raise ValueError('Closing recovery is not a current-day closing snapshot')
            if timestamp_datetime(stamp,zone).date().isoformat() != expected:
                raise ValueError('Closing recovery wrong trade date')
        index = secondary_stamps.index(closing) if kind == 'minute' else len(secondary_stamps)-1
        q = secondary['indicators']['quote'][0]
        a = secondary['indicators'].get('adjclose',[{}])[0].get('adjclose',[])
        sources[kind] = {'sourceUrl':url+'?'+urlencode(params),'symbol':secondary['meta'].get('symbol'),
            'currency':secondary['meta'].get('currency'),'dataGranularity':secondary['meta'].get('dataGranularity'),
            'requestedInterval':interval,'timestamp':secondary['timestamp'][index],
            'regularMarketTime':secondary['meta'].get('regularMarketTime'),
            'close':number(q['close'][index]),'adjustedClose':number(a[index]) if index < len(a) else None,
            'rawSource':getattr(client,'last_receipt',None),
            **{k:number(q.get(k,[])[index]) if index < len(q.get(k,[])) else None for k in ('open','high','low')}}
    snapshot = sources['snapshot']
    close = snapshot['close']
    if close is None or close <= 0 or sources['minute']['close'] is None or sources['minute']['close'] <= 0:
        raise ValueError('Closing recovery nonpositive/missing close')
    if close != sources['minute']['close']:
        raise ValueError('Closing recovery minute/snapshot close mismatch')
    if primary['close'] is not None and primary['close'] != close:
        raise ValueError('Closing recovery disagrees with valid daily close')
    if primary['high'] is not None and close > primary['high'] or primary['low'] is not None and close < primary['low']:
        raise ValueError('Closing recovery outside primary OHLC range')
    for key in ('open','high','low'):
        if primary[key] is not None and primary[key] != snapshot[key]:
            raise ValueError('Closing recovery snapshot/primary OHLC mismatch')
    if snapshot['adjustedClose'] is not None and snapshot['adjustedClose'] <= 0:
        raise ValueError('Closing recovery invalid explicit adjusted close')
    repaired = copy.deepcopy(payload)
    target = repaired['chart']['result'][0]['indicators']
    if 'close' in missing: target['quote'][0]['close'][i] = snapshot['close']
    if 'adjustedClose' in missing and snapshot['adjustedClose'] is not None:
        values = target.setdefault('adjclose',[{'adjclose':[]}])[0].setdefault('adjclose',[])
        values.extend([None]*(i+1-len(values)))
        values[i] = snapshot['adjustedClose']
    recovered = parse_yahoo(repaired,config['id'],history['sourceUrl'],now)
    recovered['providerEvidence'] = history['providerEvidence']
    recovered['providerEvidence'].update(uniqueCompletedCount=len(recovered['bars']),
        recoveredCloseCount=int('close' in missing),recoveredAdjustedCloseCount=int(config['kind'] != 'index' and 'adjustedClose' in missing and snapshot['adjustedClose'] is not None),
        latestClosingRecovery={'date':expected,'sessionCloseTimestamp':closing,'primaryTimestamp':stamps[i],
            'primaryMissingFields':missing,'primaryValues':primary,
            'primary':{'sourceUrl':history['sourceUrl'],'rawSource':primary_receipt,
                'symbol':result['meta']['symbol'],'currency':result['meta']['currency'],
                'dataGranularity':'1d','requestedInterval':'1d',
                'exchangeTimezoneName':result['meta']['exchangeTimezoneName'],
                'firstTradeTimestamp':result['meta'].get('firstTradeDate'),'rowIndex':i},**sources})
    return recovered


def fetch_history(config, client, now=None):
    from urllib.parse import quote
    now = time.time() if now is None else now
    errors = []
    if config['provider'] == 'yahoo':
        params = {'period1':-2208988800 if config['kind']=='index' else 0,'period2':int(now),'interval':'1d','events':'div,splits','includeAdjustedClose':'true'}
        hosts = ['query1','query2'] if config['country']=='AU' else ['query2','query1']
        for host in hosts:
            url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{quote(config['symbol'],safe='')}"
            try:
                payload = client.get_json(url,params)
                primary_receipt = getattr(client,'last_receipt',None)
                result = payload.get('chart',{}).get('result')
                if not result: raise ValueError(str(payload.get('chart',{}).get('error')))
                meta = result[0]['meta']
                if meta.get('symbol') != config['symbol']:
                    raise ValueError('Yahoo symbol mismatch')
                if meta.get('dataGranularity') != '1d':
                    raise ValueError('Yahoo returned non-daily granularity')
                if meta.get('currency') != config['currency']:
                    raise ValueError('Yahoo missing or mismatched listing currency')
                history = parse_yahoo(payload,config['id'],url+'?'+__import__('urllib.parse',fromlist=['urlencode']).urlencode(params),now)
                first_trade = timestamp_datetime(meta['firstTradeDate'],ZoneInfo(meta.get('exchangeTimezoneName','UTC'))).date().isoformat() if meta.get('firstTradeDate') else None
                if not first_trade and not config.get('expectedFirstDate'):
                    raise ValueError('Yahoo missing beginning-of-history evidence')
                history['providerEvidence'] = {'provider':'Yahoo Finance','symbol':meta['symbol'],
                    'dataGranularity':meta['dataGranularity'],'currency':meta['currency'],'requestedInterval':'1d',
                    'firstTradeDate':first_trade,'expectedFirstDate':config.get('expectedFirstDate'),
                    'firstDateBasis':'universe.expectedFirstDate' if config.get('expectedFirstDate') else 'Yahoo meta.firstTradeDate',
                    'rawCount':len(result[0].get('timestamp',[])),'uniqueCompletedCount':len(history['bars'])}
                raw_stamps = result[0].get('timestamp',[])
                raw_quote = result[0]['indicators']['quote'][0].get('close',[])
                zone = ZoneInfo(meta.get('exchangeTimezoneName','UTC'))
                today = timestamp_datetime(now,zone).date()
                end = meta.get('currentTradingPeriod',{}).get('regular',{}).get('end',math.inf)
                completed = [i for i,s in enumerate(raw_stamps) if timestamp_datetime(s,zone).date() < today or
                    (timestamp_datetime(s,zone).date() == today and now >= end+300)]
                missing_closes = [i for i in completed if i >= len(raw_quote) or number(raw_quote[i]) is None]
                raw_fields = result[0]['indicators']['quote'][0]
                empty_rows = [i for i in missing_closes if all(i >= len(raw_fields.get(k,[])) or raw_fields[k][i] is None for k in ('open','high','low','close','volume'))]
                if any(i != len(raw_stamps)-1 and i not in empty_rows for i in missing_closes):
                    raise ValueError('Yahoo missing historical close; only latest closing fields recoverable')
                history['providerEvidence'].update(completedRawCount=len(completed),
                    duplicateCompletedDateCount=len(completed)-len({timestamp_datetime(raw_stamps[i],zone).date() for i in completed}),historicalEmptyRowCount=sum(i != len(raw_stamps)-1 for i in empty_rows),
                    primaryValidCloseCount=len(completed)-len(missing_closes),primaryMissingCloseCount=len(missing_closes),
                    excludedIncompleteCount=len(raw_stamps)-len(completed),recoveredCloseCount=0,recoveredAdjustedCloseCount=0)
                validate_history(history,config,first_trade=first_trade)
                history = recover_yahoo_closing(payload,history,config,client,url,now,primary_receipt)
                return validate_history(history,config,first_trade=first_trade)
            except (ValueError,KeyError,IndexError,TypeError) as exc:
                errors.append(str(exc))
    else:
        params = {'secid':config['secid'],'klt':101,'fqt':0,'beg':19900101,'end':20500101,'lmt':100000,
            'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'}
        for scheme in ('https','http'):
            url = f'{scheme}://push2his.eastmoney.com/api/qt/stock/kline/get'
            try:
                payload = client.get_json(url,params)
                data = payload.get('data') or {}
                if data.get('code') != config['secid'].split('.')[1]:
                    raise ValueError('Eastmoney missing data or symbol mismatch')
                raw = data.get('klines') or []
                declared = int(data.get('dktotal',0))
                if not raw or not declared: raise ValueError('Eastmoney no declared history count')
                if len(raw) != declared:
                    # Provider caps: annual requests plus uniqueness reconciliation.
                    pages = {}
                    for year in range(1990,dt.datetime.fromtimestamp(now,UTC).year+1):
                        page = client.get_json(url,{**params,'beg':int(f'{year}0101'),'end':int(f'{year}1231')})
                        for row in (page.get('data') or {}).get('klines',[]):
                            if not row.startswith(str(year)): raise ValueError('Provider ignored annual range')
                            pages[row.split(',')[0]] = row
                    raw = sorted(pages.values())
                    if len(raw) != declared: raise ValueError(f'Eastmoney paginated mismatch {len(raw)}/{declared}')
                source = url+'?'+__import__('urllib.parse',fromlist=['urlencode']).urlencode(params)
                history = parse_cn_rows([row.split(',') for row in raw],config['id'],source,now)
                history['providerEvidence'] = {'provider':'Eastmoney','declaredCount':declared,'rawCount':len(raw),'uniqueCompletedCount':len(history['bars']),'transport':scheme}
                validate_history(history,config)
                break
            except (ValueError,KeyError,IndexError,TypeError) as exc:
                errors.append(str(exc))
        else:
            if config.get('tencent'):
                history = fetch_tencent(config,client,now)
            else:
                raise ValueError('; '.join(errors))
        if config['kind'] == 'etf':
            try:
                html = client.get_text(config['dividendUrl'])
            except (ValueError,KeyError,TypeError) as exc:
                html = None
                history['dividendError'] = str(exc)
            if html is not None:
                try:
                    history['dividends'] = parse_cn_dividends(html)
                    history['dividendSourceUrl'] = config['dividendUrl']
                except ValueError as exc:
                    history['dividends'] = None
                    history['dividendError'] = str(exc)
                try:
                    normalize_cn_splits(history,parse_cn_splits(html))
                    history['splitSourceUrl'] = config['dividendUrl']
                except ValueError as exc:
                    history['priceComparisonUnavailable'] = True
                    history['splitError'] = str(exc)
            else:
                history['priceComparisonUnavailable'] = True
        return validate_history(history,config)
    raise ValueError('; '.join(errors))


def build(universe, output, client, now=None):
    import json
    from pathlib import Path
    now = time.time() if now is None else now
    output = Path(output)
    instruments,failures = [],[]
    for config in universe:
        path = output/'history'/f"{config['id']}.json"
        try:
            history = fetch_history(config,client,now)
            item = summarize(config,history,now)
            if history.get('priceComparisonUnavailable'):
                raise ValueError('Unverified split evidence: price comparisons unavailable')
            if item['status'] != 'fresh':
                raise ValueError(f"Latest completed close is stale: {item['lastDate']}")
            atomic_json(path,history)
            instruments.append(item)
            print(f"OK {item['id']} {item['count']} {item['firstDate']}..{item['lastDate']} div={item['dividendStatus']} yield={item['cashYield']}",flush=True)
        except Exception as exc:
            error = str(exc)
            failures.append({'id':config['id'],'error':error})
            try:
                old = json.loads(path.read_text(encoding='utf-8'))
                validate_history(old,config)
                item = summarize(config,old,now)
                item.update(status='stale',error=error)
            except (OSError,ValueError,KeyError,TypeError):
                item = {**{key:config[key] for key in ('id','symbol','name','country','kind','benchmark','currency')},
                    'sourceUrl':'','historyUrl':f"data/history/{config['id']}.json",'firstDate':'','lastDate':'','count':0,
                    'status':'unavailable','close':None,'dailyChange':None,'cashYield':None,'dividendStatus':'unavailable','frankingRate':None,
                    'returns':{label:{period:None for period in PERIODS} for label in ('price','total')},'error':error}
            instruments.append(item)
            print(f"FAIL {config['id']}: {error}",flush=True)
    market = {'schemaVersion':1,'generatedAt':iso_time(now),'instruments':instruments,'failures':failures,'methodology':[
        'Full available daily provider histories, not a rolling 10-year or weekly max-range sample. All ratios are fractions, not percentages.',
        'Yahoo ETFs use period1=0; price indices use 1900 negative epoch to include pre-1970 history; interval=1d. Daily exchange-local dates are deduplicated; open sessions are excluded with a 5-minute closing buffer.',
        'Yahoo price close is provider split-normalized, not historical nominal before a split; provider adjusted close includes distributions when available.',
        'Price indices are independent index histories. Their adjustedClose and total returns are unavailable: price-index adjclose is not dividend reinvestment.',
        'CN Eastmoney daily histories reconcile dktotal; capped results use annual pagination. Tencent fallback paginates each calendar year, never latest 640 only.',
        'CN prices are split-normalized to current share units from F10 folds; rawClose/raw OHLC retain nominal trading prices. Effective sessions match observed price discontinuities; unavailable split evidence suppresses price comparisons.',
        'CN distributions use Eastmoney fund F10 ex dates and cash per 10 units divided by 10. These events are not used to fabricate total-return or adjusted-close series.',
        'TTM cash yield sums ex-date cash within the full 12 calendar months ending at last completed close; less than one year of history or unavailable events yields null.',
        'Returns use instrument lastDate minus calendar periods; baseline is on/before target within 10 calendar days. Short history returns null.',
        'Franking is unknown (null). Historical distributions and benchmark methodology can change; they are not forecasts.',
        'Source failures retain previous validated history, marked stale; strict builds fail on unavailable or stale prices. Coverage means provider-available history, not guaranteed pre-provider backtests.',
        'Eastmoney HTTP is an explicit fallback when HTTPS disconnects; sourceUrl/evidence identifies transport. No credentials are transmitted.'
    ]}
    atomic_json(output/'market.json',market)
    return market


def validate_universe(universe):
    import re
    ids = set()
    if not universe: raise ValueError('Universe is empty')
    for item in universe:
        for key in ('id','symbol','name','country','kind','benchmark','currency','provider'):
            if not isinstance(item.get(key),str) or not item[key].strip():
                raise ValueError(f'Missing/invalid instrument metadata {key}')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*',item['id']) or item['id'] in ids:
            raise ValueError('Unsafe or duplicate instrument ID')
        ids.add(item['id'])
        if item['country'] not in ('CN','US','AU') or item['kind'] not in ('etf','index'):
            raise ValueError('Invalid listing country or instrument kind')
        if item['currency'] != {'CN':'CNY','US':'USD','AU':'AUD'}[item['country']]:
            raise ValueError('Listing currency mismatch')
        if item['provider'] not in ('yahoo','eastmoney'):
            raise ValueError('Unknown data provider')
        if item['provider'] == 'eastmoney' and not re.fullmatch(r'[012]\.[A-Z0-9]+',item.get('secid','')):
            raise ValueError('Invalid Eastmoney identity')
        if item.get('expectedFirstDate'): dt.date.fromisoformat(item['expectedFirstDate'])
    return universe


def main(argv=None):
    import argparse
    import json
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=root/'public/data')
    parser.add_argument('--universe',type=Path,default=root/'data/universe.json')
    parser.add_argument('--only',help='One instrument ID for a live probe (use separate --output to preserve full dataset)')
    parser.add_argument('--strict',action='store_true',help='Nonzero exit if any instrument lacks fresh validated complete prices')
    parser.add_argument('--cache',type=Path,default=root/'.cache')
    parser.add_argument('--timeout',type=float,default=25)
    args = parser.parse_args(argv)
    universe = json.loads(args.universe.read_text(encoding='utf-8'))['instruments']
    try:
        validate_universe(universe)
    except ValueError as exc:
        print(str(exc),file=sys.stderr)
        return 2
    if args.only:
        universe = [item for item in universe if item['id']==args.only]
        if not universe:
            print('Unknown instrument ID: '+args.only,file=sys.stderr)
            return 2
    client = HTTPClient(args.cache,timeout=args.timeout)
    market = build(universe,args.output,client)
    print(f"Published {len(market['instruments'])} instruments; {len(market['failures'])} price failures; {args.output/'market.json'}")
    return 1 if args.strict and market['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
