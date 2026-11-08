import { useEffect, useState } from "react";
import { Link, NavLink, useParams } from "react-router-dom";
import { Facebook, Linkedin, Pause, Play, Plus, RefreshCw, Search, Send, Sparkles, Trash2, Plug } from "lucide-react";
import { Button, Card, Chip, Empty, Field, Modal, Notice, PageHeader, Spinner, cx, ListSkeleton, IconButton } from "../../components/ui";
import { LoadError } from "../../components/LoadError";
import { del, get, patch, post } from "../../lib/api";
import { useAction, useApi } from "../../lib/hooks";
import { useAuth } from "../../lib/auth";
import AdPlacements from "../../components/AdPlacements";
import { ApprovalGate } from "../../components/Approval";
import { SaveTemplateButton, TemplateStrip, useTemplateTracker } from "../../components/Templates";
import { StoryLine, Outcome } from "../../components/Story";

const META = {
  meta: { title: "Meta Ads", sub: "Facebook & Instagram campaigns with instant lead forms.", icon: Facebook, tone: "blue", provider: "meta",
    objectives: [["leads", "Lead generation"], ["traffic", "Traffic"]] },
  google: { title: "Google Ads", sub: "Search and Performance Max campaigns with lead form assets.", icon: Search, tone: "green", provider: "google",
    objectives: [["leads", "Leads"], ["traffic", "Website traffic"]] },
  linkedin: { title: "LinkedIn Ads", sub: "B2B campaigns with Lead Gen Forms.", icon: Linkedin, tone: "cyan", provider: "linkedin",
    objectives: [["leads", "Lead generation"], ["traffic", "Website visits"]] },
};
const STATUS_TONE = { draft: "slate", active: "green", paused: "amber" };
const FORM_FIELDS = ["full_name", "email", "phone_number", "city", "company_name", "job_title"];

