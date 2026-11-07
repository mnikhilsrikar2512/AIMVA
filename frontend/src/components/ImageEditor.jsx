import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, ChevronDown, Expand, Eye, ImageUp, MousePointerClick, Palette, Redo2, Search, SlidersHorizontal, Undo2, Wand2, X } from "lucide-react";
import { Button, Field, Modal, Tabs, cx } from "./ui";
import { post } from "../lib/api";
import { useAction, useApi } from "../lib/hooks";

const MAX_PINS = 8;
const SIZES = [["S", 0.06], ["M", 0.12], ["L", 0.2], ["XL", 0.32]];
const QUICK = [["Remove", "Remove this completely and fill the area with the matching background, so nothing is left behind."],
  ["Brighter", "Make this brighter and better lit, keep its colours natural."], ["Sharper", "Make this sharper and more detailed."],
  ["Fix it", "Fix any distortion here: natural shapes, correct hands and faces, clean edges."]];
// Mirrors the server's guess (app/image_edit.py intent): only-removing comments go to the eraser model.
const REMOVE_RE = /\b(remove|delete|erase|get rid of|take (out|away)|eliminate|hide|lose|clear (away|out))\b/i;
const ADD_RE = /\b(add|put|place|replace|swap|instead|insert|with a|with an|turn (it )?into)\b/i;
const guess = (t) => (REMOVE_RE.test(t) && !ADD_RE.test(t) ? "remove" : "change");
const WHOLE_IDEAS = ["Make it golden hour", "Make it night time", "Brighter and more vibrant"];
const TRY_STYLES = ["portrait", "skeleton", "anime", "cinematic", "watercolor"];
const PLACEMENTS = [["1:1", "Feed square"], ["4:5", "Feed portrait"], ["9:16", "Stories & Reels"], ["16:9", "YouTube & display"], ["1.91:1", "Link ads & Google"]];
const SLASH = /(^|\s)\/([\w-]*)$/; // "/ske" at the end of what's typed opens the style menu
const hasText = (p) => p.text.trim().length >= 2;

/** Image editor, chat style: click the image and type what to change there, or type in the box below for the whole
 *  image (with /styles). Enter applies. Every result is a new version you can undo; the original is never changed. */
