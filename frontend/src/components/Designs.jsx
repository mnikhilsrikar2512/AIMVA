import { useEffect, useRef, useState } from "react";
import { LayoutTemplate } from "lucide-react";
import { Button, Modal, Spinner, cx } from "./ui";
import { post } from "../lib/api";

export const LAYOUTS = [
  ["auto", "Fresh for me", "A layout you haven't used yet"],
  ["showcase", "Showcase", "Premium project microsite"],
  ["split", "Split", "Story left, form right"],
  ["centered", "Centred", "Big headline, form below"],
  ["immersive", "Full-bleed photo", "Photo hero, floating form"],
  ["editorial", "Editorial", "Magazine type, sticky form"],
  ["bento", "Bento grid", "Tiles of different sizes"],
];
export const DECORS = [["auto", "Auto"], ["blobs", "Soft glow"], ["grid", "Grid"], ["dots", "Dots"], ["plain", "Plain"]];

/** Tiny schematic of each layout so people can tell them apart at a glance. */
function Schematic({ layout }) {
  const s = "fill-current";
  const shapes = {
    auto: <><rect x="6" y="8" width="52" height="6" rx="2" className={s} opacity=".35" /><text x="32" y="34" textAnchor="middle" fontSize="16" className={s}>✦</text></>,
    showcase: <><rect x="2" y="2" width="60" height="22" rx="3" className={s} opacity=".85" /><rect x="7" y="9" width="24" height="4" rx="2" fill="#fff" /><rect x="7" y="15" width="10" height="3" rx="1.5" fill="#d4af6a" /><rect x="42" y="9" width="15" height="10" rx="2" fill="#fff" opacity=".35" /><rect x="6" y="28" width="16" height="10" rx="2" className={s} opacity=".3" /><rect x="24" y="28" width="16" height="10" rx="2" className={s} opacity=".3" /><rect x="42" y="28" width="16" height="10" rx="2" className={s} opacity=".3" /></>,
    split: <><rect x="6" y="8" width="26" height="5" rx="2" className={s} /><rect x="6" y="16" width="20" height="3" rx="1.5" className={s} opacity=".4" /><rect x="38" y="8" width="20" height="22" rx="3" className={s} opacity=".55" /><rect x="6" y="34" width="52" height="4" rx="2" className={s} opacity=".25" /></>,
    centered: <><rect x="14" y="7" width="36" height="5" rx="2" className={s} /><rect x="20" y="15" width="24" height="3" rx="1.5" className={s} opacity=".4" /><rect x="26" y="21" width="12" height="4" rx="2" className={s} opacity=".7" /><rect x="10" y="29" width="44" height="10" rx="2" className={s} opacity=".25" /></>,
    immersive: <><rect x="2" y="2" width="60" height="30" rx="3" className={s} opacity=".8" /><rect x="7" y="12" width="22" height="4" rx="2" fill="#fff" /><rect x="40" y="8" width="17" height="19" rx="2" fill="#fff" opacity=".9" /><rect x="6" y="36" width="52" height="3" rx="1.5" className={s} opacity=".25" /></>,
    editorial: <><rect x="6" y="6" width="44" height="8" rx="2" className={s} /><rect x="6" y="18" width="34" height="2" className={s} opacity=".3" /><rect x="6" y="24" width="34" height="2" className={s} opacity=".3" /><rect x="6" y="30" width="34" height="2" className={s} opacity=".3" /><rect x="44" y="18" width="14" height="20" rx="2" className={s} opacity=".55" /></>,
    bento: <><rect x="6" y="6" width="25" height="18" rx="3" className={s} opacity=".8" /><rect x="33" y="6" width="25" height="18" rx="3" className={s} opacity=".5" /><rect x="6" y="27" width="12" height="11" rx="2" className={s} opacity=".3" /><rect x="20" y="27" width="12" height="11" rx="2" className={s} opacity=".45" /><rect x="34" y="27" width="24" height="11" rx="2" className={s} opacity=".3" /></>,
  };
  return <svg viewBox="0 0 64 42" className="h-10 w-full" aria-hidden="true">{shapes[layout]}</svg>;
}

export function LayoutPicker({ value, onChange }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {LAYOUTS.map(([v, label, note]) => (
        <button key={v} type="button" onClick={() => onChange(v)} aria-pressed={value === v}
          className={cx("rounded-2xl p-3 text-left transition", value === v ? "bg-lavender text-brand ring-2 ring-brand/60" : "bg-surface-2/70 text-faint hover:bg-surface-2")}>
          <Schematic layout={v} />
          <span className="mt-2 block text-sm font-semibold text-strong">{label}</span>
          <span className="block text-xs text-muted">{note}</span>
        </button>
      ))}
    </div>
  );
}

function ScaledFrame({ html }) {
  const box = useRef(null);
  const [scale, setScale] = useState(0.3);
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setScale(e.contentRect.width / 1280));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={box} className="relative h-72 overflow-hidden rounded-xl bg-white ring-1 ring-line">
      <iframe title="Design preview" srcDoc={html} sandbox="" tabIndex={-1} style={{ transform: `scale(${scale})` }}
        className="pointer-events-none absolute left-0 top-0 h-[960px] w-[1280px] origin-top-left" />
    </div>
  );
}

/** Three clearly different designs for the current brief, rendered instantly, so people pick instead of re-rolling. */
export function DirectionsButton({ getBrief, onPick }) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState(null);
  const [error, setError] = useState("");
  const show = async () => {
    setOpen(true);
    setOptions(null);
    setError("");
    try {
      setOptions(await post("/api/sites/directions", getBrief()));
    } catch (e) {
      setError(e.message);
    }
  };
  return (
    <>
      <Button type="button" variant="ghost" onClick={show}><LayoutTemplate className="size-4" /> Show me 3 designs</Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Pick a design" wide="xl">
        <p className="mb-4 text-sm text-muted">Same content, three different structures and styles. The AI writer follows the one you pick, and you can change anything after.</p>
        {error ? <p className="rounded-xl bg-rose-50 px-4 py-2 text-sm text-rose-700">{error}</p> : !options ? (
          <div className="grid h-72 place-items-center"><Spinner className="size-6 text-brand" /></div>
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            {options.map((o) => (
              <div key={o.layout} className="flex flex-col gap-2">
                <ScaledFrame html={o.html} />
                <p className="text-sm font-semibold text-strong">{o.label} <span className="font-normal text-muted">· {o.matched ? `matched to ${o.matched}` : `${o.look}, ${o.theme}`}</span></p>
                <p className="flex-1 text-xs text-muted">{o.description}</p>
                <Button type="button" onClick={() => { onPick({ layout: o.layout, look: o.look, font: o.font, decor: o.decor, theme: o.theme }); setOpen(false); }}>Use this design</Button>
              </div>
            ))}
          </div>
        )}
      </Modal>
    </>
  );
}
