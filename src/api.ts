import { PERIODS, type Market, type Instrument, type History } from "./types";
export async function loadHistory(
  instrument: Instrument,
  signal?: AbortSignal,
): Promise<History> {
  if (!/^data\/history\/[A-Za-z0-9_.-]+\.json$/.test(instrument.historyUrl))
    throw new Error("历史路径无效（history path）。");
  const data = await json(instrument.historyUrl, signal);
  if (
    !record(data) ||
    data.id !== instrument.id ||
    typeof data.sourceUrl !== "string" ||
    typeof data.retrievedAt !== "string" ||
    !["none", "provider-adjusted-close", "split-normalized-price"].includes(
      data.adjustment as string,
    ) ||
    !Array.isArray(data.bars) ||
    !Array.isArray(data.splits) ||
    !record(data.coverage)
  )
    throw new Error("历史数据格式或资产标识不符（history schema）。");
  if (
    !data.bars.every(
      (b, i, all) =>
        record(b) &&
        date(b.date) &&
        typeof b.close === "number" &&
        Number.isFinite(b.close) &&
        b.close > 0 &&
        ["open", "high", "low", "adjustedClose", "volume"].every((k) =>
          numberOrNull(b[k]),
        ) &&
        (i === 0 || all[i - 1].date < b.date),
    )
  )
    throw new Error(
      "历史日线无效：价格须为有效数值，日期须递增且不重复（history bars）。",
    );
  if (
    data.dividends !== null &&
    (!Array.isArray(data.dividends) ||
      !data.dividends.every(
        (d) =>
          record(d) &&
          date(d.date) &&
          typeof d.amount === "number" &&
          Number.isFinite(d.amount) &&
          d.amount >= 0,
      ))
  )
    throw new Error("分红历史格式无效（dividend history）。");
  if (
    !data.splits.every(
      (s) =>
        record(s) &&
        date(s.date) &&
        typeof s.ratio === "number" &&
        Number.isFinite(s.ratio) &&
        s.ratio > 0,
    )
  )
    throw new Error("份额拆并历史格式无效（split history）。");
  const c = data.coverage;
  if (
    typeof c.complete !== "boolean" ||
    c.count !== data.bars.length ||
    !date(c.firstDate) ||
    !date(c.lastDate) ||
    (data.bars.length &&
      (c.firstDate !== data.bars[0].date ||
        c.lastDate !== data.bars.at(-1).date))
  )
    throw new Error("历史覆盖信息不符（history coverage）。");
  return data as unknown as History;
}
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const numberOrNull = (v: unknown) =>
  v === null || (typeof v === "number" && Number.isFinite(v));
const date = (v: unknown): v is string => {
  if (typeof v !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const utc = new Date(`${v}T00:00:00.000Z`);
  return Number.isFinite(utc.getTime()) && utc.toISOString().slice(0, 10) === v;
};
export const assetUrl = (path: string) =>
  new URL(path, new URL(import.meta.env.BASE_URL, document.baseURI)).href;
async function json(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(assetUrl(path), { signal, cache: "no-cache" });
  if (!response.ok)
    throw new Error(`数据请求失败（HTTP ${response.status}）。`);
  const value = await response.json();
  if (
    path === "data/market.json" &&
    response.headers?.get("X-ETF-Atlas-Cache") === "offline" &&
    record(value)
  )
    return { ...value, offlineCached: true };
  return value;
}
function validInstrument(i: unknown): i is Instrument {
  if (
    !record(i) ||
    ![
      "id",
      "symbol",
      "name",
      "currency",
      "sourceUrl",
      "historyUrl",
      "benchmark",
    ].every((k) => typeof i[k] === "string")
  )
    return false;
  if (
    !["CN", "US", "AU"].includes(i.country as string) ||
    !["etf", "index"].includes(i.kind as string) ||
    !["fresh", "stale", "unavailable"].includes(i.status as string)
  )
    return false;
  if (
    !["available", "unavailable", "no-distributions"].includes(
      i.dividendStatus as string,
    )
  )
    return false;
  if (
    !["close", "dailyChange", "cashYield", "frankingRate"].every((k) =>
      numberOrNull(i[k]),
    )
  )
    return false;
  if (
    !date(i.firstDate) ||
    !date(i.lastDate) ||
    !Number.isInteger(i.count) ||
    !record(i.returns)
  )
    return false;
  return ["price", "total"].every(
    (mode) =>
      record(i.returns) &&
      record(i.returns[mode]) &&
      PERIODS.every((p) =>
        numberOrNull(
          (i.returns as Record<string, Record<string, unknown>>)[mode][p],
        ),
      ),
  );
}
export async function loadMarket(signal?: AbortSignal): Promise<Market> {
  const data = await json("data/market.json", signal);
  if (
    !record(data) ||
    data.schemaVersion !== 1 ||
    typeof data.generatedAt !== "string" ||
    !Number.isFinite(Date.parse(data.generatedAt)) ||
    !Array.isArray(data.instruments) ||
    !data.instruments.every(validInstrument) ||
    !Array.isArray(data.failures) ||
    !data.failures.every(
      (f) =>
        record(f) && typeof f.id === "string" && typeof f.error === "string",
    ) ||
    !Array.isArray(data.methodology) ||
    !data.methodology.every((m) => typeof m === "string")
  )
    throw new Error(
      "市场快照格式无效或版本不受支持（schema），请刷新经过校验的数据。",
    );
  if (
    new Set(data.instruments.map((i) => i.id)).size !== data.instruments.length
  )
    throw new Error("市场快照包含重复的资产标识（schema）。");
  return data as unknown as Market;
}
