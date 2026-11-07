import { useEffect, useState } from "react";
import { Download, LayoutGrid } from "lucide-react";
import { Button, Field, Modal, cx } from "./ui";
import { post } from "../lib/api";
import { useAction, useApi } from "../lib/hooks";

const SIZES = [["1:1", "Feed square", "1080×1080"], ["4:5", "Feed portrait", "1080×1350"], ["9:16", "Stories & Reels", "1080×1920"],
  ["1.91:1", "Link ads & Google", "1200×628"], ["16:9", "YouTube & display", "1920×1080"]];
const RATIO = { "1:1": "1 / 1", "4:5": "4 / 5", "9:16": "9 / 16", "1.91:1": "1.91 / 1", "16:9": "16 / 9" };

/** One image → every placement size, with the headline and button typeset by AIMVA (always spelled right). */
export default function AdSetDialog({ asset, open, onClose, onMade }) {
  const { data: brand } = useApi(open ? "/api/brand" : null);
  const { data: sites } = useApi(open ? "/api/sites" : null, []);
  const [f, setF] = useState({ headline: "", subline: "", cta: "", position: "bottom", add_logo: false, sizes: ["1:1", "4:5", "9:16"] });
  const [made, setMade] = useState([]);
  const [busy, run] = useAction();

  useEffect(() => {  // start from the latest page's offer and button so copy stays consistent across channels
    if (!open) return;
    setMade([]);
    const brief = sites[0]?.brief;
    setF((x) => ({ ...x, headline: x.headline || brief?.offer || brand?.tagline || "", cta: x.cta || brief?.cta || "Learn more",
      add_logo: !!brand?.logos?.length && x.add_logo }));
  }, [open, sites, brand]);
  if (!open || !asset) return null;
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const toggle = (k) => setF((x) => ({ ...x, sizes: x.sizes.includes(k) ? x.sizes.filter((s) => s !== k) : [...x.sizes, k] }));
  const make = () => run(async () => {
    const out = await post(`/api/content/image/${asset.id}/adset`, f);
    setMade(out);
    onMade?.(out);
  }, "Ad set ready and saved to History");

  return (
    <Modal open={open} onClose={onClose} title="Make an ad set" wide>
      {made.length ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {made.map((a) => (
              <a key={a.id} href={a.url} target="_blank" rel="noreferrer" className="group block">
                <img src={a.url} alt={a.params.placement} className="w-full rounded-xl bg-surface-2 object-cover" style={{ aspectRatio: RATIO[a.params.size] }} />
                <span className="mt-1 flex items-center gap-1 text-xs text-muted group-hover:text-strong"><Download className="size-3" /> {a.params.placement} · {a.params.width}×{a.params.height}</span>
              </a>
            ))}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setMade([])}>Change the text</Button>
            <Button onClick={onClose}>Done</Button>
          </div>
        </div>
      ) : (
        <div className="grid gap-5 sm:grid-cols-[200px_1fr]">
          <div className="mx-auto w-full max-w-[200px] sm:max-w-none">
            <div className="relative overflow-hidden rounded-xl bg-surface-2" style={{ aspectRatio: "4 / 5" }}>
              <img src={asset.url} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />
              {(f.headline || f.cta) && (
                <div className={cx("absolute inset-x-0 p-3 text-white", f.position === "top" ? "top-0 bg-gradient-to-b" : "bottom-0 bg-gradient-to-t", "from-black/70 to-transparent")}>
                  <p className="text-[13px] font-extrabold leading-tight">{f.headline}</p>
                  {f.subline && <p className="mt-0.5 text-xs opacity-90">{f.subline}</p>}
                  {f.cta && <span className="mt-1.5 inline-block rounded-full px-2.5 py-1 text-xs font-bold" style={{ background: brand?.colors?.[0] || "#6d5dfc" }}>{f.cta}</span>}
                </div>
              )}
            </div>
            <p className="mt-2 text-xs text-faint">Text is added by AIMVA, not drawn by the AI, so it's always spelled right and stays sharp.</p>
          </div>
          <div className="space-y-4">
            <Field label="Headline"><input className="input" value={f.headline} onChange={set("headline")} maxLength={90} placeholder="Free site visit this weekend" /></Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Supporting line (optional)"><input className="input" value={f.subline} onChange={set("subline")} maxLength={120} /></Field>
              <Field label="Button"><input className="input" value={f.cta} onChange={set("cta")} maxLength={30} /></Field>
            </div>
            <div>
              <p className="label">Sizes</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {SIZES.map(([k, l, px]) => (
                  <label key={k} className={cx("flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2 text-sm", f.sizes.includes(k) ? "bg-lavender/70" : "bg-surface-2/60")}>
                    <input type="checkbox" className="size-4 accent-violet-500" checked={f.sizes.includes(k)} onChange={() => toggle(k)} />
                    <span className="font-medium text-strong">{l}</span><span className="ml-auto text-xs text-faint">{px}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-ink">
              <label className="flex items-center gap-2">Text at the
                <select className="input h-9 w-auto" value={f.position} onChange={set("position")}><option value="bottom">bottom</option><option value="top">top</option></select>
              </label>
              {brand?.logos?.length > 0 && <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-violet-500" checked={f.add_logo} onChange={set("add_logo")} /> Add my logo</label>}
            </div>
            <div className="flex justify-end">
              <Button onClick={make} busy={busy} disabled={!f.sizes.length}><LayoutGrid className="size-4" /> Make {f.sizes.length} size{f.sizes.length === 1 ? "" : "s"}</Button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
