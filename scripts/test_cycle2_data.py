"""Final data counterexamples: actual exchange calendars and raw cached SPY."""
import contextlib
import copy
import io
import json
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

import build_data as m

ROOT = Path(__file__).resolve().parents[1]
CASES = [(country, instant) for country in ('CN', 'US', 'AU') for instant in
         ('2025-12-31T23:00:00Z', '2026-01-01T00:00:00Z',
          '2026-12-31T23:00:00Z', '2027-01-01T00:00:00Z')]

class CalendarBoundTests(unittest.TestCase):
    def test_producer_all_twelve_actual_year_boundaries(self):
        for country, instant in CASES:
            with self.subTest(country=country, instant=instant):
                if country == 'CN' and instant.startswith(('2026-12', '2027')):
                    with self.assertRaisesRegex(ValueError, 'calendar unavailable'):
                        m.session_freshness(country, m.dt.datetime.fromisoformat(instant.replace('Z', '+00:00')).timestamp())
                    continue
                try:
                    result = m.session_freshness(country, m.dt.datetime.fromisoformat(instant.replace('Z', '+00:00')).timestamp())
                except ValueError as exc:
                    self.fail(f'Known next session rejected: {exc}')
                year = '2025' if instant.startswith(('2025', '2026-01')) else '2026'
                next_date = '2026-01-05' if country == 'CN' else ('2026-01-02' if year == '2025' else '2027-01-04')
                close = {'CN':'07', 'US':'21', 'AU':'05'}[country]
                self.assertEqual(result['expectedLastDate'], year + '-12-31')
                self.assertEqual(result['freshUntil'], next_date + 'T' + close + ':05:00Z')

    def test_independent_audit_all_twelve_actual_year_boundaries(self):
        for country, instant in CASES:
            with self.subTest(country=country, instant=instant):
                market = {'generatedAt':instant, 'failures':[], 'instruments':[
                    {'id':'boundary', 'country':country, 'status':'fresh'}]}
                with patch.object(Path, 'read_text', return_value=json.dumps(market)), patch.object(Path, 'exists', return_value=False), patch('sys.argv', ['audit']), contextlib.redirect_stdout(io.StringIO()):
                    if country == 'CN' and instant.startswith(('2026-12', '2027')):
                        with self.assertRaisesRegex(AssertionError, 'calendar coverage unavailable'):
                            runpy.run_path(str(ROOT/'qa/audit.py'))
                    else:
                        # The sentinel deliberately lacks item fields: reaching them proves
                        # the independently computed calendar had both actual sessions.
                        with self.assertRaisesRegex(AssertionError, 'calendar identity'):
                            runpy.run_path(str(ROOT/'qa/audit.py'))

SPY = json.loads((ROOT/'scripts/fixtures/cycle2_spy_actual.json').read_bytes())
CONFIG = next(c for c in json.loads((ROOT/'data/universe.json').read_text(encoding='utf-8'))['instruments'] if c['id'] == 'us-spy')
NOW = m.dt.datetime.fromisoformat('2026-11-21T00:22:47+00:00').timestamp()

