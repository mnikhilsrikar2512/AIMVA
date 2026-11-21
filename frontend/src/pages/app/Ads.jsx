// Campaigns (design.md v3 7.3): one prompt drafts the campaign (budget, area, people, ad and where it sends them);
// the ad and its settings fill the canvas, and the changes panel takes every change after that. Each setting can also
// be edited in place. Nothing is spent until Launch, which always asks first because it spends money.
import { useEffect, useMemo, useRef, useState } from "react";
import { useUrlView } from "../../lib/nav";
import { Link, NavLink, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { MoreHorizontal, Pause, Play, Plus, RefreshCw, Trash2, X, BarChart3 } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../../components/shadcn/dropdown-menu";
import { Tooltip } from "../../components/shadcn/tooltip";
import { Button, IconButton, ListSkeleton, Modal, PageHeader, cx } from "../../components/ui";
import { LoadError } from "../../components/LoadError";
import { ModulePrompt } from "../../components/ModulePrompt";
import { ChangesPanel, CompareText, ModuleFrame, ToolbarTitle, usePanelOpen } from "../../components/ModuleChanges";
import AdPlacements from "../../components/AdPlacements";
import { del, get, patch, post } from "../../lib/api";
import { useAction, useApi } from "../../lib/hooks";
import { useAuth } from "../../lib/auth";

const PLATFORMS = { meta: "Meta", google: "Google", linkedin: "LinkedIn" };
const STATUS = { draft: "Draft", paused: "Paused", active: "Running" };
const FIELD_LABEL = { full_name: "Name", email: "Email", phone_number: "Phone", city: "City", company_name: "Company", job_title: "Job title" };
const rupees = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

/** A setting shown as plain words that becomes a text box when clicked. */
function Setting({ label, value, shown, onSave, type = "text", placeholder }) {
  const [draft, setDraft] = useState(null);
  const save = () => { const v = (draft ?? "").trim(); setDraft(null); if (v !== String(value ?? "")) onSave(v); };
  return (
    <div className="grid grid-cols-[9rem_1fr] items-start gap-3 border-b border-line py-2.5 text-sm">
      <dt className="pt-1 text-muted">{label}</dt>
      <dd className="min-w-0">
        {draft !== null ? (
          <input autoFocus type={type} aria-label={label} value={draft} placeholder={placeholder} onChange={(e) => setDraft(e.target.value)} onBlur={save}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); save(); } if (e.key === "Escape") setDraft(null); }}
            className="block w-full rounded-md bg-surface px-2 py-1 text-strong ring-2 ring-brand/40 focus:outline-none" />
        ) : (
          <button type="button" title="Click to edit" onClick={() => setDraft(String(value ?? ""))}
            className={cx("w-full whitespace-pre-wrap rounded-md px-2 py-1 text-left hover:bg-surface-2", value ? "text-strong" : "text-muted")}>{shown ?? (value || placeholder || "Add…")}</button>
        )}
      </dd>
    </div>
  );
}

