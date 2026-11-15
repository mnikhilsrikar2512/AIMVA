// The workspace every module opens into after its first prompt (design.md v3, sections 4 and 7.3): the result fills
// the canvas, and the changes panel on the right lists each request in the owner's or a teammate's own words, who
// asked when it wasn't you, the version it made, Restore on older ones and Compare. The prompt box sits at its foot.
// The panel never narrates what AIMVA did or how it read a request.
import { useEffect, useRef, useState } from "react";
import { ArrowUp, ChevronDown, PanelRightClose, PanelRightOpen } from "lucide-react";
import { Tooltip } from "./shadcn/tooltip";
import { Modal, Spinner, cx } from "./ui";
import { timeAgo } from "../lib/hooks";

const PANEL_KEY = "aimva_changes_panel";

/** Whether the changes panel is open, remembered across modules (folded on one, folded on all). */
export function usePanelOpen() {
  const [open, setOpen] = useState(() => { try { return localStorage.getItem(PANEL_KEY) !== "folded"; } catch { return true; } });
  const toggle = () => setOpen((o) => { try { localStorage.setItem(PANEL_KEY, o ? "folded" : "open"); } catch { /* private window */ } return !o; });
  return [open, toggle];
}

/**
 * The frame: a toolbar over the canvas (title on the left; icons and the one primary action on the right), the
 * canvas, and the panel. Edge to edge under the header, no card around it.
 */
export function ModuleFrame({ toolbar, children, panel }) {
  return (
    <div className="-mx-4 -mt-5 -mb-8 flex flex-col border-line sm:-mx-6 sm:-my-6 lg:-mx-8 lg:-mt-8 lg:-mb-12 lg:h-[calc(100dvh-3.5rem)] lg:min-h-[560px] lg:flex-row">
      <section className="flex min-w-0 flex-1 flex-col lg:min-h-0">
        {toolbar && <div className="flex min-h-12 shrink-0 flex-wrap items-center gap-2 border-b border-line px-4 py-2 sm:px-6 lg:flex-nowrap lg:px-8">{toolbar}</div>}
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8">{children}</div>
      </section>
      {panel}
    </div>
  );
}

/** Left side of the toolbar: the thing's name and one muted status word. */
export function ToolbarTitle({ children, status }) {
  return (
    <p className="mr-auto flex min-w-0 basis-full items-baseline gap-2 sm:basis-auto sm:flex-1">
      <span className="truncate text-sm font-medium text-strong">{children}</span>
      {status && <span className="shrink-0 text-xs text-muted">{status}</span>}
    </p>
  );
}

/** The words a version shows: the request itself, else its plain label. */
const said = (v) => (v.request || "").trim() || v.note || `Version ${v.number}`;

/**
 * The changes panel.
 * - versions: [{id, number, request, note, by, created_at, current, state?: "making" | "failed"}], newest first
 * - onRestore(v), onCompare(v): Restore and Compare on older versions (Compare is left out when not given)
 * - onSend(text): the prompt box; resolves true when the text should clear
 * - extra: anything the module keeps above the list (a switch, a note)
 */
