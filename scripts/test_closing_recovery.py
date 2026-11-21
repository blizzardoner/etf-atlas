"""Real Yahoo outage tracer bullets; source fixtures are unmodified captures."""
import copy
import json
from pathlib import Path
import unittest
import build_data as m

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {k: json.loads((ROOT/'scripts/fixtures'/f'closing_spy_actual_{k}.json').read_bytes()) for k in ('daily','minute','weekly')}
CONFIG = next(c for c in json.loads((ROOT/'data/universe.json').read_text(encoding='utf-8'))['instruments'] if c['id']=='us-spy')
NOW = 1795225650  # exact primary captured request cutoff, after the completed close

class ActualClient:
    def __init__(self, fixtures=None):
        self.fixtures = copy.deepcopy(fixtures or FIXTURES)
        self.calls = []
    def get_json(self, url, params):
        self.calls.append((url, copy.deepcopy(params)))
        kind = {'1d':'daily','15m':'minute','1wk':'weekly'}[params['interval']]
        import hashlib
        fixture_path = ROOT/'scripts/fixtures'/f'closing_spy_actual_{kind}.json'
        self.last_receipt = {'path':fixture_path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
            'url':self.fixtures[kind]['url'],'retrievedAt':self.fixtures[kind]['retrievedAt'],'format':'captured-wrapper'}
        return self.fixtures[kind]['payload']

