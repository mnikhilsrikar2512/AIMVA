import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Check, ImagePlus, Palette, Plus, Sparkles, Star, Trash2, UploadCloud, X } from "lucide-react";
import { toast } from "sonner";
import { Button, Card, Field, PageHeader, Spinner, cx } from "../../components/ui";
import { api, del, post, put } from "../../lib/api";
import { useApi } from "../../lib/hooks";

const VOICES = [
  { value: "friendly", label: "Friendly", hint: "Warm, approachable, positive" },
  { value: "professional", label: "Professional", hint: "Clear, credible, polished" },
  { value: "bold", label: "Bold", hint: "Confident, punchy, energetic" },
  { value: "playful", label: "Playful", hint: "Fun, light-hearted, witty" },
  { value: "luxury", label: "Luxury", hint: "Elegant, refined, premium" },
];
const STYLE_IDEAS = ["minimal", "bright natural light", "bold colours", "cinematic", "flat illustration", "premium", "warm tones", "lifestyle photography"];
const FIELDS = ["name", "tagline", "colors", "voice", "voice_notes", "style", "audience", "avoid"];

function Dropzone({ onFiles, busy, label, compact }) {
  const input = useRef(null);
  const [over, setOver] = useState(false);
  return (
    <button
      type="button"
      onClick={() => input.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onFiles([...e.dataTransfer.files]); }}
      className={cx(
        "flex w-full cursor-pointer flex-col items-center justify-center gap-1.5 rounded-2xl border-2 border-dashed text-center transition",
        compact ? "h-28" : "h-36",
        over ? "border-brand bg-lavender" : "border-line-strong bg-surface-2/50 hover:border-brand/50 hover:bg-lavender/50"
      )}
    >
      {busy ? <Spinner className="size-5 text-brand" /> : <UploadCloud className="size-5 text-brand" />}
      <span className="text-sm font-semibold text-strong">{label}</span>
      <span className="text-xs text-faint">PNG, JPG or WebP · up to 5 MB</span>
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" multiple hidden
        onChange={(e) => { onFiles([...e.target.files]); e.target.value = ""; }} />
    </button>
  );
}

