import copy
import datetime as dt
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import build_data as m

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT/'scripts/fixtures/review_actual.json').read_text())
CONFIG = {'id':'us-spy','symbol':'SPY','name':'SPY','country':'US','kind':'etf','benchmark':'S&P500','currency':'USD'}

def stamp(value):
    return dt.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()

class CalendarTests(unittest.TestCase):
    def test_actual_spy_missing_completed_sessions_is_stale(self):
        h = copy.deepcopy(FIXTURE['spy'])
        h['bars'] = [b for b in h['bars'] if b['date'] <= '2026-11-17']
        m.validate_history(h, CONFIG)
        item = m.summarize(CONFIG,h,stamp('2026-11-20T23:00:00Z'))
        self.assertEqual(item['status'],'stale')
        self.assertEqual(item['expectedLastDate'],'2026-11-20')
        self.assertEqual(item['freshUntil'],'2026-11-23T21:05:00Z')
        self.assertEqual(item['calendar'],'XNYS')

    def test_real_2026_holiday_and_half_day_boundaries(self):
        for country,now,last,expiry in [
            ('CN','2026-10-08T06:00:00Z','2026-09-30','2026-10-08T07:05:00Z'),
            ('US','2026-11-27T18:04:59Z','2026-11-25','2026-11-27T18:05:00Z'),
            ('US','2026-11-27T18:05:00Z','2026-11-27','2026-11-30T21:05:00Z'),
            ('AU','2026-12-24T03:09:59Z','2026-12-23','2026-12-24T03:15:00Z')]:
            with self.subTest(country=country,now=now):
                h=copy.deepcopy(FIXTURE['spy']); h['bars']=[{'date':last,'close':100,'adjustedClose':None}]
                item=m.summarize({**CONFIG,'country':country},h,stamp(now))
                self.assertEqual(item['status'],'fresh')
                self.assertEqual(item['expectedLastDate'],last)
                self.assertEqual(item['freshUntil'],expiry)

    def test_calendar_unavailable_fails_closed(self):
        with patch('exchange_calendars.get_calendar',side_effect=ValueError('unavailable')):
            with self.assertRaises(ValueError):
                m.summarize(CONFIG,copy.deepcopy(FIXTURE['spy']),stamp('2035-11-20T23:00:00Z'))

class SplitTests(unittest.TestCase):
    def test_actual_terminal_fold_defers_without_inventing_gain(self):
        h=copy.deepcopy(FIXTURE['cn'])
        h['bars']=[b for b in h['bars'] if b['date'] <= '2022-08-26']
        before=copy.deepcopy(h['bars'])
        m.normalize_cn_splits(h,[{'date':'2022-08-26','ratio':1.1454}])
        self.assertTrue(h.get('priceComparisonUnavailable'))
        self.assertEqual(h['splits'],[])
        self.assertEqual([b['close'] for b in h['bars']],[b['close'] for b in before])
        self.assertEqual(h['bars'][-1]['rawClose'],before[-1]['close'])
        item=m.summarize({**CONFIG,'country':'CN'},h,stamp('2022-08-26T23:00:00Z'))
        self.assertIsNone(item['dailyChange'])
        self.assertTrue(all(v is None for v in item['returns']['price'].values()))

    def test_actual_full_fold_establishes_aug29(self):
        h=copy.deepcopy(FIXTURE['cn'])
        m.normalize_cn_splits(h,[{'date':'2022-08-26','ratio':1.1454}])
        self.assertEqual(h['splits'][0]['effectiveDate'],'2022-08-29')
        for b,raw in zip(h['bars'],FIXTURE['cn']['bars']):
            self.assertEqual(b['rawClose'],raw['close'])
            self.assertAlmostEqual(b['close'],raw['close']/(1.1454 if b['date']<'2022-08-29' else 1))

class GateTests(unittest.TestCase):
    def test_workflow_is_strict_every_calendar_day(self):
        workflow=(ROOT/'.github/workflows/pages.yml').read_text()
        self.assertIn("cron: '30 7,22 * * *'",workflow)
        self.assertIn('run: python scripts/build_data.py --strict',workflow)
        self.assertIn('needs: build',workflow)
        self.assertNotIn('continue-on-error',workflow)
        self.assertNotIn('always()',workflow)

    def audit(self,mutation=None,asof='2026-11-21T00:00:00Z'):
        import runpy
        import tempfile
        import contextlib
        import io
        h=copy.deepcopy(FIXTURE['spy']); h['id']=CONFIG['id']
        m.validate_history(h,CONFIG)
        item=m.summarize(CONFIG,h,stamp('2026-11-20T23:00:00Z'))
        market={'generatedAt':'2026-11-20T23:00:00Z','instruments':[item],'failures':[]}
        if mutation: mutation(market,h)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp); (p/'history').mkdir()
            (p/'market.json').write_text(json.dumps(market))
            (p/'history'/f"{item['id']}.json").write_text(json.dumps(h))
            with patch('time.time',return_value=stamp(asof)),patch('sys.argv',['audit',temp]),patch.object(Path,'exists',return_value=False),contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(ROOT/'qa/audit.py'))

    def test_audit_rejects_source_failures(self):
        with self.assertRaises(AssertionError):
            self.audit(lambda market,h: market.update(failures=[{'id':CONFIG['id'],'error':'source down'}]*42))

    def test_audit_rejects_stale_retention(self):
        with self.assertRaises(AssertionError):
            self.audit(lambda market,h: market['instruments'][0].update(status='stale'))

    def test_audit_rejects_fake_index_total_return_and_zero_yield(self):
        def mutate(market,h):
            item=market['instruments'][0]; item.update(kind='index',cashYield=0,dividendStatus='no-distributions')
            h['dividends']=[]
            for b in h['bars']: b['adjustedClose']=b['close']
            item['returns']['total']=copy.deepcopy(item['returns']['price'])
        with self.assertRaises(AssertionError): self.audit(mutate)

    def test_audit_rejects_expired_previously_fresh_snapshot(self):
        with self.assertRaises(AssertionError):
            self.audit(asof='2026-11-23T21:05:00Z')

    def test_audit_rejects_forged_fresh_calendar(self):
        with self.assertRaises(AssertionError):
            self.audit(lambda market,h: market['instruments'][0].update(expectedLastDate='2026-11-17'))

    def test_build_retains_old_when_new_split_evidence_ambiguous(self):
        import tempfile
        h=copy.deepcopy(FIXTURE['spy']); h['id']=CONFIG['id']
        m.validate_history(h,CONFIG)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'history'/f"{CONFIG['id']}.json"
            m.atomic_json(p,h); before=p.read_bytes()
            ambiguous=copy.deepcopy(h); ambiguous['priceComparisonUnavailable']=True
            with patch.object(m,'fetch_history',return_value=ambiguous):
                market=m.build([CONFIG],temp,None,stamp('2026-11-20T23:00:00Z'))
            self.assertEqual(len(market['failures']),1)
            self.assertEqual(market['instruments'][0]['status'],'stale')
            self.assertEqual(before,p.read_bytes())

    def test_all_requirements_have_upper_bounds(self):
        for line in (ROOT/'requirements.txt').read_text().splitlines():
            if line and not line.startswith('#'): self.assertIn(',<',line)

if __name__ == '__main__':
    unittest.main()