class ClosingRecoveryTests(unittest.TestCase):
    def test_actual_latest_null_daily_fields_recovered_without_mutating_primary(self):
        client = ActualClient()
        before = copy.deepcopy(client.fixtures)
        history = m.fetch_history(CONFIG, client, NOW)
        self.assertEqual(history['bars'][-1]['date'], '2026-11-20')
        self.assertEqual(history['bars'][-1]['close'], 689.8099975585938)
        self.assertEqual(history['bars'][-1]['adjustedClose'], 689.8099975585938)
        self.assertEqual(len(history['bars']), 8512)
        self.assertEqual(client.fixtures, before)
        proof = history['providerEvidence']['latestClosingRecovery']
        self.assertEqual(proof['primaryMissingFields'], ['close','adjustedClose'])
        self.assertEqual(proof['sessionCloseTimestamp'], 1795208400)
        self.assertEqual(proof['minute']['timestamp'], 1795208400)
        self.assertEqual(proof['snapshot']['timestamp'], 1795208404)
        self.assertEqual(history['providerEvidence']['recoveredCloseCount'], 1)
        self.assertEqual(history['providerEvidence']['rawCount'], 8512)
        self.assertEqual([p['interval'] for _,p in client.calls], ['1d','15m','1wk'])
        self.assertEqual(client.calls[1][1]['range'], '5d')
        self.assertEqual(client.calls[2][1]['range'], '1mo')
        self.assertEqual(client.calls[2][1]['includeAdjustedClose'], 'true')
        self.assertTrue(all(p['includePrePost']=='false' for _,p in client.calls[1:]))

    def test_actual_au_wholly_empty_source_rows_stay_excluded_not_recovered(self):
        payload = json.loads((ROOT/'scripts/fixtures/closing_vhy_actual_daily.json').read_bytes())
        config = next(c for c in json.loads((ROOT/'data/universe.json').read_text(encoding='utf-8'))['instruments'] if c['id']=='au-vhy')
        class Client:
            def get_json(self,url,params):
                if params['interval'] != '1d': raise AssertionError('No recovery for historical empty rows')
                return payload
        history = m.fetch_history(config,Client(),NOW)
        self.assertEqual(len(history['bars']),3923)
        self.assertEqual(history['providerEvidence'].get('duplicateCompletedDateCount'),1)
        self.assertEqual(history['providerEvidence'].get('historicalEmptyRowCount'),2)
        self.assertEqual(history['providerEvidence']['recoveredCloseCount'],0)

    def test_proof_contains_hash_verifiable_source_receipts_and_snapshot_ohlc(self):
        history = m.fetch_history(CONFIG,ActualClient(),NOW)
        proof = history['providerEvidence']['latestClosingRecovery']
        for key in ('primary','minute','snapshot'):
            self.assertIn(key,proof)
            self.assertIn('rawSource',proof[key])
            self.assertTrue(proof[key]['rawSource']['sha256'])
        self.assertEqual(proof['snapshot']['open'],proof['primaryValues']['open'])

    def test_snapshot_ohlc_mismatch_rejected_even_if_close_inside_daily_range(self):
        fixtures = copy.deepcopy(FIXTURES)
        fixtures['weekly']['payload']['chart']['result'][0]['indicators']['quote'][0]['open'][-1] = 700
        with self.assertRaises(ValueError):
            m.fetch_history(CONFIG,ActualClient(fixtures),NOW)

    def test_secondary_proof_rejects_time_identity_values_and_weekly_candles(self):
        cases = [('minute','meta','symbol','OTHER'),('minute','meta','currency','EUR'),
                 ('minute','meta','dataGranularity','1d'),('weekly','meta','symbol','OTHER'),
                 ('weekly','meta','currency','EUR'),('weekly','meta','dataGranularity','1d'),
                 ('weekly','meta','regularMarketTime',1795206600),
                 ('weekly','timestamp',None,1795206600),('weekly','timestamp',None,1794805200),
                 ('weekly','timestamp',None,1795208461),('weekly','close',None,700),
                 ('weekly','close',None,0),('weekly','close',None,None)]
        for kind, group, field, value in cases:
            with self.subTest(kind=kind,group=group,field=field,value=value):
                fixtures = copy.deepcopy(FIXTURES)
                r = fixtures[kind]['payload']['chart']['result'][0]
                if group=='meta': r['meta'][field] = value
                elif group=='timestamp':
                    r['timestamp'][-1] = value
                    if value != 1795206600: r['meta']['regularMarketTime'] = value
                else: r['indicators']['quote'][0]['close'][-1] = value
                with self.assertRaises(ValueError):
                    m.fetch_history(CONFIG, ActualClient(fixtures), NOW)

    def test_nonmissing_primary_ohlc_must_constrain_snapshot(self):
        fixtures = copy.deepcopy(FIXTURES)
        fixtures['daily']['payload']['chart']['result'][0]['indicators']['quote'][0]['high'][-1] = 680
        with self.assertRaises(ValueError):
            m.fetch_history(CONFIG, ActualClient(fixtures), NOW)

    def test_historical_missing_close_is_not_silently_dropped(self):
        fixtures = copy.deepcopy(FIXTURES)
        fixtures['daily']['payload']['chart']['result'][0]['indicators']['quote'][0]['close'][-2] = None
        with self.assertRaises(ValueError):
            m.fetch_history(CONFIG, ActualClient(fixtures), NOW)

    def test_missing_first_trade_anchor_rejects_before_secondary_fetch(self):
        fixtures = copy.deepcopy(FIXTURES)
        fixtures['daily']['payload']['chart']['result'][0]['meta'].pop('firstTradeDate')
        client = ActualClient(fixtures)
        with self.assertRaisesRegex(ValueError, 'beginning'):
            m.fetch_history(CONFIG, client, NOW)
        self.assertTrue(all(p['interval']=='1d' for _,p in client.calls))

    def test_incomplete_lifetime_suffix_rejects_before_secondary_fetch(self):
        fixtures = copy.deepcopy(FIXTURES)
        r = fixtures['daily']['payload']['chart']['result'][0]
        r['timestamp'] = r['timestamp'][-5:]
        for q in r['indicators']['quote']+r['indicators']['adjclose']:
            for field in q: q[field] = q[field][-5:]
        client = ActualClient(fixtures)
        with self.assertRaisesRegex(ValueError, 'Truncated beginning'):
            m.fetch_history(CONFIG, client, NOW)
        self.assertTrue(all(p['interval']=='1d' for _,p in client.calls))

    def test_exact_close_minute_required_not_1530_or_last_intraday_bar(self):
        fixtures = copy.deepcopy(FIXTURES)
        r = fixtures['minute']['payload']['chart']['result'][0]
        r['timestamp'] = [s-1800 if s==1795208400 else s for s in r['timestamp']]
        with self.assertRaises(ValueError):
            m.fetch_history(CONFIG, ActualClient(fixtures), NOW)

    def test_missing_explicit_adjusted_close_leaves_total_returns_null(self):
        fixtures = copy.deepcopy(FIXTURES)
        fixtures['weekly']['payload']['chart']['result'][0]['indicators'].pop('adjclose')
        history = m.fetch_history(CONFIG, ActualClient(fixtures), NOW)
        self.assertEqual(history['bars'][-1]['close'], 689.8099975585938)
        self.assertIsNone(history['bars'][-1]['adjustedClose'])
        self.assertTrue(all(v is None for v in m.summarize(CONFIG,history,NOW)['returns']['total'].values()))

    def test_valid_daily_close_never_replaced_and_index_total_stays_null(self):
        fixtures = copy.deepcopy(FIXTURES)
        fixtures['daily']['payload']['chart']['result'][0]['indicators']['quote'][0]['close'][-1] = 689.8099975585938
        history = m.fetch_history(CONFIG, ActualClient(fixtures), NOW)
        self.assertEqual(history['providerEvidence']['recoveredCloseCount'],0)
        self.assertEqual(history['bars'][-1]['close'],689.8099975585938)
        history = m.fetch_history({**CONFIG,'kind':'index'}, ActualClient(), NOW)
        self.assertTrue(all(b['adjustedClose'] is None for b in history['bars']))
        self.assertEqual(history['providerEvidence']['recoveredAdjustedCloseCount'],0)

    def test_duplicate_terminal_primary_date_never_replaces_existing_valid_price(self):
        fixtures = copy.deepcopy(FIXTURES)
        r = fixtures['daily']['payload']['chart']['result'][0]
        r['indicators']['quote'][0]['close'][-1] = 689.8099975585938
        r['indicators']['adjclose'][0]['adjclose'][-1] = 689.8099975585938
        r['timestamp'].append(r['timestamp'][-1]+60)
        for q in r['indicators']['quote']+r['indicators']['adjclose']:
            for field in q: q[field].append(q[field][-1])
        r['indicators']['quote'][0]['close'][-1] = None
        r['indicators']['adjclose'][0]['adjclose'][-1] = None
        with self.assertRaises(ValueError):
            m.fetch_history(CONFIG,ActualClient(fixtures),NOW)

