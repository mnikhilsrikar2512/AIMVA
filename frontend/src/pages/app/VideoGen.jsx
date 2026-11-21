// Videos (design.md v3 7.3): one prompt makes the clip; the result fills the canvas and the changes panel takes every
// change after that. A typed change makes a new version of the whole clip; C opens the frame-by-frame comment view
// to point at a moment and a spot. Engine and fine-tuning stay hidden from owners.
import { useEffect, useMemo, useRef, useState } from "react";
import { useUrlView } from "../../lib/nav";
import { shareToWhatsApp } from "../../lib/utils";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Download, Send, LayoutGrid, MessageSquarePlus, MoreHorizontal, Plus, SlidersHorizontal, Trash2, Video } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../../components/shadcn/dropdown-menu";
import { Tooltip } from "../../components/shadcn/tooltip";
import { Button, Empty, IconButton, JobProgress, ListSkeleton, Modal, PageHeader, cx } from "../../components/ui";
import { LoadError } from "../../components/LoadError";
import { ModulePrompt } from "../../components/ModulePrompt";
import { ChangesPanel, ModuleFrame, ToolbarTitle, usePanelOpen } from "../../components/ModuleChanges";
import { ProviderPicker } from "../../components/GenControls";
import { Rate } from "../../components/Quality";
import VideoStudio from "../../components/VideoStudio";
import { del, get, post } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useAuth } from "../../lib/auth";

/** The words a video version shows in the panel. */
function said(a, first) {
  const p = a.params || {};
  if (first) return a.prompt;
  const words = [p.request, ...(p.changes || []).map((c) => c.text)].filter(Boolean);
  return words.join("; ") || "New version";
}