export default function ImageEditor({ asset, open, onClose, onEdited }) {
  const { data: info } = useApi(open ? "/api/content/image/edit-engines" : null, { engines: [] });
  const { data: styles } = useApi(open ? "/api/content/image/styles" : null, []);
  const [versions, setVersions] = useState([]);
  const [at, setAt] = useState(0);
  const [pins, setPins] = useState([]);
  const [active, setActive] = useState(null);
  const [text, setText] = useState("");
  const [style, setStyle] = useState(null);
  const [engine, setEngine] = useState("auto");
  const [side, setSide] = useState("versions");
  const [peek, setPeek] = useState(false);
  const [busy, run] = useAction();
  const box = useRef(null);
  const composer = useRef(null);

  useEffect(() => {
    if (!open || !asset) return;
    setVersions([asset]); setAt(0); setPins([]); setActive(null); setText(""); setStyle(null); setEngine("auto"); setSide("versions");
  }, [open, asset]);
  const source = versions[at];
  if (!open || !asset || !source) return null;

  const engines = info?.engines || [];
  const chosen = engine === "auto" ? engines[0] : engines.find((e) => e.ref === engine);
  const canSelect = !!info?.select_objects;
  const typed = text.replace(SLASH, "$1").trim();
  const queued = pins.filter(hasText);
  const ready = !busy && (queued.length > 0 || !!style || typed.length >= 3);
  const before = versions[at - 1];
  const shown = peek && before ? before : source;

  const reset = () => { setPins([]); setActive(null); setText(""); setStyle(null); };
  const place = (e) => {
    if (busy || peek) return;
    // Clicking away from an open, empty comment just closes it.
    const open_ = pins.find((p) => p.id === active);
    if (open_ && !hasText(open_)) { setPins((p) => p.filter((x) => x.id !== active)); setActive(null); return; }
    if (pins.length >= MAX_PINS) return;
    const r = box.current.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    const y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
    const id = Date.now();
    setPins((p) => [...p, { id, x, y, r: 0.12, text: "", mode: canSelect ? "object" : "area", action: "auto" }]);
    setActive(id);
  };
  const update = (id, patch) => setPins((p) => p.map((x) => (x.id === id ? { ...x, ...patch } : x)));
  const remove = (id) => { setPins((p) => p.filter((x) => x.id !== id)); if (active === id) setActive(null); };

  const saved = (out) => {
    if (!out) return;
    setVersions((v) => [...v.slice(0, at + 1), out]);
    setAt(at + 1);
    reset();
    onEdited?.(out);
  };
  const send = () => {
    if (!ready) return;
    const body = { engine, instruction: typed, style: style?.id || "",
      pins: queued.map(({ x, y, r, text: t, mode, action }) => ({ x, y, r, text: t.trim(), mode, action })) };
    run(async () => saved(await post(`/api/content/image/${source.id}/edit`, body)), style && !queued.length ? `${style.name} style applied` : "Done. Saved as a new version");
  };
  const tool = (path, body, msg) => run(async () => saved(await post(`/api/content/image/${source.id}/${path}`, body)), msg);
  const ideas = styles.length ? TRY_STYLES.map((id) => styles.find((s) => s.id === id)).filter(Boolean) : [];

  return (
    <Modal open={open} onClose={onClose} title="Edit image" wide="xl">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0">
          <div ref={box} className={cx("relative select-none rounded-2xl bg-surface-2", !busy && "cursor-crosshair")} onClick={place}>
            <img src={shown.url} alt={shown.prompt || "Image"} className="block w-full rounded-2xl" draggable={false} />
            {!peek && pins.map((p, i) => (
              <PinMark key={p.id} pin={p} n={i + 1} open={active === p.id} canSelect={canSelect} busy={busy}
                onOpen={() => setActive(p.id)} onClose={() => setActive(null)} update={(patch) => update(p.id, patch)}
                onRemove={() => remove(p.id)} onSend={send} ready={ready} />
            ))}
            {busy && (
              <div className="absolute inset-0 grid place-items-center rounded-2xl bg-strong/30 backdrop-blur-[2px]">
                <div className="rounded-full bg-white/95 px-4 py-2 text-sm font-semibold text-strong shadow-lg">
                  <Wand2 className="mr-1.5 inline size-4 animate-pulse text-violet-600" /> Working on it… up to a minute
                </div>
              </div>
            )}
            {peek && <span className="absolute left-3 top-3 rounded-full bg-strong/80 px-2.5 py-1 text-xs font-semibold text-white">Before</span>}
            <ShortSide target={box} />
          </div>

          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
            <span>{pins.length ? `${queued.length} spot${queued.length === 1 ? "" : "s"} ready · click again to add more` : "Tip: click anything in the image to change just that spot"}</span>
            <span className="flex items-center gap-1">
              <span data-repeat className="contents"><IconBtn label="Undo" disabled={busy || at === 0} onClick={() => { setAt(at - 1); reset(); }}><Undo2 className="size-4" /></IconBtn>
              <IconBtn label="Redo" disabled={busy || at >= versions.length - 1} onClick={() => { setAt(at + 1); reset(); }}><Redo2 className="size-4" /></IconBtn></span>
              {before && (
                <button type="button" className="ml-1 inline-flex items-center gap-1 rounded-full bg-ink/[0.05] px-2.5 py-1 font-semibold hover:text-strong"
                  onPointerDown={() => setPeek(true)} onPointerUp={() => setPeek(false)} onPointerLeave={() => setPeek(false)}>
                  <Eye className="size-3.5" /> Hold to compare
                </button>
              )}
            </span>
          </div>

          <Composer {...{ composer, text, setText, style, setStyle, styles, pins: queued, removePin: remove, ready, busy, send }} />

          {!pins.length && !style && !text.trim() && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-xs text-muted">Try</span>
              {ideas.map((s) => (
                <Chip key={s.id} title={s.hint} onClick={() => { setStyle(s); composer.current?.focus(); }}>/{s.id}</Chip>
              ))}
              {WHOLE_IDEAS.map((t) => <Chip key={t} onClick={() => { setText(t); composer.current?.focus(); }}>{t}</Chip>)}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <Tabs value={side} onChange={setSide} tabs={[{ value: "versions", label: "Versions" }, { value: "more", label: "More tools" }]} />
          {side === "versions" && (
            <Versions versions={versions} at={at} busy={busy} onPick={(i) => { setAt(i); reset(); }} onClose={onClose} />
          )}
          {side === "more" && (
            <MorePanel busy={busy} chosen={chosen} info={info} source={source}
              onExtend={(size) => tool("extend", { size, engine }, `Extended to ${size} and saved`)}
              onBackground={(prompt) => tool("background", { prompt }, "New background saved")}
              onUpscale={(factor) => tool("upscale", { factor }, "Upscaled copy saved")} />
          )}
          <details className="rounded-2xl border border-ink/10 p-3 text-sm">
            <summary className="flex cursor-pointer items-center gap-1.5 font-semibold text-strong"><SlidersHorizontal className="size-4" /> Settings</summary>
            <div className="mt-3 space-y-3"><EngineSelect engines={engines} engine={engine} setEngine={setEngine} chosen={chosen} /></div>
          </details>
        </div>
      </div>
    </Modal>
  );
}

/** A pin on the image. While open it shows a small comment box right there; Enter applies. */
function PinMark({ pin: p, n, open, canSelect, busy, onOpen, onClose, update, onRemove, onSend, ready }) {
  const right = p.x > 0.6;
  const low = p.y > 0.62;
  const does = (p.action || "auto") === "auto" ? guess(p.text) : p.action;
  return (
    <div className="absolute" style={{ left: `${p.x * 100}%`, top: `${p.y * 100}%` }} onClick={(e) => e.stopPropagation()}>
      {p.mode === "area" && (
        <div className={cx("pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-dashed",
          open ? "border-violet-500 bg-violet-500/15" : "border-white/90 bg-white/10")}
          style={{ width: `calc(${p.r * 2} * var(--short))`, height: `calc(${p.r * 2} * var(--short))` }} />
      )}
      <button type="button" title={p.text || "Comment"} onClick={open ? onClose : onOpen}
        className={cx("absolute grid size-7 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full text-xs font-bold text-white shadow-lg ring-2 ring-white",
          open ? "bg-violet-600" : hasText(p) ? "bg-strong/85" : "bg-strong/50")}>
        {p.mode === "object" ? <MousePointerClick className="size-3.5" /> : n}
      </button>
      {open && !busy && (
        <div className={cx("absolute z-10 w-72 max-w-[80vw] cursor-default rounded-2xl bg-surface p-2.5 shadow-2xl ring-1 ring-ink/10",
          right ? "right-5" : "left-5", low ? "bottom-1" : "top-1")}>
          <textarea autoFocus rows={2} maxLength={300} value={p.text} placeholder="What should change here?"
            className="w-full resize-none bg-transparent px-1 text-sm text-strong outline-none placeholder:text-faint"
            onChange={(e) => update({ text: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (ready) onSend(); }
              if (e.key === "Escape") { e.stopPropagation(); hasText(p) ? onClose() : onRemove(); }
            }} />
          <div className="flex flex-wrap gap-1">
            {QUICK.map(([label, t]) => <Chip key={label} small onClick={() => update({ text: t, action: label === "Remove" ? "remove" : "auto" })}>{label}</Chip>)}
          </div>
          <div className="mt-2 flex items-center justify-between gap-2 border-t border-ink/5 pt-2">
            <div className="flex flex-wrap items-center gap-1">
              {canSelect && <Chip small on={p.mode === "object"} onClick={() => update({ mode: "object" })}>Object</Chip>}
              {SIZES.map(([label, r]) => <Chip key={label} small on={p.mode === "area" && p.r === r} onClick={() => update({ r, mode: "area" })}>{label}</Chip>)}
              <button type="button" className="ml-0.5 text-xs font-semibold text-muted hover:text-strong" title="Change what this comment does"
                onClick={() => update({ action: { auto: "change", change: "remove", remove: "auto" }[p.action || "auto"] })}>
                {p.text.trim() || p.action !== "auto" ? (does === "remove" ? "Removes" : "Changes") + ((p.action || "auto") === "auto" ? " (auto)" : "") : ""}
              </button>
            </div>
            <div className="flex items-center gap-1">
              <IconBtn label="Delete comment" onClick={onRemove}><X className="size-4" /></IconBtn>
              <SendBtn disabled={!ready} onClick={onSend} />
            </div>
          </div>
          <p className="mt-1 px-1 text-xs text-faint">Enter to apply · Shift+Enter new line · click elsewhere for another spot</p>
        </div>
      )}
    </div>
  );
}

/** The chat box under the image: whole-image changes, /styles, and Enter to apply everything. */
function Composer({ composer, text, setText, style, setStyle, styles, pins, removePin, ready, busy, send }) {
  const [menu, setMenu] = useState(false);
  const [hi, setHi] = useState(0);
  const slash = text.match(SLASH);
  const query = slash ? slash[2].toLowerCase() : "";
  const matches = useMemo(() => (slash ? styles.filter((s) => s.id.includes(query) || s.name.toLowerCase().includes(query)).slice(0, 8) : []),
    [slash, query, styles]);
  useEffect(() => setHi(0), [query]);
  const pick = (s) => { setStyle(s); setText((t) => t.replace(SLASH, "$1").replace(/\s+$/, "")); setMenu(false); composer.current?.focus(); };
  const grow = (el) => { el.style.height = "auto"; el.style.height = `${Math.min(el.scrollHeight, 160)}px`; };

  return (
    <div className="relative mt-3">
      {matches.length > 0 && (
        <div className="absolute bottom-full left-0 z-20 mb-2 w-full max-w-sm overflow-hidden rounded-2xl bg-surface shadow-2xl ring-1 ring-ink/10">
          <p className="px-3 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-faint">Styles</p>
          {matches.map((s, i) => (
            <button key={s.id} type="button" onMouseEnter={() => setHi(i)} onMouseDown={(e) => { e.preventDefault(); pick(s); }}
              className={cx("flex w-full items-baseline gap-2 px-3 py-1.5 text-left text-sm", i === hi && "bg-violet-50")}>
              <b className="text-strong">/{s.id}</b><span className="truncate text-xs text-muted">{s.hint}</span>
            </button>
          ))}
        </div>
      )}
      {menu && <StyleMenu styles={styles} current={style} onPick={pick} onClose={() => setMenu(false)} />}
      <div className={cx("rounded-3xl border bg-surface p-2 shadow-sm transition focus-within:border-violet-400 focus-within:shadow-md", busy ? "opacity-60" : "border-ink/15")}>
        {(style || pins.length > 0) && (
          <div className="flex flex-wrap gap-1.5 px-1.5 pb-1.5 pt-0.5">
            {style && (
              <span className="inline-flex items-center gap-1 rounded-full bg-violet-100 py-0.5 pl-2.5 pr-1 text-xs font-semibold text-violet-800" title={style.prompt}>
                <Palette className="size-3.5" /> {style.name}
                <button type="button" aria-label="Remove style" className="rounded-full p-0.5 hover:bg-violet-200" onClick={() => setStyle(null)}><X className="size-3" /></button>
              </span>
            )}
            {pins.map((p, i) => (
              <span key={p.id} className="inline-flex max-w-[16rem] items-center gap-1 rounded-full bg-ink/[0.06] py-0.5 pl-2.5 pr-1 text-xs text-strong">
                <b>{i + 1}</b> <span className="truncate">{p.text}</span>
                <button type="button" aria-label="Remove comment" className="rounded-full p-0.5 hover:bg-ink/10" onClick={() => removePin(p.id)}><X className="size-3" /></button>
              </span>
            ))}
          </div>
        )}
        <textarea ref={composer} rows={1} maxLength={500} value={text} disabled={busy}
          placeholder={pins.length || style ? "Anything else? (optional) · Enter to apply" : "Describe a change to the whole image, or type / for styles"}
          className="block max-h-40 w-full resize-none bg-transparent px-2 py-1.5 text-sm text-strong outline-none placeholder:text-faint"
          onChange={(e) => { setText(e.target.value); grow(e.target); }}
          onKeyDown={(e) => {
            if (matches.length) {
              if (e.key === "ArrowDown") { e.preventDefault(); setHi((hi + 1) % matches.length); return; }
              if (e.key === "ArrowUp") { e.preventDefault(); setHi((hi - 1 + matches.length) % matches.length); return; }
              if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); pick(matches[hi]); return; }
              if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setText((t) => t.replace(SLASH, "$1")); return; }
            }
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }} />
        <div className="flex items-center justify-between gap-2 px-1 pt-1">
          <button type="button" data-style-toggle onClick={() => setMenu((m) => !m)} disabled={busy}
            className={cx("inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold", style ? "bg-violet-100 text-violet-800" : "bg-ink/[0.05] text-muted hover:text-strong")}>
            <Palette className="size-3.5" /> {style ? style.name : "Style"} <ChevronDown className="size-3" />
          </button>
          <SendBtn disabled={!ready} busy={busy} onClick={send} big />
        </div>
      </div>
    </div>
  );
}

