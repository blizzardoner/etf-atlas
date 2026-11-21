// @vitest-environment node
import { it, expect, vi } from "vitest";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

function worker(fetcher: typeof fetch, storage: unknown) {
  const handlers: Record<string, (event: any) => void> = {};
  const source = readFileSync(new URL("../public/sw.js", import.meta.url), "utf8")
    .replace("__BUILD__", "test")
    .replace("__PRECACHE__", "[]");
  runInNewContext(source, {
    self: {
      registration: { scope: "https://example.test/atlas/" },
      location: { origin: "https://example.test" },
      addEventListener: (name: string, fn: (event: any) => void) => (handlers[name] = fn),
    },
    URL, Headers, Response, caches: storage, fetch: fetcher,
  });
  return (path: string, mode = "cors") => {
    let result!: Promise<Response>;
    handlers.fetch({
      request: { url: `https://example.test/atlas/${path}`, method: "GET", mode },
      respondWith: (promise: Promise<Response>) => (result = promise),
    });
    return result;
  };
}

it.each([false, true])("returns fresh online JSON despite quota failure (stale cached: %s)", async (hasCached) => {
  const fresh = new Response('{"id":"AAA","bars":[{"close":120}]}', {
    headers: { "Content-Type": "application/json" },
  });
  const match = vi.fn(async () => hasCached ? new Response('{"id":"AAA","bars":[{"close":100}]}') : undefined);
  const run = worker(vi.fn(async () => fresh), {
    open: async () => ({
      put: async () => { throw new DOMException("Storage quota exceeded", "QuotaExceededError"); },
      match,
    }),
  });
  const response = await run("data/history/AAA.json");
  expect(response).toBe(fresh);
  expect(response.headers.get("X-ETF-Atlas-Cache")).toBeNull();
  expect(await response.json()).toEqual({ id: "AAA", bars: [{ close: 120 }] });
  expect(match).not.toHaveBeenCalled();
});

it.each(["data/history/AAA.json", "assets/app.js", "./"])(
  "uses successful network response when Cache.open is unavailable for %s",
  async (path) => {
    const fresh = new Response("fresh", { headers: { "Content-Type": "application/json" } });
    const fetcher = vi.fn(async () => fresh);
    const run = worker(fetcher, {
      open: async () => { throw new DOMException("Storage disabled", "SecurityError"); },
    });
    expect(await run(path, path === "./" ? "navigate" : "cors")).toBe(fresh);
    expect(fetcher).toHaveBeenCalledTimes(1);
  },
);
it.each(["data/history/AAA.json", "assets/app.js"])(
  "uses successful network response when Cache.match is unavailable for %s",
  async (path) => {
    const fresh = new Response("fresh", { headers: { "Content-Type": "application/json" } });
    const run = worker(vi.fn(async () => fresh), {
      open: async () => ({
        put: async () => undefined,
        match: async () => { throw new DOMException("Storage read failed", "InvalidStateError"); },
      }),
    });
    expect(await run(path)).toBe(fresh);
  },
);
it("falls back to the exact offline history without changing cached data or mixing assets", async () => {
  const original = '{"id":"AAA","bars":[{"date":"2020-01-02","close":100}]}';
  const stored = new Response(original, { headers: { "Content-Type": "application/json" } });
  const networkError = new TypeError("Failed to fetch");
  const put = vi.fn();
  const match = vi.fn(async (request: { url: string }, options: { ignoreVary?: boolean }) =>
    request.url.endsWith("/AAA.json") && options.ignoreVary ? stored.clone() : undefined);
  const run = worker(vi.fn(async () => { throw networkError; }), { open: async () => ({ match, put }) });
  const result = await run("data/history/AAA.json");
  expect(result.headers.get("X-ETF-Atlas-Cache")).toBe("offline");
  expect(await result.text()).toBe(original);
  expect(stored.headers.get("X-ETF-Atlas-Cache")).toBeNull();
  expect(await stored.text()).toBe(original);
  await expect(run("data/history/BBB.json")).rejects.toBe(networkError);
  expect(put).not.toHaveBeenCalled();
});
it.each(["open", "match"])("retains network failure when optional offline cache %s fails", async (failure) => {
  const networkError = new TypeError("Failed to fetch");
  const run = worker(vi.fn(async () => { throw networkError; }), {
    open: async () => {
      if (failure === "open") throw new DOMException("Storage disabled", "SecurityError");
      return { match: async () => { throw new DOMException("Storage read failed", "InvalidStateError"); } };
    },
  });
  await expect(run("data/history/AAA.json")).rejects.toBe(networkError);
});
it("serves the precached shell navigation only after an actual network failure", async () => {
  const match = vi.fn(async () => new Response("cached shell"));
  const run = worker(vi.fn(async () => { throw new TypeError("offline"); }), { open: async () => ({ match }) });
  expect(await (await run("./", "navigate")).text()).toBe("cached shell");
  expect(match).toHaveBeenCalledWith("https://example.test/atlas/", { ignoreVary: true });
});

it("serves same-origin precached JS offline despite Vite Vary: Origin request-mode differences", async () => {
  const handlers: Record<string, (event: any) => void> = {};
  let result!: Promise<Response>;
  const cached = new Response("cached asset", {
    headers: { "Content-Type": "text/javascript", Vary: "Origin" },
  });
  const self = {
    registration: { scope: "https://example.test/atlas/" },
    location: { origin: "https://example.test" },
    addEventListener: (name: string, fn: (event: any) => void) =>
      (handlers[name] = fn),
  };
  const cache = {
    match: async (_request: unknown, options?: { ignoreVary?: boolean }) =>
      options?.ignoreVary ? cached : undefined,
  };
  const source = readFileSync(
    new URL("../public/sw.js", import.meta.url),
    "utf8",
  )
    .replace("__BUILD__", "test")
    .replace("__PRECACHE__", "[]");
  runInNewContext(source, {
    self,
    URL,
    Headers,
    Response,
    caches: { open: async () => cache },
    fetch: async () => {
      throw new Error("offline");
    },
  });
  handlers.fetch({
    request: new Request("https://example.test/atlas/assets/app.js"),
    respondWith: (promise: Promise<Response>) => (result = promise),
  });
  expect(await (await result).text()).toBe("cached asset");
});
