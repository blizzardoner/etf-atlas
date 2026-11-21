"""Read actual artifacts; exercise failure paths only in temporary directories."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch
import exchange_calendars as xc
import pandas as pd
import build_data as m

ROOT = Path(__file__).resolve().parents[1]
market = json.loads((ROOT/'public/data/market.json').read_text(encoding='utf-8'))
universe = json.loads((ROOT/'data/universe.json').read_text(encoding='utf-8'))['instruments']
baseline = json.loads((ROOT/'artifacts/pre-fix-live-prices.json').read_text())
now = dt.datetime.fromisoformat(market['generatedAt'].replace('Z','+00:00')).timestamp()
calendars = {}
for name in ('XSHG','XNYS','XASX'):
    cal = xc.get_calendar(name,start='2026-01-01',end='2026-12-31')
    calendars[name] = {'version':xc.__version__,'first':str(cal.first_session.date()),'last':str(cal.last_session.date()),'sessions':len(cal.schedule),
                       'boundMax':str(cal.bound_max()), 'nov20Close':str(cal.schedule.loc['2026-11-20','close'])}
calendars['XSHG']['goldenWeekSessions'] = [str(d.date()) for d in xc.get_calendar('XSHG',start='2026-01-01',end='2026-12-31').schedule.loc['2026-09-30':'2026-10-08'].index]
calendars['XNYS']['nov27Close'] = str(xc.get_calendar('XNYS',start='2026-01-01',end='2026-12-31').schedule.loc['2026-11-27','close'])
calendars['XASX']['dec24Close'] = str(xc.get_calendar('XASX',start='2026-01-01',end='2026-12-31').schedule.loc['2026-12-24','close'])
changes,bar_changes=[],[]
for item in market['instruments']:
    h=json.loads((ROOT/'public/data/history'/f"{item['id']}.json").read_text(encoding='utf-8'))
    before=baseline['instruments'][item['id']]
    if item['close']!=before['close'] or item['lastDate']!=before['lastDate']: changes.append(item['id'])
    digest=hashlib.sha256(json.dumps(h['bars'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest != before['barsSha256']: bar_changes.append(item['id'])
assert changes == [], changes
assert market['failures']==[]
assert len(market['instruments'])==len(universe)==42
with tempfile.TemporaryDirectory() as temp:
    output=Path(temp)/'data'; shutil.copytree(ROOT/'public/data',output)
    files=list((output/'history').glob('*.json'))
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    with patch.object(m,'fetch_history',side_effect=ValueError('source down')),patch.object(m,'HTTPClient',return_value=None):
        exit_code=m.main(['--strict','--output',str(output),'--cache',str(Path(temp)/'cache')])
    failed=json.loads((output/'market.json').read_text(encoding='utf-8'))
    assert exit_code==1
    assert len(failed['failures'])==42
    assert all(i['status']=='stale' for i in failed['instruments'])
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[p.name] for p in files)
    outage={'strictExit':exit_code,'failures':len(failed['failures']),'staleRetained':sum(i['status']=='stale' for i in failed['instruments']),'historyFilesUnchanged':len(files)}
    config=next(c for c in universe if c['id']=='us-spy')
    h=json.loads((output/'history/us-spy.json').read_text(encoding='utf-8'))
    h['bars']=[b for b in h['bars'] if b['date']<='2026-11-17']
    m.validate_history(h,config)
    with patch.object(m,'fetch_history',return_value=h):
        lag=m.build([config],output,None,now)
    assert len(lag['failures'])==1
    assert lag['instruments'][0]['status']=='stale'
    assert lag['instruments'][0]['lastDate']=='2026-11-20'
    assert hashlib.sha256((output/'history/us-spy.json').read_bytes()).hexdigest()==hashes['us-spy.json']
fixtures=json.loads((ROOT/'scripts/fixtures/review_actual.json').read_text())
raw=fixtures['cn']['bars']; terminal=[b for b in raw if b['date']<='2022-08-26']
nominal=terminal[-1]['close']/terminal[-2]['close']-1
false_gain=terminal[-1]['close']/(terminal[-2]['close']/1.1454)-1
h=copy.deepcopy(fixtures['cn']); m.normalize_cn_splits(h,[{'date':'2022-08-26','ratio':1.1454}])
report={'generatedAt':market['generatedAt'],'interpreter':__import__('sys').executable,'pandas':pd.__version__,'calendarChecks':calendars,
        'liveCoverage':{'instruments':len(market['instruments']),'bars':sum(i['count'] for i in market['instruments']),'failures':len(market['failures']),'fresh':sum(i['status']=='fresh' for i in market['instruments']),'priceChanges':changes,'barHashChanges':bar_changes,'firstGSPC':next(i['firstDate'] for i in market['instruments'] if i['symbol']=='^GSPC')},
        'outageRetention':outage,'lagRetention':{'failures':len(lag['failures']),'status':lag['instruments'][0]['status'],'retainedLastDate':lag['instruments'][0]['lastDate'],'expectedLastDate':lag['instruments'][0]['expectedLastDate']},
        'actualFold':{'nominalAug26DailyChange':nominal,'formerFalseGain':false_gain,'fullEffectiveDate':h['splits'][0]['effectiveDate']}}
print(json.dumps(report,indent=2))
