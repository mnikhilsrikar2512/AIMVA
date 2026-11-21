// Navigation that behaves like people expect (plan S7, 2026-11-21): what is open on a screen lives in the address, so
// the Back button undoes the last step, and "← Home" takes you back to exactly where you came from.
import { useCallback, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

/** [params, set]: set({ key: value | null }, { replace }) changes only those keys. It reads the live address, so two
 *  calls in one tick both land (react-router's own setter would let the second overwrite the first). */
export function useUrlState() {
  const navigate = useNavigate();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const set = useCallback((changes, { replace = false } = {}) => {
    const p = new URLSearchParams(window.location.search);
    let changed = false;
    for (const [k, v] of Object.entries(changes)) {
      const next = v === null || v === undefined || v === "" ? null : String(v);
      if (p.get(k) === next) continue;
      changed = true;
      if (next === null) p.delete(k); else p.set(k, next);
    }
    if (!changed) return;
    const qs = p.toString();
    navigate({ pathname: window.location.pathname, search: qs ? `?${qs}` : "" }, { replace, state: window.history.state?.usr ?? null });
  }, [navigate]);
  return [params, set];
}

/**
 * A module's "which view, which item" (prompt | work | all, and the open item's id), kept in the address.
 * Opening a different view adds a step to history (Back returns); choosing an item inside a view, or the screen
 * settling on its first view by itself, replaces the step. `initial` is used until the address names a view.
 */
export function useUrlView(initial = null) {
  const [params, set] = useUrlState();
  const [fallback] = useState(initial);
  const view = params.get("view") || fallback;
  const id = params.get("id");
  const selId = id === null ? null : Number(id);
  const setView = useCallback((v) => {
    const cur = new URLSearchParams(window.location.search).get("view");
    set({ view: v }, { replace: !cur || !v });
  }, [set]);
  const setSelId = useCallback((v) => set({ id: v }, { replace: true }), [set]);
  return [view, setView, selId, setSelId, set];
}

// ---- where you came from --------------------------------------------------------------------------------------
const ORIGIN_KEY = "aimva_nav_origin";
const readMap = () => { try { return JSON.parse(sessionStorage.getItem(ORIGIN_KEY) || "{}"); } catch { return {}; } };
const saveMap = (m) => {
  const keys = Object.keys(m);
  if (keys.length > 200) keys.slice(0, keys.length - 200).forEach((k) => delete m[k]);
  try { sessionStorage.setItem(ORIGIN_KEY, JSON.stringify(m)); } catch { /* storage blocked */ }
};

/** Remember, per history entry, the screen it was opened from. Rail and tab-bar clicks are fresh starts, not "from". */
export function recordOrigin({ prev, prevIdx, location, navType, sectionOf, labelOf }) {
  const map = readMap();
  const key = location.key;
  if (navType === "PUSH" && prev && !location.state?.rail && sectionOf(prev.pathname) !== sectionOf(location.pathname)) {
    map[key] = { to: prev.pathname + prev.search, label: labelOf(prev.pathname), idx: prevIdx };
    saveMap(map);
  } else if (navType === "PUSH" && prev && sectionOf(prev.pathname) === sectionOf(location.pathname) && map[prev.key]) {
    map[key] = map[prev.key];  // a step inside the same screen keeps the way back
    saveMap(map);
  } else if (navType === "REPLACE" && prev && map[prev.key] && !map[key]) {
    map[key] = map[prev.key];  // tidying the address keeps the way back
    saveMap(map);
  }
  return map[key] || null;
}

/** Go back to the origin: through history when we can (exact place, scroll and all), else by its address. */
export function useGoToOrigin() {
  const navigate = useNavigate();
  return useCallback((origin) => {
    const cur = window.history.state?.idx;
    if (typeof origin.idx === "number" && typeof cur === "number" && origin.idx < cur) navigate(origin.idx - cur);
    else navigate(origin.to);
  }, [navigate]);
}
