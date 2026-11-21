import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Globe2,
  RefreshCw,
  Layers3,
  ShieldCheck,
} from "lucide-react";
import { loadMarket } from "./api";
import {
  PERIODS,
  type Market,
  type Filters,
  type Period,
  type Mode,
} from "./types";
import { filterAndRank, assessFreshness } from "./domain";
import ComparisonPanel from "./ComparisonPanel";
import DetailsPanel from "./DetailsPanel";
import Methodology from "./Methodology";
import { useHistories, readSelection, saveSelection } from "./useHistories";
const DEFAULT_FILTERS: Filters = {
  search: "",
  country: "all",
  kind: "all",
  yieldKnown: false,
  yieldMin: "",
  yieldMax: "",
};
export const pct = (v: number | null | undefined, signed = false) =>
  v == null ? "—" : `${signed && v > 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
export default function App() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS),
    [sort, setSort] = useState<Period | "cashYield" | "dailyChange">("1y"),
    [direction, setDirection] = useState<"asc" | "desc">("desc"),
    [mode, setMode] = useState<Mode>("price");
  const updateFilter = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    setFilters((f) => ({ ...f, [key]: value }));
  const [snapshot, setMarket] = useState<Market | null>(null),
    [error, setError] = useState(""),
    [reload, setReload] = useState(0),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    const abort = new AbortController();
    let current = true;
    setLoading(true);
    setError("");
    loadMarket(abort.signal)
      .then((data) => {
        if (current) setMarket(data);
      })
      .catch((e) => {
        if (current) setError(String(e.message));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
      abort.abort();
    };
  }, [reload]);
  useEffect(() => {
    let lastRefresh = Date.now();
    const refresh = () => {
      if (
        document.visibilityState === "visible" &&
        navigator.onLine &&
        Date.now() - lastRefresh >= 60000
      ) {
        lastRefresh = Date.now();
        setReload((x) => x + 1);
      }
    };
    const timer = setInterval(() => {
      lastRefresh = 0;
      refresh();
    }, 15 * 60000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("online", refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener("online", refresh);
    };
  }, []);
  const [now, setNow] = useState(Date.now),
    [offline, setOffline] = useState(!navigator.onLine);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000);
    const update = () => setOffline(!navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      clearInterval(timer);
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  const freshness = snapshot ? assessFreshness(snapshot, now) : null;
  const market = freshness?.market ?? null;
  const [selected, setSelected] = useState<string[]>(readSelection),
    [retryHistory, setRetryHistory] = useState(0),
    [saveError, setSaveError] = useState(false);
  const toggle = (id: string) =>
    setSelected((s) =>
      s.includes(id) ? s.filter((x) => x !== id) : [...s, id],
    );
  useEffect(() => {
    setSaveError(!saveSelection(selected));
  }, [selected]);
  const selectedItems =
    market?.instruments.filter((i) => selected.includes(i.id)) ?? [];
  const [detailId, setDetailId] = useState<string | null>(null);
  const closeDetails = useCallback(() => setDetailId(null), []);
  const detailItem = market?.instruments.find((i) => i.id === detailId);
  const requestedItems =
    market?.instruments.filter(
      (i) => selected.includes(i.id) || i.id === detailId,
    ) ?? [];
  const histories = useHistories(
    requestedItems,
    market?.generatedAt ?? "",
    retryHistory,
  );
  const rows = filterAndRank(
    market?.instruments ?? [],
    filters,
    sort,
    mode,
    direction,
  );
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="./">
          <span className="brand-mark">
            <Activity size={25} />
          </span>
          <span>
            ETF<span className="brand-light"> ATLAS</span>
            <small>GLOBAL INVESTMENT INTELLIGENCE</small>
          </span>
        </a>
        <div className="header-right">
          <button
            className="refresh-button"
            aria-label="Refresh market data"
            disabled={loading}
            onClick={() => {
              setNow(Date.now());
              setReload((x) => x + 1);
            }}
          >
            <RefreshCw size={14} className={loading ? "spin" : ""} /> 刷新数据
          </button>
          <span className="market-clock">
            <span className="live-dot" /> 已完成交易日数据
          </span>
          <span className="version">RESEARCH TERMINAL / 01</span>
        </div>
      </header>
      <main>
        <section className="intro">
          <div>
            <div className="eyebrow">
              <Globe2 size={14} /> THREE MARKETS. ONE PERSPECTIVE.
            </div>
            <h1>
              全球指数，<span>一眼看清。</span>
            </h1>
            <p>
              横跨中国、美国与澳洲，追踪 ETF 与真实基准指数。
              <br className="desktop-break" />{" "}
              让价格表现与现金分红，各自说明问题。
            </p>
          </div>
          <div className="intro-note">
            <ShieldCheck size={20} />
            <span>
              真实来源，不造数据。
              <small>完整交易日 · 本币收益 · 不进行汇率换算</small>
            </span>
          </div>
        </section>
        {loading && !market ? (
          <div className="loading-state" role="status">
            <RefreshCw className="spin" /> 正在加载经过校验的市场快照…
          </div>
        ) : error && !market ? (
          <section className="error-panel" role="alert">
            <h2>市场数据暂不可用</h2>
            <p>{error}</p>
            <p>不会用示例价格填补缺失。请检查有效数据快照后重试。</p>
            <button
              className="primary"
              aria-label="Retry market data"
              onClick={() => setReload((x) => x + 1)}
            >
              <RefreshCw size={16} /> 重试市场数据
            </button>
          </section>
        ) : (
          market && (
            <>
              {error && (
                <div className="notice network-notice" role="alert">
                  刷新失败：{error} 正在保留上一份有效快照（{market.generatedAt}
                  ）。请稍后重试。
                </div>
              )}
              {(offline || market.offlineCached) && (
                <div className="notice network-notice" role="status">
                  当前离线 · 仅显示此前缓存的快照，无法保证最新行情。快照时间：
                  {market.generatedAt}；未缓存的历史不可用。
                </div>
              )}
              {freshness?.outdated && (
                <div className="notice network-notice" role="status">
                  {freshness.future
                    ? "数据日期晚于当前时间，请检查设备时钟与数据来源。"
                    : "快照已超过 5 个自然日或时间格式无效；行情是否滞后按各资产交易日历与到期时间判断，无日历元数据时采用五日回退。"}{" "}
                  数据快照：{market.generatedAt}
                </div>
              )}
              <section className="metrics">
                <div>
                  <span>研究资产库</span>
                  <strong>
                    {market.instruments.length}
                    <small> 个资产</small>
                  </strong>
                  <p>ETF 与独立价格指数</p>
                </div>
                <div>
                  <span>覆盖市场</span>
                  <strong>
                    CN <b>/</b> US <b>/</b> AU
                  </strong>
                  <p>当地上市市场 · 原始计价币种</p>
                </div>
                <div>
                  <span>数据健康</span>
                  <strong>
                    {
                      market.instruments.filter((i) => i.status === "fresh")
                        .length
                    }
                    <small> 已更新</small>
                  </strong>
                  <p>
                    {
                      market.instruments.filter((i) => i.status !== "fresh")
                        .length
                    }{" "}
                    项滞后或不可用
                  </p>
                </div>
                <div>
                  <span>快照更新时间</span>
                  <strong className="date-stat">
                    {new Date(market.generatedAt).toLocaleDateString("zh-CN", {
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                      timeZone: "UTC",
                    })}
                  </strong>
                  <p>
                    {new Date(market.generatedAt).toLocaleTimeString("en-GB", {
                      timeZone: "UTC",
                    })}{" "}
                    UTC
                  </p>
                </div>
              </section>
              {(market.failures.length > 0 ||
                market.instruments.some((i) => i.status !== "fresh")) && (
                <details className="health-details" open>
                  <summary>
                    来源与覆盖提醒 ·{" "}
                    {
                      market.instruments.filter((i) => i.status !== "fresh")
                        .length
                    }{" "}
                    项数据滞后或不可用
                  </summary>
                  <p>
                    表格保留上次可验证数据，并展示来源交易日。滞后记录不会被升级为最新数据；缺失收益以
                    — 标记。
                  </p>
                  {market.failures.map((f, n) => (
                    <p key={`${f.id}-${n}`}>
                      {market.instruments.find((i) => i.id === f.id)?.symbol ??
                        f.id}
                      ：{f.error}
                    </p>
                  ))}
                  {market.instruments
                    .filter(
                      (i) =>
                        i.error && !market.failures.some((f) => f.id === i.id),
                    )
                    .map((i) => (
                      <p key={i.id}>
                        {i.symbol}：{i.error}
                      </p>
                    ))}
                </details>
              )}
              {saveError && (
                <div className="notice" role="status">
                  本机存储不可用，当前选择无法在刷新后恢复。
                </div>
              )}
              <ComparisonPanel
                items={selectedItems}
                data={histories.data}
                errors={histories.errors}
                loading={histories.loading}
                mode={mode}
                remove={(id) => setSelected((s) => s.filter((x) => x !== id))}
                clear={() => setSelected([])}
                retry={() => setRetryHistory((x) => x + 1)}
              />
              <section className="panel universe">
                <div className="panel-heading">
                  <div>
                    <div className="eyebrow">02 / 研究资产库</div>
                    <h2>
                      市场排行榜{" "}
                      <span className="count-pill">
                        {rows.length} / {market.instruments.length}
                      </span>
                    </h2>
                  </div>
                  <div className="segmented" aria-label="Return basis">
                    <button
                      aria-pressed={mode === "price"}
                      aria-label="Price return"
                      onClick={() => setMode("price")}
                    >
                      价格涨跌幅
                    </button>
                    <button
                      aria-pressed={mode === "total"}
                      aria-label="Total return"
                      onClick={() => setMode("total")}
                    >
                      含分红总回报
                    </button>
                  </div>
                </div>
                <div className="filter-bar">
                  <label className="search-field">
                    <span>搜索资产</span>
                    <input
                      aria-label="Search instruments"
                      placeholder="代码、名称或跟踪基准…"
                      value={filters.search}
                      onChange={(e) => updateFilter("search", e.target.value)}
                    />
                  </label>
                  <label>
                    <span>上市市场</span>
                    <select
                      aria-label="Country"
                      value={filters.country}
                      onChange={(e) =>
                        updateFilter(
                          "country",
                          e.target.value as Filters["country"],
                        )
                      }
                    >
                      <option value="all">全部市场</option>
                      <option value="CN">中国 · CN</option>
                      <option value="US">美国 · US</option>
                      <option value="AU">澳洲 · AU</option>
                    </select>
                  </label>
                  <label>
                    <span>资产类型</span>
                    <select
                      aria-label="Instrument kind"
                      value={filters.kind}
                      onChange={(e) =>
                        updateFilter("kind", e.target.value as Filters["kind"])
                      }
                    >
                      <option value="all">ETF 与指数</option>
                      <option value="etf">仅 ETF</option>
                      <option value="index">仅指数</option>
                    </select>
                  </label>
                  <label>
                    <span>最低现金收益率 %</span>
                    <input
                      type="number"
                      min="0"
                      step="0.1"
                      aria-label="Minimum cash yield (%)"
                      placeholder="不限"
                      value={filters.yieldMin}
                      onChange={(e) => updateFilter("yieldMin", e.target.value)}
                    />
                  </label>
                  <label>
                    <span>最高现金收益率 %</span>
                    <input
                      type="number"
                      min="0"
                      step="0.1"
                      aria-label="Maximum cash yield (%)"
                      placeholder="不限"
                      value={filters.yieldMax}
                      onChange={(e) => updateFilter("yieldMax", e.target.value)}
                    />
                  </label>
                </div>
                <div className="ranking-bar">
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={filters.yieldKnown}
                      onChange={(e) =>
                        updateFilter("yieldKnown", e.target.checked)
                      }
                    />{" "}
                    只看已知现金收益率
                  </label>
                  <button
                    className="text-button"
                    aria-label="Reset filters"
                    onClick={() => setFilters(DEFAULT_FILTERS)}
                  >
                    重置筛选
                  </button>
                  <div className="sort-controls">
                    <label>
                      排序周期{" "}
                      <select
                        aria-label="Ranking period"
                        value={sort}
                        onChange={(e) => setSort(e.target.value as typeof sort)}
                      >
                        {PERIODS.map((p) => (
                          <option key={p} value={p}>
                            {p.toUpperCase()} 收益
                          </option>
                        ))}
                        <option value="cashYield">现金收益率（TTM）</option>
                        <option value="dailyChange">单日涨跌幅</option>
                      </select>
                    </label>
                    <button
                      className="sort-button"
                      aria-label={
                        direction === "desc"
                          ? "Sort ascending"
                          : "Sort descending"
                      }
                      onClick={() =>
                        setDirection((d) => (d === "desc" ? "asc" : "desc"))
                      }
                    >
                      {direction === "desc" ? "↓ 从高到低" : "↑ 从低到高"}
                    </button>
                  </div>
                </div>
                <div
                  className="table-scroll"
                  tabIndex={0}
                  aria-label="Scrollable market ranking"
                >
                  <table>
                    <thead>
                      <tr>
                        <th className="select-cell">对比</th>
                        <th>资产</th>
                        <th>最近收盘</th>
                        <th>
                          <button
                            onClick={() => {
                              setSort("dailyChange");
                              setDirection(
                                sort === "dailyChange" && direction === "desc"
                                  ? "asc"
                                  : "desc",
                              );
                            }}
                          >
                            单日
                          </button>
                        </th>
                        {PERIODS.map((p) => (
                          <th
                            key={p}
                            aria-sort={
                              sort === p
                                ? direction === "desc"
                                  ? "descending"
                                  : "ascending"
                                : "none"
                            }
                            className={sort === p ? "active-column" : ""}
                          >
                            <button
                              aria-label={`Rank ${p.toUpperCase()}`}
                              onClick={() => {
                                setSort(p);
                                setDirection(
                                  sort === p && direction === "desc"
                                    ? "asc"
                                    : "desc",
                                );
                              }}
                            >
                              {p.toUpperCase()}
                              {sort === p
                                ? direction === "desc"
                                  ? " ↓"
                                  : " ↑"
                                : ""}
                            </button>
                          </th>
                        ))}
                        <th>
                          <button
                            onClick={() => {
                              setSort("cashYield");
                              setDirection(
                                sort === "cashYield" && direction === "desc"
                                  ? "asc"
                                  : "desc",
                              );
                            }}
                          >
                            现金收益率
                          </button>
                        </th>
                        <th>数据状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((i) => (
                        <tr
                          key={i.id}
                          className={
                            selected.includes(i.id) ? "selected-row" : ""
                          }
                        >
                          <td className="select-cell">
                            <label className="row-check">
                              <input
                                type="checkbox"
                                aria-label={`Compare ${i.symbol}`}
                                checked={selected.includes(i.id)}
                                onChange={() => toggle(i.id)}
                              />
                            </label>
                          </td>
                          <td>
                            <button
                              className="instrument-button"
                              aria-label={`Details ${i.symbol}`}
                              onClick={() => setDetailId(i.id)}
                            >
                              <strong>
                                {i.symbol}
                                <span className={`country-chip ${i.country}`}>
                                  {i.country}
                                </span>
                                <ArrowUpRight size={13} />
                              </strong>
                              <span>{i.name}</span>
                              <small>
                                {i.kind === "index" ? "价格指数" : "ETF"} ·{" "}
                                {i.benchmark}
                              </small>
                            </button>
                          </td>
                          <td>
                            {i.close?.toFixed(
                              i.country === "CN" && i.kind === "etf" ? 3 : 2,
                            ) ?? "—"}
                            <small className="currency">{i.currency}</small>
                          </td>
                          <td
                            className={
                              i.dailyChange == null
                                ? "missing"
                                : i.dailyChange >= 0
                                  ? "positive"
                                  : "negative"
                            }
                          >
                            {pct(i.dailyChange, true)}
                          </td>
                          {PERIODS.map((p) => (
                            <td
                              key={p}
                              className={`${sort === p ? "active-column " : ""}${i.returns[mode][p] == null ? "missing" : i.returns[mode][p]! >= 0 ? "positive" : "negative"}`}
                              title={
                                i.returns[mode][p] == null
                                  ? "不可用：历史不足或复权数据缺失"
                                  : `${p} ${mode === "price" ? "价格涨跌幅（份额拆并调整，不含现金分红）" : "含分红总回报"}`
                              }
                            >
                              {pct(i.returns[mode][p], true)}
                            </td>
                          ))}
                          <td
                            className="yield-cell"
                            title={
                              i.cashYield === null
                                ? "现金收益率未知，不等于零。"
                                : "过去完整 12 个月现金分配 ÷ 最近收盘价，不是收益预测"
                            }
                          >
                            {pct(i.cashYield)}
                            <small>
                              {i.cashYield === null ? "未知" : "过去12个月"}
                            </small>
                          </td>
                          <td>
                            <span
                              className={`status ${{ fresh: "已更新", stale: "数据滞后", unavailable: "不可用" }[i.status]}`}
                            >
                              {
                                {
                                  fresh: "已更新",
                                  stale: "数据滞后",
                                  unavailable: "不可用",
                                }[i.status]
                              }
                            </span>
                            <small className="as-of">{i.lastDate}</small>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!rows.length && (
                    <div className="no-results">
                      没有符合当前筛选条件的资产。
                    </div>
                  )}
                </div>
                <div className="table-footnote">
                  价格涨跌幅已按份额拆并调整，不含现金分红。所有收益为累计值，非年化。—
                  表示数据不可用，不是零。点击代码查看来源和分红；左右滑动查看全部周期。
                </div>
              </section>
              <Methodology source={market.methodology} />
            </>
          )
        )}
      </main>
      <footer>
        <span className="footer-brand">
          ETF ATLAS <span> / </span> 以数据为据。
        </span>
        <span>仅供研究，不构成投资建议。</span>
      </footer>
      {detailItem && (
        <DetailsPanel
          item={detailItem}
          history={histories.data[detailItem.id]}
          error={histories.errors[detailItem.id]}
          loading={histories.loading}
          close={closeDetails}
          retry={() => setRetryHistory((x) => x + 1)}
        />
      )}
    </div>
  );
}
