import { useCallback, useEffect, useRef, useState } from "react";

/** Load data now and again every `ms` while the browser tab is visible. `deps` restart it;
 *  `enabled` false pauses it (the last data is kept). */
export function usePoll<T>(load: () => Promise<T>, ms: number, deps: unknown[] = [], enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  loadRef.current = load;

  const seq = useRef(0);

  const refresh = useCallback(async () => {
    const mine = ++seq.current;            // only the latest request may write (filters change mid-flight)
    try {
      const d = await loadRef.current();
      if (mine !== seq.current) return;
      setData(d);
      setError(null);
    } catch (e) {
      if (mine !== seq.current) return;
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let live = true;
    refresh();
    const id = window.setInterval(() => {
      if (live && document.visibilityState === "visible") refresh();
    }, ms);
    return () => {
      live = false;
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, refresh, enabled, ...deps]);

  return { data, error, loading, refresh, setData };
}

/** sessionStorage that never throws (private windows, blocked storage). */
export const store = {
  get<T>(key: string, fallback: T): T {
    try {
      const v = window.sessionStorage.getItem(key);
      return v ? (JSON.parse(v) as T) : fallback;
    } catch {
      return fallback;
    }
  },
  set(key: string, value: unknown) {
    try {
      window.sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage unavailable: the page still works, it just forgets on reload */
    }
  },
  remove(key: string) {
    try {
      window.sessionStorage.removeItem(key);
    } catch {
      /* ignore */
    }
  },
};

export function newSessionId(): string {
  const rand = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  return `web-${rand}`;
}

/** Re-render every `ms` so "3 min ago" labels stay true. */
export function useNow(ms = 30000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [ms]);
  return now;
}
