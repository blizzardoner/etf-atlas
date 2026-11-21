import { describe, it, expect } from "vitest";
import { compare, filterAndRank } from "./domain";
import { PERIODS, type Instrument, type Filters } from "./types";
const filters: Filters = {
  search: "",
  country: "all",
  kind: "all",
  yieldKnown: false,
  yieldMin: "",
  yieldMax: "",
};
const item = (
  id: string,
  yieldValue: number | null,
  ret: number | null,
  country: "AU" | "US" = "AU",
): Instrument =>
  ({
    id,
    symbol: id,
    name: id,
    country,
    kind: "etf",
    cashYield: yieldValue,
    returns: {
      price: Object.fromEntries(PERIODS.map((p) => [p, ret])),
      total: Object.fromEntries(PERIODS.map((p) => [p, ret])),
    },
  }) as Instrument;
it("filters markets and known dividend ranges then ranks all seven periods both ways with missing values last", () => {
  const items = [
    item("missing", null, null),
    item("low", 0.02, 0.01),
    item("high", 0.08, 0.1),
    item("us", 0.04, 0.05, "US"),
  ];
  for (const period of [...PERIODS, "cashYield"] as const) {
    expect(
      filterAndRank(items, filters, period, "price", "desc").map((i) => i.id),
    ).toEqual(["high", "us", "low", "missing"]);
    expect(
      filterAndRank(items, filters, period, "total", "asc").map((i) => i.id),
    ).toEqual(["low", "us", "high", "missing"]);
  }
  expect(
    filterAndRank(
      items,
      {
        ...filters,
        country: "AU",
        yieldKnown: true,
        yieldMin: "3",
        yieldMax: "9",
      },
      "1y",
      "price",
      "desc",
    ).map((i) => i.id),
  ).toEqual(["high"]);
  expect(
    filterAndRank(items, { ...filters, kind: "index" }, "1y", "price", "desc"),
  ).toEqual([]);
  expect(
    filterAndRank(
      items,
      { ...filters, search: "LOW" },
      "1y",
      "price",
      "desc",
    ).map((i) => i.id),
  ).toEqual(["low"]);
});
const history = (id: string, dates: string[], values: number[]) => ({
  id,
  bars: dates.map((date, i) => ({
    date,
    close: values[i],
    adjustedClose: values[i],
  })),
  coverage: { complete: true },
});
describe("comparison", () => {
  it("blocks unknown share-fold price basis and does not treat a price index adjusted close as total return", () => {
    const h = history("a", ["2025-01-02", "2025-01-03"], [100, 120]);
    expect(
      compare([{ ...h, priceComparisonUnavailable: true }], "all", "price")
        .error,
    ).toMatch(/share|份额/);
    expect(compare([{ ...h, kind: "index" }], "all", "total").error).toMatch(
      /index|指数/,
    );
  });
  it("uses calendar ranges and refuses partial total-return baselines", () => {
    const a = history(
      "a",
      ["2024-12-31", "2025-01-31", "2025-02-28"],
      [10, 20, 30],
    );
    expect(compare([a], "1m", "price").dates).toEqual([
      "2025-01-31",
      "2025-02-28",
    ]);
    const b = {
      ...a,
      bars: a.bars.map((bar) => ({ ...bar, adjustedClose: null })),
    };
    expect(compare([a, b], "all", "total").error).toMatch(/复权/);
    expect(
      compare([history("x", ["2000-01-01"], [1]), a], "all", "price").error,
    ).toMatch(/共同交易日/);
  });
  it("rebases every instrument at the same actual shared session, never its own inception", () => {
    const a = history(
      "a",
      ["2025-01-01", "2025-01-02", "2025-01-03"],
      [10, 20, 30],
    );
    const b = history("b", ["2025-01-02", "2025-01-03"], [40, 60]);
    const chart = compare([a, b], "all", "price");
    expect(chart.baseline).toBe("2025-01-02");
    expect(chart.dates).toEqual(["2025-01-02", "2025-01-03"]);
    expect(chart.series.map((s: any) => s.values)).toEqual([
      [100, 150],
      [100, 150],
    ]);
  });
});
