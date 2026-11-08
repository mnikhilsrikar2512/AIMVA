import { useEffect, useState } from "react";
import { SaveTemplateButton, TemplateStrip, useTemplateTracker } from "../../components/Templates";
import { motion } from "framer-motion";
import { rise, stagger } from "../../components/Motion";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Clapperboard, KeyRound, MessageSquarePlus, Plus, Trash2, Video, Volume2, VolumeX, Wand2 } from "lucide-react";
import { Button, Card, Chip, Empty, Field, Notice, PageHeader, Spinner, Tabs, cx, ListSkeleton, JobProgress } from "../../components/ui";
import { LoadError } from "../../components/LoadError";
import { del, get, post } from "../../lib/api";
import { timeAgo, useAction, useApi } from "../../lib/hooks";
import BrandControls from "../../components/BrandControls";
import { useAuth } from "../../lib/auth";
import { Advanced, LibraryImagePicker, ProviderPicker, SeedField, STYLES } from "../../components/GenControls";
import { EnhanceButton, Rate } from "../../components/Quality";
import VideoStudio from "../../components/VideoStudio";

const DURATION_LABEL = (d) => `${String(d).replace(/s$/, "")} seconds`;

function Switch({ checked, onChange, label }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
      className={cx("relative h-6 w-10 shrink-0 rounded-full transition", checked ? "bg-strong" : "bg-ink/15")}>
      <span className={cx("absolute top-0.5 size-5 rounded-full bg-white shadow transition-all", checked ? "left-[18px]" : "left-0.5")} />
    </button>
  );
}

function VideoCard({ a, rating, onChange, onDelete, onComment }) {
  const [soundBusy, setSoundBusy] = useState(false);
  const p = a.params || {};
  const addingSound = a.status === "queued" && p.stage === "audio";
  const addSound = async () => {
    setSoundBusy(true);
    try {
      onChange(await post(`/api/content/video/${a.id}/sound`, {}));
      toast.success("Adding sound. This usually takes about a minute.");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSoundBusy(false);
    }
  };
  return (
    <motion.div variants={rise} initial="hidden" animate="show" className="card overflow-hidden">
      <div className="relative grid aspect-video place-items-center bg-strong/90">
        {a.status === "done" || (addingSound && p.silent_url) ? (
          <video src={a.url} controls className="h-full w-full" />
        ) : a.status === "queued" ? (
          <div className="w-[min(18rem,85%)] rounded-lg bg-surface/95 p-3"><JobProgress startedAt={a.created_at} seconds={150} canLeave steps={["Reading your description…", "Planning the shots…", "Rendering the frames…", "Smoothing the motion…", "Almost there…"]} /></div>
        ) : <p className="px-4 text-center text-sm text-rose-300">Render failed{p.error ? `: ${p.error}` : ""}</p>}
        {addingSound && (
          <span className="absolute left-3 top-3 inline-flex items-center gap-1.5 rounded-full bg-white/90 px-3 py-1 text-xs font-semibold text-strong">
            <Spinner className="size-3.5" /> Adding sound…
          </span>
        )}
      </div>
      <div className="flex items-start justify-between gap-2 p-4">
        <div className="min-w-0">
          <p className="line-clamp-2 text-sm text-ink">{a.prompt}</p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-faint">
            {timeAgo(a.created_at)}{p.aspect_ratio ? ` · ${p.aspect_ratio}` : ""}
            {a.status === "done" && (p.has_audio
              ? <span className="inline-flex items-center gap-1 font-semibold text-emerald-600"><Volume2 className="size-3" /> With sound</span>
              : <span className="inline-flex items-center gap-1"><VolumeX className="size-3" /> Silent{p.audio_error ? " (sound failed)" : ""}</span>)}
          </p>
          {a.status === "done" && !p.has_audio && (
            <button onClick={addSound} disabled={soundBusy} className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-lavender px-3 py-1 text-xs font-semibold text-strong hover:bg-brand/15 disabled:opacity-50">
              {soundBusy ? <Spinner className="size-3" /> : <Wand2 className="size-3" />} Add sound
            </button>
          )}
        </div>
        <div className="flex items-center gap-1">
          {a.status === "done" && <button className="btn-subtle btn-sm" title="Comment to change it" aria-label="Comment to change it" onClick={onComment}><MessageSquarePlus className="size-3.5" /></button>}
          {a.status === "done" && <Rate kind="video" id={a.id} initial={rating} />}
          <Chip tone={a.status === "done" ? "green" : a.status === "queued" ? "amber" : "rose"}>{addingSound ? "sound" : a.status}</Chip>
          <button className="btn-subtle btn-sm" aria-label="Delete video" onClick={onDelete}><Trash2 className="size-3.5" /></button>
        </div>
      </div>
    </motion.div>
  );
}

