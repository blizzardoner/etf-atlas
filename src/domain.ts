import type { Mode, Period, Instrument, Filters } from "./types";
export function filterAndRank(
  items: Instrument[],
  f: Filters,
  sort: Period | "cashYield" | "dailyChange",
  mode: Mode,
  direction: "asc" | "desc",
): Instrument[] {
  const value = (i: Instrument) =>
    sort === "cashYield" || sort === "dailyChange"
      ? i[sort]
      : i.returns[mode][sort];
  return items
    .filter((i) => {
      const term = f.search.trim().toLocaleLowerCase();
      if (
        term &&
        !`${i.symbol} ${i.name} ${i.benchmark ?? ""}`
          .toLocaleLowerCase()
          .includes(term)
      )
        return false;
      if (
        (f.country !== "all" && i.country !== f.country) ||
        (f.kind !== "all" && i.kind !== f.kind)
      )
        return false;
      if (
        (f.yieldKnown || f.yieldMin !== "" || f.yieldMax !== "") &&
        i.cashYield === null
      )
        return false;
      if (f.yieldMin !== "" && i.cashYield! < Number(f.yieldMin) / 100)
        return false;
      if (f.yieldMax !== "" && i.cashYield! > Number(f.yieldMax) / 100)
        return false;
      return true;
    })
    .sort((a, b) => {
      const av = value(a),
        bv = value(b);
      if (av == null && bv == null) return a.symbol.localeCompare(b.symbol);
      if (av == null) return 1;
      if (bv == null) return -1;
      return (
        (av - bv) * (direction === "asc" ? 1 : -1) ||
        a.symbol.localeCompare(b.symbol)
      );
    });
}
function validSessionDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const time = Date.parse(value + "T00:00:00Z");
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value;
}
function zonedTimestamp(value: unknown): number {
  if (typeof value !== "string") return NaN;
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!match || !validSessionDate(match[1]) || Number(match[2]) > 23 || Number(match[3]) > 59 || Number(match[4]) > 59) return NaN;
  return Date.parse(value);
}
export function assessFreshness(source: import("./types").Market, now: number) {
  const day = 86400000,
    generated = zonedTimestamp(source.generatedAt),
    today = new Date(now).toISOString().slice(0, 10);
  const future =
    generated > now ||
    source.instruments.some((i) => i.lastDate > today);
  const outdated =
    !Number.isFinite(generated) || now - generated > 5 * day || future;
  const instruments = source.instruments.map((i) => {
    // Any calendar field opts into validation; partial metadata must not use legacy fallback.
    const hasCalendar = ["calendar", "expectedLastDate", "freshUntil"].some(key => key in i);
    const expiry = zonedTimestamp(i.freshUntil);
    const quoteStale = hasCalendar
      ? typeof i.calendar !== "string" || !i.calendar.trim() ||
        !validSessionDate(i.expectedLastDate) || i.expectedLastDate !== i.lastDate ||
        !Number.isFinite(expiry) || now >= expiry
      : outdated || now - Date.parse(i.lastDate + "T00:00:00Z") > 5 * day;
    return i.status === "fresh" &&
      (!Number.isFinite(generated) || future || quoteStale || !validSessionDate(i.lastDate) || i.lastDate > today)
      ? { ...i, status: "stale" as const }
      : i;
  });
  return { market: { ...source, instruments }, outdated, future };
}
export type ComparisonInput = {
  priceComparisonUnavailable?: boolean;
  kind?: "etf" | "index";
  totalReturnAvailable?: boolean;
  id: string;
  bars: { date: string; close: number; adjustedClose: number | null }[];
};
export interface Comparison {
  baseline?: string;
  end?: string;
  dates: string[];
  series: { id: string; values: (number | null)[] }[];
  error?: string;
  shortened?: boolean;
}
export function compare(
  histories: ComparisonInput[],
  period: Period | "all",
  mode: Mode,
): Comparison {
  const empty = { dates: [], series: [] };
  if (mode === "price" && histories.some((h) => h.priceComparisonUnavailable))
    return {
      ...empty,
      error:
        "份额拆并基准未知，价格对比不可用。可下载原始历史，但不估算调整价格。",
    };
  if (
    mode === "total" &&
    histories.some((h) => h.kind === "index" && !h.totalReturnAvailable)
  )
    return {
      ...empty,
      error: "价格指数不包含现金分红，不能将复权收盘价当作总回报指数。",
    };
  if (!histories.length)
    return {
      ...empty,
      error: "请先勾选需要对比的资产。",
    };
  const maps = histories.map(
    (h) =>
      new Map(
        h.bars.map((b) => [
          b.date,
          mode === "price" ? b.close : b.adjustedClose,
        ]),
      ),
  );
  if (
    mode === "total" &&
    maps.some((m) => ![...m.values()].some((v) => v !== null && v > 0))
  )
    return {
      ...empty,
      error: "复权收盘数据不可用，无法估算含分红总回报。",
    };
  const lastDates = histories.map((h) => h.bars.at(-1)?.date);
  if (lastDates.some((d) => !d))
    return { ...empty, error: "没有共同交易日，部分资产历史为空。" };
  const end = lastDates.sort()[0]!;
  let start = "";
  if (period !== "all") {
    const endDate = new Date(end + "T00:00:00Z");
    const day = endDate.getUTCDate();
    const months = parseInt(period) * (period.endsWith("y") ? 12 : 1);
    const target = new Date(
      Date.UTC(endDate.getUTCFullYear(), endDate.getUTCMonth() - months, 1),
    );
    const maxDay = new Date(
      Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0),
    ).getUTCDate();
    target.setUTCDate(Math.min(day, maxDay));
    start = target.toISOString().slice(0, 10);
  }
  const shared = histories[0].bars
    .map((b) => b.date)
    .filter(
      (d) =>
        d <= end &&
        maps.every((m) => {
          const v = m.get(d);
          return v != null && Number.isFinite(v) && v > 0;
        }),
    )
    .sort();
  // A single actual session anchors every line. No independently rebased inceptions.
  const baseline = shared.find((d) => d >= start);
  if (!baseline)
    return {
      ...empty,
      error: "当前资产组合没有价格有效的共同交易日。",
    };
  const dates = [
    ...new Set(histories.flatMap((h) => h.bars.map((b) => b.date))),
  ]
    .filter((d) => d >= baseline && d <= end)
    .sort();
  return {
    baseline,
    end,
    dates,
    shortened:
      period !== "all" &&
      new Date(baseline).getTime() - new Date(start).getTime() > 10 * 86400000,
    series: histories.map((h, i) => ({
      id: h.id,
      values: dates.map((d) => {
        const v = maps[i].get(d);
        return v != null && v > 0 ? (v / maps[i].get(baseline)!) * 100 : null;
      }),
    })),
  };
}