export default function Ads() {
  const { platform = "meta" } = useParams();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { data: campaigns, setData, loading, reload, error } = useApi(`/api/campaigns?platform=${platform}`, []);
  const { data: integrations, reload: reloadInteg } = useApi("/api/integrations", []);
  const { data: sites } = useApi("/api/sites", []);
  const { data: kit } = useApi("/api/brand");
  const { user } = useAuth();
  const given = useRef(params.get("prompt") || "");
  const [media, setMedia] = useState(null);  // a picture or video from "Use in a campaign"
  const [view, setView, selId, setSelId, setUrl] = useUrlView(null);  // prompt | work | all, in the address (plan S7)
  const sel = campaigns.find((c) => c.id === selId) || null;
  const { data: versions, reload: reloadVersions, loading: vLoading } = useApi(sel ? `/api/versions/campaign/${sel.id}` : null, []);
  const [busy, setBusy] = useState(false);
  const [panelOpen, togglePanel] = usePanelOpen();
  const [comparing, setComparing] = useState(null);
  const [launching, setLaunching] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [accounts, setAccounts] = useState(null);
  const [acting, act] = useAction();
  const integ = integrations.find((i) => i.provider === platform);
  const live = sites.find((s) => s.published);
  const logo = kit?.logos?.find((l) => l.is_primary) || kit?.logos?.[0];
  const preview = useMemo(() => ({
    brand: kit?.name || user.company || user.name, logo: logo?.url,
    domain: live ? (live.custom_domain || (() => { try { return new URL(live.deploy_url || live.url).host; } catch { return undefined; } })()) : undefined,
    connected: new Set(integrations.filter((i) => i.connected).map((i) => i.provider)),
  }), [kit, user, logo, live, integrations]);

  useEffect(() => {  // a picture or video sent here from Pictures or Videos
    const image = params.get("image"), video = params.get("video");
    if (image || video) {
      get(`/api/content/assets?kind=${image ? "image" : "video"}`).then((all) => {
        const a = all.find((x) => String(x.id) === (image || video));
        if (a) setMedia(a);
      }).catch(() => {});
      setView("prompt");
    }
    if (image || video || params.get("prompt")) setUrl({ image: null, video: null, prompt: null }, { replace: true });
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps
  const firstPlatform = useRef(platform);
  useEffect(() => {  // switching platform starts that platform fresh (not on first load: the address may name an open campaign)
    if (firstPlatform.current === platform) return;
    firstPlatform.current = platform;
    setSelId(null); if (view !== "prompt" || !media) setView(null);
  }, [platform]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {  // first visit: the prompt; with campaigns, the newest one
    if (loading || view) return;
    if (!given.current && campaigns.length) { setSelId(campaigns[0].id); setView("work"); } else setView("prompt");
  }, [loading, view, campaigns]);

  const replace = (c) => { setData((all) => (all.some((x) => x.id === c.id) ? all.map((x) => (x.id === c.id ? c : x)) : [c, ...all])); setSelId(c.id); reloadVersions(); };
  const draft = async (prompt) => {
    setBusy(true);
    try {
      const c = await post("/api/campaigns/draft", { prompt, platform, asset_id: media?.id ?? null });
      replace(c); setMedia(null); setView("work"); given.current = "";
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };
  const change = async (request) => {
    setBusy(true);
    try { replace(await post(`/api/campaigns/${sel.id}/change`, { request })); return true; }
    catch (e) { toast.error(e.message); return false; } finally { setBusy(false); }
  };
  const save = async (fields) => { try { replace(await patch(`/api/campaigns/${sel.id}`, fields)); } catch (e) { toast.error(e.message); } };
  const setCreative = (k) => (v) => save({ creative: { ...sel.creative, [k]: v } });
  const setTarget = (fields) => save({ targeting: { ...sel.targeting, ...fields } });
  const restore = async (v) => { try { replace(await post(`/api/versions/${v.id}/restore`)); toast(`Back to v${v.number}.`); } catch (e) { toast.error(e.message); } };
  const compare = async (v) => {
    setComparing({ v, before: null });
    try { setComparing({ v, before: (await get(`/api/versions/${v.id}`)).data }); } catch (e) { toast.error(e.message); setComparing(null); }
  };
  const plain = (c) => c && ({ Budget: `${rupees(c.daily_budget)} a day`, Where: [c.targeting?.locations, c.targeting?.radius_km ? `${c.targeting.radius_km} km around` : ""].filter(Boolean).join(", "),
    Who: [c.targeting?.interests, `ages ${c.targeting?.age_min || 18}–${c.targeting?.age_max || 65}`].filter(Boolean).join(", "),
    Headline: c.creative?.headline, Text: c.creative?.text, Button: c.creative?.cta });

  const launch = () => act(async () => {
    let c = sel;
    if (!c.external_id) c = await post(`/api/campaigns/${c.id}/publish`);
    c = await patch(`/api/campaigns/${c.id}`, { status: "active" });
    replace(c); setLaunching(false);
    navigate(`/app/command?campaign=${c.id}`);  // straight to this campaign's overview (owner, 2026-11-21)
    return c;
  }, `Launched on ${PLATFORMS[platform]}.`);
  const remove = () => {
    if (sel.external_id) { setRemoving(true); return; }
    const gone = sel, keep = campaigns;
    setData((all) => all.filter((x) => x.id !== gone.id));
    const next = campaigns.find((x) => x.id !== gone.id);
    setSelId(next?.id ?? null);
    if (!next) setView("prompt");
    let undone = false;
    const t = setTimeout(() => { if (!undone) del(`/api/campaigns/${gone.id}`).catch((e) => { toast.error(e.message); reload(); }); }, 5000);
    toast("Draft deleted.", { duration: 5000, action: { label: "Undo", onClick: () => { undone = true; clearTimeout(t); setData(keep); setSelId(gone.id); setView("work"); } } });
  };

  const tabs = (
    <nav aria-label="Platform" className="flex gap-1">
      {Object.entries(PLATFORMS).map(([k, l]) => (
        <NavLink key={k} to={`/app/ads/${k}`} className={({ isActive }) => cx("rounded-md px-2.5 py-1 text-sm font-medium", isActive ? "bg-accent-soft text-strong" : "text-muted hover:bg-surface-2 hover:text-strong")}>{l}</NavLink>
      ))}
    </nav>
  );

  if (view === null) return <><PageHeader title="Campaigns" /><ListSkeleton /></>;
  if (error && !campaigns.length && view !== "prompt") return <><PageHeader title="Campaigns" /><LoadError error={error} what="your campaigns" onRetry={reload} /></>;

  if (view === "prompt") {
    return (
      <div>
        <PageHeader title="Campaigns" />
        <div className="mb-6">{tabs}</div>
        {media && (
          <div className="mb-4 flex max-w-3xl items-center gap-3 text-sm text-muted">
            {media.kind === "video" ? <video src={media.url} muted className="h-12 w-12 rounded-md bg-strong object-cover" /> : <img src={media.url} alt="" className="size-12 rounded-md object-cover" />}
            <span className="flex-1">The ad uses this {media.kind === "video" ? "video" : "picture"}.</span>
            <IconButton label="Don't use it" onClick={() => setMedia(null)}><X className="size-4" /></IconButton>
          </div>
        )}
        <ModulePrompt key={platform} moduleKey="campaigns" given={given.current} busy={busy} submitLabel="Draft the campaign" onSubmit={draft}
          outcome={`You'll get a ${PLATFORMS[platform]} campaign with the ad, the area and a daily budget. Nothing is spent until you press Launch.`}
          secondary={campaigns.length > 0 && <button type="button" className="font-medium text-brand hover:underline" onClick={() => { setSelId(sel?.id || campaigns[0].id); setView("work"); }}>Back to my campaigns</button>} />
      </div>
    );
  }

  if (view === "all") {
    return (
      <div>
        <PageHeader title="Campaigns" />
        <div className="mb-6 flex items-center justify-between gap-3">{tabs}<Button variant="ghost" onClick={() => setView("prompt")}><Plus className="size-4" /> New campaign</Button></div>
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-left text-xs text-muted"><tr><th className="px-3 py-2 font-medium">Campaign</th><th className="px-3 py-2 font-medium">Budget</th><th className="hidden px-3 py-2 font-medium sm:table-cell">Spent</th><th className="px-3 py-2 font-medium">State</th></tr></thead>
          <tbody>
            {campaigns.map((c) => (
              <tr key={c.id} onClick={() => { setSelId(c.id); setView("work"); }} className="cursor-pointer border-b border-line hover:bg-surface-2/60">
                <td className="px-3 py-2.5"><button type="button" className="text-left font-medium text-strong" onClick={() => { setSelId(c.id); setView("work"); }}>{c.name}</button></td>
                <td className="px-3 py-2.5 tabular-nums">{rupees(c.daily_budget)} a day</td>
                <td className="hidden px-3 py-2.5 tabular-nums sm:table-cell">{rupees(c.spend)}</td>
                <td className="px-3 py-2.5 text-muted">{STATUS[c.status] || c.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs text-muted">{campaigns.length} campaign{campaigns.length === 1 ? "" : "s"}</p>
      </div>
    );
  }

  const t = sel?.targeting || {}, cr = sel?.creative || {};
  const connected = !!integ?.connected;
  const toolbar = (
    <>
      <ToolbarTitle status={sel ? STATUS[sel.status] || sel.status : null}>{sel?.name || "Campaign"}</ToolbarTitle>
      {tabs}
      {sel && (
        <span className="flex items-center gap-1">
          {sel.external_id && <IconButton label="Get the latest results" busy={acting} onClick={() => act(async () => replace(await post(`/api/campaigns/${sel.id}/sync`)))}><RefreshCw className="size-4" /></IconButton>}
          {sel.external_id && sel.status === "active" && <IconButton label="Pause" onClick={() => act(async () => replace(await patch(`/api/campaigns/${sel.id}`, { status: "paused" })), "Paused.")}><Pause className="size-4" /></IconButton>}
          <IconButton label="Delete" danger onClick={remove}><Trash2 className="size-4" /></IconButton>
        </span>
      )}
      <DropdownMenu>
        <Tooltip content="More"><DropdownMenuTrigger asChild><button type="button" className="btn-subtle btn-sm w-8 px-0" aria-label="More"><MoreHorizontal className="size-4" /></button></DropdownMenuTrigger></Tooltip>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => setView("all")}>All campaigns</DropdownMenuItem>
          {connected && platform === "meta" && <DropdownMenuItem onSelect={() => act(async () => setAccounts(await get("/api/campaigns/meta/ad-accounts")))}>Choose the ad account</DropdownMenuItem>}
        </DropdownMenuContent>
      </DropdownMenu>
      <Button variant="ghost" size="sm" onClick={() => setView("prompt")}><Plus className="size-3.5" /> New</Button>
      {sel && sel.status !== "draft" && <Link to={`/app/command?campaign=${sel.id}`} className="btn-ghost btn-sm"><BarChart3 className="size-3.5" /> See results</Link>}
      {sel && sel.status !== "active" && (connected
        ? <Button variant="accent" size="sm" onClick={() => setLaunching(true)}>{sel.status === "paused" ? <><Play className="size-3.5" /> Resume</> : "Launch"}</Button>
        : <Link to="/app/settings?tab=integrations" className="btn-ghost btn-sm">Connect {PLATFORMS[platform]} to launch</Link>)}
    </>
  );

  return (
    <>
      <PageHeader title="Campaigns" />
      <ModuleFrame toolbar={toolbar} panel={
        <ChangesPanel open={panelOpen} onToggle={togglePanel} versions={versions} loading={vLoading} onSend={sel ? change : null} sending={busy}
          placeholder="Change anything: “₹800 a day”, “within 5 km”, “shorter headline”" onRestore={restore} onCompare={compare} />
      }>
        {sel && (
          <div className="grid gap-8 xl:grid-cols-[300px_minmax(0,1fr)]">
            <div className="order-2 xl:order-1"><AdPlacements creative={cr} platform={platform} still {...preview} /></div>
            <dl className="order-1 max-w-2xl border-t border-line xl:order-2">
              <Setting label="Budget" type="number" value={sel.daily_budget} shown={`${rupees(sel.daily_budget)} a day · about ${rupees(sel.daily_budget * 30)} a month`}
                onSave={(v) => { const n = Number(v); if (n >= 0) save({ daily_budget: n }); }} />
              <Setting label="Where" value={t.locations ? `${t.radius_km ? `${t.radius_km} km around ` : ""}${t.locations}` : ""} placeholder="A city or area, like “8 km around Kukatpally”"
                onSave={(v) => { const m = v.match(/^\s*(\d{1,3})\s*km\s*(?:around|of|from)?\s*(.*)$/i); setTarget(m ? { radius_km: Number(m[1]), locations: m[2].trim() } : { radius_km: 0, locations: v }); }} />
              <Setting label="Who" value={t.interests} placeholder="Anyone" onSave={(v) => setTarget({ interests: v })} />
              <Setting label="Ages" value={`${t.age_min || 18}-${t.age_max || 65}`} shown={`${t.age_min || 18} to ${t.age_max || 65}`}
                onSave={(v) => { const m = v.match(/(\d{2})\D+(\d{2})/); if (m) setTarget({ age_min: Number(m[1]), age_max: Number(m[2]) }); }} />
              <Setting label="Headline" value={cr.headline} onSave={setCreative("headline")} />
              <Setting label="Text" value={cr.text} onSave={setCreative("text")} />
              <Setting label="Button" value={cr.cta} onSave={setCreative("cta")} />
              <div className="grid grid-cols-[9rem_1fr] gap-3 border-b border-line py-2.5 text-sm">
                <dt className="text-muted">Sends people to</dt>
                <dd className="px-2 text-strong">{cr.destination === "whatsapp" ? "Your WhatsApp" : cr.link ? <a href={cr.link} target="_blank" rel="noreferrer" className="text-brand hover:underline">Your page</a>
                  : <span className="text-muted">Your page, once you make one. <Link to="/app/websites" className="font-medium text-brand hover:underline">Make a page</Link></span>}</dd>
              </div>
              <div className="grid grid-cols-[9rem_1fr] gap-3 border-b border-line py-2.5 text-sm">
                <dt className="text-muted">Form asks for</dt>
                <dd className="px-2 text-strong">{(sel.lead_form?.fields || []).map((f) => FIELD_LABEL[f] || f).join(", ") || "Name, Phone"}</dd>
              </div>
              {cr.video_url && (
                <div className="grid grid-cols-[9rem_1fr] gap-3 border-b border-line py-2.5 text-sm">
                  <dt className="text-muted">Video</dt>
                  <dd className="px-2"><video src={cr.video_url} controls className="max-h-40 rounded-md bg-strong" /></dd>
                </div>
              )}
              {sel.external_id && (
                <p className="py-3 text-sm text-muted"><span className="tabular-nums text-strong">{rupees(sel.spend)}</span> spent · <span className="tabular-nums text-strong">{sel.clicks}</span> clicks · <span className="tabular-nums text-strong">{sel.impressions}</span> views</p>
              )}
            </dl>
          </div>
        )}
      </ModuleFrame>
      <CompareText open={!!comparing} onClose={() => setComparing(null)} title={comparing ? `v${comparing.v.number} and now` : ""}
        before={plain(comparing?.before)} after={plain(sel)} />
      <Modal open={launching} onClose={() => setLaunching(false)} title={`${sel?.status === "paused" ? "Resume" : "Launch"} on ${PLATFORMS[platform]}?`}>
        {sel && (
          <>
            <p className="text-sm text-ink">This starts spending up to <b className="tabular-nums text-strong">{rupees(sel.daily_budget)} a day</b> (about <span className="tabular-nums">{rupees(sel.daily_budget * 30)}</span> a month) from your {PLATFORMS[platform]} account. You can pause it any time.</p>
            {platform === "meta" && !integ?.meta?.ad_account_id && <p className="mt-3 text-sm text-warm">Choose which Meta ad account to use first, from ⋯ → Choose the ad account.</p>}
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="subtle" onClick={() => setLaunching(false)}>Not now</Button>
              <Button variant="accent" busy={acting} disabled={platform === "meta" && !integ?.meta?.ad_account_id} onClick={launch}>Spend {rupees(sel.daily_budget)} a day</Button>
            </div>
          </>
        )}
      </Modal>
      <Modal open={removing} onClose={() => setRemoving(false)} title="Delete this campaign?">
        <p className="text-sm text-ink">It is paused on {PLATFORMS[platform]} first, then removed from AIMVA.</p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="subtle" onClick={() => setRemoving(false)}>Keep it</Button>
          <Button variant="danger" busy={acting} onClick={() => act(async () => { await del(`/api/campaigns/${sel.id}`); setRemoving(false); setSelId(null); await reload(); setView(null); }, "Deleted.")}>Delete</Button>
        </div>
      </Modal>
      <Modal open={!!accounts} onClose={() => setAccounts(null)} title="Choose the Meta ad account">
        <ul className="divide-y divide-line">
          {(accounts || []).map((a) => (
            <li key={a.id}><button type="button" className="flex w-full items-center justify-between py-2.5 text-left text-sm hover:bg-surface-2" onClick={() => act(async () => {
              await patch("/api/integrations/meta/meta", { meta: { ad_account_id: a.id } }); setAccounts(null); reloadInteg();
            }, "Ad account chosen.")}><span className="text-strong">{a.name}</span><span className="text-xs text-muted">{a.id} · {a.currency}</span></button></li>
          ))}
          {accounts?.length === 0 && <li className="py-2 text-sm text-muted">No ad accounts on this Meta login.</li>}
        </ul>
      </Modal>
    </>
  );
}
