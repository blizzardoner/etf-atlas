import { useEffect, useRef, useState } from "react";
import { loadHistory } from "./api";
import type { History, Instrument } from "./types";
interface State {
  key: string;
  data: Record<string, History>;
  errors: Record<string, string>;
  loading: boolean;
}
export function useHistories(items: Instrument[], snapshot: string, retry = 0) {
  const cache = useRef(new Map<string, History>()),
    epoch = useRef(0);
  const key = JSON.stringify([snapshot, items.map((i) => i.id).sort(), retry]);
  const [state, setState] = useState<State>({
    key: "",
    data: {},
    errors: {},
    loading: false,
  });
  useEffect(() => {
    const token = ++epoch.current,
      abort = new AbortController();
    const current = () => epoch.current === token && !abort.signal.aborted;
    const data: Record<string, History> = {},
      errors: Record<string, string> = {};
    const jobs = items.map(async (i) => {
      const cacheKey = `${snapshot}/${i.id}`;
      const cached = cache.current.get(cacheKey);
      if (cached) {
        data[i.id] = cached;
        return;
      }
      try {
        const h = await loadHistory(i, abort.signal);
        if (!current()) return;
        cache.current.set(cacheKey, h);
        data[i.id] = h;
      } catch (e) {
        if (current())
          errors[i.id] = e instanceof Error ? e.message : String(e);
      }
    });
    setState({ key, data: { ...data }, errors: {}, loading: jobs.length > 0 });
    Promise.all(jobs).then(() => {
      if (current())
        setState({
          key,
          data: { ...data },
          errors: { ...errors },
          loading: false,
        });
    });
    return () => {
      ++epoch.current;
      abort.abort();
    };
    // The key expresses the complete request ownership; caller arrays are ephemeral.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state.key === key
    ? state
    : { key, data: {}, errors: {}, loading: items.length > 0 };
}
export const SELECTION_KEY = "etf-atlas.selection.v1";
export function readSelection(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(SELECTION_KEY) ?? "null");
    return v?.version === 1 &&
      Array.isArray(v.ids) &&
      v.ids.length <= 500 &&
      v.ids.every((id: unknown) => typeof id === "string")
      ? [...new Set<string>(v.ids)]
      : [];
  } catch {
    return [];
  }
}
export function saveSelection(ids: string[]): boolean {
  try {
    localStorage.setItem(SELECTION_KEY, JSON.stringify({ version: 1, ids }));
    return true;
  } catch {
    return false;
  }
}
