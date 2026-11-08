import { useEffect, useState } from "react";
import { SaveTemplateButton, TemplateStrip, useTemplateTracker } from "../../components/Templates";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { ease, rise, stagger } from "../../components/Motion";
import { Download, Image as ImageIcon, LayoutGrid, MessageSquarePlus, Plus, RotateCcw, Sparkles, Trash2, Upload, Wand2 } from "lucide-react";
import { Button, Card, Empty, Field, PageHeader, Spinner, Tabs, cx, ListSkeleton, JobProgress } from "../../components/ui";
import { LoadError } from "../../components/LoadError";
import { api, del, get, post } from "../../lib/api";
import { useAction, useApi } from "../../lib/hooks";
import BrandControls from "../../components/BrandControls";
import { useAuth } from "../../lib/auth";
import { Advanced, LibraryImagePicker, ProviderPicker, SeedField, STYLES } from "../../components/GenControls";
import AdSetDialog from "../../components/AdSet";
import ImageEditor from "../../components/ImageEditor";
import { EnhanceButton, Rate } from "../../components/Quality";
import { StoryLine, UsedIn } from "../../components/Story";


const SIZE_OPTIONS = [["1:1", "Square 1:1"], ["4:5", "Portrait 4:5"], ["9:16", "Story 9:16"], ["16:9", "Wide 16:9"], ["1.91:1", "Link ad 1.91:1"], ["custom", "Custom size…"]];

