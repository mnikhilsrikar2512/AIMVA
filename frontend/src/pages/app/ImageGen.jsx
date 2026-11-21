// Pictures (design.md v3 7.3): one prompt, written from the business profile, makes the pictures; the result fills
// the canvas and the changes panel takes every change after that. Owners change a picture three ways: type in the
// panel, point at a spot (C opens the comment editor), or edit directly (words, crop, colour in the same editor).
// Engine, count, style and seed are hidden from owners; the platform admin finds them under ⋯ → Advanced.
import { useEffect, useMemo, useRef, useState } from "react";
import { useUrlView } from "../../lib/nav";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Download, Image as ImageIcon, Send, LayoutGrid, MessageSquarePlus, MoreHorizontal, Plus, SlidersHorizontal, Trash2, Upload } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../../components/shadcn/dropdown-menu";
import { Tooltip } from "../../components/shadcn/tooltip";
import { Button, Empty, Field, IconButton, JobProgress, ListSkeleton, Modal, PageHeader, cx } from "../../components/ui";
import { LoadError } from "../../components/LoadError";
import { ModulePrompt } from "../../components/ModulePrompt";
import { ChangesPanel, CompareSplit, ModuleFrame, ToolbarTitle, usePanelOpen } from "../../components/ModuleChanges";
import { Rate } from "../../components/Quality";
import { ProviderPicker, SeedField, STYLES } from "../../components/GenControls";
import AdSetDialog from "../../components/AdSet";
import ImageEditor from "../../components/ImageEditor";
import { api, del, post } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { shareToWhatsApp } from "../../lib/utils";
import { useAuth } from "../../lib/auth";

const rootId = (a) => a?.params?.edit_root || a?.id;
const isAdSize = (a) => !!a?.params?.parent;  // ad-set placements hang off a picture; they are not versions of it

/** The words a picture version shows in the panel. */
function said(a, first) {
  const p = a.params || {};
  if (first) return a.prompt;
  if (p.instruction) return p.instruction;
  if (p.restyle) return `${p.restyle} style`;
  if (p.text_layers) return "Words on the picture";
  if (p.edits?.length) return p.edits.map((e) => e.text).filter(Boolean).join("; ") || "Comments on the picture";
  return "Edited";
}

/** Typing "c" anywhere but a text field opens comment mode (design.md 4: single-key shortcuts outside text fields). */
function useKey(key, fn, on) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (!on) return undefined;
    const k = (e) => {
      if (e.key.toLowerCase() !== key || e.metaKey || e.ctrlKey || e.altKey) return;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable) return;
      if (document.querySelector("[role=dialog]")) return;
      e.preventDefault(); ref.current();
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [key, on]);
}