/** Every style, grouped and searchable, each with one line on what it does. */
function StyleMenu({ styles, current, onPick, onClose }) {
  const [q, setQ] = useState("");
  const ref = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const away = (e) => { if (ref.current && !ref.current.contains(e.target) && !e.target.closest?.("[data-style-toggle]")) close.current(); };
    window.addEventListener("pointerdown", away);
    return () => window.removeEventListener("pointerdown", away);
  }, []);
  const shown = styles.filter((s) => `${s.id} ${s.name} ${s.hint} ${s.group}`.toLowerCase().includes(q.trim().toLowerCase()));
  const groups = [...new Set(shown.map((s) => s.group))];
  return (
    <div ref={ref} className="absolute bottom-full left-0 z-20 mb-2 w-full max-w-lg rounded-2xl bg-surface p-3 shadow-2xl ring-1 ring-ink/10">
      <div className="mb-2 flex items-center gap-2 rounded-xl bg-ink/[0.04] px-3">
        <Search className="size-4 text-faint" />
        <input autoFocus className="w-full bg-transparent py-2 text-sm outline-none" placeholder="Search styles… e.g. anime, skeleton, night"
          value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } if (e.key === "Enter" && shown[0]) onPick(shown[0]); }} />
      </div>
      <p className="mb-2 px-1 text-xs text-muted">Changes the look of the whole picture and keeps the same people and layout. Tip: type <b>/</b> in the box to pick one faster.</p>
      <div className="max-h-72 space-y-3 overflow-y-auto pr-1">
        {groups.map((g) => (
          <section key={g}>
            <p className="mb-1 px-1 text-xs font-semibold uppercase tracking-wide text-faint">{g}</p>
            <div className="grid grid-cols-2 gap-1.5">
              {shown.filter((s) => s.group === g).map((s) => (
                <button key={s.id} type="button" onClick={() => onPick(s)}
                  className={cx("rounded-xl border px-2.5 py-1.5 text-left hover:border-violet-400", current?.id === s.id ? "border-violet-500 bg-violet-50" : "border-ink/10")}>
                  <span className="block text-sm font-semibold text-strong">{s.name}</span>
                  <span className="block text-xs leading-snug text-muted">{s.hint}</span>
                </button>
              ))}
            </div>
          </section>
        ))}
        {!shown.length && <p className="px-1 py-4 text-center text-sm text-muted">No style matches. Describe the look in the box instead.</p>}
      </div>
    </div>
  );
}