export default function ImageGen() {
  const { data: assets, setData: setAssets, loading, error: assetsError, reload: reloadAssets } = useApi("/api/content/assets?kind=image", []);
  const { data: options } = useApi("/api/providers/options?kind=image", []);
  const EMPTY = { prompt: "", size: "1:1", width: 1024, height: 1024, count: 1, negative_prompt: "", seed: null, style: "", reference: "", keep_product: false };
  const [form, setForm] = useState(EMPTY);
  const admin = !!useAuth().user?.is_admin; // the platform owner sees engine and fine-tuning options; customers get the essentials
  const [tab, setTab] = useState("create");
  const [current, setCurrent] = useState([]);  // only the latest generation is shown in Create
  const [q, setQ] = useState("");
  const [prov, setProv] = useState({ provider: "builtin:free", model: "free-standard" });
  const { data: brandKit } = useApi("/api/brand");
  const [brandOpts, setBrandOpts] = useState({ use_brand: true, add_logo: false, logo_position: "top-right" });
  const [busy, run] = useAction();
  const { data: ratings } = useApi("/api/feedback?kind=image", {});
  const [adFor, setAdFor] = useState(null);
  const [editFor, setEditFor] = useState(null);
  const [uploading, runUpload] = useAction();
  const uploadPhoto = (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    runUpload(async () => {
      const a = await api("/api/content/image/upload", { method: "POST", form });
      setAssets((all) => [a, ...all]);
      setEditFor(a);
    });
  };
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const option = options.find((o) => o.ref === prov.provider);
  const free = prov.provider === "builtin:free";
  const maxCount = option?.max_count || 1;

  const tpl = useTemplateTracker("image");
  const tplPayload = () => ({ prompt: form.prompt, style: form.style || "", size: ["1:1", "4:5", "9:16", "16:9", "1.91:1"].includes(form.size) ? form.size : "1:1", negative_prompt: form.negative_prompt });
  const generate = async (e) => {
    e.preventDefault();
    const custom = form.size === "custom";
    const out = await run(() => post("/api/content/image", {
      prompt: form.prompt, provider: prov.provider, model: prov.model || option?.model || "",
      size: custom ? "1:1" : form.size, width: custom ? Number(form.width) : null, height: custom ? Number(form.height) : null,
      count: admin ? Math.min(Number(form.count), maxCount) : Math.min(4, maxCount), negative_prompt: form.negative_prompt, seed: form.seed,
      style: form.style || null, reference: form.reference, keep_product: !!form.reference && !free && form.keep_product,
      ...brandOpts, use_brand: !!brandKit?.is_set_up && brandOpts.use_brand,
    }));
    if (out) {
      tpl.track(tplPayload());
      setCurrent(out);
      setAssets((a) => [...out, ...a]);
    }
  };
  const startNew = () => { setForm(EMPTY); setCurrent([]); setTab("create"); };
  const remove = async (a) => {
    await del(`/api/content/assets/${a.id}`);
    setAssets((all) => all.filter((x) => x.id !== a.id));
    setCurrent((c) => c.filter((x) => x.id !== a.id));
  };
  const reuse = (a) => {
    setForm((f) => ({ ...f, prompt: a.prompt, seed: a.params?.seed ?? null, style: a.params?.style || "", negative_prompt: a.params?.negative_prompt || "" }));
    setTab("create");
    document.getElementById("app-scroll")?.scrollTo({ top: 0, behavior: "smooth" });
  };
  const history = assets.filter((a) => a.prompt.toLowerCase().includes(q.toLowerCase()));

  return (
    <div>
      <PageHeader title="Pictures"
        actions={<div className="flex gap-2">
          <label className={cx("btn-ghost cursor-pointer", uploading && "pointer-events-none opacity-60")} title="Edit any photo: product shots, rooms, people…">
            {uploading ? <Spinner className="size-4" /> : <Upload className="size-4" />} Upload a photo to edit
            <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={uploadPhoto} />
          </label>
          <Button variant="ghost" onClick={startNew}><Plus className="size-4" /> Start new</Button>
        </div>} />
      <StoryLine module="pictures" />
      <div className="mb-6"><Tabs value={tab} onChange={setTab} tabs={[{ value: "create", label: "Create" }, { value: "history", label: `History${assets.length ? ` (${assets.length})` : ""}` }]} /></div>
      {tab === "history" ? (
        loading ? <ListSkeleton /> : assetsError && assets.length === 0 ? (
          <LoadError error={assetsError} what="your pictures" onRetry={reloadAssets} />
        ) : assets.length === 0 ? (
          <Empty icon={ImageIcon} preview="tiles" title="Your pictures will live here" text="Everything you make is saved here, with every version you edit." action={<Button onClick={startNew}><Plus className="size-4" /> Make your first picture</Button>} />
        ) : (
          <>
            <input className="input mb-4 max-w-sm" placeholder="Search by prompt" value={q} onChange={(e) => setQ(e.target.value)} />
            <motion.div variants={stagger} initial="hidden" animate="show" className="columns-1 gap-4 sm:columns-2 xl:columns-4">
              {history.map((a) => <ImageTile key={a.id} a={a} rating={ratings[a.id]} onAdSet={() => setAdFor(a)} onEdit={() => setEditFor(a)} onDelete={() => remove(a)} onReuse={() => reuse(a)} />)}
            </motion.div>
          </>
        )
      ) : (
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[400px_minmax(0,1fr)]">
        <Card className="h-fit lg:sticky lg:top-6">
          <form onSubmit={generate} className="space-y-4">
            {admin && <TemplateStrip module="image" onApply={(t) => { tpl.apply(t); setForm((f) => ({ ...f, prompt: t.payload.prompt, style: t.payload.style || "", size: t.payload.size || f.size, negative_prompt: t.payload.negative_prompt || "" })); }} />}
            <Field label="Prompt">
              <textarea className="input" rows={5} value={form.prompt} onChange={set("prompt")} required minLength={3} maxLength={2000}
                placeholder="Describe the image you want…" />
            </Field>
            <PromptSense prompt={form.prompt} size={form.size} onFormat={(v) => setForm((f) => ({ ...f, size: v }))} />
            <div className="-mt-2 flex justify-end">
              <EnhanceButton prompt={form.prompt} kind="image" useBrand={!!brandKit?.is_set_up && brandOpts.use_brand}
                onEnhanced={(r) => setForm((f) => ({ ...f, prompt: r.prompt, negative_prompt: f.negative_prompt || r.negative_prompt || "" }))} />
            </div>
            <ProviderPicker kind="image" value={prov} onChange={setProv} />
            <div className="grid grid-cols-2 gap-3">
              <Field label="Format">
                <select className="input" value={form.size} onChange={set("size")}>
                  {SIZE_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </Field>
              {admin && <Field label="Images" hint={maxCount === 1 ? "This provider makes 1 at a time" : undefined}>
                <select className="input" value={Math.min(form.count, maxCount)} onChange={set("count")} disabled={maxCount === 1}>
                  {[1, 2, 3, 4].slice(0, maxCount).map((n) => <option key={n}>{n}</option>)}
                </select>
              </Field>}
            </div>
            {form.size === "custom" && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Width (px)"><input className="input" type="number" min="256" max="2048" step="16" value={form.width} onChange={set("width")} /></Field>
                <Field label="Height (px)"><input className="input" type="number" min="256" max="2048" step="16" value={form.height} onChange={set("height")} /></Field>
              </div>
            )}
            <LibraryImagePicker label="Your photo (optional)" value={form.reference} onChange={(v) => setForm((f) => ({ ...f, reference: v }))}
              hint={form.keep_product ? "Your product photo. It's cut out and placed in a new scene, unchanged." : "A product or shop photo to build the picture around."} />
            {form.reference && (
              <label className={cx("flex items-start gap-2 rounded-xl border border-ink/10 p-3 text-sm", free && "opacity-60")}>
                <input type="checkbox" className="mt-0.5" disabled={free} checked={!free && form.keep_product}
                  onChange={(e) => setForm((f) => ({ ...f, keep_product: e.target.checked }))} />
                <span><b className="text-strong">Keep my product exactly</b>
                  <span className="block text-xs text-muted">{free ? "Needs Studio images. The free engine redraws the product." : "AI paints only the scene around it, so labels and shape stay true."}</span></span>
              </label>
            )}
            {admin && <Advanced>
              <Field label="Style">
                <select className="input" value={form.style} onChange={set("style")}>{STYLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              </Field>
              <Field label="Avoid (negative prompt)"><input className="input" value={form.negative_prompt} onChange={set("negative_prompt")} maxLength={1000} placeholder="text, watermark, blurry, extra fingers" /></Field>
              <SeedField value={form.seed} onChange={(v) => setForm((f) => ({ ...f, seed: v }))} />
            </Advanced>}
            <BrandControls brand={brandKit} value={brandOpts} onChange={setBrandOpts} freeModel={free} />
            <Button type="submit" busy={busy} className="h-11 w-full"><Wand2 className="size-4" /> {admin ? "Generate" : "Create pictures"}</Button>
            {admin && form.prompt.trim().length >= 3 && <div className="flex justify-center"><SaveTemplateButton module="image" getPayload={tplPayload} /></div>}
          </form>
        </Card>

        <div>
          {busy ? (
            <>
            <JobProgress className="mb-4" seconds={18} steps={["Reading your sentence…", "Composing the picture…", "Adding light and detail…", "Applying your brand…", "Finishing up…"]} />
            <div className="grid gap-4 sm:grid-cols-2">
              {Array.from({ length: Math.min(Number(form.count), maxCount) }).map((_, i) => (
                <div key={i} className="card grid aspect-square animate-pulse place-items-center text-sm text-muted">
                  <span className="flex items-center gap-2"><Sparkles className="size-4 text-muted" /> Picture {i + 1}</span>
                </div>
              ))}
            </div>
            </>
          ) : current.length === 0 ? (
            <Empty icon={ImageIcon} preview="tiles" title="Your new pictures appear here"
              text="Describe one sentence on the left, like “a sunlit 3 BHK balcony at golden hour”. The free model needs no key." />
          ) : (
            <>
              <div className="mb-3 flex items-center justify-between">
                <p className="text-sm font-semibold text-strong">Latest result · saved to History</p>
                <Button size="sm" variant="ghost" onClick={startNew}><Plus className="size-3.5" /> Start new</Button>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {current.map((a) => <ImageTile key={a.id} a={a} rating={ratings[a.id]} onAdded={(out) => { setAssets((x) => [out, ...x]); setCurrent((c) => [out, ...c]); }} onAdSet={() => setAdFor(a)} onEdit={() => setEditFor(a)} onDelete={() => remove(a)} onReuse={() => reuse(a)} />)}
              </div>
              <p className="mt-3 text-xs text-muted">Happy with it? <b className="text-strong">Make an ad set</b> to get every placement size with your headline and button added cleanly.</p>
            </>
          )}
        </div>
      </div>
      )}
      <ImageEditor asset={editFor} open={!!editFor} onClose={() => setEditFor(null)}
        onEdited={(out) => { setAssets((a) => [out, ...a]); setCurrent((c) => (c.length ? [out, ...c] : c)); }} />
      <AdSetDialog asset={adFor} open={!!adFor} onClose={() => setAdFor(null)}
        onMade={(out) => { setAssets((a) => [...out, ...a]); }} />
    </div>
  );
}

const FORMAT_NAME = { "9:16": "a story or reel (9:16)", "16:9": "a banner or thumbnail (16:9)", "1:1": "a square post (1:1)", "4:5": "a portrait post (4:5)" };

/** What AIMVA reads in the prompt as it's typed: the shape it asks for, and words meant for the picture. */
function PromptSense({ prompt, size, onFormat }) {
  const [sense, setSense] = useState(null);
  useEffect(() => {
    if (prompt.trim().length < 6) { setSense(null); return undefined; }
    const t = setTimeout(() => {
      get(`/api/content/prompt-sense?text=${encodeURIComponent(prompt)}&size=${encodeURIComponent(size)}`).then(setSense).catch(() => setSense(null));
    }, 450);
    return () => clearTimeout(t);
  }, [prompt, size]);
  if (!sense?.format && !sense?.words) return null;
  return (
    <div className="-mt-2 space-y-1 text-xs text-muted">
      {sense.format && (
        <p>Sounds like {FORMAT_NAME[sense.format]}. <button type="button" className="font-medium text-brand hover:underline" onClick={() => onFormat(sense.format)}>Use {sense.format}</button></p>
      )}
      {sense.words && <p>“{sense.words}” will be added as real text after, so it's spelled right. The picture itself is made without words.</p>}
    </div>
  );
}

function ImageTile({ a, rating, onAdSet, onEdit, onDelete, onReuse, onAdded }) {
  const [loaded, setLoaded] = useState(false);
  const [adding, setAdding] = useState(false);
  const words = a.params?.words && !a.params?.text_layers ? a.params.words : null;
  const addWords = async () => {
    setAdding(true);
    try {
      onAdded?.(await post(`/api/content/image/${a.id}/text`, { layers: [{ text: words, x: 0.5, y: 0.86, size: 0.07, weight: "bold", bg: "band", color: "#ffffff" }] }));
    } catch (e) {
      toast.error(e.message);
    } finally {
      setAdding(false);
    }
  };
  const [failed, setFailed] = useState(false);
  return (
    <motion.div variants={rise} initial="hidden" animate="show" className="group card mb-4 break-inside-avoid overflow-hidden">
      <div className={cx("relative bg-ink/[0.03]", !loaded && "aspect-square")}>
        {!loaded && !failed && <div className="absolute inset-0 grid place-items-center text-muted"><Spinner className="size-5" /></div>}
        {failed ? (
          <div className="grid aspect-square place-items-center text-sm text-muted">Image failed to load</div>
        ) : (
          <motion.img src={a.url} alt={a.prompt} loading="lazy" onLoad={() => setLoaded(true)} onError={() => setFailed(true)}
            initial={false} animate={loaded ? { opacity: 1, filter: "blur(0px)", scale: 1 } : { opacity: 0, filter: "blur(14px)", scale: 1.04 }}
            transition={{ duration: 0.8, ease }} className="w-full" />
        )}
        <div className="absolute right-2 top-2 flex gap-1.5 opacity-0 transition group-hover:opacity-100">
          <a href={a.url} target="_blank" rel="noreferrer" className="btn-ghost btn-sm bg-white/90" title="Open full size"><Download className="size-3.5" /></a>
          {!a.params?.parent && <button className="btn-ghost btn-sm bg-white/90" onClick={onEdit} title="Edit with comments"><MessageSquarePlus className="size-3.5" /></button>}
          {!a.params?.parent && <button className="btn-ghost btn-sm bg-white/90" onClick={onAdSet} title="Make an ad set (all sizes + headline)"><LayoutGrid className="size-3.5" /></button>}
          <button className="btn-ghost btn-sm bg-white/90" onClick={onReuse} title="Reuse these settings"><RotateCcw className="size-3.5" /></button>
          <button className="btn-ghost btn-sm bg-white/90" onClick={onDelete} title="Delete"><Trash2 className="size-3.5" /></button>
        </div>
      </div>
      <div className="p-3">
        <p className="line-clamp-2 text-xs text-muted">{a.params?.headline ? `“${a.params.headline}” · ` : ""}{a.prompt}</p>
        <p className="mt-1 truncate text-xs text-faint">{a.params?.placement ? `Ad set · ${a.params.placement}` : a.params?.edited_from ? (a.params.provider_label || "Edited") : a.model} · {a.params?.size}{a.params?.style ? ` · ${a.params.style}` : ""}{a.params?.seed != null ? ` · seed ${a.params.seed}` : ""}</p>
        <UsedIn assetId={a.id} className="mt-1" />
        {words && onAdded && (
          <button type="button" disabled={adding} onClick={addWords} className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-lavender px-3 py-1 text-xs font-semibold text-strong hover:bg-brand/15 disabled:opacity-50">
            {adding ? <Spinner className="size-3" /> : <Plus className="size-3" />} Add “{words}”
          </button>
        )}
        <div className="mt-2 flex items-center justify-between gap-2">
          <Rate kind="image" id={a.id} initial={rating} />
          {!a.params?.parent && (
            <div className="flex gap-1">
              <button className="btn-ghost btn-sm" onClick={onEdit}><MessageSquarePlus className="size-3.5" /> Edit</button>
              <button className="btn-ghost btn-sm" onClick={onAdSet}><LayoutGrid className="size-3.5" /> Ad set</button>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
