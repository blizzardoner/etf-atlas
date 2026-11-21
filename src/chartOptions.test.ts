import { it, expect } from "vitest";
import { chartOptions } from "./chartOptions";
it("renders real daily multiple series with gaps, a rebased tooltip and both slider and gesture zoom", () => {
  const comparison = {
    dates: ["2025-01-02", "2025-01-03"],
    series: [
      { id: "a", values: [100, 120] },
      { id: "b", values: [100, null] },
    ],
    baseline: "2025-01-02",
  };
  const option = chartOptions(comparison, [
    { id: "a", symbol: "AAA" },
    { id: "b", symbol: "BBB" },
  ]);
  expect(option.series.map((s: any) => s.data)).toEqual([
    [100, 120],
    [100, null],
  ]);
  expect(option.series.every((s: any) => s.connectNulls === false)).toBe(true);
  expect(option.xAxis.data).toEqual(comparison.dates);
  expect(option.dataZoom.map((z: any) => z.type)).toEqual(["inside", "slider"]);
  expect(option.tooltip.trigger).toBe("axis");
  expect(option.tooltip.valueFormatter(120)).toContain("+20.00%");
  expect(option.tooltip.valueFormatter(null)).toContain("unavailable");
});
