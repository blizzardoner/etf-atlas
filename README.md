# ETF Atlas · 全球指数

A mobile-installable Chinese-language research app comparing mainstream Chinese, US and Australian ETFs and their index benchmarks.

## Product contract

- Full obtainable daily history since each instrument's own inception; benchmark indexes are separate instruments, not backfilled ETF returns.
- One chart compares multiple selections rebased at a common start, with local-currency price and dividend-adjusted modes.
- Rankings for 1 / 3 / 6 months and 1 / 3 / 5 / 10 years. Country, ETF/index, cash distribution yield filters and ascending/descending sorting.
- Trailing 12-month cash distribution yield is **not** forecast yield, ordinary annual income, tax-adjusted yield, or franking credits. Unknown data stays unknown.
- Daily scheduled server-side ingestion; generated market snapshots are deployment artifacts, not daily code commits.
- No accounts, brokerage credentials, or trading actions. Saved selections stay on device.

## Development

```sh
npm ci
python -m pip install -r requirements.txt
python -m unittest discover -s scripts -p 'test_*.py'
python scripts/build_data.py
npm test
npm run build
npm run preview
```

See `CONTRACT.md` for schema and calculation rules. Production deployment is GitHub Pages via Actions. Public market-data providers can throttle, revise, or omit records; coverage and stale-data flags are shown rather than silently manufacturing observations. Data is for personal research and not suitable for order execution; upstream data rights and redistribution terms still apply.
