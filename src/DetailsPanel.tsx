import { useEffect, useRef } from "react";
import { Download, ExternalLink, RefreshCw, X } from "lucide-react";
import type { History, Instrument } from "./types";
import { downloadHistory, safeSource } from "./downloads";
const pct = (v: number | null) =>
  v === null ? "未知" : `${(v * 100).toFixed(2)}%`;
export default function DetailsPanel({
  item,
  history,
  error,
  loading,
  close,
  retry,
}: {
  item: Instrument;
  history?: History;
  error?: string;
  loading: boolean;
  close: () => void;
  retry: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null),
    closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null,
      overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButton.current?.focus();
    function key(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
      if (e.key === "Tab") {
        const els = panel.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),a[href],input,select,[tabindex="0"]',
        );
        if (!els?.length) return;
        const first = els[0],
          last = els[els.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", key);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [close]);
  const dividends = history?.dividends;
  return (
    <div
      className="drawer-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        className="detail-drawer"
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="detail-title"
      >
        <div className="drawer-top">
          <span className="eyebrow">INSTRUMENT BRIEF / 资产档案</span>
          <button
            className="icon-button"
            ref={closeButton}
            onClick={close}
            aria-label="Close details"
          >
            <X size={21} />
          </button>
        </div>
        <h2 id="detail-title">
          {item.symbol}
          <span className={`country-chip ${item.country}`}>{item.country}</span>
        </h2>
        <p className="detail-name">{item.name}</p>
        <div className="detail-tags">
          <span>{item.kind === "etf" ? "交易所交易基金" : "价格指数"}</span>
          <span>{item.currency}</span>
          <span className={`status ${item.status}`}>
            {
              { fresh: "已更新", stale: "数据滞后", unavailable: "不可用" }[
                item.status
              ]
            }
          </span>
        </div>
        <p className="benchmark-note">
          跟踪基准 <strong>{item.benchmark}</strong>
        </p>
        <div className="detail-metrics">
          <div>
            <span>最近收盘</span>
            <strong>
              {item.close?.toFixed(
                item.country === "CN" && item.kind === "etf" ? 3 : 2,
              ) ?? "—"}
            </strong>
            <small>
              {item.lastDate} · {item.currency}
            </small>
          </div>
          <div>
            <span>过去 12 个月现金收益率</span>
            <strong>{pct(item.cashYield)}</strong>
            <small>历史分配，不是未来预测</small>
          </div>
          <div>
            <span>Franking · 抵税比例</span>
            <strong>
              {item.frankingRate === null
                ? "抵税比例未知"
                : pct(item.frankingRate)}
            </strong>
            <small>未知不等于 0，不估算税后回报</small>
          </div>
          <div>
            <span>历史覆盖</span>
            <strong>
              {(history?.coverage.count ?? item.count).toLocaleString()}{" "}
              <small>交易日</small>
            </strong>
            <small>
              {history?.coverage.firstDate ?? item.firstDate} →{" "}
              {history?.coverage.lastDate ?? item.lastDate}
            </small>
          </div>
        </div>
        {item.error && (
          <p className="notice" role="alert">
            {item.error}
          </p>
        )}
        <section className="detail-section">
          <h3>来源与口径</h3>
          <a
            className="source-link"
            href={safeSource(item.sourceUrl)}
            target="_blank"
            rel="noopener noreferrer"
          >
            打开原始价格来源 <ExternalLink size={14} />
          </a>
          {history && (
            <>
              <p>获取时间：{history.retrievedAt}</p>
              <p>
                {history.adjustment === "provider-adjusted-close"
                  ? "价格已按份额拆并调整；总回报采用供应商复权收盘价，仅在确实可用时展示。"
                  : history.adjustment === "split-normalized-price"
                    ? "价格涨跌幅已按份额拆并调整，不含现金分红。原始成交价格保留在完整历史下载中。"
                    : "价格收益不包含现金分红；无可验证的总回报数据。"}
              </p>
              <p>
                {history.coverage.complete
                  ? "来源声明的完整日线历史"
                  : "覆盖不完整：" +
                    (history.coverage.reason ?? "上游来源存在缺口")}
              </p>
              {!!history.splits.length && (
                <p>
                  记录到 {history.splits.length}{" "}
                  次份额拆并事件；明细保留在下载文件。
                </p>
              )}
            </>
          )}
        </section>
        <section className="detail-section">
          <div className="detail-section-head">
            <h3>现金分红明细</h3>
            <span>除息日 · 每份金额</span>
          </div>
          {loading && !history ? (
            <p className="loading-inline" role="status">
              <RefreshCw className="spin" size={16} /> 正在读取完整历史…
            </p>
          ) : error && !history ? (
            <div role="alert">
              <p>{error}</p>
              <button className="primary" onClick={retry}>
                重试历史数据
              </button>
            </div>
          ) : dividends === null || item.dividendStatus === "unavailable" ? (
            <div className="unknown-box">
              分红历史不可用
              <p>上游未提供可验证的分红事件。现金收益率缺失不代表没有分红。</p>
            </div>
          ) : dividends?.length ? (
            <div className="dividend-scroll">
              <table className="dividend-table">
                <thead>
                  <tr>
                    <th>除息日</th>
                    <th>每份分配 · {item.currency}</th>
                  </tr>
                </thead>
                <tbody>
                  {[...dividends].reverse().map((d, i) => (
                    <tr key={`${d.date}-${i}`}>
                      <td>{d.date}</td>
                      <td>
                        {d.amount.toLocaleString("en-US", {
                          maximumFractionDigits: 6,
                        })}
                        {d.sourceUrl && (
                          <a
                            href={safeSource(d.sourceUrl)}
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label={`Dividend source ${d.date}`}
                          >
                            <ExternalLink size={12} />
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : history ? (
            <div className="unknown-box">
              {item.dividendStatus === "no-distributions"
                ? "来源明确报告无现金分配。"
                : "来源事件列表为空；不将缺失解读为零收益。"}
            </div>
          ) : null}
        </section>
        <div className="drawer-download">
          <button
            className="primary"
            aria-label="Download full history JSON"
            disabled={!history}
            onClick={() => history && downloadHistory(history)}
          >
            <Download size={17} /> 下载完整日线与分红 JSON
          </button>
          <p>
            包含全部历史、现金分配、拆并、覆盖与来源元数据。下载不受图表周期或缩放限制。
          </p>
        </div>
      </div>
    </div>
  );
}