const CAMERAS = [["", "No camera move"], ["static", "Static"], ["push_in", "Slow push-in"], ["pull_out", "Pull-out reveal"], ["pan_left", "Pan left"],
  ["pan_right", "Pan right"], ["orbit", "Orbit"], ["drone", "Drone flyover"], ["handheld", "Handheld"], ["tilt_up", "Tilt up"]];
const GENERIC_DURATIONS = ["4s", "5s", "6s", "8s", "10s"];

export default function VideoGen() {
  const { data: models } = useApi("/api/content/models");
  const { data: options } = useApi("/api/providers/options?kind=video", []);
  const { data: assets, setData: setAssets, loading, error: assetsError, reload: reloadAssets } = useApi("/api/content/assets?kind=video", []);
  const EMPTY = { prompt: "", aspect_ratio: "16:9", duration: "", resolution: "", negative_prompt: "", seed: null,
                  camera: "", style: "", start: "", generate_audio: false };
  const [form, setForm] = useState(EMPTY);
  const admin = !!useAuth().user?.is_admin; // the platform owner sees engine and fine-tuning options; customers get the essentials
  const [tab, setTab] = useState("create");
  const [currentIds, setCurrentIds] = useState([]);  // renders started in this session, shown in Create
  const [q, setQ] = useState("");
  const [prov, setProv] = useState({ provider: "builtin:studio", model: "video-sound" });
  const [sound, setSound] = useState({ add_sound: true, sound_prompt: "" });
  const [busy, run] = useAction();
  const { data: brandKit } = useApi("/api/brand");
  const [brandOpts, setBrandOpts] = useState({ use_brand: true });
  const { data: ratings } = useApi("/api/feedback?kind=video", {});
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const queued = assets.filter((a) => a.status === "queued").map((a) => a.id).join(",");

  const isFal = prov.provider === "builtin:studio";  // AIMVA video (neutral id from the backend)
  const known = isFal ? models?.video.find((m) => m.id === prov.model) : null;
  const durations = known ? known.durations : GENERIC_DURATIONS;
  const duration = durations.includes(form.duration) ? form.duration : durations[0] || "";
  const makesSound = known ? known.audio : form.generate_audio;
  const anyAvailable = options.some((o) => o.available);
  const falConnected = models?.studio_available;

  // Poll queued renders every 6s (also picks up the "adding sound" stage).
  useEffect(() => {
    if (!queued) return;
    const t = setInterval(async () => {
      for (const id of queued.split(",")) {
        const a = await get(`/api/content/video/${id}`).catch(() => null);
        if (a) setAssets((all) => all.map((x) => (x.id === a.id ? a : x)));
      }
    }, 6000);
    return () => clearInterval(t);
  }, [queued, setAssets]);

  const tpl = useTemplateTracker("video");
  const tplPayload = () => ({ prompt: form.prompt, aspect_ratio: form.aspect_ratio, camera: form.camera || "", style: form.style || "", negative_prompt: form.negative_prompt });
  const submit = async (e) => {
    e.preventDefault();
    const start = form.start;
    const out = await run(() => post("/api/content/video", {
      prompt: form.prompt, provider: prov.provider, model: prov.model, aspect_ratio: form.aspect_ratio, duration,
      resolution: form.resolution || null, negative_prompt: form.negative_prompt, seed: form.seed,
      camera: form.camera || null, style: form.style || null, generate_audio: known ? null : form.generate_audio,
      start_ref: start || "",
      ...sound, add_sound: sound.add_sound && !makesSound,
      use_brand: !!brandKit?.is_set_up && brandOpts.use_brand,
    }), "Render started");
    if (out) {
      tpl.track(tplPayload());
      setAssets((a) => [out, ...a]);
      setCurrentIds((ids) => [out.id, ...ids]);
    }
  };
  const startNew = () => { setForm(EMPTY); setCurrentIds([]); setTab("create"); };
  const current = assets.filter((a) => currentIds.includes(a.id));
  const history = assets.filter((a) => a.prompt.toLowerCase().includes(q.toLowerCase()));
  const [studio, setStudio] = useState(null);
  const rootOf = (a) => { let x = a; const seen = new Set(); while (x?.params?.parent && !seen.has(x.id)) { seen.add(x.id); x = assets.find((y) => y.id === x.params.parent) || x; if (seen.has(x.id)) break; } return x?.id; };
  const chain = studio ? assets.filter((x) => rootOf(x) === rootOf(studio)).sort((a, b) => a.id - b.id) : [];
  const card = (a) => (
    <VideoCard key={a.id} a={a} rating={ratings[a.id]} onComment={() => setStudio(a)}
      onChange={(n) => setAssets((all) => all.map((x) => (x.id === n.id ? n : x)))}
      onDelete={async () => { await del(`/api/content/assets/${a.id}`); setAssets((all) => all.filter((x) => x.id !== a.id)); }} />
  );

  return (
    <div>
      <VideoStudio video={studio} versions={chain} open={!!studio} onClose={() => setStudio(null)} onPick={setStudio}
        onCreated={(n) => { setAssets((all) => [n, ...all]); setStudio(null); setTab("history"); }} />
      <PageHeader icon={Video} tone="pink" title="Videos" subtitle="Turn a sentence or a picture into a short promo clip, with sound."
        actions={<Button variant="ghost" onClick={startNew}><Plus className="size-4" /> Start new</Button>} />
      <div className="mb-6"><Tabs value={tab} onChange={setTab} tabs={[{ value: "create", label: "Create" }, { value: "history", label: `History${assets.length ? ` (${assets.length})` : ""}` }]} /></div>
      {options.length > 0 && !anyAvailable && (
        <Notice tone="amber" icon={KeyRound}>
          Video isn't switched on for your account yet.
        </Notice>
      )}
      {tab === "history" ? (
        loading ? <ListSkeleton /> : assetsError && assets.length === 0 ? (
          <LoadError error={assetsError} what="your videos" onRetry={reloadAssets} />
        ) : assets.length === 0 ? (
          <Empty icon={Video} preview="tiles" title="Your videos will live here" text="Every video you make is saved here, with its sound." action={<Button onClick={() => setTab("create")}><Plus className="size-4" /> Make your first video</Button>} />
        ) : (
          <>
            <input className="input mb-4 max-w-sm" placeholder="Search by prompt" value={q} onChange={(e) => setQ(e.target.value)} />
            <motion.div variants={stagger} initial="hidden" animate="show" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{history.map(card)}</motion.div>
          </>
        )
      ) : (
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[400px_minmax(0,1fr)]">
        <Card className="h-fit">
          <form onSubmit={submit} className="space-y-4">
            {admin && <TemplateStrip module="video" onApply={(t) => { tpl.apply(t); setForm((f) => ({ ...f, prompt: t.payload.prompt, aspect_ratio: t.payload.aspect_ratio || f.aspect_ratio, camera: t.payload.camera || "", style: t.payload.style || "", negative_prompt: t.payload.negative_prompt || "" })); }} />}
            <Field label="Prompt">
              <textarea className="input" rows={5} value={form.prompt} onChange={set("prompt")} required minLength={3} maxLength={2000}
                placeholder="A slow cinematic drone shot over a beachfront villa at sunset, waves and soft music…" />
            </Field>
            <div className="-mt-2 flex justify-end">
              <EnhanceButton prompt={form.prompt} kind="video" useBrand={!!brandKit?.is_set_up && brandOpts.use_brand}
                onEnhanced={(r) => setForm((f) => ({ ...f, prompt: r.prompt, negative_prompt: f.negative_prompt || r.negative_prompt || "" }))} />
            </div>
            <ProviderPicker kind="video" value={prov} onChange={setProv}
              models={isFal ? (models?.video || []).map((m) => m.id) : undefined}
              modelHint={known ? (known.audio ? "Generates video and matching audio together." : "This model makes silent video.") : "Any model this provider offers. Settings below are passed through."} />
            <div className="grid grid-cols-2 gap-3">
              <Field label="Aspect ratio">
                <select className="input" value={form.aspect_ratio} onChange={set("aspect_ratio")} disabled={known && !known.aspect_ratio}
                  title={known && !known.aspect_ratio ? "This model picks the shape itself" : undefined}>
                  {(known ? ["16:9", "9:16", "1:1"] : ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]).map((s) => <option key={s}>{s}</option>)}
                </select>
              </Field>
              <Field label="Duration">
                <select className="input" value={duration} onChange={set("duration")} disabled={!durations.length}>
                  {durations.length ? durations.map((d) => <option key={d} value={d}>{DURATION_LABEL(d)}</option>) : <option value="">Auto</option>}
                </select>
              </Field>
            </div>

            {admin && <Advanced>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Camera">
                  <select className="input" value={form.camera} onChange={set("camera")}>{CAMERAS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
                </Field>
                <Field label="Style">
                  <select className="input" value={form.style} onChange={set("style")}>{STYLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
                </Field>
              </div>
              <Field label="Resolution" hint={known && !known.audio ? "Chosen by this model." : "Leave on Auto unless your model needs it."}>
                <select className="input" value={form.resolution} onChange={set("resolution")} disabled={known && !known.audio}>
                  {["", "480p", "540p", "720p", "1080p", "1440p", "2160p"].map((r) => <option key={r} value={r}>{r || "Auto"}</option>)}
                </select>
              </Field>
              <Field label="Avoid (negative prompt)"><input className="input" value={form.negative_prompt} onChange={set("negative_prompt")} maxLength={1000} placeholder="blurry, distorted faces, text" /></Field>
              <SeedField value={form.seed} onChange={(v) => setForm((f) => ({ ...f, seed: v }))} />
              {!known && (
                <label className="flex items-center gap-2 text-sm text-ink">
                  <input type="checkbox" className="size-4 accent-violet-500" checked={form.generate_audio}
                    onChange={(e) => setForm((f) => ({ ...f, generate_audio: e.target.checked }))} />
                  This engine renders its own sound
                </label>
              )}
            </Advanced>}

            <LibraryImagePicker label="Start from an image (optional)" value={form.start} onChange={(v) => setForm((f) => ({ ...f, start: v }))}
              hint="Animates a product photo or one of your generated images." />

            {!makesSound && falConnected && (
              <div className="space-y-3 rounded-2xl bg-surface-2/60 p-4">
                <div className="flex items-center gap-3">
                  <Volume2 className="size-4 text-brand" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-strong">Add sound</p>
                    <p className="text-xs text-muted">Adds matching ambience and music after rendering.</p>
                  </div>
                  <Switch label="Add sound" checked={sound.add_sound} onChange={(v) => setSound((s) => ({ ...s, add_sound: v }))} />
                </div>
                {sound.add_sound && (
                  <input className="input" value={sound.sound_prompt} onChange={(e) => setSound((s) => ({ ...s, sound_prompt: e.target.value }))}
                    maxLength={500} placeholder="Optional: describe the sound, e.g. waves, seagulls, soft piano" />
                )}
              </div>
            )}

            <BrandControls brand={brandKit} value={brandOpts} onChange={setBrandOpts} mode="video-plain" />
            <Button type="submit" busy={busy} disabled={!anyAvailable} className="h-11 w-full"><Clapperboard className="size-4" /> Render video</Button>
            {admin && form.prompt.trim().length >= 3 && <div className="flex justify-center"><SaveTemplateButton module="video" getPayload={tplPayload} /></div>}
          </form>
        </Card>
        <div>
          {current.length === 0 ? (
            <Empty icon={Video} preview="tiles" title="Your new video appears here"
              text="Describe it on the left. It usually takes 1–3 minutes, plus about a minute for sound. Earlier videos are in History." />
          ) : (
            <>
              <p className="mb-3 text-sm font-semibold text-strong">This session · saved to History</p>
              <div className="grid gap-4 sm:grid-cols-2">{current.map(card)}</div>
            </>
          )}
        </div>
      </div>
      )}
    </div>
  );
}
