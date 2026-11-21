/* Build replaces the version and precache list. No synthetic market data. */
const VERSION = "__BUILD__";
const SHELL = `etf-atlas-shell-${VERSION}`;
const DATA = "etf-atlas-data-v1";
const PRECACHE = __PRECACHE__;
const scoped = (path) => new URL(path, self.registration.scope).href;
const cachedResponse = async (name, request) => {
  try {
    return await (await caches.open(name)).match(request, { ignoreVary: true });
  } catch {
    // Cache Storage can be disabled or unavailable; network stays usable.
    return undefined;
  }
};
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((cache) => cache.addAll(PRECACHE.map(scoped)))
      .then(() => self.skipWaiting()),
  );
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter(
              (key) => key.startsWith("etf-atlas-shell-") && key !== SHELL,
            )
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});
self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    !url.href.startsWith(self.registration.scope)
  )
    return;
  const isData = url.pathname.startsWith(
    new URL("data/", self.registration.scope).pathname,
  );
  if (isData) {
    event.respondWith(
      (async () => {
        let response;
        try {
          response = await fetch(request);
        } catch (error) {
          const cached = await cachedResponse(DATA, request);
          if (!cached) throw error;
          const headers = new Headers(cached.headers);
          headers.set("X-ETF-Atlas-Cache", "offline");
          return new Response(await cached.blob(), {
            status: cached.status,
            statusText: cached.statusText,
            headers,
          });
        }
        if (
          response.ok &&
          (response.headers.get("content-type") || "").includes("json")
        ) {
          try {
            const cache = await caches.open(DATA);
            await cache.put(request, response.clone());
          } catch {
            // Persistence is optional; never replace fresh data with stale data.
          }
        }
        return response;
      })(),
    );
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async (error) => {
        const cached = await cachedResponse(SHELL, scoped("./"));
        if (!cached) throw error;
        return cached;
      }),
    );
    return;
  }
  event.respondWith(
    (async () => {
      const cached = await cachedResponse(SHELL, request);
      return cached || fetch(request);
    })(),
  );
});
