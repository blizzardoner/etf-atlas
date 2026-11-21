# ETF Atlas daily ingestion

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s scripts -p 'test_*.py'
python scripts/build_data.py --strict
python scripts/build_data.py --only us-spy --output .cache/probe-spy --strict
```

Defaults resolve relative to the repository, not the caller's working directory. `--output` defaults to `public/data`; `--cache` defaults to repository `.cache`. Probe into a separate output directory: `--only` intentionally creates a one-instrument market manifest. `--strict` returns a nonzero exit if any required price history cannot be refreshed. Generated snapshots and raw evidence must remain ignored by git. No credentials are needed.

## Sources and coverage

- Yahoo ETF requests explicitly use `period1=0`, `period2=now`, `interval=1d`, `events=div,splits`, and adjusted close. Price indices request from 1900 (negative UNIX epoch), including S&P 500 daily observations before 1970. Epoch arithmetic works on Windows, which rejects negative `datetime.fromtimestamp` values.
- Yahoo daily granularity, firstTradeDate, date density, ascending unique dates, numerical finiteness, long gaps, and latest completed closes are checked. Duplicate exchange-local dates are collapsed, and open current sessions are excluded until five minutes after the regular close. Provider split-normalized closes are **not** historical nominal prices before a split.
- Eastmoney requests the complete daily unadjusted series from 1990 with a 100,000 observation limit. Raw observation counts must equal `dktotal`; if capped, annual pagination must reconcile the same declared total. All requested Chinese benchmark indices are independent index series, not ETF backfills. Provider-available first dates can differ from conceptual index inception or older backtests.
- HTTPS is attempted first. In environments where Eastmoney HTTPS disconnects, HTTP is an explicit public-data fallback; actual transport is recorded in sourceUrl/providerEvidence. This is not an authenticated financial feed or cryptographically verified market data.
- Tencent fallback visits every calendar year from 1990 to the present, rejects ignored date ranges and duplicate rows, and never presents its latest-640 result as full history. Past annual responses reuse hash-verified raw cache; current-year data are always refreshed. Raw evidence is bounded to 2,000 entries and rolling Yahoo requests replace their previous cache entry instead of accumulating each period2 timestamp.
- Every source payload is cached as exact raw bytes with URL, retrieval time and SHA-256. Publication is atomic per JSON file, uses `allow_nan=False`, and retains previous validated history unchanged on source failure. Retained rows are **stale**, never fresh.

## Corporate actions and missing data

Chinese ETF distributions come from the full fund F10 distribution table: use **ex date**, not registration/payment date, and divide cash per ten units by ten. Empty distributions are zero only when the table explicitly says there have been no distributions; a failed/missing table is `dividends: null` and yield unavailable.

F10 fold/split ratios are parsed independently. Post-listing actions are applied to comparison OHLC and historical cash amounts on a consistent latest-share basis; all original trading OHLC remain available as `rawOpen`, `rawHigh`, `rawLow`, `rawClose`, and changed cash amounts as `rawAmount`. Pre-listing folds are not applied. F10 dates can be after the named session's close; the actual effective session is selected from the listed/next available session by matching the observed price discontinuity to the share ratio, and recorded as `effectiveDate` with its evidence basis. Inconsistent action evidence suppresses price comparisons and yield rather than fabricating a return. `adjustment: split-normalized-price` denotes share normalization **only**, never dividend reinvestment; adjustedClose remains null for CN sources.

Yahoo prices and dividend events are already split-normalized by the provider: splits are recorded, not applied a second time. All genuine price-index series have `adjustment: none`, `adjustedClose: null`, `dividends: null`, and unavailable total returns even if Yahoo supplies an adjclose equal to close.

## Calculations

Seven periods: 1/3/6 calendar months and 1/3/5/10 calendar years, measured from each instrument's last completed session. The baseline is the last available close on or before the anniversary, within a ten-day tolerance. Short histories and missing baseline/adjusted prices return null. Ratios are fractions (0.05 means 5%), not percentages.

Daily change uses the previous **distinct completed session**, never Yahoo chartPreviousClose. TTM yield uses ex-date cash in `(lastDate minus 12 calendar months, lastDate]` divided by the current close. A full year of price history is mandatory; forecasts, franking and unknown events are not inferred. All franking rates remain null.

The independently owned `qa/audit.py` can audit the generated manifest, individual histories, all seven period returns, cash yields, splits, price-index semantics, and universe equality. No generated dataset should be published until both strict ingestion and that audit pass.
