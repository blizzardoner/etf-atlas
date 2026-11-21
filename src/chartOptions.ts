import type { Comparison } from "./domain";
import type { Instrument } from "./types";
export const COLORS = [
  "#48e1d5",
  "#eac27a",
  "#92a2ff",
  "#ff8c9e",
  "#a4d986",
  "#c392e9",
  "#77bcf3",
  "#eeab80",
];
export function chartOptions(
  chart: Comparison,
  items: Pick<Instrument, "id" | "symbol">[],
) {
  return {
    animation: false,
    color: COLORS,
    backgroundColor: "transparent",
    aria: { enabled: true },
    tooltip: {
      trigger: "axis",
      renderMode: "richText",
      confine: true,
      backgroundColor: "#15212b",
      borderColor: "#334652",
      textStyle: { color: "#e5eef3", fontSize: 12 },
      axisPointer: { type: "cross", label: { backgroundColor: "#263a46" } },
      valueFormatter: (v: unknown) =>
        v == null
          ? "数据不可用 / unavailable"
          : `${Number(v).toFixed(2)} · ${Number(v) >= 100 ? "+" : ""}${(Number(v) - 100).toFixed(2)}%`,
    },
    grid: { left: 55, right: 24, top: 25, bottom: 73 },
    xAxis: {
      type: "category",
      data: chart.dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#263640" } },
      axisTick: { show: false },
      axisLabel: {
        color: "#8b9eac",
        hideOverlap: true,
        formatter: (date: string) => date.slice(0, 7),
      },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { color: "#8b9eac", formatter: (v: number) => v.toFixed(0) },
      splitLine: { lineStyle: { color: "#1c2a33", type: "dashed" } },
    },
    dataZoom: [
      {
        type: "inside",
        start: 0,
        end: 100,
        zoomOnMouseWheel: "ctrl",
        moveOnMouseWheel: false,
      },
      {
        type: "slider",
        start: 0,
        end: 100,
        bottom: 13,
        height: 22,
        borderColor: "#2b3b44",
        backgroundColor: "#0c141d",
        fillerColor: "rgba(72,225,213,.08)",
        handleStyle: { color: "#48e1d5", borderColor: "#48e1d5" },
        textStyle: { color: "#8b9eac" },
        dataBackground: {
          lineStyle: { color: "#48616c" },
          areaStyle: { color: "#243941" },
        },
        selectedDataBackground: {
          lineStyle: { color: "#48e1d5" },
          areaStyle: { color: "#2a6865" },
        },
      },
    ],
    series: chart.series.map((s, i) => ({
      id: s.id,
      name: items.find((x) => x.id === s.id)?.symbol ?? s.id,
      type: "line",
      data: s.values,
      showSymbol: false,
      connectNulls: false,
      sampling: "lttb",
      lineStyle: { width: 2.3, color: COLORS[i % 8] },
      emphasis: { focus: "series" },
      markLine:
        i === 0
          ? {
              silent: true,
              symbol: "none",
              label: { show: false },
              lineStyle: { color: "#617481", type: "dashed", width: 1 },
              data: [{ yAxis: 100 }],
            }
          : undefined,
    })),
  };
}