function CampaignForm({ platform, onCreated, preview }) {
  const cfg = META[platform];
  const [c, setC] = useState({
    name: "", objective: "leads", daily_budget: 20,
    creative: { headline: "", text: "", image_url: "", cta: "Learn more" },
    targeting: { locations: "", age_min: 18, age_max: 65, interests: "" },
    lead_form: { fields: ["full_name", "email", "phone_number"], privacy_url: "", form_id: "" },
  });
  const [product, setProduct] = useState("");
  const [busy, run] = useAction();
  const [copyBusy, runCopy] = useAction();
  const { data: images } = useApi("/api/content/assets?kind=image", []);
  const setIn = (sec, k) => (e) => setC((x) => ({ ...x, [sec]: { ...x[sec], [k]: e.target.value } }));
  const tpl = useTemplateTracker("ads");
  const applyTemplate = (t) => {
    tpl.apply(t);
    const p = t.payload;
    setC((x) => ({ ...x, name: x.name || t.name, objective: p.objective, daily_budget: p.daily_budget,
      creative: { ...x.creative, headline: p.creative.headline, text: p.creative.text, cta: p.creative.cta },
      targeting: { ...p.targeting, locations: x.targeting.locations || p.targeting.locations },
      lead_form: { ...x.lead_form, fields: p.lead_form.fields } }));
  };
  const templatePayload = () => ({
    platform, objective: c.objective, daily_budget: Number(c.daily_budget) || 0,
    creative: { headline: c.creative.headline, text: c.creative.text, cta: c.creative.cta || "Learn more" },
    targeting: { locations: c.targeting.locations, interests: c.targeting.interests, age_min: Number(c.targeting.age_min) || 18, age_max: Number(c.targeting.age_max) || 65 },
    lead_form: { fields: c.lead_form.fields },
  });

  const suggest = () => runCopy(async () => {
    const d = await post("/api/content/ad-copy", { product: product || c.name, platform, audience: c.targeting.interests });
    const v = d.variants[0];
    setC((x) => ({ ...x, creative: { ...x.creative, headline: v.headline, text: v.text } }));
  });

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_290px]">
    <form className="min-w-0 space-y-5" onSubmit={(e) => {
      e.preventDefault();
      run(async () => { const out = await post("/api/campaigns", { ...c, platform, daily_budget: Number(c.daily_budget) }); tpl.track(templatePayload()); onCreated(out); }, "Campaign saved as draft");
    }}>
      <TemplateStrip module="ads" onApply={applyTemplate} title="Start from a campaign template" />
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Campaign name" className="sm:col-span-2"><input className="input" value={c.name} onChange={(e) => setC({ ...c, name: e.target.value })} required minLength={2} /></Field>
        <Field label="Daily budget (₹)"><input className="input" type="number" min="0" value={c.daily_budget} onChange={(e) => setC({ ...c, daily_budget: e.target.value })} /></Field>
      </div>
      <Field label="Objective">
        <select className="input" value={c.objective} onChange={(e) => setC({ ...c, objective: e.target.value })}>
          {cfg.objectives.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </Field>

      <fieldset className="space-y-3 rounded-2xl bg-surface-2/60 p-4">
        <legend className="px-1 text-sm font-semibold text-strong">Creative</legend>
        <div className="flex gap-2">
          <input className="input" placeholder="What are you promoting? (for AI copy)" value={product} onChange={(e) => setProduct(e.target.value)} />
          <Button type="button" variant="ghost" busy={copyBusy} onClick={suggest}><Sparkles className="size-4" /> Write copy</Button>
        </div>
        <Field label="Headline"><input className="input" value={c.creative.headline} onChange={setIn("creative", "headline")} /></Field>
        <Field label="Primary text"><textarea className="input" rows={3} value={c.creative.text} onChange={setIn("creative", "text")} /></Field>
        <Field label="Image" hint="Pick a generated image or paste a URL">
          <input className="input" value={c.creative.image_url} onChange={setIn("creative", "image_url")} />
        </Field>
        {images.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {images.slice(0, 10).map((a) => (
              <button type="button" key={a.id} onClick={() => setC((x) => ({ ...x, creative: { ...x.creative, image_url: a.url } }))}
                className={`size-16 shrink-0 overflow-hidden rounded-lg border-2 ${c.creative.image_url === a.url ? "border-brand-2" : "border-transparent"}`}>
                <img src={a.url} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />
              </button>
            ))}
          </div>
        )}
      </fieldset>

      <fieldset className="grid gap-3 rounded-2xl bg-surface-2/60 p-4 sm:grid-cols-2">
        <legend className="px-1 text-sm font-semibold text-strong">Targeting</legend>
        <Field label="Locations"><input className="input" placeholder="Hyderabad, Bengaluru" value={c.targeting.locations} onChange={setIn("targeting", "locations")} /></Field>
        <Field label="Interests / job titles"><input className="input" value={c.targeting.interests} onChange={setIn("targeting", "interests")} /></Field>
        <Field label="Min age"><input className="input" type="number" value={c.targeting.age_min} onChange={setIn("targeting", "age_min")} /></Field>
        <Field label="Max age"><input className="input" type="number" value={c.targeting.age_max} onChange={setIn("targeting", "age_max")} /></Field>
      </fieldset>

      <fieldset className="space-y-3 rounded-2xl bg-surface-2/60 p-4">
        <legend className="px-1 text-sm font-semibold text-strong">Lead form</legend>
        <div className="flex flex-wrap gap-2">
          {FORM_FIELDS.map((f) => {
            const on = c.lead_form.fields.includes(f);
            return (
              <button type="button" key={f} onClick={() => setC((x) => ({ ...x, lead_form: { ...x.lead_form, fields: on ? x.lead_form.fields.filter((y) => y !== f) : [...x.lead_form.fields, f] } }))}
                className={`chip cursor-pointer ${on ? "border-brand/50 bg-brand/15 text-strong" : "border-line text-muted"}`}>{f.replace("_", " ")}</button>
            );
          })}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Privacy policy URL"><input className="input" value={c.lead_form.privacy_url} onChange={setIn("lead_form", "privacy_url")} /></Field>
          {platform === "meta" && <Field label="Existing form ID (to sync leads)"><input className="input" value={c.lead_form.form_id} onChange={setIn("lead_form", "form_id")} /></Field>}
        </div>
      </fieldset>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" busy={busy}>Save campaign</Button>
        <SaveTemplateButton module="ads" getPayload={templatePayload} />
      </div>
    </form>
    <div className="hidden lg:block">
      <div className="sticky top-0"><AdPlacements creative={c.creative} platform={platform} {...preview} /></div>
    </div>
    </div>
  );
}