function Section({ title, hint, children }) {
  return (
    <section className="py-6 first:pt-0 last:pb-0">
      <h2 className="text-base font-bold text-strong">{title}</h2>
      {hint && <p className="mt-0.5 text-sm text-muted">{hint}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Preview({ kit }) {
  const logo = kit.logos.find((l) => l.is_primary) || kit.logos[0];
  const [c1, c2] = [kit.colors[0] || "#6d5dfc", kit.colors[1] || kit.colors[0] || "#ff8a65"];
  const voice = VOICES.find((v) => v.value === kit.voice);
  return (
    <div className="space-y-4">
      <p className="px-1 text-xs font-semibold uppercase tracking-wider text-faint">Live preview</p>
      <div className="overflow-hidden rounded-3xl bg-surface shadow-[var(--shadow-lift)]">
        <div className="relative h-40" style={{ background: `linear-gradient(135deg, ${c1}, ${c2})` }}>
          {kit.images[0] && <img src={kit.images[0].url} alt="" className="absolute inset-0 h-full w-full object-cover opacity-90" />}
          {logo && (
            <img src={logo.url} alt="Logo" className="absolute bottom-3 right-3 max-h-10 max-w-[96px] rounded-lg bg-white/85 object-contain p-1.5 shadow" />
          )}
        </div>
        <div className="p-5">
          <p className="font-display text-lg font-bold text-strong">{kit.name || "Your brand"}</p>
          <p className="mt-0.5 text-sm text-muted">{kit.tagline || "Your tagline appears here"}</p>
          <div className="mt-4 flex gap-1.5">
            {(kit.colors.length ? kit.colors : ["#e5e2f0"]).map((c) => <span key={c} className="size-6 rounded-full ring-2 ring-white shadow" style={{ background: c }} />)}
          </div>
          <span className="mt-4 inline-block rounded-full px-4 py-1.5 text-xs font-semibold text-white" style={{ background: c1 }}>Book now</span>
        </div>
      </div>
      <div className="rounded-2xl bg-surface-2/60 p-4 text-sm text-muted">
        <p className="mb-1.5 flex items-center gap-1.5 font-semibold text-strong"><Sparkles className="size-4 text-brand" /> How AIMVA uses this</p>
        <ul className="space-y-1">
          <li>Images & videos: your style{kit.colors.length ? ", colours" : ""}{kit.avoid ? " and things to avoid" : ""} guide every generation{logo ? ", and your logo can be placed on images" : ""}.</li>
          <li>Ad copy: written in a {voice?.label.toLowerCase()} voice.</li>
          <li>Landing pages: start with your name and colours.</li>
        </ul>
      </div>
    </div>
  );
}

export default function Brand() {
  const { data: loaded, loading } = useApi("/api/brand");
  const [kit, setKit] = useState(null);
  const [saved, setSaved] = useState(null);
  const [suggested, setSuggested] = useState([]);
  const [styleText, setStyleText] = useState("");
  const [uploading, setUploading] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (loaded) { setKit(loaded); setSaved(loaded); } }, [loaded]);
  if (loading || !kit) return <div className="grid h-60 place-items-center"><Spinner className="size-6" /></div>;

  const dirty = FIELDS.some((f) => JSON.stringify(kit[f]) !== JSON.stringify(saved[f]));
  const set = (k, v) => setKit((x) => ({ ...x, [k]: v }));
  const applyServer = (k) => { setKit((x) => ({ ...k, ...Object.fromEntries(FIELDS.map((f) => [f, x[f]])) })); setSaved((s) => ({ ...s, logos: k.logos, images: k.images })); };

  const save = async () => {
    setSaving(true);
    try {
      const k = await put("/api/brand", Object.fromEntries(FIELDS.map((f) => [f, kit[f]])));
      setKit(k); setSaved(k);
      toast.success("Brand Kit saved. It will be used in your next generations.");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const uploadFiles = async (files, kind) => {
    setUploading(kind);
    for (const file of files) {
      const form = new FormData();
      form.append("file", file);
      form.append("kind", kind);
      try {
        const r = await api("/api/brand/assets", { method: "POST", form });
        setKit((x) => ({ ...x, [kind === "logo" ? "logos" : "images"]: [...x[kind === "logo" ? "logos" : "images"], r.asset] }));
        if (r.suggested_colors?.length) setSuggested(r.suggested_colors);
      } catch (e) {
        toast.error(`${file.name}: ${e.message}`);
      }
    }
    setUploading("");
  };

  const addStyle = (s) => {
    const v = s.trim();
    if (v && !kit.style.includes(v) && kit.style.length < 12) set("style", [...kit.style, v]);
    setStyleText("");
  };

  return (
    <div>
      <PageHeader icon={Palette} tone="pink" title="Brand kit"
        subtitle="Your brand's memory. AIMVA uses it in every image, video, ad and landing page you create."
        actions={<Button onClick={save} busy={saving} disabled={!dirty}>{dirty ? "Save changes" : <><Check className="size-4" /> Saved</>}</Button>} />

      <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
        <Card className="divide-y divide-line">
          <Section title="Logo" hint="Upload your logo. We'll place it on images and pull your colours from it.">
            <div className="flex flex-wrap gap-3">
              {kit.logos.map((l) => (
                <div key={l.id} className="group relative grid size-28 place-items-center rounded-2xl bg-surface-2/70 p-3">
                  <img src={l.url} alt={l.filename} loading="lazy" decoding="async" className="max-h-full max-w-full object-contain" />
                  {l.is_primary && <span className="absolute left-2 top-2 rounded-full bg-strong px-2 py-0.5 text-xs font-bold text-white">Primary</span>}
                  <div className="absolute inset-x-2 bottom-2 flex justify-center gap-1 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
                    {!l.is_primary && (
                      <button className="grid size-7 place-items-center rounded-full bg-white shadow" title="Make primary"
                        onClick={async () => applyServer(await post(`/api/brand/assets/${l.id}/primary`))}><Star className="size-3.5" /></button>
                    )}
                    <button className="grid size-7 place-items-center rounded-full bg-white text-rose-600 shadow" title="Delete"
                      onClick={async () => applyServer(await del(`/api/brand/assets/${l.id}`))}><Trash2 className="size-3.5" /></button>
                  </div>
                </div>
              ))}
              <div className={kit.logos.length ? "w-40" : "w-full"}>
                <Dropzone compact={!!kit.logos.length} busy={uploading === "logo"} label={kit.logos.length ? "Add another" : "Drop your logo here"}
                  onFiles={(f) => uploadFiles(f, "logo")} />
              </div>
            </div>
            {suggested.length > 0 && (
              <div className="mt-4 flex flex-wrap items-center gap-3 rounded-2xl bg-lavender/60 px-4 py-3 text-sm">
                <span className="font-medium text-strong">Colours from your logo:</span>
                <span className="flex gap-1.5">{suggested.map((c, i) => <motion.span key={c} className="size-6 rounded-full ring-2 ring-white" style={{ background: c }} title={c}
                  initial={{ scale: 0, y: 6 }} animate={{ scale: 1, y: 0 }} transition={{ type: "spring", stiffness: 420, damping: 18, delay: i * 0.07 }} />)}</span>
                <button className="btn-ghost btn-sm" onClick={() => { set("colors", suggested.slice(0, 5)); setSuggested([]); }}>Use these</button>
                <button className="btn-subtle btn-sm" onClick={() => setSuggested([])}>Dismiss</button>
              </div>
            )}
          </Section>

          <Section title="Name & tagline">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Brand name"><input className="input" value={kit.name} onChange={(e) => set("name", e.target.value)} placeholder="Skyline Homes" /></Field>
              <Field label="Tagline"><input className="input" value={kit.tagline} onChange={(e) => set("tagline", e.target.value)} placeholder="Homes near everything you love" /></Field>
            </div>
          </Section>

          <Section title="Colours" hint="Up to 8. The first two are your main colours.">
            <div className="flex flex-wrap items-center gap-3">
              {kit.colors.map((c, i) => (
                <label key={i} className="group relative cursor-pointer">
                  <span className="block size-12 rounded-2xl ring-1 ring-line shadow-sm" style={{ background: c }} />
                  <input type="color" value={c} className="sr-only" aria-label={`Colour ${i + 1}`}
                    onChange={(e) => set("colors", kit.colors.map((x, j) => (j === i ? e.target.value : x)))} />
                  <span className="mt-1 block text-center font-mono text-xs text-faint">{c}</span>
                  <button type="button" aria-label={`Remove ${c}`} onClick={(e) => { e.preventDefault(); set("colors", kit.colors.filter((_, j) => j !== i)); }}
                    className="absolute -right-2 -top-2 hidden size-6 place-items-center rounded-full bg-white text-muted shadow group-hover:grid group-focus-within:grid"><X className="size-3.5" /></button>
                </label>
              ))}
              {kit.colors.length < 8 && (
                <button type="button" onClick={() => set("colors", [...kit.colors, "#6d5dfc"])}
                  className="mb-5 grid size-12 place-items-center rounded-2xl border-2 border-dashed border-line-strong text-faint hover:border-brand hover:text-brand" aria-label="Add colour">
                  <Plus className="size-5" />
                </button>
              )}
            </div>
          </Section>

          <Section title="Brand voice" hint="How your ad copy and messages should sound.">
            <div className="flex flex-wrap gap-2">
              {VOICES.map((v) => (
                <button key={v.value} type="button" onClick={() => set("voice", v.value)} title={v.hint}
                  className={cx("rounded-full px-4 py-2 text-sm font-medium transition", kit.voice === v.value ? "bg-strong text-white" : "bg-surface-2 text-ink hover:bg-lavender")}>
                  {v.label}
                </button>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted">{VOICES.find((v) => v.value === kit.voice)?.hint}</p>
            <textarea className="input mt-3" rows={2} value={kit.voice_notes} onChange={(e) => set("voice_notes", e.target.value)}
              placeholder="Anything else? e.g. Use simple English, mention free site visits, never use slang." />
          </Section>

          <Section title="Visual style" hint="Words that describe how your images and videos should look.">
            <div className="flex flex-wrap gap-2">
              {kit.style.map((s) => (
                <span key={s} className="inline-flex items-center gap-1 rounded-full bg-lavender px-3 py-1.5 text-sm font-medium text-strong">
                  {s}<button type="button" aria-label={`Remove ${s}`} onClick={() => set("style", kit.style.filter((x) => x !== s))} className="-my-1 -mr-2 grid size-6 place-items-center rounded-full hover:bg-black/5"><X className="size-3.5 text-muted" /></button>
                </span>
              ))}
              <input className="input h-9 w-48 rounded-full" value={styleText} placeholder="Add a style, press Enter" onChange={(e) => setStyleText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addStyle(styleText); } }} onBlur={() => styleText && addStyle(styleText)} />
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {STYLE_IDEAS.filter((s) => !kit.style.includes(s)).map((s) => (
                <button key={s} type="button" onClick={() => addStyle(s)} className="rounded-full bg-surface-2 px-3 py-1 text-xs text-muted hover:bg-lavender hover:text-strong">+ {s}</button>
              ))}
            </div>
          </Section>

          <Section title="Audience & guardrails">
            <div className="grid gap-4">
              <Field label="Who are your customers?"><input className="input" value={kit.audience} onChange={(e) => set("audience", e.target.value)} placeholder="First-time home buyers in Hyderabad" /></Field>
              <Field label="Things to avoid" hint="Kept out of images, videos and copy where possible.">
                <input className="input" value={kit.avoid} onChange={(e) => set("avoid", e.target.value)} placeholder="cartoons, clutter, competitor names" />
              </Field>
            </div>
          </Section>

          <Section title="Brand images" hint="Product photos or references. Videos can start from one of these.">
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-4">
              {kit.images.map((im) => (
                <div key={im.id} className="group relative aspect-square overflow-hidden rounded-2xl bg-surface-2">
                  <img src={im.url} alt={im.filename} loading="lazy" decoding="async" className="h-full w-full object-cover" />
                  <button className="absolute right-2 top-2 grid size-7 place-items-center rounded-full bg-white text-rose-600 opacity-0 shadow transition group-hover:opacity-100" title="Delete"
                    onClick={async () => applyServer(await del(`/api/brand/assets/${im.id}`))}><Trash2 className="size-3.5" /></button>
                </div>
              ))}
              <div className={kit.images.length ? "aspect-square" : "col-span-3 sm:col-span-4"}>
                <Dropzone compact busy={uploading === "image"} label={kit.images.length ? "Add" : "Drop product photos here"} onFiles={(f) => uploadFiles(f, "image")} />
              </div>
            </div>
          </Section>
        </Card>

        <div className="lg:sticky lg:top-8 lg:self-start"><Preview kit={kit} /></div>
      </div>

      {dirty && (
        <div className="fixed inset-x-0 bottom-[calc(4.25rem+env(safe-area-inset-bottom))] z-30 flex justify-center px-4 md:bottom-5 lg:pl-64">
          <div className="flex items-center gap-3 rounded-full bg-strong py-2 pl-5 pr-2 text-sm text-white shadow-2xl animate-[rise_250ms_ease-out]">
            <ImagePlus className="size-4 opacity-70" /> You have unsaved brand changes
            <button className="rounded-full bg-white px-4 py-1.5 text-sm font-semibold text-strong" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
          </div>
        </div>
      )}
    </div>
  );
}
