// The changes panel's history (design.md 3.1 and 7.3): each request in the owner's or a teammate's own words, who
// asked when it wasn't you, the version it made, Restore on older ones and Compare (a before/after split with a drag
// handle). It never narrates what AIMVA did or how it read the request.
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { get, post } from "../lib/api";
import { useApi, timeAgo } from "../lib/hooks";
import { Modal, cx } from "./ui";

/** The words a version shows: the request itself when the server kept it, else its plain label. */
function said(v) {
  const words = (v.request || v.note || "").trim();
  return words || `Version ${v.number}`;
}

/** Before/after: the older version under, the current page over it, clipped at the handle. Scripts never run. */
function Compare({ site, page, version, onClose }) {
  const [before, setBefore] = useState(null);
  const [split, setSplit] = useState(50);
  const box = useRef(null);
  useEffect(() => {
    setBefore(null);
    if (!version) return undefined;
    let live = true;
    get(`/api/sites/${site.id}/versions/${version.id}`).then((v) => { if (live) setBefore(v.html); })
      .catch((e) => { toast.error(e.message); onClose(); });
    return () => { live = false; };
  }, [version?.id]);  // eslint-disable-line react-hooks/exhaustive-deps
  const drag = (e) => {
    const r = box.current?.getBoundingClientRect();
    if (r) setSplit(Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100)));
  };
  return (
    <Modal open={!!version} onClose={onClose} title={version ? `v${version.number} and now` : ""} wide="xl">
      <div ref={box} className="relative h-[65vh] select-none overflow-hidden rounded-md ring-1 ring-line"
        onPointerMove={(e) => { if (e.buttons === 1) drag(e); }} onPointerDown={drag}>
        {before === null || !version ? <div className="size-full bg-surface-2" aria-label="Loading" /> : (
          <>
            <iframe title={`Version ${version.number}`} srcDoc={before} sandbox="" className="pointer-events-none absolute inset-0 size-full bg-white" tabIndex={-1} />
            <iframe title="Now" srcDoc={(page && site.pages?.find((p) => p.slug === page)?.html) || site.html} sandbox="" className="pointer-events-none absolute inset-0 size-full bg-white" tabIndex={-1}
              style={{ clipPath: `inset(0 0 0 ${split}%)` }} />
          </>
        )}
        <div className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-strong" style={{ left: `${split}%` }}>
          <span className="absolute top-1/2 left-1/2 h-10 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-strong ring-2 ring-white" />
        </div>
        <span className="absolute top-2 left-2 rounded bg-strong px-1.5 text-xs font-medium leading-5 text-white">v{version?.number}</span>
        <span className="absolute top-2 right-2 rounded bg-strong px-1.5 text-xs font-medium leading-5 text-white">Now</span>
      </div>
      <label className="mt-3 flex items-center gap-3 text-xs text-muted">
        <span className="shrink-0">Before</span>
        <input type="range" min={0} max={100} value={split} onChange={(e) => setSplit(+e.target.value)} className="w-full accent-[var(--color-strong)]" aria-label="Move the split" />
        <span className="shrink-0">Now</span>
      </label>
    </Modal>
  );
}

export function ChangesList({ site, page = "", onRestore }) {
  const { data: versions, reload, loading } = useApi(`/api/sites/${site.id}/versions?page=${encodeURIComponent(page)}`, []);
  const [busy, setBusy] = useState(null);
  const [comparing, setComparing] = useState(null);
  useEffect(() => { reload(); }, [site.html, site.pages, reload]);
  const restore = async (v) => {
    setBusy(v.id);
    try { onRestore(await post(`/api/sites/${site.id}/versions/${v.id}/restore`)); toast(`Back to v${v.number}.`); }
    catch (e) { toast.error(e.message); } finally { setBusy(null); }
  };
  if (loading && !versions.length) return <p className="px-4 py-3 text-sm text-muted">…</p>;
  if (!versions.length) return <p className="px-4 py-3 text-sm text-muted">Your changes will show here.</p>;
  return (
    <>
      <ol className="divide-y divide-line">
        {versions.map((v) => (
          <li key={v.id} className={cx("px-4 py-3", v.current && "bg-accent-soft/50")}>
            <p className="text-sm text-strong">
              {v.by && <span className="font-medium">{v.by}: </span>}{said(v)} <span className="text-muted">· v{v.number}</span>
            </p>
            <p className="mt-0.5 flex items-center gap-3 text-xs text-muted">
              <span>{timeAgo(v.created_at)}</span>
              {v.current ? <span className="font-medium text-strong">Showing now</span> : (
                <>
                  <button type="button" className="font-medium text-brand hover:underline disabled:opacity-50" disabled={busy !== null} onClick={() => restore(v)}>
                    {busy === v.id ? "Restoring…" : "Restore"}
                  </button>
                  <button type="button" className="font-medium text-brand hover:underline" onClick={() => setComparing(v)}>Compare</button>
                </>
              )}
            </p>
          </li>
        ))}
      </ol>
      <Compare site={site} page={page} version={comparing} onClose={() => setComparing(null)} />
    </>
  );
}
