import { PERIODS, type Instrument, type History, type Market } from "../types";
export const instrument = (
  id = "AAA",
  country: Instrument["country"] = "US",
  cashYield: number | null = 0.03,
): Instrument => ({
  id,
  symbol: id,
  name: `${id} fund`,
  country,
  kind: "etf",
  benchmark: "Broad market",
  currency: country === "AU" ? "AUD" : country === "CN" ? "CNY" : "USD",
  sourceUrl: "https://example.test/source",
  historyUrl: `data/history/${id}.json`,
  firstDate: "2020-01-02",
  lastDate: "2025-01-03",
  count: 3,
  status: "fresh",
  close: 120,
  dailyChange: 0.02,
  cashYield,
  dividendStatus: "available",
  frankingRate: null,
  returns: {
    price: Object.fromEntries(
      PERIODS.map((p) => [p, 0.2]),
    ) as Instrument["returns"]["price"],
    total: Object.fromEntries(
      PERIODS.map((p) => [p, 0.3]),
    ) as Instrument["returns"]["total"],
  },
});
export const history = (id = "AAA", end = 120): History => ({
  id,
  sourceUrl: "https://example.test/source",
  retrievedAt: "2025-01-04T00:00:00Z",
  adjustment: "provider-adjusted-close",
  bars: ["2020-01-02", "2025-01-02", "2025-01-03"].map((date, i) => ({
    date,
    open: 100,
    high: 130,
    low: 90,
    close: i === 2 ? end : 100,
    adjustedClose: i === 2 ? end : 100,
    volume: 1000,
  })),
  dividends: [{ date: "2024-12-02", amount: 1.2 }],
  splits: [],
  coverage: {
    firstDate: "2020-01-02",
    lastDate: "2025-01-03",
    count: 3,
    complete: true,
  },
});
export const market = (
  items = [instrument(), instrument("BBB", "AU", null)],
): Market => ({
  schemaVersion: 1,
  generatedAt: "2025-01-04T00:00:00Z",
  instruments: items,
  failures: [],
  methodology: ["Completed daily exchange sessions."],
});
