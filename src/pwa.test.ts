// @vitest-environment node
import { it, expect } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
it("ships a subpath-safe standalone PWA with real 180/192/512 PNG icons and production SW registration", () => {
  const root = resolve(import.meta.dirname, "..");
  expect(existsSync(resolve(root, "index.html"))).toBe(true);
  const manifest = JSON.parse(
    readFileSync(resolve(root, "public/manifest.webmanifest"), "utf8"),
  );
  expect(manifest.start_url).toBe("./");
  expect(manifest.scope).toBe("./");
  expect(manifest.display).toBe("standalone");
  for (const size of [180, 192, 512]) {
    const png = readFileSync(resolve(root, `public/icons/icon-${size}.png`));
    expect([...png.subarray(0, 8)]).toEqual([137, 80, 78, 71, 13, 10, 26, 10]);
    expect(png.readUInt32BE(16)).toBe(size);
    expect(png.readUInt32BE(20)).toBe(size);
  }
  expect(readFileSync(resolve(root, "index.html"), "utf8")).toContain(
    "viewport-fit=cover",
  );
  expect(readFileSync(resolve(root, "src/main.tsx"), "utf8")).toContain(
    "import.meta.env.PROD",
  );
  expect(readFileSync(resolve(root, "public/sw.js"), "utf8")).toContain(
    "self.registration.scope",
  );
});