function Versions({ versions, at, busy, onPick, onClose }) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted">Each change is saved as a new version in History. The original is never changed.</p>
      <ol className="grid max-h-[40vh] grid-cols-3 gap-2 overflow-y-auto">
        {versions.map((v, i) => (
          <li key={v.id}>
            <button type="button" disabled={busy} onClick={() => onPick(i)} title={label(v, i)}
              className={cx("block w-full overflow-hidden rounded-xl ring-2", i === at ? "ring-violet-500" : "ring-transparent hover:ring-ink/20")}>
              <img src={v.url} alt="" loading="lazy" decoding="async" className="aspect-square w-full object-cover" />
            </button>
            <p className="mt-0.5 truncate text-xs text-muted">{label(v, i)}</p>
          </li>
        ))}
      </ol>
      <Button className="w-full" onClick={onClose}>Done</Button>
    </div>
  );
}

const label = (v, i) => (i === 0 ? "Original" : v.params?.restyle && !v.params?.edits?.length ? v.params.restyle
  : v.params?.edits?.length ? `${v.params.edits.length} spot${v.params.edits.length > 1 ? "s" : ""}` : v.params?.extended_for ? `Size ${v.params.extended_for}`
  : v.params?.provider_label || `Version ${i + 1}`);

function Chip({ children, on, small, ...props }) {
  return (
    <button type="button" {...props} className={cx("rounded-full font-semibold", small ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-xs",
      on ? "bg-violet-600 text-white" : "bg-ink/[0.05] text-muted hover:text-strong")}>{children}</button>
  );
}