export function ChangesPanel({ open, onToggle, versions = [], loading, onRestore, onCompare, onSend, sending, placeholder = "Change anything…", extra, restoreLabel = "Restore" }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(null);
  const [listOpen, setListOpen] = useState(false);  // phones: the list folds under one line, the prompt box stays
  const ref = useRef(null);
  const send = async (e) => {
    e?.preventDefault();
    const t = text.trim();
    if (!t || sending || !onSend) return;
    if ((await onSend(t)) !== false) setText("");
  };
  const restore = async (v) => { setBusy(v.id); try { await onRestore(v); } finally { setBusy(null); } };

  if (!open) {
    return (
      <aside aria-label="Changes" className="hidden w-12 shrink-0 flex-col items-center border-l border-line pt-2 lg:flex">
        <Tooltip content="Changes"><button type="button" className="btn-subtle btn-sm w-8 px-0" onClick={onToggle} aria-label="Open the changes panel"><PanelRightOpen className="size-4" /></button></Tooltip>
      </aside>
    );
  }
  const list = loading && !versions.length ? <p className="px-4 py-3 text-sm text-muted">…</p>
    : !versions.length ? <p className="px-4 py-3 text-sm text-muted">Your changes will show here.</p> : (
      <ol className="divide-y divide-line">
        {versions.map((v) => (
          <li key={v.id} className={cx("px-4 py-3", v.current && "bg-accent-soft/50")}>
            <p className="text-sm text-strong">
              {v.by && <span className="font-medium">{v.by}: </span>}{said(v)} <span className="text-muted">· v{v.number}</span>
            </p>
            <p className="mt-0.5 flex items-center gap-3 text-xs text-muted">
              <span>{v.state === "making" ? "Making it…" : timeAgo(v.created_at)}</span>
              {v.state === "failed" ? <span className="text-danger">Didn't finish</span>
                : v.state === "making" ? null
                : v.current ? <span className="font-medium text-strong">Showing now</span> : (
                  <>
                    {onRestore && (
                      <button type="button" className="font-medium text-brand hover:underline disabled:opacity-50" disabled={busy !== null} onClick={() => restore(v)}>
                        {busy === v.id ? "Restoring…" : restoreLabel}
                      </button>
                    )}
                    {onCompare && <button type="button" className="font-medium text-brand hover:underline" onClick={() => onCompare(v)}>Compare</button>}
                  </>
                )}
            </p>
          </li>
        ))}
      </ol>
    );
  return (
    <aside aria-label="Changes" className="flex w-full shrink-0 flex-col border-t border-line bg-surface lg:w-[360px] lg:border-l lg:border-t-0">
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-line pl-4 pr-2">
        <button type="button" className="flex items-center gap-1.5 text-sm font-semibold text-strong lg:pointer-events-none" aria-expanded={listOpen} onClick={() => setListOpen((o) => !o)}>
          Changes{versions.length ? <span className="font-normal text-muted lg:hidden"> · {versions.length}</span> : null}
          <ChevronDown className={cx("size-4 text-muted lg:hidden", listOpen && "rotate-180")} />
        </button>
        <Tooltip content="Fold"><button type="button" className="btn-subtle btn-sm hidden w-8 px-0 lg:inline-flex" onClick={onToggle} aria-label="Fold the changes panel"><PanelRightClose className="size-4" /></button></Tooltip>
      </div>
      {extra && <div className="shrink-0 border-b border-line px-4 py-3">{extra}</div>}
      <div className={cx("min-h-0 flex-1 overflow-y-auto", !listOpen && "hidden lg:block")}>{list}</div>
      {onSend && (
        <form onSubmit={send} className="sticky bottom-0 shrink-0 border-t border-line bg-surface p-3">
          <div className="flex items-end gap-2 rounded-[10px] ring-1 ring-line-strong focus-within:ring-2 focus-within:ring-brand/50">
            <textarea ref={ref} rows={2} value={text} onChange={(e) => setText(e.target.value)} maxLength={300} disabled={sending}
              aria-label="What should change?" placeholder={placeholder}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) send(e); }}
              className="block min-h-[3.25rem] w-full resize-none bg-transparent px-3 py-2.5 text-sm text-strong placeholder:text-muted focus:outline-none" />
            <Tooltip content="Send (Enter)">
              <button type="submit" aria-label="Send" disabled={!text.trim() || sending}
                className="m-1.5 grid size-8 shrink-0 place-items-center rounded-md bg-strong text-white disabled:opacity-40">
                {sending ? <Spinner className="size-4" /> : <ArrowUp className="size-4" />}
              </button>
            </Tooltip>
          </div>
        </form>
      )}
    </aside>
  );
}

/** Before/after with a drag handle. `before` and `after` are elements of the same size (img, video poster, iframe). */
export function CompareSplit({ open, onClose, title, before, after }) {
  const [split, setSplit] = useState(50);
  const box = useRef(null);
  useEffect(() => { if (open) setSplit(50); }, [open]);
  const drag = (e) => {
    const r = box.current?.getBoundingClientRect();
    if (r) setSplit(Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100)));
  };
  return (
    <Modal open={open} onClose={onClose} title={title} wide="xl">
      <div ref={box} className="relative mx-auto grid h-[65vh] select-none place-items-center overflow-hidden rounded-md bg-surface-2"
        onPointerMove={(e) => { if (e.buttons === 1) drag(e); }} onPointerDown={drag}>
        <div className="pointer-events-none absolute inset-0 grid place-items-center">{before}</div>
        <div className="pointer-events-none absolute inset-0 grid place-items-center" style={{ clipPath: `inset(0 0 0 ${split}%)` }}>{after}</div>
        <div className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-strong" style={{ left: `${split}%` }}>
          <span className="absolute top-1/2 left-1/2 h-10 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-strong ring-2 ring-white" />
        </div>
        <span className="absolute top-2 left-2 rounded bg-strong px-1.5 text-xs font-medium leading-5 text-white">Before</span>
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

/** Before/after for words (a call script, an ad): two columns, the lines that changed marked. */
export function CompareText({ open, onClose, title, before, after }) {
  const rows = before && after ? Object.keys({ ...before, ...after }) : [];
  return (
    <Modal open={open} onClose={onClose} title={title} wide="xl">
      {!before || !after ? <div className="h-40 rounded-md bg-surface-2" aria-label="Loading" /> : (
        <div className="max-h-[65vh] overflow-y-auto">
          <div className="grid grid-cols-[8rem_1fr_1fr] gap-x-4 border-b border-line pb-2 text-xs font-medium text-muted">
            <span /><span>Before</span><span>Now</span>
          </div>
          {rows.map((k) => {
            const changed = JSON.stringify(before[k]) !== JSON.stringify(after[k]);
            return (
              <div key={k} className={cx("grid grid-cols-[8rem_1fr_1fr] gap-x-4 border-b border-line py-2.5 text-sm", changed && "bg-warm-soft/60")}>
                <span className="text-xs text-muted">{k}</span>
                <span className="whitespace-pre-wrap text-ink">{before[k]}</span>
                <span className="whitespace-pre-wrap text-strong">{after[k]}</span>
              </div>
            );
          })}
        </div>
      )}
    </Modal>
  );
}