export default function Ads() {
  const { platform } = useParams();
  const cfg = META[platform] || META.meta;
  const { data: campaigns, setData, loading, reload, error } = useApi(`/api/campaigns?platform=${platform}`, []);
  const { data: integrations, reload: reloadInteg } = useApi("/api/integrations", []);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState(null);
  const [accounts, setAccounts] = useState(null);
  const [busy, run] = useAction();
  const integ = integrations.find((i) => i.provider === cfg.provider);
  const { user } = useAuth();
  const { data: sites } = useApi("/api/sites", []);
  const live = sites.find((s) => s.published);
  const { data: kit } = useApi("/api/brand");
  const logo = kit?.logos?.find((l) => l.is_primary) || kit?.logos?.[0];
  const preview = {
    brand: kit?.name || user.company || user.name,
    logo: logo?.url,
    domain: live ? (live.custom_domain || new URL(live.deploy_url || live.url).host) : undefined,
    connected: new Set(integrations.filter((i) => i.connected).map((i) => i.provider)),
  };
  useEffect(() => { setSelected(null); }, [platform]);

  const replace = (c) => { setData((all) => all.map((x) => (x.id === c.id ? c : x))); setSelected(c); };

  return (
    <div>
      <PageHeader title="Campaigns" subtitle={cfg.sub}
        actions={<Button onClick={() => setCreating(true)}><Plus className="size-4" /> New campaign</Button>} />
      {/* One Campaigns page; the platforms are tabs, not three sidebar items. */}
      <nav aria-label="Platform" className="-mt-4 mb-6 flex gap-1 border-b border-line">
        {Object.entries(META).map(([k, m]) => (
          <NavLink key={k} to={`/app/ads/${k}`} className={({ isActive }) => cx("-mb-px flex h-9 items-center gap-1.5 border-b-2 px-3 text-sm font-medium transition",
            isActive ? "border-strong text-strong" : "border-transparent text-muted hover:text-strong")}>
            <m.icon className="size-4" /> {m.title.replace(" Ads", "")}
          </NavLink>
        ))}
      </nav>
      <StoryLine module="campaigns" className="mt-0 sm:mt-0" />

      {integ && !integ.connected && (
        <Notice tone="blue" icon={Plug} action={<Link to="/app/settings?tab=integrations" className="btn-ghost btn-sm">Connect account</Link>}>
          {integ.app_configured ? `Connect your ${integ.label} account to publish campaigns and sync results.`
            : `You can draft campaigns now. Publishing to ${integ.label} is being switched on for your account; we'll let you know when it's ready.`}
        </Notice>
      )}
      {integ?.connected && platform === "meta" && !integ.meta?.ad_account_id && (
        <Notice tone="amber" action={<Button size="sm" variant="ghost" onClick={() => run(async () => setAccounts(await get("/api/campaigns/meta/ad-accounts")))}>Choose ad account</Button>}>
          Pick which Meta ad account AIMVA should publish to.
        </Notice>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card className="min-w-0 p-0 sm:p-0">
          {loading ? <ListSkeleton /> : error && campaigns.length === 0 ? (
            <LoadError error={error} what="your campaigns" onRetry={reload} />
          ) : campaigns.length === 0 ? (
            <Empty icon={cfg.icon} title="Your campaigns will live here" text="Draft one with AI-written copy and a lead form. Nothing is spent until you publish." action={<Button onClick={() => setCreating(true)}><Plus className="size-4" /> New campaign</Button>} />
          ) : (
            <ul>
              {campaigns.map((c) => (
                <li key={c.id}>
                  <button onClick={() => setSelected(c)} className={`flex w-full items-center gap-4 border-b border-line px-5 py-4 text-left last:border-0 hover:bg-ink/[0.03] ${selected?.id === c.id ? "bg-ink/[0.04]" : ""}`}>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold text-strong">{c.name}</p>
                      <p className="text-xs text-muted">₹{Number(c.daily_budget).toLocaleString("en-IN")}/day · {c.objective}{c.external_id ? ` · ID ${c.external_id}` : ""}</p>
                      <Outcome id={c.id} className="sm:hidden" />
                    </div>
                    <div className="hidden text-right text-xs text-muted sm:block">
                      <p>₹{Number(c.spend || 0).toLocaleString("en-IN")} spent · {c.clicks} clicks</p><Outcome id={c.id} />
                    </div>
                    <Chip tone={STATUS_TONE[c.status]}>{c.status}</Chip>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-4">
          {selected ? (
            <Card className="space-y-4">
              <div className="flex items-center justify-between"><h2 className="font-semibold text-strong">{selected.name}</h2><Chip tone={STATUS_TONE[selected.status]}>{selected.status}</Chip></div>
              <AdPlacements creative={selected.creative} platform={platform} {...preview} />
              <div className="flex flex-wrap gap-2">
                {!selected.external_id && <ApprovalGate kind="campaign" refId={selected.id}><Button size="sm" busy={busy} onClick={() => run(async () => replace(await post(`/api/campaigns/${selected.id}/publish`)), "Published (paused) to Meta")}><Send className="size-3.5" /> Publish</Button></ApprovalGate>}
                {selected.external_id && <IconButton label="Sync results from the platform" busy={busy} onClick={() => run(async () => { const r = await post(`/api/campaigns/${selected.id}/sync`); replace(r); return r; }, "Synced")}><RefreshCw className="size-4" /></IconButton>}
                {selected.status !== "draft" && (
                  <Button size="sm" variant="ghost" onClick={() => run(async () => replace(await patch(`/api/campaigns/${selected.id}`, { status: selected.status === "active" ? "paused" : "active" })))}>
                    {selected.status === "active" ? <><Pause className="size-3.5" /> Pause</> : <><Play className="size-3.5" /> Activate</>}
                  </Button>
                )}
                <Button size="sm" variant="danger" onClick={() => confirm("Delete this campaign from AIMVA?") && run(async () => { await del(`/api/campaigns/${selected.id}`); setSelected(null); reload(); }, "Deleted")}><Trash2 className="size-3.5" /></Button>
              </div>
            </Card>
          ) : (
            <Card><p className="text-sm text-muted">Select a campaign to preview the ad and publish it.</p></Card>
          )}
        </div>
      </div>

      <Modal open={creating} onClose={() => setCreating(false)} title={`New ${cfg.title} campaign`} wide="xl">
        <CampaignForm platform={platform} preview={preview} onCreated={(c) => { setData((all) => [c, ...all]); setSelected(c); setCreating(false); }} />
      </Modal>
      <Modal open={!!accounts} onClose={() => setAccounts(null)} title="Choose Meta ad account">
        <ul className="space-y-2">
          {(accounts || []).map((a) => (
            <li key={a.id}><button className="btn-ghost w-full justify-between" onClick={() => run(async () => {
              await patch("/api/integrations/meta/meta", { meta: { ad_account_id: a.id } });
              setAccounts(null); reloadInteg();
            }, "Ad account selected")}>{a.name}<span className="text-xs text-faint">{a.id} · {a.currency}</span></button></li>
          ))}
          {accounts?.length === 0 && <p className="text-sm text-muted">No ad accounts found on this Meta login.</p>}
        </ul>
      </Modal>
    </div>
  );
}