function IconBtn({ label: l, children, ...props }) {
  return <button type="button" aria-label={l} title={l} className="rounded-full p-1.5 text-muted hover:bg-ink/[0.06] hover:text-strong disabled:opacity-30" {...props}>{children}</button>;
}

function SendBtn({ disabled, busy, onClick, big }) {
  return (
    <button type="button" aria-label="Apply" title="Apply (Enter)" disabled={disabled} onClick={onClick}
      className={cx("grid place-items-center rounded-full bg-violet-600 text-white transition hover:bg-violet-700 disabled:bg-ink/15 disabled:text-white", big ? "size-9" : "size-7")}>
      {busy ? <span className="size-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" /> : <ArrowUp className={big ? "size-4" : "size-3.5"} />}
    </button>
  );
}

function EngineSelect({ engines, engine, setEngine, chosen }) {
  if (!engines.length) return null;
  return (
    <>
      <Field label="Edit with">
        <select className="input" value={engine} onChange={(e) => setEngine(e.target.value)}>
          <option value="auto">Best available ({engines[0]?.name})</option>
          {engines.map((e) => <option key={e.ref} value={e.ref}>{e.name}</option>)}
        </select>
      </Field>
      {chosen && !chosen.precise && (
        <p className="rounded-xl bg-amber-50 p-3 text-xs text-amber-800">
          The free model can't repaint one spot, so it redraws the picture and AIMVA keeps only the parts you marked.
          Results can look patched. Connect fal.ai in Settings for precise edits and object selection.
        </p>
      )}
    </>
  );
}

