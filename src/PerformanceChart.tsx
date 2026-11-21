import { useEffect, useRef } from "react";
import { init, use, type ECharts } from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  AriaComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import type { Comparison } from "./domain";
import type { Instrument } from "./types";
import { chartOptions } from "./chartOptions";
use([
  LineChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  AriaComponent,
  SVGRenderer,
]);
export default function PerformanceChart({
  chart,
  items,
}: {
  chart: Comparison;
  items: Instrument[];
}) {
  const element = useRef<HTMLDivElement>(null),
    instance = useRef<ECharts | null>(null);
  useEffect(() => {
    if (!element.current) return;
    const c = init(element.current, undefined, { renderer: "svg" });
    instance.current = c;
    const observer = new ResizeObserver(() => c.resize());
    observer.observe(element.current);
    return () => {
      observer.disconnect();
      c.dispose();
      instance.current = null;
    };
  }, []);
  useEffect(() => {
    instance.current?.setOption(chartOptions(chart, items), { notMerge: true });
  }, [chart, items]);
  function zoom(action: "in" | "out" | "reset") {
    const c = instance.current;
    if (!c) return;
    const option = c.getOption() as {
      dataZoom?: { start: number; end: number }[];
    };
    const z = option.dataZoom?.[0] ?? { start: 0, end: 100 };
    const width = z.end - z.start,
      center = (z.start + z.end) / 2;
    const next =
      action === "reset"
        ? 100
        : Math.max(2, Math.min(100, width * (action === "in" ? 0.6 : 1.7)));
    const start =
      action === "reset"
        ? 0
        : Math.max(0, Math.min(100 - next, center - next / 2));
    c.dispatchAction({ type: "dataZoom", start, end: start + next });
  }
  return (
    <div aria-label="Performance comparison chart">
      <div className="chart-actions">
        <span>拖动底部滑块 · 双指缩放 · Ctrl + 滚轮</span>
        <div>
          <button aria-label="Zoom in" onClick={() => zoom("in")}>
            放大 +
          </button>
          <button aria-label="Zoom out" onClick={() => zoom("out")}>
            缩小 −
          </button>
          <button aria-label="Reset zoom" onClick={() => zoom("reset")}>
            重置视图
          </button>
        </div>
      </div>
      <div
        className="chart-container"
        ref={element}
        role="img"
        aria-label={`多资产表现图，共同基准 ${chart.baseline}，${items.map((i) => i.symbol).join("、")}`}
      />
    </div>
  );
}