class IndependentClosingAuditTests(unittest.TestCase):
    def audit(self, change=None, portable=False):
        import contextlib
        import io
        import runpy
        from unittest.mock import patch
        history = m.fetch_history(CONFIG,ActualClient(),NOW)
        if change: change(history['providerEvidence'])
        market = {'generatedAt':m.iso_time(NOW),'failures':[], 'instruments':[m.summarize(CONFIG,history,NOW)]}
        original_read = Path.read_text
        def read(path,*args,**kwargs):
            if path.name=='market.json': return json.dumps(market)
            if path.name=='universe.json': return json.dumps({'instruments':[CONFIG]})
            if path.name=='us-spy.json': return json.dumps(history)
            return original_read(path,*args,**kwargs)
        argv = ['audit']+(['--portable-recovery'] if portable else [])
        with patch.object(Path,'read_text',read),patch('sys.argv',argv),patch('time.time',return_value=NOW),contextlib.redirect_stdout(io.StringIO()) as output:
            with contextlib.ExitStack() as stack:
                if portable:
                    stack.enter_context(patch.object(Path,'read_bytes',side_effect=AssertionError('Portable mode must not read private raw files')))
                runpy.run_path(str(ROOT/'qa/audit.py'))
        return json.loads(output.getvalue())

    def test_portable_copy_no_private_paths_validates_witness_without_raw_reads(self):
        from unittest.mock import patch
        def change(e):
            for key in ('primary','minute','snapshot'):
                e['latestClosingRecovery'][key]['rawSource'].pop('path')
        # Fixture build occurs before audit; count actual reads during audit by
        # loading an already-built history outside the read_bytes guard.
        result = self.audit(change,portable=True)
        self.assertEqual(result.get('auditMode'),'portable-recovery-witness')
        self.assertFalse(result.get('rawBytesVerified'))

    def test_default_audit_rejects_path_traversal_and_arbitrary_external_paths(self):
        for path in ('../../outside.raw','C:/Users/blizz/.ssh/id_rsa','scripts/../CONTRACT.md'):
            with self.subTest(path=path),self.assertRaisesRegex(AssertionError,'path'):
                self.audit(lambda e:e['latestClosingRecovery']['primary']['rawSource'].update(path=path))

    def test_portable_rejects_invalid_hash_shape_and_witness_time(self):
        for source,field,value in [('snapshot','timestamp',1795206600),('minute','currency','EUR')]:
            with self.subTest(field=field),self.assertRaises(AssertionError):
                self.audit(lambda e:e['latestClosingRecovery'][source].update({field:value}),portable=True)
        with self.assertRaises(AssertionError):
            self.audit(lambda e:e['latestClosingRecovery']['primary']['rawSource'].update(sha256='not-a-hash'),portable=True)

    def test_actual_proven_recovery_independent_audit_accepts(self):
        self.audit()

    def test_independent_audit_rejects_tampered_source_proof(self):
        cases = [('snapshot','timestamp',1795206600),('snapshot','regularMarketTime',1795206600),
                 ('snapshot','close',700),('snapshot','adjustedClose',700),('snapshot','open',700),
                 ('snapshot','currency','EUR'),('snapshot','symbol','OTHER'),('snapshot','dataGranularity','1d'),
                 ('minute','timestamp',1795206600),('minute','close',700),('minute','currency','EUR')]
        for source,field,value in cases:
            with self.subTest(source=source,field=field),self.assertRaises(AssertionError):
                self.audit(lambda e:e['latestClosingRecovery'][source].update({field:value}))
        for field,value in [('primaryMissingCloseCount',0),('recoveredCloseCount',0),('completedRawCount',8511)]:
            with self.subTest(field=field),self.assertRaises(AssertionError):
                self.audit(lambda e:e.update({field:value}))
        with self.assertRaises(AssertionError):
            self.audit(lambda e:e['latestClosingRecovery']['primary']['rawSource'].update(sha256='0'*64))
        with self.assertRaises(AssertionError):
            self.audit(lambda e:e['latestClosingRecovery'].update(primaryMissingFields=[]))

if __name__ == '__main__':
    unittest.main()
