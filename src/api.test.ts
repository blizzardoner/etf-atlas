import { it, expect, vi } from "vitest";
import { loadMarket, loadHistory } from "./api";
import { history, instrument } from "./test/fixtures";
it.each(
  ["2020-01-00", "2020-01-32", "2020-00-02", "2020-13-02", "2020-04-31", "2021-02-29", "1900-02-29", "2020-1-02"].flatMap(
    (invalidDate) => (["bar", "firstDate", "lastDate", "dividend", "split"] as const).map((field) => ({ invalidDate, field })),
  ),
)(
  "rejects impossible/noncanonical $field date $invalidDate",
  async ({ invalidDate, field }) => {
      const input = history();
      if (field === "bar") {
        input.bars = [{ ...input.bars[0], date: invalidDate }];
        input.coverage = { complete: true, count: 1, firstDate: invalidDate, lastDate: invalidDate };
      } else if (field === "firstDate" || field === "lastDate") {
        // Empty bars isolate coverage validation from boundary matching.
        input.bars = [];
        input.coverage.count = 0;
        input.coverage[field] = invalidDate;
      } else if (field === "dividend") {
        input.dividends = [{ date: invalidDate, amount: 1 }];
      } else {
        input.splits = [{ date: invalidDate, ratio: 2 }];
      }
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => input }));
      await expect(loadHistory(instrument()), field).rejects.toThrow(/history/i);
  },
);
it.each(["2020-02-29", "2000-02-29", "2021-02-28", "0099-01-01"])(
  "accepts real UTC calendar dates %s without mutating history",
  async (validDate) => {
    const input = history();
    input.bars = [{ ...input.bars[0], date: validDate }];
    input.coverage = { complete: true, count: 1, firstDate: validDate, lastDate: validDate };
    input.dividends = [{ date: validDate, amount: 1 }];
    input.splits = [{ date: validDate, ratio: 2 }];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => input }));
    expect(await loadHistory(instrument())).toEqual(input);
  },
);
it("identifies a cached offline market snapshot so the UI cannot present it as a live refresh", async () => {
  const data = {
    schemaVersion: 1,
    generatedAt: "2025-01-01T00:00:00Z",
    instruments: [],
    failures: [],
    methodology: [],
  };
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({
        ok: true,
        headers: new Headers({ "X-ETF-Atlas-Cache": "offline" }),
        json: async () => data,
      }),
  );
  expect((await loadMarket()).offlineCached).toBe(true);
});
it("accepts split-normalized price histories while preserving optional raw prices", async () => {
  const input = {
    ...history(),
    adjustment: "split-normalized-price",
    bars: history().bars.map((b) => ({ ...b, rawClose: b.close * 2 })),
    dividends: null,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => input }),
  );
  expect(await loadHistory(instrument())).toEqual(input);
});
it("accepts unknown dividends but rejects mismatched or unsorted full histories", async () => {
  const input = { ...history(), dividends: null };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => input }),
  );
  expect(await loadHistory(instrument())).toEqual(input);
  vi.mocked(fetch).mockResolvedValue({
    ok: true,
    json: async () => ({ ...input, id: "wrong" }),
  } as Response);
  await expect(loadHistory(instrument())).rejects.toThrow(/history/i);
  vi.mocked(fetch).mockResolvedValue({
    ok: true,
    json: async () => ({ ...input, bars: [...input.bars].reverse() }),
  } as Response);
  await expect(loadHistory(instrument())).rejects.toThrow(/history/i);
});
it("loads only a supported market schema and surfaces HTTP or malformed snapshot errors", async () => {
  const valid = {
    schemaVersion: 1,
    generatedAt: "2025-01-01T00:00:00Z",
    instruments: [],
    failures: [],
    methodology: [],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => valid }),
  );
  expect(await loadMarket()).toEqual(valid);
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("data/market.json"),
    expect.objectContaining({ cache: "no-cache" }),
  );
  vi.mocked(fetch).mockResolvedValue({ ok: false, status: 404 } as Response);
  await expect(loadMarket()).rejects.toThrow(/404/);
  vi.mocked(fetch).mockResolvedValue({
    ok: true,
    json: async () => ({ ...valid, schemaVersion: 2 }),
  } as Response);
  await expect(loadMarket()).rejects.toThrow(/schema/i);
});
