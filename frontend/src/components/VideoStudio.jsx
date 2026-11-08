import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowUp, Pause, Play, X } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle } from "./shadcn/dialog";
import { Button, cx } from "./ui";
import { post } from "../lib/api";

const MAX = 12;
const clock = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

/**
 * Full-screen video review, with comments drawn like Claude's: pause anywhere, click a spot on the frame,
 * type what should change. Each comment remembers its moment and spot. "Make new version" renders a new clip
 * with those changes (AI video models redo the whole clip; they can't patch one spot).
 */
export default function VideoStudio({ video, versions = [], open, onClose, onCreated, onPick }) {
  const v = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [t, setT] = useState(0);
  const [dur, setDur] = useState(0);
  const [notes, setNotes] = useState([]);   // {id, t, x, y, text}
  const [active, setActive] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setNotes([]); setActive(null); setT(0); setPlaying(false); }, [video?.id]);
  if (!video) return null;

  const toggle = () => { const el = v.current; if (!el) return; if (el.paused) { el.play(); setActive(null); } else el.pause(); };
  const seek = (s) => { const el = v.current; if (el) { el.pause(); el.currentTime = s; setT(s); } };
  const drop = (e) => {
    const el = v.current;
    if (!el || busy) return;
    if (!el.paused) { el.pause(); return; }
    const open_ = notes.find((n) => n.id === active);
    if (open_ && !open_.text.trim()) { setNotes((all) => all.filter((n) => n.id !== active)); setActive(null); return; }
    if (notes.length >= MAX) { toast.info(`Up to ${MAX} comments per version.`); return; }
    const r = e.currentTarget.getBoundingClientRect();
    const id = Date.now();
    setNotes((all) => [...all, { id, t: el.currentTime, x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height, text: "" }]);
    setActive(id);
  };
  const ready = notes.filter((n) => n.text.trim().length >= 2);
  const make = async () => {
    if (!ready.length || busy) return;
    setBusy(true);
    try {
      const p = video.params || {};
      const out = await post("/api/content/video", {
        prompt: video.prompt, model: video.model?.replace(/\/image-to-video$/, "") || "", aspect_ratio: p.aspect_ratio || "16:9",
        duration: String(p.duration || "5s"), add_sound: !p.has_audio, use_brand: !!p.brand, parent_id: video.id,
        changes: ready.map(({ t: at, x, y, text }) => ({ t: Math.round(at * 10) / 10, x, y, text: text.trim() })),
      });
      toast.success("Making the new version. It usually takes 1 to 3 minutes.");
      onCreated?.(out);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  const near = (n) => Math.abs(n.t - t) < 0.6 || n.id === active;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose?.(); }}>
      <DialogContent hideClose aria-describedby={undefined}
        className="inset-0 h-dvh max-h-none rounded-none bg-bg p-0 sm:inset-0 sm:left-0 sm:top-0 sm:max-w-none sm:translate-x-0 sm:translate-y-0 sm:rounded-none lg:overflow-hidden">
        <div className="flex min-h-full flex-col lg:h-full lg:flex-row">
          <div className="flex min-w-0 flex-1 flex-col lg:min-h-0">
            <div className="flex h-12 shrink-0 items-center gap-2 border-b border-ink/5 px-3">
              <button type="button" onClick={onClose} aria-label="Back to videos" title="Back (Esc)"
                className="grid size-8 place-items-center rounded-lg text-muted hover:bg-ink/[0.06] hover:text-strong"><ArrowLeft className="size-4" /></button>
              <DialogTitle className="truncate text-sm font-semibold text-strong">{video.prompt}</DialogTitle>
            </div>

            <div className="grid flex-1 place-items-center overflow-auto p-4 lg:min-h-0">
              <div className="relative w-fit select-none" onClick={drop} style={{ cursor: busy ? "default" : "crosshair" }}>
                <video ref={v} src={video.url} playsInline className="block max-h-[55dvh] w-auto max-w-full rounded-lg bg-strong shadow-[0_8px_30px_-12px_rgb(40_20_10/0.35)] lg:max-h-[calc(100dvh-14rem)]"
                  onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onTimeUpdate={(e) => setT(e.currentTarget.currentTime)}
                  onLoadedMetadata={(e) => setDur(e.currentTarget.duration || 0)} />
                {!playing && notes.filter(near).map((n) => (
                  <Pin key={n.id} n={n} num={notes.indexOf(n) + 1} open={active === n.id} onOpen={() => setActive(n.id)} onClose={() => setActive(null)}
                    onText={(text) => setNotes((all) => all.map((x) => (x.id === n.id ? { ...x, text } : x)))}
                    onRemove={() => { setNotes((all) => all.filter((x) => x.id !== n.id)); setActive(null); }} onSend={make} canSend={ready.length > 0 && !busy} />
                ))}
              </div>
            </div>

            <div className="mx-auto w-full max-w-3xl shrink-0 px-4 pb-4">
              <div className="flex items-center gap-3">
                <button type="button" onClick={toggle} aria-label={playing ? "Pause" : "Play"}
                  className="grid size-9 shrink-0 place-items-center rounded-full bg-strong text-white">{playing ? <Pause className="size-4" /> : <Play className="size-4" />}</button>
                <div className="relative h-8 flex-1">
                  <input type="range" min={0} max={dur || 1} step={0.05} value={t} onChange={(e) => seek(Number(e.target.value))}
                    aria-label="Position in the video" className="absolute inset-x-0 top-1/2 w-full -translate-y-1/2 accent-violet-600" />
                  {dur > 0 && notes.map((n, i) => (
                    <button key={n.id} type="button" title={`${clock(n.t)} · ${n.text || "comment"}`} onClick={() => { seek(n.t); setActive(n.id); }}
                      className="absolute top-0 grid size-4 -translate-x-1/2 place-items-center rounded-[50%_50%_50%_2px] bg-violet-600 text-[9px] font-semibold text-white"
                      style={{ left: `${(n.t / dur) * 100}%` }}>{i + 1}</button>
                  ))}
                </div>
                <span className="w-20 shrink-0 text-right font-mono text-xs text-muted">{clock(t)} / {clock(dur)}</span>
              </div>
              <p className="mt-2 text-xs text-muted">{playing ? "Pause where something should change." : "Click the frame to comment on that moment and spot."}</p>
            </div>
          </div>

          <aside className="w-full shrink-0 space-y-4 border-t border-ink/5 bg-surface p-4 lg:w-80 lg:overflow-y-auto lg:border-l lg:border-t-0">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-strong">Comments</h3>
              {notes.length ? (
                <ul className="divide-y divide-line text-sm">
                  {notes.map((n, i) => (
                    <li key={n.id} className="flex items-start gap-2 py-2">
                      <button type="button" onClick={() => { seek(n.t); setActive(n.id); }} className="shrink-0 font-mono text-xs text-violet-700 hover:underline">{i + 1} · {clock(n.t)}</button>
                      <span className={cx("min-w-0 flex-1", !n.text && "text-muted")}>{n.text || "Empty"}</span>
                      <button type="button" aria-label="Delete comment" onClick={() => setNotes((all) => all.filter((x) => x.id !== n.id))} className="text-muted hover:text-strong"><X className="size-3.5" /></button>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-muted">Pause the video and click the frame to say what should change.</p>}
            </div>
            <Button className="w-full" busy={busy} disabled={!ready.length} onClick={make}>Make new version{ready.length ? ` (${ready.length} change${ready.length === 1 ? "" : "s"})` : ""}</Button>
            <p className="text-xs text-muted">AI video redraws the whole clip with your changes, so other parts can shift a little. Your original stays as it is.</p>
            {versions.length > 1 && (
              <div>
                <h3 className="mb-2 text-sm font-semibold text-strong">Versions</h3>
                <div className="flex flex-wrap gap-1.5">
                  {versions.map((x, i) => (
                    <button key={x.id} type="button" onClick={() => onPick?.(x)} disabled={x.status !== "done"}
                      className={cx("rounded-md px-2 py-1 text-xs font-medium", x.id === video.id ? "bg-strong text-white" : "bg-ink/[0.05] text-ink hover:bg-ink/10", x.status !== "done" && "opacity-60")}>
                      V{i + 1}{x.status === "queued" ? " · making" : x.status === "failed" ? " · failed" : ""}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </aside>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Pin({ n, num, open, onOpen, onClose, onText, onRemove, onSend, canSend }) {
  const right = n.x > 0.62;
  const low = n.y > 0.7;
  return (
    <div className="group absolute" style={{ left: `${n.x * 100}%`, top: `${n.y * 100}%` }} onClick={(e) => e.stopPropagation()}>
      <button type="button" onClick={open ? onClose : onOpen} aria-label={`Comment ${num}${n.text ? `: ${n.text}` : ""}`}
        className={cx("absolute bottom-0 left-0 grid size-6 place-items-center rounded-[50%_50%_50%_2px] text-[11px] font-semibold text-white shadow-md ring-[1.5px] ring-white",
          open ? "bg-violet-600" : n.text ? "bg-strong" : "bg-strong/60")}>{num}</button>
      {!open && n.text && <span className="pointer-events-none absolute bottom-7 left-0 hidden max-w-56 truncate rounded-md bg-strong px-2 py-1 text-xs text-white shadow-md group-hover:block">{n.text}</span>}
      {open && (
        <div className={cx("absolute z-10 w-64 max-w-[70vw] rounded-xl bg-surface shadow-xl ring-1 ring-ink/10", low ? "bottom-8" : "top-2", right ? "right-0" : "left-0")}>
          <div className="flex items-end gap-1 p-1.5">
            <textarea autoFocus rows={1} maxLength={300} value={n.text} placeholder={`Comment at ${clock(n.t)}…`}
              className="min-h-7 flex-1 resize-none bg-transparent px-1.5 py-1 text-sm leading-5 text-strong outline-none placeholder:text-muted"
              onChange={(e) => { onText(e.target.value); e.target.style.height = "auto"; e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`; }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onClose(); }
                if (e.key === "Escape") { e.stopPropagation(); n.text ? onClose() : onRemove(); }
              }} />
            <button type="button" aria-label="Make new version" title="Make new version with all comments" disabled={!canSend} onClick={onSend}
              className="grid size-7 shrink-0 place-items-center rounded-full bg-violet-600 text-white disabled:bg-ink/15"><ArrowUp className="size-3.5" /></button>
          </div>
        </div>
      )}
    </div>
  );
}
