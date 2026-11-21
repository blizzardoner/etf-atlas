export const PERIODS = ["1m", "3m", "6m", "1y", "3y", "5y", "10y"] as const;
export type Period = (typeof PERIODS)[number];
export type Mode = "price" | "total";
export type Country = "CN" | "US" | "AU";
export interface Instrument {
  id: string;
  symbol: string;
  name: string;
  country: Country;
  kind: "etf" | "index";
  benchmark: string;
  currency: "CNY" | "USD" | "AUD";
  sourceUrl: string;
  historyUrl: string;
  firstDate: string;
  lastDate: string;
  expectedLastDate?: string;
  freshUntil?: string;
  calendar?: string;
  count: number;
  status: "fresh" | "stale" | "unavailable";
  close: number | null;
  dailyChange: number | null;
  cashYield: number | null;
  dividendStatus: "available" | "unavailable" | "no-distributions";
  frankingRate: number | null;
  returns: Record<Mode, Record<Period, number | null>>;
  error?: string;
}
export interface Market {
  offlineCached?: boolean;
  schemaVersion: 1;
  generatedAt: string;
  instruments: Instrument[];
  failures: { id: string; error: string }[];
  methodology: string[];
}
export interface Bar {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  adjustedClose: number | null;
  volume: number | null;
  rawClose?: number | null;
  rawOpen?: number | null;
  rawHigh?: number | null;
  rawLow?: number | null;
}
export interface History {
  priceComparisonUnavailable?: boolean;
  splitError?: string;
  id: string;
  sourceUrl: string;
  retrievedAt: string;
  adjustment: "provider-adjusted-close" | "none" | "split-normalized-price";
  bars: Bar[];
  dividends: { date: string; amount: number; sourceUrl?: string }[] | null;
  splits: { date: string; ratio: number }[];
  coverage: {
    firstDate: string;
    lastDate: string;
    count: number;
    complete: boolean;
    reason?: string;
  };
}
export interface Filters {
  search: string;
  country: "all" | Country;
  kind: "all" | "etf" | "index";
  yieldKnown: boolean;
  yieldMin: string;
  yieldMax: string;
}
