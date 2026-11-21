import type { History } from "./types";
export function download(
  filename: string,
  text: string,
  type = "application/json",
) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function downloadHistory(h: History) {
  download(`${h.id}-full-history.json`, JSON.stringify(h, null, 2));
}
export function safeSource(url: string): string | undefined {
  try {
    const u = new URL(url);
    return ["https:", "http:"].includes(u.protocol) ? u.href : undefined;
  } catch {
    return undefined;
  }
}