class ActualYahooEvidenceTests(unittest.TestCase):
    def fetch(self, payload, config=None):
        class Client:
            def get_json(self, url, params):
                return payload
        return m.fetch_history(config or CONFIG, Client(), NOW)

    def test_actual_spy_suffix_missing_lifetime_anchor_fails_strict_retains_bytes(self):
        import tempfile
        payload = copy.deepcopy(SPY)
        result = payload['chart']['result'][0]
        result['meta'].pop('firstTradeDate')
        result['timestamp'] = result['timestamp'][-5:]
        for quote in result['indicators'].get('quote', []) + result['indicators'].get('adjclose', []):
            for field in quote:
                quote[field] = quote[field][-5:]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            old = self.fetch(copy.deepcopy(SPY))
            target = output/'history/us-spy.json'
            m.atomic_json(target, old)
            before = target.read_bytes()
            class Client:
                def get_json(self, url, params):
                    return payload
            with patch.object(m, 'HTTPClient', return_value=Client()), patch.object(m.time, 'time', return_value=NOW), contextlib.redirect_stdout(io.StringIO()):
                code = m.main(['--only', 'us-spy', '--output', str(output), '--strict'])
            self.assertEqual(code, 1, 'five actual sessions without a lifetime anchor must not pass strict')
            market = json.loads((output/'market.json').read_text())
            self.assertEqual(market['instruments'][0]['status'], 'stale')
            self.assertEqual(market['instruments'][0]['firstDate'], '1993-01-29')
            self.assertEqual(len(market['failures']), 1)
            self.assertEqual(target.read_bytes(), before)

    def test_actual_spy_missing_identity_or_granularity_fails_closed(self):
        for field in ('symbol', 'dataGranularity'):
            with self.subTest(field=field):
                payload = copy.deepcopy(SPY)
                payload['chart']['result'][0]['meta'].pop(field)
                with self.assertRaises(ValueError):
                    self.fetch(payload)

    def test_actual_spy_missing_or_mismatched_currency_fails_closed(self):
        for currency in (None, 'EUR'):
            with self.subTest(currency=currency):
                payload = copy.deepcopy(SPY)
                meta = payload['chart']['result'][0]['meta']
                if currency is None:
                    meta.pop('currency')
                else:
                    meta['currency'] = currency
                with self.assertRaisesRegex(ValueError, 'currency'):
                    self.fetch(payload)

    def test_verified_expected_first_date_fallback_accepts_only_full_actual_history(self):
        payload = copy.deepcopy(SPY)
        payload['chart']['result'][0]['meta'].pop('firstTradeDate')
        history = self.fetch(payload, {**CONFIG, 'expectedFirstDate':'1993-01-29'})
        self.assertTrue(history['coverage']['complete'])
        self.assertEqual(history['bars'][0]['date'], '1993-01-29')
        self.assertEqual(history['providerEvidence'].get('firstDateBasis'), 'universe.expectedFirstDate')
        self.assertEqual(history['providerEvidence'].get('expectedFirstDate'), '1993-01-29')
        result = payload['chart']['result'][0]
        result['timestamp'] = result['timestamp'][-5:]
        for quote in result['indicators'].get('quote', []) + result['indicators'].get('adjclose', []):
            for field in quote:
                quote[field] = quote[field][-5:]
        with self.assertRaisesRegex(ValueError, 'Truncated beginning'):
            self.fetch(payload, {**CONFIG, 'expectedFirstDate':'1993-01-29'})

class IndependentEvidenceAuditTests(unittest.TestCase):
    def audit(self, item_changes=None, evidence_changes=None, suffix=False):
        history = ActualYahooEvidenceTests().fetch(copy.deepcopy(SPY))
        item = m.summarize(CONFIG, history, NOW)
        if item_changes:
            item.update(item_changes)
        if evidence_changes:
            history['providerEvidence'].update(evidence_changes)
        if suffix:
            history['bars'] = history['bars'][-5:]
            history['coverage'].update(count=5, firstDate=history['bars'][0]['date'])
            history['providerEvidence']['uniqueCompletedCount'] = 5
            item.update(count=5, firstDate=history['bars'][0]['date'])
            # Make derived statistics honestly match the suffix; only its false
            # lifetime completeness claim should cause the independent rejection.
            item.update(m.summarize(CONFIG, history, NOW))
        market = {'generatedAt':m.iso_time(NOW), 'failures':[], 'instruments':[item]}
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            if path.name == 'market.json': return json.dumps(market)
            if path.name == 'universe.json': return json.dumps({'instruments':[CONFIG]})
            if path.name == 'us-spy.json': return json.dumps(history)
            return original_read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read), patch('sys.argv', ['audit']), patch('time.time', return_value=NOW), contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(ROOT/'qa/audit.py'))

    def test_audit_independently_matches_universe_metadata(self):
        for field, value in [('symbol','OTHER'), ('country','AU'), ('kind','index'), ('currency','EUR'), ('name','wrong'), ('benchmark','wrong')]:
            with self.subTest(field=field), self.assertRaisesRegex(AssertionError, 'metadata'):
                self.audit(item_changes={field:value})

    def test_audit_rejects_missing_or_mismatched_provider_evidence(self):
        for change in ({'firstTradeDate':None}, {'rawCount':4}, {'uniqueCompletedCount':4}, {'symbol':'OTHER'}, {'currency':'EUR'}, {'dataGranularity':None}):
            with self.subTest(change=change), self.assertRaisesRegex(AssertionError, 'evidence'):
                self.audit(evidence_changes=change)

    def test_audit_rejects_actual_suffix_claiming_lifetime_complete(self):
        with self.assertRaisesRegex(AssertionError, 'beginning'):
            self.audit(suffix=True)

    def test_audit_accepts_full_actual_spy_evidence(self):
        self.audit()

if __name__ == '__main__':
    unittest.main()
