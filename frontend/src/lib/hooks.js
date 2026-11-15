import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { get } from "./api";

// Load JSON from the API with loading/error state and a reload() handle.
export function useApi(path, initial = null) {
  const [data, setData] = useState(initial);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const loaded = useRef(false);

  // Spinner only on the first load; later reloads (filters, live updates) swap data in place.
  const reload = useCallback(async () => {
    if (!path) { setLoading(false); return; }
    if (!loaded.current) setLoading(true);
    try {
      setData(await get(path));
      loaded.current = true;
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, setData, loading, error, reload };
}

// Run an async action with busy state and toast on error.
export function useAction() {
  const [busy, setBusy] = useState(false);
  const run = useCallback(async (fn, successMsg) => {
    setBusy(true);
    try {
      const out = await fn();
      const msg = typeof successMsg === "function" ? successMsg(out) : successMsg;
      if (msg) toast.success(msg);
      return out;
    } catch (e) {
      toast.error(e.message || "Something went wrong");
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return [busy, run];
}

/**
 * Server times are UTC without a zone and with microseconds ("2026-11-06T18:59:21.701117"). Older Safari can't
 * parse more than 3 fraction digits, so trim them and add the Z here, once, for every browser.
 */
export function parseServerDate(iso) {
  if (!iso) return new Date(NaN);
  let s = String(iso).trim().replace(" ", "T").replace(/(\.\d{3})\d+/, "$1");
  if (!/[zZ]|[+-]\d\d:?\d\d$/.test(s)) s += "Z";
  return new Date(s);
}

export const timeAgo = (iso) => {
  const s = (Date.now() - parseServerDate(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};
