import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
export default defineConfig({
  base: "./",
  plugins: [
    react(),
    {
      name: "atlas-pwa-shell",
      apply: "build",
      writeBundle(options, bundle) {
        const assets = Object.keys(bundle).filter(
          (file) => !file.startsWith("data/") && file !== "sw.js",
        );
        const version = createHash("sha256")
          .update(
            assets.sort().join("|") +
              readFileSync(resolve("public/sw.js"), "utf8") +
              readFileSync(resolve("public/manifest.webmanifest"), "utf8"),
          )
          .digest("hex")
          .slice(0, 12);
        const list = [
          "./",
          "index.html",
          "manifest.webmanifest",
          "icons/icon-180.png",
          "icons/icon-192.png",
          "icons/icon-512.png",
          ...assets,
        ];
        const source = readFileSync(resolve("public/sw.js"), "utf8")
          .replace("__BUILD__", version)
          .replace("__PRECACHE__", JSON.stringify([...new Set(list)]));
        writeFileSync(resolve(options.dir ?? "dist", "sw.js"), source);
      },
    },
  ],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    restoreMocks: true,
    exclude: ["node_modules/**", "dist/**", "qa/**"],
  },
});