export default function ImageGen() {
  const { data: assets, setData: setAssets, loading, error, reload } = useApi("/api/content/assets?kind=image", []);
  const { data: options } = useApi("/api/providers/options?kind=image", []);
  const { data: brandKit } = useApi("/api/brand");
  const { data: ratings } = useApi("/api/feedback?kind=image", {});
  const admin = !!useAuth().user?.is_admin;
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const given = useRef(params.get("prompt") || "");
  // prompt | work | all and the open picture, kept in the address so Back returns to the list (plan S7)
  const [view, setView, selId, setSelId, setUrl] = useUrlView(given.current ? "prompt" : null);
  const [making, setMaking] = useState(null);  // {count, startedAt} while a new set is being made
  const [changing, setChanging] = useState(false);
  const [panelOpen, togglePanel] = usePanelOpen();
  const [comparing, setComparing] = useState(null);
  const [editing, setEditing] = useState(false);
  const [adSet, setAdSet] = useState(false);
  const [advOpen, setAdvOpen] = useState(false);
  const [adv, setAdv] = useState({ provider: null, model: "", count: 4, style: "", negative_prompt: "", seed: null });
  const uploadRef = useRef(null);

  useEffect(() => {  // first load: the newest picture, unless the page was opened with a prompt or a picture
    if (loading || view) return;
    const want = Number(params.get("asset")) || null;
    const start = (want && assets.find((a) => a.id === want)) || assets.find((a) => !isAdSize(a));
    if (start) { setSelId(start.id); setView("work"); } else setView("prompt");
    if (params.get("prompt") || params.get("asset")) setUrl({ prompt: null, asset: null }, { replace: true });
  }, [loading]);  // eslint-disable-line react-hooks/exhaustive-deps

  const pictures = assets.filter((a) => !isAdSize(a));
  const sel = pictures.find((a) => a.id === selId) || null;
  // Every version of the picture on the canvas, oldest first (v1 is the one the prompt made).
  const chain = useMemo(() => (sel ? pictures.filter((a) => rootId(a) === rootId(sel)).sort((a, b) => a.id - b.id) : []), [pictures, sel]);
  const latestOf = (root) => pictures.filter((a) => rootId(a) === root).sort((a, b) => b.id - a.id)[0];
  // The other pictures the same prompt made, each at its latest version.
  const batch = useMemo(() => {
    const root = chain[0];
    if (!root?.params?.batch) return [];
    return pictures.filter((a) => a.params?.batch === root.params.batch && !a.params?.edited_from).sort((a, b) => a.id - b.id).map((a) => latestOf(a.id));
  }, [pictures, chain]);  // eslint-disable-line react-hooks/exhaustive-deps
  const versions = chain.map((a, i) => ({ id: a.id, number: i + 1, request: said(a, i === 0), by: a.by, created_at: a.created_at, current: a.id === selId })).reverse();

  const engine = () => {
    if (admin && adv.provider) return adv.provider;
    const best = options.find((o) => o.available && !o.free) || options.find((o) => o.available) || options[0];
    return best ? { provider: best.ref, model: best.model, max: best.max_count || 1 } : { provider: "", model: "", max: 1 };
  };
  const make = async (prompt) => {
    const e = engine();
    const max = e.max || options.find((o) => o.ref === e.provider)?.max_count || 1;
    const count = Math.max(1, Math.min(admin ? adv.count : 4, max));
    setMaking({ count });
    setView("work");
    try {
      const out = await post("/api/content/image", {
        prompt, provider: e.provider, model: e.model || "", size_auto: true, count,
        use_brand: !!brandKit?.is_set_up, ...(admin ? { style: adv.style || null, negative_prompt: adv.negative_prompt, seed: adv.seed } : {}),
      });
      setAssets((a) => [...out, ...a]);
      setSelId(out[0]?.id ?? null);
    } catch (err) {
      toast.error(err.message);
      if (!sel) setView("prompt");
    } finally { setMaking(null); }
  };
  const change = async (instruction) => {
    if (!sel) return false;
    setChanging(true);
    try {
      const out = await post(`/api/content/image/${sel.id}/edit`, { instruction });
      setAssets((a) => [out, ...a]);
      setSelId(out.id);
      return true;
    } catch (err) { toast.error(err.message); return false; } finally { setChanging(false); }
  };
  const remove = (a) => {  // acts at once, with Undo (design.md: undo over confirm)
    const keep = assets;
    const gone = pictures.filter((x) => rootId(x) === rootId(a)).map((x) => x.id);
    setAssets((all) => all.filter((x) => !gone.includes(x.id)));
    const next = pictures.find((x) => !gone.includes(x.id));
    setSelId(next?.id ?? null);
    if (!next) setView("prompt");
    let undone = false;
    const t = setTimeout(() => { if (!undone) Promise.all(gone.map((id) => del(`/api/content/assets/${id}`))).catch((e) => { toast.error(e.message); reload(); }); }, 5000);
    toast("Picture deleted.", { duration: 5000, action: { label: "Undo", onClick: () => { undone = true; clearTimeout(t); setAssets(keep); setSelId(a.id); setView("work"); } } });
  };
  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const a = await api("/api/content/image/upload", { method: "POST", form });
      setAssets((all) => [a, ...all]);
      setSelId(a.id); setView("work"); setEditing(true);
    } catch (err) { toast.error(err.message); }
  };
  useKey("c", () => setEditing(true), view === "work" && !!sel && !making);

  const more = (
    <DropdownMenu>
      <Tooltip content="More"><DropdownMenuTrigger asChild><button type="button" className="btn-subtle btn-sm w-8 px-0" aria-label="More"><MoreHorizontal className="size-4" /></button></DropdownMenuTrigger></Tooltip>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => uploadRef.current?.click()}><Upload className="size-4" /> Upload a photo to edit</DropdownMenuItem>
        {pictures.length > 0 && <DropdownMenuItem onSelect={() => setView("all")}><LayoutGrid className="size-4" /> All pictures</DropdownMenuItem>}
        {admin && <DropdownMenuItem onSelect={() => setAdvOpen(true)}><SlidersHorizontal className="size-4" /> Advanced</DropdownMenuItem>}
      </DropdownMenuContent>
    </DropdownMenu>
  );
  const hiddenUpload = <input ref={uploadRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={upload} aria-hidden tabIndex={-1} />;

  if (view === null || (loading && !assets.length && view !== "prompt")) return <><PageHeader title="Pictures" /><ListSkeleton /></>;
  if (error && !assets.length && view !== "prompt") return <><PageHeader title="Pictures" /><LoadError error={error} what="your pictures" onRetry={reload} /></>;

  if (view === "prompt") {
    return (
      <div>
        <PageHeader title="Pictures" />
        {hiddenUpload}
        <ModulePrompt moduleKey="pictures" given={given.current} busy={!!making} submitLabel="Make pictures" onSubmit={make}
          outcome="You'll get pictures in your colours, ready for posts, ads and your page."
          secondary={<span className="flex flex-wrap gap-x-5 gap-y-2">
            <button type="button" className="font-medium text-brand hover:underline" onClick={() => uploadRef.current?.click()}>Upload a photo to edit</button>
            {pictures.length > 0 && <button type="button" className="font-medium text-brand hover:underline" onClick={() => setView(sel ? "work" : "all")}>Back to my pictures</button>}
          </span>} />
        <AdvancedModal open={advOpen} onClose={() => setAdvOpen(false)} value={adv} onChange={setAdv} />
      </div>
    );
  }

  if (view === "all") {
    const roots = pictures.filter((a) => !a.params?.edited_from).map((a) => latestOf(a.id));
    return (
      <div>
        <PageHeader title="Pictures" />
        {hiddenUpload}
        <div className="mb-6 flex items-center justify-between gap-3">
          <p className="text-sm text-muted">{roots.length} picture{roots.length === 1 ? "" : "s"}</p>
          <span className="flex items-center gap-1">{more}<Button variant="ghost" onClick={() => setView("prompt")}><Plus className="size-4" /> New pictures</Button></span>
        </div>
        {roots.length === 0 ? <Empty icon={ImageIcon} preview="tiles" title="Your pictures will live here" text="Everything you make is kept, with every version." action={<Button variant="ghost" onClick={() => setView("prompt")}>Make pictures</Button>} /> : (
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4">
            {roots.map((a) => (
              <li key={a.id}>
                <button type="button" onClick={() => { setSelId(a.id); setView("work"); }} className="block w-full overflow-hidden rounded-[10px] ring-1 ring-line hover:ring-line-strong">
                  <img src={a.url} alt={a.prompt} loading="lazy" className="aspect-square w-full bg-surface-2 object-cover" />
                </button>
                <p className="mt-1.5 line-clamp-1 text-xs text-muted">{a.by ? `${a.by} · ` : ""}{a.prompt}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  const toolbar = (
    <>
      <ToolbarTitle status={sel && chain.length > 1 ? `v${chain.findIndex((a) => a.id === sel.id) + 1}` : null}>{sel?.prompt || "New pictures"}</ToolbarTitle>
      {sel && !making && (
        <span className="flex items-center gap-1">
          <span className="hidden sm:inline-flex"><Rate kind="image" id={sel.id} initial={ratings[sel.id]} /></span>
          <IconButton label="Point and change (C)" onClick={() => setEditing(true)}><MessageSquarePlus className="size-4" /></IconButton>
          <IconButton label="Every ad size" onClick={() => setAdSet(true)}><LayoutGrid className="size-4" /></IconButton>
          <IconButton label="Download" href={sel.url} download target="_blank" rel="noreferrer"><Download className="size-4" /></IconButton>
          <IconButton label="Send on WhatsApp" onClick={() => shareToWhatsApp(sel.url, "picture").then((r) => r === "downloaded" && toast("Saved. Attach it in the WhatsApp tab that just opened.")).catch((e) => toast.error(e.message))}><Send className="size-4" /></IconButton>
          <IconButton label="Delete" danger onClick={() => remove(sel)}><Trash2 className="size-4" /></IconButton>
        </span>
      )}
      {more}
      <Button variant="ghost" size="sm" onClick={() => setView("prompt")}><Plus className="size-3.5" /> New</Button>
      {sel && !making && <Button variant="accent" size="sm" onClick={() => navigate(`/app/ads/meta?image=${sel.id}`)}>Use in a campaign</Button>}
    </>
  );

  return (
    <>
      <PageHeader title="Pictures" />
      {hiddenUpload}
      <ModuleFrame toolbar={toolbar} panel={
        <ChangesPanel open={panelOpen} onToggle={togglePanel} versions={making ? [] : versions} onSend={sel && !making ? change : null} sending={changing}
          placeholder="Change anything: “warmer light”, “remove the car”" restoreLabel="Use this"
          onRestore={(v) => setSelId(v.id)} onCompare={(v) => setComparing(pictures.find((a) => a.id === v.id))} />
      }>
        {making ? (
          <div className="max-w-3xl">
            <JobProgress seconds={18} label="Making your pictures…" />
            <div className={cx("mt-6 grid gap-4", making.count > 1 && "sm:grid-cols-2")}>
              {Array.from({ length: making.count }).map((_, i) => <div key={i} className="aspect-square rounded-[10px] bg-surface-2" />)}
            </div>
          </div>
        ) : !sel ? (
          <Empty icon={ImageIcon} preview="tiles" title="Your pictures appear here" text="Say what you want in one line." action={<Button variant="ghost" onClick={() => setView("prompt")}>Make pictures</Button>} />
        ) : (
          <div className="flex flex-col items-center">
            <div className="relative w-full">
              <img key={sel.id} src={sel.url} alt={sel.prompt} className={cx("mx-auto max-h-[calc(100dvh-16rem)] w-auto max-w-full rounded-[10px] bg-surface-2 object-contain", changing && "opacity-60")} />
              {changing && <div className="absolute inset-x-0 bottom-4 mx-auto w-[min(22rem,90%)] rounded-md bg-surface p-3 ring-1 ring-line"><JobProgress seconds={20} label="Making the change…" /></div>}
            </div>
            {batch.length > 1 && (
              <div className="mt-5 flex flex-wrap justify-center gap-2" role="list" aria-label="From the same prompt">
                {batch.map((a) => (
                  <button key={a.id} type="button" role="listitem" onClick={() => setSelId(a.id)} aria-label={`Picture ${batch.indexOf(a) + 1}`} aria-current={rootId(a) === rootId(sel) || undefined}
                    className={cx("size-16 overflow-hidden rounded-md ring-1", rootId(a) === rootId(sel) ? "ring-2 ring-strong" : "ring-line hover:ring-line-strong")}>
                    <img src={a.url} alt="" className="size-full object-cover" />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </ModuleFrame>
      <CompareSplit open={!!comparing} onClose={() => setComparing(null)} title={comparing ? `v${chain.findIndex((a) => a.id === comparing.id) + 1} and now` : ""}
        before={comparing && <img src={comparing.url} alt="Before" className="max-h-full max-w-full object-contain" />}
        after={sel && <img src={sel.url} alt="Now" className="max-h-full max-w-full object-contain" />} />
      <ImageEditor asset={editing ? sel : null} open={editing && !!sel} onClose={() => setEditing(false)}
        onEdited={(out) => { setAssets((a) => [out, ...a]); setSelId(out.id); }} />
      <AdSetDialog asset={adSet ? sel : null} open={adSet && !!sel} onClose={() => setAdSet(false)} onMade={(out) => setAssets((a) => [...out, ...a])} />
      <AdvancedModal open={advOpen} onClose={() => setAdvOpen(false)} value={adv} onChange={setAdv} />
    </>
  );
}

/** Platform admin only: engine, count, style, what to avoid and seed for the next set. */
function AdvancedModal({ open, onClose, value, onChange }) {
  const set = (k) => (e) => onChange((v) => ({ ...v, [k]: e.target.value }));
  const prov = value.provider || { provider: "", model: "" };
  return (
    <Modal open={open} onClose={onClose} title="Advanced">
      <div className="space-y-4">
        <ProviderPicker kind="image" value={prov} onChange={(p) => onChange((v) => ({ ...v, provider: p }))} />
        <div className="grid grid-cols-2 gap-3">
          <Field label="How many"><select className="input" value={value.count} onChange={(e) => onChange((v) => ({ ...v, count: Number(e.target.value) }))}>{[1, 2, 3, 4].map((n) => <option key={n}>{n}</option>)}</select></Field>
          <Field label="Style"><select className="input" value={value.style} onChange={set("style")}>{STYLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
        </div>
        <Field label="Avoid"><input className="input" value={value.negative_prompt} onChange={set("negative_prompt")} maxLength={1000} placeholder="text, watermark, blurry" /></Field>
        <SeedField value={value.seed} onChange={(s) => onChange((v) => ({ ...v, seed: s }))} />
        <div className="flex justify-end"><Button variant="ghost" onClick={onClose}>Done</Button></div>
      </div>
    </Modal>
  );
}
