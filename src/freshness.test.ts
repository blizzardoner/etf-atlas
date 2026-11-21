import { it, expect } from "vitest";
import { assessFreshness } from "./domain";
import { market, instrument } from "./test/fixtures";

it("expires calendar quotes at the explicit session boundary even after only one or three days", () => {
  const items = ["2025-01-03", "2025-01-01"].map((lastDate) => ({
    ...instrument(lastDate), lastDate, expectedLastDate: lastDate,
    freshUntil: "2025-01-04T12:00:00Z", calendar: "XNYS",
  }));
  const source = market(items);
  expect(assessFreshness(source, Date.parse("2025-01-04T11:59:59Z")).market.instruments.map(i => i.status)).toEqual(["fresh", "fresh"]);
  expect(assessFreshness(source, Date.parse("2025-01-04T12:00:00Z")).market.instruments.map(i => i.status)).toEqual(["stale", "stale"]);
});
it("keeps a validated long-holiday quote fresh while warning separately about snapshot age", () => {
  const quote = { ...instrument(), expectedLastDate: "2025-01-03", freshUntil: "2025-01-15T21:05:00Z", calendar: "XNYS" };
  const source = market([quote, instrument("LEGACY")]);
  const result = assessFreshness(source, Date.parse("2025-01-12T12:00:00Z"));
  expect(result.outdated).toBe(true);
  expect(result.market.instruments.map(i => i.status)).toEqual(["fresh", "stale"]);
  expect(source.instruments.map(i => i.status)).toEqual(["fresh", "fresh"]);
});
it.each([
  { expectedLastDate: "2025-01-02" },
  { expectedLastDate: "2025-02-30", lastDate: "2025-02-30" },
  { expectedLastDate: undefined },
  { calendar: undefined },
  { calendar: "" },
  { calendar: null },
  { freshUntil: undefined },
  { freshUntil: null },
  { freshUntil: "2025-01-06T21:05:00" },
  { freshUntil: "2025-01-06" },
  { freshUntil: "2025-01-06T21:05:00+25:00" },
  { freshUntil: "2025-02-30T21:05:00Z" },
])("fails closed for inconsistent or incomplete calendar metadata: %j", (override) => {
  const quote = { ...instrument(), expectedLastDate: "2025-01-03", freshUntil: "2025-01-06T21:05:00Z", calendar: "XNYS", ...override };
  const source = market([quote as ReturnType<typeof instrument>]);
  expect(assessFreshness(source, Date.parse("2025-01-04T12:00:00Z")).market.instruments[0].status).toBe("stale");
});
it.each(["2025-01-04T12:00:01Z", "2025-01-04T00:00:00", "2025-01-04", "2025-02-30T00:00:00Z", "invalid"])("rejects invalid or future snapshot timestamps independently of valid calendar expiry: %s", (generatedAt) => {
  const quote = { ...instrument(), expectedLastDate: "2025-01-03", freshUntil: "2025-01-06T21:05:00Z", calendar: "XNYS" };
  const source = { ...market([quote, { ...quote, id: "S", status: "stale" as const }, { ...quote, id: "U", status: "unavailable" as const }]), generatedAt };
  const result = assessFreshness(source, Date.parse("2025-01-04T12:00:00Z"));
  expect(result.outdated).toBe(true);
  expect(result.market.instruments.map(i => i.status)).toEqual(["stale", "stale", "unavailable"]);
});
it("accepts explicit offsets and never upgrades upstream stale or unavailable quotes", () => {
  const quote = { ...instrument(), expectedLastDate: "2025-01-03", freshUntil: "2025-01-06T08:05:00+11:00", calendar: "XNYS" };
  const source = market([quote, { ...quote, id: "S", status: "stale" as const }, { ...quote, id: "U", status: "unavailable" as const }]);
  expect(assessFreshness(source, Date.parse("2025-01-05T21:04:59Z")).market.instruments.map(i => i.status)).toEqual(["fresh", "stale", "unavailable"]);
  expect(assessFreshness(source, Date.parse("2025-01-05T21:05:00Z")).market.instruments.map(i => i.status)).toEqual(["stale", "stale", "unavailable"]);
});
it("retains the legacy five-day quote-age boundary when every calendar field is absent", () => {
  const source = { ...market(), generatedAt: "2025-01-08T00:00:00Z" };
  expect(assessFreshness(source, Date.parse("2025-01-08T00:00:00Z")).market.instruments[0].status).toBe("fresh");
  expect(assessFreshness(source, Date.parse("2025-01-08T00:00:00.001Z")).market.instruments[0].status).toBe("stale");
});
it("marks old snapshot fresh records stale at runtime, preserving stale/unavailable and rejecting future timestamps", () => {
  const a = instrument(),
    b = { ...instrument("B"), status: "stale" as const },
    c = { ...instrument("C"), status: "unavailable" as const };
  const source = market([a, b, c]);
  const aged = assessFreshness(source, Date.parse("2025-02-01T00:00:00Z"));
  expect(aged.outdated).toBe(true);
  expect(aged.market.instruments.map((i: any) => i.status)).toEqual([
    "stale",
    "stale",
    "unavailable",
  ]);
  expect(source.instruments[0].status).toBe("fresh");
  expect(
    assessFreshness(source, Date.parse("2025-01-04T12:00:00Z")).market
      .instruments[0].status,
  ).toBe("fresh");
  const future = assessFreshness(source, Date.parse("2024-12-01T00:00:00Z"));
  expect(future.future).toBe(true);
  expect(future.market.instruments[0].status).toBe("stale");
});
