import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).parent

class PipelineTests(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('build_data', ROOT / 'build_data.py')
        self.assertTrue(spec.origin and pathlib.Path(spec.origin).exists(), 'pipeline implementation is missing')
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_yahoo_daily_parser_preserves_nulls_and_excludes_intraday(self):
        m = self.module()
        payload = {'chart': {'result': [{'meta': {'exchangeTimezoneName': 'America/New_York', 'currentTradingPeriod': {'regular': {'start': 1704205800, 'end':1704229200}}}, 'timestamp': [1704121200,1704207600], 'indicators': {'quote':[{'open':[100,101],'high':[102,103],'low':[99,100],'close':[101,102],'volume':[5,6]}], 'adjclose':[{'adjclose':[100,None]}]}, 'events': {'dividends': {'a':{'date':1704121200,'amount':1.5}},'splits':{'b':{'date':1704121200,'numerator':2,'denominator':1}}}}], 'error': None}}
        history = m.parse_yahoo(payload, 'SPY', 'https://example.com', now=1704210000)
        self.assertEqual(len(history['bars']), 1)
        self.assertEqual(history['bars'][0]['adjustedClose'], 100)
        self.assertEqual(history['dividends'][0]['amount'],1.5)
        self.assertEqual(history['splits'][0]['ratio'],2)
        self.assertEqual(history['adjustment'],'provider-adjusted-close')

    def test_eastmoney_and_tencent_are_unadjusted_and_null_dividends(self):
        m = self.module()
        em = {'data':{'code':'510300','name':'ETF','dktotal':2,'klines':['2024-01-01,1,2,3,0.5,10','2024-01-02,2,3,4,1,20']}}
        h = m.parse_eastmoney(em,'x','url',now=1704300000)
        self.assertIsNone(h['dividends'])
        self.assertEqual(h['adjustment'],'none')
        self.assertIsNone(h['bars'][0]['adjustedClose'])
        self.assertEqual(h['bars'][1]['close'],3)
        tx = {'code':0,'data':{'sh510300':{'day':[['2024-01-01','1','2','3','0.5','10']]}}}
        t = m.parse_tencent(tx,'sh510300','x','url',now=1704300000)
        self.assertEqual(t['bars'][0]['close'],2)
        self.assertIsNone(t['dividends'])
        em['data']['dktotal'] = 3
        with self.assertRaises(ValueError):
            m.parse_eastmoney(em,'x','url',now=1704300000)

    def test_calendar_returns_ttm_and_missing_adjusted_not_guessed(self):
        m = self.module()
        bars = [{'date':d,'open':1,'high':1,'low':1,'close':c,'adjustedClose':None,'volume':0} for d,c in [('2023-02-28',100),('2024-01-29',110),('2024-02-29',121)]]
        h = {'id':'x','bars':bars,'dividends':[{'date':'2023-02-28','amount':99},{'date':'2023-03-01','amount':2},{'date':'2024-02-29','amount':3},{'date':'2024-03-01','amount':100}],'adjustment':'none','sourceUrl':'url'}
        config = {'id':'x','symbol':'X','name':'测试','country':'US','kind':'etf','benchmark':'test','currency':'USD'}
        out = m.summarize(config,h,now=1709300000)
        self.assertAlmostEqual(out['returns']['price']['1m'],0.1)
        self.assertAlmostEqual(out['returns']['price']['1y'],0.21)
        self.assertIsNone(out['returns']['price']['3m'])
        self.assertIsNone(out['returns']['total']['1y'])
        self.assertAlmostEqual(out['cashYield'],5/121)
        self.assertAlmostEqual(out['dailyChange'],0.1)
        self.assertIsNone(out['frankingRate'])
        h['dividends'] = None
        self.assertIsNone(m.summarize(config,h,now=1709300000)['cashYield'])
        self.assertEqual(m.summarize(config,h,now=1709300000)['dividendStatus'],'unavailable')

    def test_cn_dividends_parse_ex_dates_per_unit_and_explicit_missing(self):
        m = self.module()
        html = '''<h4>分红送配详情</h4><table><tr><th>年份</th><th>权益登记日</th><th>除息日</th><th>每10份分红</th><th>分红发放日</th></tr><tr><td>2026年</td><td>2026-01-16</td><td>2026-01-19</td><td>每10份派现金1.2300元</td><td>2026-01-27</td></tr></table><h4>拆分详情</h4><table><tr><td>2012-05-11</td><td>1:0.3709</td></tr></table>'''
        self.assertEqual(m.parse_cn_dividends(html),[{'date':'2026-01-19','amount':0.123}])
        self.assertEqual(m.parse_cn_dividends('<table><tr><th>年份</th><th>权益登记日</th><th>除息日</th><th>每10份分红</th><th>分红发放日</th></tr><tr><td colspan="5">暂无分红信息!</td></tr></table>'),[])
        with self.assertRaises(ValueError):
            m.parse_cn_dividends('<html>blocked</html>')
        with self.assertRaises(ValueError):
            m.parse_cn_dividends(html.replace('每10份派现金1.2300元','未知'))

    def test_validation_rejects_weekly_truncation_gaps_and_bad_numbers(self):
        m = self.module()
        bars = [{'date':(m.dt.date(2020,1,1)+m.dt.timedelta(days=i)).isoformat(),'close':1,'adjustedClose':1,'open':1,'high':1,'low':1,'volume':0} for i in range(730)]
        h = {'id':'x','sourceUrl':'url','retrievedAt':'2022-01-01T00:00:00Z','adjustment':'provider-adjusted-close','bars':bars,'dividends':[],'splits':[]}
        config = {'id':'x','expectedFirstDate':'2020-01-01','kind':'etf'}
        m.validate_history(h,config)
        self.assertTrue(h['coverage']['complete'])
        h['bars'] = bars[::7]
        with self.assertRaises(ValueError): m.validate_history(h,config)
        h['bars'] = bars[100:]
        with self.assertRaises(ValueError): m.validate_history(h,config)
        h['bars'] = bars[:100]+bars[150:]
        with self.assertRaises(ValueError): m.validate_history(h,config)
        h['bars'] = [dict(b) for b in bars]
        h['bars'][0]['close'] = float('nan')
        with self.assertRaises(ValueError): m.validate_history(h,config)
        h['bars'] = [dict(b) for b in bars]
        config['kind'] = 'index'
        m.validate_history(h,config)
        self.assertEqual(h['adjustment'],'none')
        self.assertTrue(all(b['adjustedClose'] is None for b in h['bars']))

    def test_full_fetch_publication_retains_failed_validated_snapshot(self):
        import tempfile
        import json
        m = self.module()
        class Client:
            def __init__(self): self.calls=[]; self.fail=False
            def get_json(self,url,params):
                self.calls.append((url,params))
                if self.fail: raise ValueError('source down')
                return {'chart':{'error':None,'result':[{'meta':{'symbol':'SPY','dataGranularity':'1d','currency':'USD','exchangeTimezoneName':'America/New_York','firstTradeDate':1704205800},'timestamp':[1704205800], 'indicators':{'quote':[{'close':[101],'open':[100],'high':[102],'low':[99],'volume':[4]}],'adjclose':[{'adjclose':[100]}]},'events':{'dividends':{}}}]}}
        c=Client()
        config={'id':'x','symbol':'SPY','name':'测试','country':'US','kind':'etf','benchmark':'标普500','currency':'USD','provider':'yahoo'}
        with tempfile.TemporaryDirectory() as out:
            result=m.build([config],pathlib.Path(out),c,now=1704300000)
            self.assertEqual(result['failures'],[])
            path=pathlib.Path(out)/'history/x.json'
            before=path.read_bytes()
            self.assertEqual(c.calls[0][1]['period1'],0)
            self.assertEqual(c.calls[0][1]['interval'],'1d')
            self.assertNotIn('range',c.calls[0][1])
            self.assertEqual(json.loads(before)['coverage']['count'],1)
            c.fail=True
            result=m.build([config],pathlib.Path(out),c,now=1704300000)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(result['instruments'][0]['status'],'stale')
            self.assertEqual(result['failures'][0]['id'],'x')
            self.assertIsNotNone(result['instruments'][0]['error'])

    def test_tencent_fallback_requests_all_years_and_rejects_ignored_range(self):
        m=self.module()
        class Client:
            def __init__(self): self.calls=[]; self.ignore=False
            def get_json(self,url,params):
                self.calls.append(params)
                year=int(params['param'].split(',')[2][:4])
                date='2023-01-03' if self.ignore else f'{year}-01-03'
                rows=[[date,'1','2','3','0.5','4']] if year>=2023 else []
                return {'code':0,'data':{'sh510300':{'day':rows}}}
        c=Client()
        config={'id':'x','tencent':'sh510300','kind':'etf','expectedFirstDate':'2023-01-03','maxGapDays':366}
        h=m.fetch_tencent(config,c,now=1704300000)
        self.assertEqual(h['coverage']['count'],2)
        self.assertEqual(c.calls[0]['param'],'sh510300,day,1990-01-01,1990-12-31,640,')
        self.assertEqual(c.calls[-1]['param'],'sh510300,day,2024-01-01,2024-12-31,640,')
        c.ignore=True
        with self.assertRaises(ValueError): m.fetch_tencent(config,c,now=1704300000)

    def test_cli_rejects_unknown_instrument_before_network(self):
        m=self.module()
        self.assertEqual(m.main(['--only','does-not-exist']),2)

    def test_price_index_fetches_pre_epoch_full_history_on_windows(self):
        m=self.module()
        class Client:
            def __init__(self): self.calls=[]
            def get_json(self,url,params):
                self.calls.append(params.copy())
                return {'chart':{'result':[{'meta':{'symbol':'^GSPC','dataGranularity':'1d','currency':'USD','exchangeTimezoneName':'America/New_York','firstTradeDate':-1325583000},'timestamp':[-1325583000], 'indicators':{'quote':[{'close':[17.66]}],'adjclose':[{'adjclose':[17.66]}]}}]}}
        config={'id':'idx','symbol':'^GSPC','country':'US','kind':'index','provider':'yahoo','currency':'USD'}
        c=Client()
        h=m.fetch_history(config,c,now=1704300000)
        self.assertEqual(h['bars'][0]['date'],'1927-12-30')
        self.assertLessEqual(c.calls[-1]['period1'],-1325583000)
        self.assertIsNone(h['bars'][0]['adjustedClose'])

    def test_cn_splits_normalize_price_not_dividend_total_returns(self):
        m=self.module()
        html='<table><tr><th>年份</th><th>拆分折算日</th><th>拆分类型</th><th>拆分折算比例</th></tr><tr><td>2024年</td><td>2024-02-01</td><td>份额分拆</td><td>1:2</td></tr><tr><td>2020年</td><td>2020-01-01</td><td>份额折算</td><td>1:0.28</td></tr></table>'
        splits=m.parse_cn_splits(html)
        self.assertEqual(splits[-1],{'date':'2024-02-01','ratio':2})
        h={'bars':[{'date':'2024-01-01','close':10,'open':9,'high':11,'low':9,'volume':2,'adjustedClose':None},{'date':'2024-02-01','close':5,'open':5,'high':5,'low':5,'volume':4,'adjustedClose':None}], 'dividends':[{'date':'2024-01-15','amount':2}], 'adjustment':'none','splits':[]}
        m.normalize_cn_splits(h,splits)
        self.assertEqual(h['bars'][0]['close'],5)
        self.assertEqual(h['bars'][0]['rawClose'],10)
        self.assertEqual(h['dividends'][0]['amount'],1)
        self.assertEqual(h['splits'][0]['date'],'2024-02-01')
        self.assertEqual(h['splits'][0]['effectiveDate'],'2024-02-01')
        self.assertIsNone(h['bars'][0]['adjustedClose'])
        self.assertEqual(h['adjustment'],'split-normalized-price')
        self.assertEqual(m.parse_cn_splits('<table><tr><th>拆分折算日</th><th>拆分折算比例</th></tr><tr><td>暂无拆分信息!</td></tr></table>'),[])
        with self.assertRaises(ValueError): m.parse_cn_splits('<html>blocked</html>')

    def test_raw_cache_reuses_immutable_pages_and_bounds_mutable_evidence(self):
        import tempfile
        import requests
        m=self.module()
        class Session:
            def __init__(self): self.headers={}; self.calls=0
            def get(self,url,params,timeout):
                self.calls+=1
                r=requests.Response(); r.status_code=200; r.url=url+'?year='+str(params['year']); r._content=b'{"code":0,"data":{}}'; return r
        with tempfile.TemporaryDirectory() as out:
            s=Session(); c=m.HTTPClient(out,session=s,max_entries=2)
            c.get_json_cached('https://example.com',{'year':2020})
            c.get_json_cached('https://example.com',{'year':2020})
            self.assertEqual(s.calls,1)
            c.get_json('https://example.com',{'year':2021})
            c.get_json('https://example.com',{'year':2022})
            self.assertLessEqual(len(list(pathlib.Path(out).glob('*.raw'))),2)

    def test_cn_split_effective_session_uses_actual_discontinuity(self):
        m=self.module()
        bars=[{'date':d,'close':c,'open':c,'high':c,'low':c,'volume':1,'adjustedClose':None} for d,c in [('2022-08-25',7.20),('2022-08-26',7.22),('2022-08-29',6.3)]]
        h={'bars':bars,'splits':[],'dividends':[],'adjustment':'none'}
        m.normalize_cn_splits(h,[{'date':'2022-08-26','ratio':1.1454}])
        self.assertAlmostEqual(h['bars'][1]['close'],7.22/1.1454)
        self.assertEqual(h['splits'][0]['effectiveDate'],'2022-08-29')
        self.assertEqual(h['bars'][2]['rawClose'],6.3)
        self.assertEqual(h['adjustment'],'split-normalized-price')

    def test_unverified_split_actions_suppress_price_rankings(self):
        m=self.module()
        config={'id':'x','symbol':'X','name':'测试','country':'CN','kind':'etf','benchmark':'test','currency':'CNY'}
        h={'sourceUrl':'url','adjustment':'none','bars':[{'date':'2023-11-20','close':1,'adjustedClose':None},{'date':'2024-11-20','close':2,'adjustedClose':None}], 'dividends':None,'priceComparisonUnavailable':True}
        item=m.summarize(config,h,now=1732200000)
        self.assertTrue(all(v is None for v in item['returns']['price'].values()))
        self.assertIsNone(item['dailyChange'])
        self.assertTrue(item['priceComparisonUnavailable'])
        self.assertIsNone(item['cashYield'])

    def test_universe_metadata_validation_rejects_unsafe_ids_and_currency_mismatch(self):
        m=self.module()
        config={'id':'test','symbol':'SPY','name':'测试','country':'US','kind':'etf','benchmark':'标普500','currency':'USD','provider':'yahoo'}
        m.validate_universe([config])
        for changes in ({'id':'../bad'},{'currency':'AUD'},{'name':''},{'kind':'stock'},{'provider':'fabricated'}):
            with self.assertRaises(ValueError): m.validate_universe([{**config,**changes}])
        with self.assertRaises(ValueError): m.validate_universe([config,config])

if __name__ == '__main__':
    unittest.main()