function MorePanel({ busy, chosen, info, source, onExtend, onBackground, onUpscale }) {
  const [bg, setBg] = useState("");
  const ratio = (source.params?.width || 1) / (source.params?.height || 1);
  return (
    <div className="space-y-5">
      <section>
        <p className="flex items-center gap-1.5 text-sm font-semibold text-strong"><Expand className="size-4" /> Extend to another size</p>
        <p className="mb-2 mt-0.5 text-xs text-muted">Paints in the missing edges instead of cropping. Your image stays untouched in the middle.</p>
        <div className="grid grid-cols-2 gap-2">
          {PLACEMENTS.map(([k, label]) => {
            const [a, b] = k.split(":").map(Number);
            const same = Math.abs(ratio - a / b) < 0.02;
            return (
              <button key={k} type="button" disabled={busy || same} onClick={() => onExtend(k)}
                className="rounded-xl border border-ink/10 px-3 py-2 text-left text-xs hover:border-violet-400 disabled:opacity-40">
                <b className="text-strong">{k}</b><br /><span className="text-muted">{same ? "Current size" : label}</span>
              </button>
            );
          })}
        </div>
        {chosen && !chosen.precise && <p className="mt-2 text-xs text-amber-700">Free model: the edges are redrawn separately and may not match perfectly.</p>}
      </section>
      <section>
        <p className="flex items-center gap-1.5 text-sm font-semibold text-strong"><ImageUp className="size-4" /> New background</p>
        <p className="mb-2 mt-0.5 text-xs text-muted">Keeps your main subject exactly and paints a new scene behind it.</p>
        {info?.replace_background ? (
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); onBackground(bg); }}>
            <input className="input text-sm" value={bg} onChange={(e) => setBg(e.target.value)} minLength={3} maxLength={500} required placeholder="e.g. a sunny beach terrace" />
            <Button type="submit" busy={busy} size="sm">Go</Button>
          </form>
        ) : <p className="rounded-xl bg-ink/[0.03] p-3 text-xs text-muted">Needs fal.ai. Connect it in Settings → Integrations.</p>}
      </section>
      <section>
        <p className="flex items-center gap-1.5 text-sm font-semibold text-strong"><Wand2 className="size-4" /> Upscale</p>
        <p className="mb-2 mt-0.5 text-xs text-muted">{info?.ai_upscale ? "AI upscaling adds real detail (fal.ai)." : "Basic high-quality resize. Connect fal.ai for AI upscaling that adds detail."}</p>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => onUpscale(2)}>2× larger</Button>
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => onUpscale(4)}>4× larger</Button>
        </div>
      </section>
    </div>
  );
}

/** Keeps a CSS variable with the image's shorter side in px, so circle sizes match what the server masks. */
function ShortSide({ target }) {
  useEffect(() => {
    const el = target.current;
    if (!el) return;
    const set = () => el.style.setProperty("--short", `${Math.min(el.clientWidth, el.clientHeight)}px`);
    set();
    const ro = new ResizeObserver(set);
    ro.observe(el);
    return () => ro.disconnect();
  }, [target]);
  return null;
}