export default function VideoGen() {
  const { data: assets, setData: setAssets, loading, error, reload } = useApi("/api/content/assets?kind=video", []);
  const { data: options, loading: optsLoading } = useApi("/api/providers/options?kind=video", []);
  const { data: brandKit } = useApi("/api/brand");
  const { data: ratings } = useApi("/api/feedback?kind=video", {});
  const admin = !!useAuth().user?.is_admin;
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const given = useRef(params.get("prompt") || "");
  const [view, setView, selId, setSelId, setUrl] = useUrlView(given.current ? "prompt" : null);  // in the address (plan S7)
  const [busy, setBusy] = useState(false);
  const [panelOpen, togglePanel] = usePanelOpen();
  const [comparing, setComparing] = useState(null);
  const [studio, setStudio] = useState(false);
  const [advOpen, setAdvOpen] = useState(false);
  const [engine, setEngine] = useState(null);  // admin only
  const available = options.some((o) => o.available);

  useEffect(() => {
    if (loading || view) return;
    const want = Number(params.get("asset")) || null;
    const start = (want && assets.find((a) => a.id === want)) || assets[0];
    if (start) { setSelId(start.id); setView("work"); } else setView("prompt");
    if (params.get("prompt") || params.get("asset")) setUrl({ prompt: null, asset: null }, { replace: true });
  }, [loading]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Renders take minutes: check the unfinished ones every 6 seconds (also picks up the sound stage).
  const queued = assets.filter((a) => a.status === "queued").map((a) => a.id).join(",");
  useEffect(() => {
    if (!queued) return undefined;
    const t = setInterval(async () => {
      for (const id of queued.split(",")) {
        const a = await get(`/api/content/video/${id}`).catch(() => null);
        if (a) setAssets((all) => all.map((x) => (x.id === a.id ? { ...x, ...a } : x)));
      }
    }, 6000);
    return () => clearInterval(t);
  }, [queued, setAssets]);

  const byId = useMemo(() => new Map(assets.map((a) => [a.id, a])), [assets]);
  const rootOf = (a) => { let x = a; const seen = new Set(); while (x?.params?.parent && byId.has(x.params.parent) && !seen.has(x.id)) { seen.add(x.id); x = byId.get(x.params.parent); } return x?.id; };
  const sel = byId.get(selId) || null;
  const chain = sel ? assets.filter((a) => rootOf(a) === rootOf(sel)).sort((a, b) => a.id - b.id) : [];
  const versions = chain.map((a, i) => ({ id: a.id, number: i + 1, request: said(a, i === 0), by: a.by, created_at: a.created_at,
    current: a.id === selId, state: a.status === "queued" && a.params?.stage !== "audio" ? "making" : a.status === "failed" ? "failed" : null })).reverse();

  const make = async (prompt) => {
    setBusy(true);
    try {
      const e = engine || {};
      const out = await post("/api/content/video", { prompt, aspect_auto: true, add_sound: true, use_brand: !!brandKit?.is_set_up,
        ...(e.provider ? { provider: e.provider, model: e.model || "" } : {}) });
      setAssets((a) => [out, ...a]);
      setSelId(out.id); setView("work");
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  const change = async (request) => {
    if (!sel) return false;
    setBusy(true);
    try {
      const p = sel.params || {};
      const root = byId.get(rootOf(sel)) || sel;
      const out = await post("/api/content/video", { prompt: root.prompt, parent_id: sel.id, request, aspect_ratio: p.aspect_ratio || "16:9",
        duration: String(p.duration || "5s"), add_sound: !p.has_audio, use_brand: !!p.brand });
      setAssets((a) => [out, ...a]);
      setSelId(out.id);
      return true;
    } catch (err) { toast.error(err.message); return false; } finally { setBusy(false); }
  };
  const remove = (a) => {
    const keep = assets;
    setAssets((all) => all.filter((x) => x.id !== a.id));
    const next = chain.filter((x) => x.id !== a.id).pop() || assets.find((x) => x.id !== a.id);
    setSelId(next?.id ?? null);
    if (!next) setView("prompt");
    let undone = false;
    const t = setTimeout(() => { if (!undone) del(`/api/content/assets/${a.id}`).catch((e) => { toast.error(e.message); reload(); }); }, 5000);
    toast("Video deleted.", { duration: 5000, action: { label: "Undo", onClick: () => { undone = true; clearTimeout(t); setAssets(keep); setSelId(a.id); setView("work"); } } });
  };
  const addSound = async () => {
    try {
      const out = await post(`/api/content/video/${sel.id}/sound`, {});
      setAssets((all) => all.map((x) => (x.id === out.id ? { ...x, ...out } : x)));
    } catch (err) { toast.error(err.message); }
  };
  useEffect(() => {
    if (view !== "work" || !sel || sel.status !== "done") return undefined;
    const k = (e) => {
      if (e.key.toLowerCase() !== "c" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.querySelector("[role=dialog]")) return;
      e.preventDefault(); setStudio(true);
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [view, sel]);

  const notOn = !optsLoading && options.length > 0 && !available ? "Video isn't switched on for your account yet." : null;
  const more = (
    <DropdownMenu>
      <Tooltip content="More"><DropdownMenuTrigger asChild><button type="button" className="btn-subtle btn-sm w-8 px-0" aria-label="More"><MoreHorizontal className="size-4" /></button></DropdownMenuTrigger></Tooltip>
      <DropdownMenuContent align="end">
        {assets.length > 0 && <DropdownMenuItem onSelect={() => setView("all")}><LayoutGrid className="size-4" /> All videos</DropdownMenuItem>}
        {admin && <DropdownMenuItem onSelect={() => setAdvOpen(true)}><SlidersHorizontal className="size-4" /> Advanced</DropdownMenuItem>}
      </DropdownMenuContent>
    </DropdownMenu>
  );
  const advanced = (
    <Modal open={advOpen} onClose={() => setAdvOpen(false)} title="Advanced">
      <ProviderPicker kind="video" value={engine || { provider: "", model: "" }} onChange={setEngine} />
      <div className="mt-4 flex justify-end"><Button variant="ghost" onClick={() => setAdvOpen(false)}>Done</Button></div>
    </Modal>
  );

  if (view === null) return <><PageHeader title="Videos" /><ListSkeleton /></>;
  if (error && !assets.length && view !== "prompt") return <><PageHeader title="Videos" /><LoadError error={error} what="your videos" onRetry={reload} /></>;

  if (view === "prompt") {
    return (
      <div>
        <PageHeader title="Videos" />
        <ModulePrompt moduleKey="videos" given={given.current} busy={busy} submitLabel="Make the video" onSubmit={make} disabled={!!notOn} note={notOn}
          outcome="You'll get a short video with sound. It takes a few minutes, and you can leave this page."
          secondary={assets.length > 0 && <button type="button" className="font-medium text-brand hover:underline" onClick={() => setView(sel ? "work" : "all")}>Back to my videos</button>} />
        {advanced}
      </div>
    );
  }

  if (view === "all") {
    const roots = assets.filter((a) => !a.params?.parent || !byId.has(a.params.parent));
    return (
      <div>
        <PageHeader title="Videos" />
        <div className="mb-6 flex items-center justify-between gap-3">
          <p className="text-sm text-muted">{roots.length} video{roots.length === 1 ? "" : "s"}</p>
          <span className="flex items-center gap-1">{more}<Button variant="ghost" onClick={() => setView("prompt")}><Plus className="size-4" /> New video</Button></span>
        </div>
        <ul className="border-t border-line">
          {roots.map((r) => {
            const latest = assets.filter((a) => rootOf(a) === r.id).sort((a, b) => b.id - a.id)[0] || r;
            return (
              <li key={r.id}>
                <button type="button" onClick={() => { setSelId(latest.id); setView("work"); }} className="flex w-full items-center gap-4 border-b border-line py-3 text-left hover:bg-surface-2/60">
                  <span className="grid h-14 w-24 shrink-0 place-items-center overflow-hidden rounded-md bg-strong">
                    {latest.status === "done" ? <video src={latest.url} muted preload="metadata" className="size-full object-cover" /> : <Video className="size-4 text-white/70" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-strong">{r.prompt}</span>
                    <span className="block text-xs text-muted">{latest.by ? `${latest.by} · ` : ""}{latest.status === "queued" ? "Making it…" : latest.status === "failed" ? "Didn't finish" : `${assets.filter((a) => rootOf(a) === r.id).length} version${assets.filter((a) => rootOf(a) === r.id).length === 1 ? "" : "s"}`}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        {advanced}
      </div>
    );
  }

  const p = sel?.params || {};
  const making = sel?.status === "queued" && p.stage !== "audio";
  const toolbar = (
    <>
      <ToolbarTitle status={chain.length > 1 ? `v${chain.findIndex((a) => a.id === sel?.id) + 1}` : null}>{(byId.get(rootOf(sel)) || sel)?.prompt || "New video"}</ToolbarTitle>
      {sel?.status === "done" && (
        <span className="flex items-center gap-1">
          <span className="hidden sm:inline-flex"><Rate kind="video" id={sel.id} initial={ratings[sel.id]} /></span>
          <IconButton label="Point and change (C)" onClick={() => setStudio(true)}><MessageSquarePlus className="size-4" /></IconButton>
          <IconButton label="Download" href={sel.url} download target="_blank" rel="noreferrer"><Download className="size-4" /></IconButton>
          <IconButton label="Send on WhatsApp" onClick={() => shareToWhatsApp(sel.url, "video").then((r) => r === "downloaded" && toast("Saved. Attach it in the WhatsApp tab that just opened.")).catch((e) => toast.error(e.message))}><Send className="size-4" /></IconButton>
        </span>
      )}
      {sel && sel.status !== "queued" && <IconButton label="Delete" danger onClick={() => remove(sel)}><Trash2 className="size-4" /></IconButton>}
      {more}
      <Button variant="ghost" size="sm" onClick={() => setView("prompt")}><Plus className="size-3.5" /> New</Button>
      {sel?.status === "done" && <Button variant="accent" size="sm" onClick={() => navigate(`/app/ads/meta?video=${sel.id}`)}>Use in a campaign</Button>}
    </>
  );

  return (
    <>
      <PageHeader title="Videos" />
      <ModuleFrame toolbar={toolbar} panel={
        <ChangesPanel open={panelOpen} onToggle={togglePanel} versions={versions} onSend={sel?.status === "done" ? change : null} sending={busy}
          placeholder="Change anything: “slower”, “more people smiling”" restoreLabel="Use this"
          onRestore={(v) => setSelId(v.id)} onCompare={(v) => setComparing(byId.get(v.id))} />
      }>
        {!sel ? <Empty icon={Video} title="Your video appears here" text="Say what you want in one line." action={<Button variant="ghost" onClick={() => setView("prompt")}>Make a video</Button>} />
          : making ? (
            <div className="mx-auto max-w-xl">
              <div className={cx("mb-5 w-full rounded-[10px] bg-surface-2", p.aspect_ratio === "9:16" ? "mx-auto aspect-[9/16] max-h-[55dvh] w-auto" : "aspect-video")} />
              <JobProgress startedAt={sel.created_at} seconds={150} canLeave label="Making your video…" />
            </div>
          ) : sel.status === "failed" ? (
            <div className="max-w-xl">
              <p role="alert" className="text-sm text-danger">This version didn't finish{p.error ? `: ${p.error}` : "."}</p>
              <p className="mt-2 text-sm text-muted">Try the change again in the panel, or pick an earlier version.</p>
            </div>
          ) : (
            <div className="flex flex-col items-center">
              <video key={sel.id} src={sel.url} controls playsInline className="max-h-[calc(100dvh-16rem)] w-auto max-w-full rounded-[10px] bg-strong" />
              <p className="mt-3 flex items-center gap-3 text-xs text-muted">
                {p.has_audio ? "With sound" : p.stage === "audio" ? "Adding sound…" : "No sound yet"}
                {!p.has_audio && p.stage !== "audio" && <button type="button" className="font-medium text-brand hover:underline" onClick={addSound}>Add sound</button>}
              </p>
            </div>
          )}
      </ModuleFrame>
      <Modal open={!!comparing} onClose={() => setComparing(null)} title={comparing ? `v${chain.findIndex((a) => a.id === comparing.id) + 1} and now` : ""} wide="xl">
        {comparing && sel && (
          <div className="grid gap-4 sm:grid-cols-2">
            {[["Before", comparing], ["Now", sel]].map(([l, a]) => (
              <figure key={l}>
                <figcaption className="mb-1.5 text-xs font-medium text-muted">{l}</figcaption>
                {a.status === "done" ? <video src={a.url} controls playsInline className="w-full rounded-md bg-strong" /> : <div className="grid aspect-video place-items-center rounded-md bg-surface-2 text-xs text-muted">Not ready</div>}
              </figure>
            ))}
          </div>
        )}
      </Modal>
      <VideoStudio video={studio ? sel : null} versions={chain} open={studio && !!sel} onClose={() => setStudio(false)} onPick={(v) => setSelId(v.id)}
        onCreated={(n) => { setAssets((all) => [n, ...all]); setSelId(n.id); setStudio(false); }} />
      {advanced}
    </>
  );
}
