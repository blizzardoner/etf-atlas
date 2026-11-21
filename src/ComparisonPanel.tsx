import { Activity, Layers3, RefreshCw, X } from "lucide-react";
import { lazy, Suspense, useMemo, useState } from "react";
const PerformanceChart = lazy(() => import("./PerformanceChart"));
import { compare } from "./domain";
import {
  PERIODS,
  type Instrument,
  type History,
  type Mode,
  type Period,
} from "./types";
interface Props {
  items: Instrument[];
  data: Record<string, History>;
  errors: Record<string, string>;
  loading: boolean;
  mode: Mode;
  remove: (id: string) => void;
  clear: () => void;
  retry: () => void;
}
export default function ComparisonPanel({
  items,
  data,
  errors,
  loading,
  mode,
  remove,
  clear,
  retry,
}: Props) {
  const [period, setPeriod] = useState<Period | "all">("1y");
  const chart = useMemo(
    () =>
      compare(
        items.flatMap((i) =>
          data[i.id]
            ? [
                {
                  ...data[i.id],
                  kind: i.kind,
                  totalReturnAvailable: Object.values(i.returns.total).some(
                    (v) => v !== null,
                  ),
                },
              ]
            : [],
        ),
        period,
        mode,
      ),
    [items, data, period, mode],
  );
  const complete = items.every((i) => data[i.id]);
  return (
    <section className="panel comparison-panel" id="comparison">
      <div className="panel-heading">
        <div>
          <div className="eyebrow">01 / PERFORMANCE LAB</div>
          <h2>
            <Layers3 size={20} /> 多资产同图
          </h2>
        </div>
        <span className="subtle-tag">共同基准 · 100</span>
      </div>
      <div className="chart-toolbar">
        <div className="periods" aria-label="Chart period">
          {[...PERIODS, "all"].map((p) => (
            <button
              key={p}
              aria-label={`Chart period ${p.toUpperCase()}`}
              aria-pressed={period === p}
              onClick={() => setPeriod(p as Period | "all")}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>
        <span className="chart-basis">
          {mode === "price"
            ? "价格涨跌幅 · 不含现金分红"
            : "含分红总回报 · 复权收盘"}
        </span>
      </div>
      <div className="selection-strip">
        {items.map((i, n) => (
          <button
            className="selection-chip"
            key={i.id}
            onClick={() => remove(i.id)}
            aria-label={`Remove ${i.symbol} from comparison`}
          >
            <span className={`series-dot series-${n % 8}`} />
            {i.symbol}
            <X size={13} />
          </button>
        ))}
        {!!items.length && (
          <button
            className="text-button"
            onClick={clear}
            aria-label="Clear comparison"
          >
            清空对比
          </button>
        )}
        <span className="selection-help">
          {items.length
            ? `已选 ${items.length} 项 · 自动保存在本机`
            : "从下方市场排行榜勾选资产"}
        </span>
      </div>
      {!items.length ? (
        <div className="chart-empty">
          <div className="empty-orbit">
            <Activity size={32} />
          </div>
          <h3>勾选资产，开启历史对比。</h3>
          <p>真实每日历史，同一天归一为 100，让市场表现更可比。</p>
        </div>
      ) : loading ? (
        <div className="chart-empty" role="status">
          <RefreshCw className="spin" />
          <h3>正在读取完整日线历史…</h3>
          <p>图表仅展示你最新选择的资产组合。</p>
        </div>
      ) : !complete ? (
        <div className="chart-empty" role="alert">
          <h3>部分所选资产的历史不可用。</h3>
          {Object.entries(errors)
            .filter(([id]) => items.some((i) => i.id === id))
            .map(([id, error]) => (
              <p key={id}>
                {items.find((i) => i.id === id)?.symbol}: {error}
              </p>
            ))}
          <p>不会以不完整组合替代当前选择。</p>
          <button
            className="primary"
            onClick={retry}
            aria-label="Retry histories"
          >
            重试历史数据
          </button>
        </div>
      ) : chart.error ? (
        <div className="chart-empty" role="alert">
          <h3>{chart.error}</h3>
          <p>请切换价格收益或调整资产选择。缺失数据不会被 估算。</p>
        </div>
      ) : (
        <>
          <div className="comparison-summary">
            {chart.series.map((s, n) => {
              const end = s.values.at(-1);
              return (
                <div key={s.id}>
                  <span>
                    <i className={`series-dot series-${n % 8}`} />
                    {items.find((i) => i.id === s.id)?.symbol}
                  </span>
                  <strong data-testid={`comparison-end-${s.id}`}>
                    {end == null
                      ? "—"
                      : `${end >= 100 ? "+" : ""}${(end - 100).toFixed(2)}%`}
                  </strong>
                  <small>共同基准以来的累计表现</small>
                </div>
              );
            })}
          </div>
          <Suspense
            fallback={
              <div className="chart-empty" role="status">
                正在加载图表引擎…
              </div>
            }
          >
            <PerformanceChart chart={chart} items={items} />
          </Suspense>
          <div className="chart-caption">
            <span>
              共同基准： {chart.baseline} = 100 <b>→</b> {chart.end}
            </span>
            <span>本币收益 · 未进行汇率换算</span>
          </div>
          {chart.shortened && (
            <p className="notice">
              所选周期受共同历史覆盖限制，已缩短至实际可比区间。不会补造
              更早的数据。
            </p>
          )}
          {items.map(
            (i) =>
              data[i.id] &&
              !data[i.id].coverage.complete && (
                <p className="notice" key={i.id}>
                  {i.symbol}: 覆盖不完整 —{" "}
                  {data[i.id].coverage.reason ?? "来源历史存在缺口"}
                </p>
              ),
          )}
        </>
      )}
    </section>
  );
}
