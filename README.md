# ETF Atlas · 全球指数

A mobile-installable Chinese-language research app comparing mainstream Chinese, US and Australian ETFs and their index benchmarks.

## 使用

正式网址：https://blizzardoner.github.io/etf-atlas/

1. 在排行榜勾选多个 ETF / 指数，曲线以共同日期的 100 为起点进行比较。
2. 选择 1、3、6 个月或 1、3、5、10 年；排行榜可切换涨幅优先、跌幅优先和现金分配收益率。
3. 国家按上市市场区分；跨国收益按各自币种计算，不含汇率变化。
4. 分红筛选是过去 12 个月现金分配 / 最新完整交易日收盘价，不是未来收益承诺。Franking 未核实时显示未知。
5. ETF 与指数历史分开，上市时间不足的长期收益显示不可用，不拼接指数回测冒充 ETF 收益。
6. iPhone 用 Safari 打开，分享 → 添加到主屏幕。离线时可查看已缓存的行情和已加载的历史；未加载过的历史仍需联网。

更新工作流每日 UTC 07:30、22:30 运行，分别覆盖亚太及美股收盘。周末和休市日保留最后一个真实交易日，不生成虚假新报价。新旧行情按交易所日历、节假日和收盘时间校验；不以“距今天不到五天”冒充最新价格。校验失败时保留上一版线上应用与数据，缓存过期会显示滞后状态。每月独立维护 `maintenance/keepalive` 心跳分支，防止 GitHub 长期无仓库活动停用定时任务；该分支只有维护时间戳，不修改主分支、不提交每日行情。GitHub 调度可能延迟、公共接口可能限流；不承诺第三方服务无故障运行。

当 Yahoo 完整日线只缺最新已完成交易日的收盘字段时，管道会核对两个真实收盘证据：分钟接口的准确收盘时点报价，以及另一接口附带的当天收盘快照。只有代码、币种、交易日期、收盘时间和价格一致时，才补该日缺失字段，并保留补证链接及时间戳；不会把周 K 历史冒充日线，也不会猜测复权价格。证据不完整仍拒绝发布。

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
python -m unittest discover -s maintenance -p 'test_*.py'
python scripts/build_data.py --strict
npm test
npm run build
npm run preview
```

数据管道建议使用 Python 3.11 的项目独立 `.venv`。生产预览启动后，运行 `node qa/browser.cjs`、`node qa/race.cjs` 和 `node qa/details.cjs` 进行真实 Microsoft Edge 验收。当前 XSHG 节假日日历的已知范围有限；超出供应商已知日历会暂停发布，而不是猜测交易日。更新兼容版日历依赖后可以恢复。

See `CONTRACT.md` for schema and calculation rules. Production deployment is GitHub Pages via Actions. Public market-data providers can throttle, revise, or omit records; coverage and stale-data flags are shown rather than silently manufacturing observations. Data is for personal research and not suitable for order execution; upstream data rights and redistribution terms still apply.
