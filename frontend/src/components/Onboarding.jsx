import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight, Briefcase, Copy, ImageUp, Loader2, Building2, CalendarCheck, Check, GraduationCap, Headphones, HeartPulse,
  Megaphone, PartyPopper, Rocket, ShoppingBag, Sparkles, Store, Wrench, X,
} from "lucide-react";
import { toast } from "sonner";
import { Button, Card, Field, IconButton, Modal, cx } from "./ui";
import { api, get, post, put } from "../lib/api";
import { useAuth } from "../lib/auth";
import { signupHint } from "../lib/signupHint";

const INDUSTRY_ICONS = {
  real_estate: Building2, healthcare: HeartPulse, education: GraduationCap, saas: Briefcase,
  retail: ShoppingBag, services: Wrench, other: Store,
};
const GOALS = [
  { value: "more_leads", label: "Get more leads", icon: Megaphone },
  { value: "book_visits", label: "Book visits & appointments", icon: CalendarCheck },
  { value: "sell_online", label: "Sell online", icon: ShoppingBag },
  { value: "support", label: "Answer customers faster", icon: Headphones },
];

function Tile({ active, icon: Icon, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cx(
        "flex items-center gap-3 rounded-2xl p-3 text-left text-sm font-medium transition cursor-pointer",
        active ? "bg-lavender text-strong ring-2 ring-brand/60" : "bg-surface-2/70 text-ink hover:bg-surface-2"
      )}
    >
      <Icon className={cx("size-5 shrink-0", active ? "text-brand-2" : "text-faint")} />
      {label}
    </button>
  );
}

export function WelcomeWizard({ open, status, onClose, onSaved }) {
  const { user, setUser } = useAuth();
  const [step, setStep] = useState(0);
  const [company, setCompany] = useState(user.company || "");
  const [industry, setIndustry] = useState(status?.industry || "");
  const [goal, setGoal] = useState(status?.goal || "more_leads");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      const s = await post("/api/onboarding/profile", { company, industry, goal });
      setUser({ ...user, company, industry, goal });
      toast.success("All set! We wrote a voice agent script for your business.");
      onSaved(s);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={step === 0 ? `Welcome to AIMVA, ${user.name.split(" ")[0]}` : "What matters most right now?"}>
      <div className="mb-5 flex gap-1.5" aria-hidden>
        {[0, 1].map((i) => <div key={i} className={cx("h-1 flex-1 rounded-full", i <= step ? "bg-brand-2" : "bg-ink/[0.06]")} />)}
      </div>
      {step === 0 ? (
        <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); if (company.trim() && industry) setStep(1); }}>
          <p className="text-sm text-muted">Two quick questions so we can pre-fill your landing pages, voice agent and ad copy.</p>
          <Field label="Business name">
            <input className="input" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Skyline Homes" required autoFocus />
          </Field>
          <div>
            <span className="label">Industry</span>
            <div className="grid gap-2 sm:grid-cols-2">
              {(status?.industries || []).map((i) => (
                <Tile key={i.value} active={industry === i.value} icon={INDUSTRY_ICONS[i.value] || Store} label={i.label} onClick={() => setIndustry(i.value)} />
              ))}
            </div>
          </div>
          <div className="flex items-center justify-between pt-1">
            <button type="button" className="btn-subtle" onClick={onClose}>Skip for now</button>
            <Button type="submit" disabled={!company.trim() || !industry}>Continue <ArrowRight className="size-4" /></Button>
          </div>
        </form>
      ) : (
        <div className="space-y-5">
          <div className="grid gap-2">
            {GOALS.map((g) => <Tile key={g.value} active={goal === g.value} icon={g.icon} label={g.label} onClick={() => setGoal(g.value)} />)}
          </div>
          <div className="flex items-center justify-between pt-1">
            <button type="button" className="btn-subtle" onClick={() => setStep(0)}>Back</button>
            <Button busy={busy} onClick={save}><Sparkles className="size-4" /> Set up my workspace</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

export function SetupChecklist({ status, onOpenWizard, onDismiss }) {
  const pct = Math.round((status.completed / status.total) * 100);
  const next = status.steps.find((s) => !s.done);

  if (status.all_done) {
    return (
      <Card className="relative mb-6 flex flex-col items-start gap-4 overflow-hidden sm:flex-row sm:items-center">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_left,rgba(52,211,153,0.15),transparent_60%)]" />
        <div className="relative grid size-12 shrink-0 place-items-center rounded-2xl bg-emerald-500/15 text-emerald-600"><PartyPopper className="size-6" /></div>
        <div className="relative flex-1">
          <p className="font-semibold text-strong">You're all set up</p>
          <p className="text-sm text-muted">Every module is ready. Leads from your page, calls and WhatsApp will flow into one place.</p>
        </div>
        <Button variant="ghost" className="relative" onClick={onDismiss}>Hide</Button>
      </Card>
    );
  }

  return (
    <Card className="mb-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-4">
          <ProgressRing pct={pct} />
          <div>
            <h2 className="font-semibold text-strong">Get set up</h2>
            <p className="text-sm text-muted">{status.completed} of {status.total} done · about {Math.max(1, (status.total - status.completed) * 2)} min left</p>
          </div>
        </div>
        <button className="btn-subtle btn-sm" onClick={onDismiss} aria-label="Hide setup checklist"><X className="size-4" /> Hide</button>
      </div>

      <ol className="mt-5 space-y-1">
        {status.steps.map((s, i) => {
          if (s.done) return null;
          const isNext = s === next;
          const action = s.key === "profile"
            ? <Button size="sm" variant={isNext ? "primary" : "ghost"} onClick={onOpenWizard}>Start</Button>
            : s.to && <Link to={s.to} className={cx(isNext ? "btn-primary" : "btn-ghost", "btn-sm")}>{isNext ? "Start" : "Open"}</Link>;
          return (
            <li
              key={s.key}
              className={cx(
                "flex items-center gap-3 rounded-2xl px-3 py-2.5 transition",
                isNext ? "bg-lavender/70" : "hover:bg-ink/[0.03]"
              )}
            >
              <span className={cx(
                "grid size-7 shrink-0 place-items-center rounded-full text-xs font-bold",
                s.done ? "bg-emerald-500/20 text-emerald-600" : isNext ? "bg-brand-2/20 text-brand-2" : "bg-ink/[0.04] text-faint"
              )}>
                {s.done ? <Check className="size-4" /> : i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className={cx("text-sm font-semibold", s.done ? "text-muted line-through decoration-white/20" : "text-strong")}>{s.title}</p>
                {!s.done && <p className="truncate text-xs text-muted">{s.desc}</p>}
              </div>
              {!s.done && action}
            </li>
          );
        })}
      </ol>
      {status.completed > 0 && (
        <p className="mt-3 flex items-center gap-1.5 px-3 text-xs text-muted">
          <Check className="size-3.5 text-emerald-500" />
          {status.steps.filter((s) => s.done).map((s) => s.title).join(" · ")}
        </p>
      )}
    </Card>
  );
}

function ProgressRing({ pct }) {
  const r = 20;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative size-14 shrink-0" role="img" aria-label={`${pct}% complete`}>
      <svg viewBox="0 0 48 48" className="size-14 -rotate-90">
        <circle cx="24" cy="24" r={r} fill="none" stroke="rgba(148,163,184,0.15)" strokeWidth="4" />
        <circle cx="24" cy="24" r={r} fill="none" stroke="url(#ring)" strokeWidth="4" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)} style={{ transition: "stroke-dashoffset 600ms ease" }} />
        <defs>
          <linearGradient id="ring" x1="0" x2="1"><stop offset="0" stopColor="#7c6cff" /><stop offset="1" stopColor="#22d3ee" /></linearGradient>
        </defs>
      </svg>
      <span className="absolute inset-0 grid place-items-center text-xs font-bold text-strong">{pct}%</span>
    </div>
  );
}

export function SetupPill({ status }) {
  if (!status || status.dismissed || status.all_done) return null;
  return (
    <Link to="/app" className="mx-3 mb-2 flex items-center gap-2.5 rounded-full bg-lavender px-3.5 py-2.5 text-sm transition hover:bg-brand/15">
      <Rocket className="size-4 text-brand-2" />
      <span className="flex-1 font-medium text-strong">Setup guide</span>
      <span className="text-xs font-semibold text-brand-2">{status.completed}/{status.total}</span>
    </Link>
  );
}

/* ---- The path to the first lead (design.md 4.2): inline on Home, one step open at a time, no pop-ups. ---------- */
const SKIP_KEY = "aimva_path_skipped";
const readSkipped = () => { try { return JSON.parse(localStorage.getItem(SKIP_KEY) || "[]"); } catch { return []; } };

function PathStep({ n, title, done, open, summary, children, onOpen }) {
  return (
    <li className="border-b border-line">
      <button type="button" onClick={onOpen} aria-expanded={open} disabled={open}
        className="flex w-full items-center gap-3 py-3.5 text-left disabled:cursor-default">
        <span className={cx("grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold transition",
          done ? "bg-strong text-white" : open ? "bg-warm-soft text-warm ring-1 ring-warm/30" : "bg-surface-2 text-muted")}>
          {done ? <Check className="size-3.5" strokeWidth={3} /> : n}
        </span>
        <span className={cx("flex-1 text-[15px]", done ? "text-muted" : "font-medium text-strong")}>{title}</span>
        {done && summary && <span className="hidden truncate text-xs text-muted sm:block">{summary}</span>}
      </button>
      {open && <div className="pb-6 pl-9 animate-[rise_.35s_cubic-bezier(.22,1,.36,1)]">{children}</div>}
    </li>
  );
}

export function ProfileForm({ status, onSaved, submitLabel = "Save and continue", intro = "Three answers, and every page, script and ad starts already written for you.", autoFocus = true, nameLabel = "Business name", namePlaceholder = "Skyline Homes", secondary = null }) {
  const { user, setUser } = useAuth();
  const [company, setCompany] = useState(user.workspace?.name || user.company || "")  // a client workspace starts from the client's name;
  const [industry, setIndustry] = useState(status?.industry || (user.workspace ? "" : signupHint().industry) || "");
  const [goal, setGoal] = useState(status?.goal || "more_leads");
  const [busy, setBusy] = useState(false);
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const s = await post("/api/onboarding/profile", { company: company.trim(), industry, goal });
      setUser(user.workspace ? { ...user, workspace: { ...user.workspace, name: company.trim() } } : { ...user, company: company.trim(), industry, goal });
      toast.success("Saved. Your call assistant already has a script for your business.", { id: "profile-saved" });
      onSaved(s);
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  const chip = (on) => cx("h-8 rounded-full px-3 text-sm transition", on ? "bg-strong text-white" : "bg-surface-2 text-ink hover:bg-line-strong/40");
  return (
    <form onSubmit={save} className="max-w-xl space-y-5">
      {intro && <p className="text-sm text-muted">{intro}</p>}
      <Field label={nameLabel}><input className="input" value={company} onChange={(e) => setCompany(e.target.value)} placeholder={namePlaceholder} required autoFocus={autoFocus} maxLength={160} /></Field>
      <div>
        <span className="label">What kind of business?</span>
        <div className="flex flex-wrap gap-1.5">
          {(status?.industries || []).map((i) => { const I = INDUSTRY_ICONS[i.value] || Store; return (
            <button key={i.value} type="button" aria-pressed={industry === i.value} onClick={() => setIndustry(i.value)} className={cx(chip(industry === i.value), "inline-flex items-center gap-1.5")}><I className="size-3.5" />{i.label}</button>
          ); })}
        </div>
      </div>
      <div>
        <span className="label">What matters most right now?</span>
        <div className="flex flex-wrap gap-1.5">
          {GOALS.map((g) => <button key={g.value} type="button" aria-pressed={goal === g.value} onClick={() => setGoal(g.value)} className={chip(goal === g.value)}>{g.label}</button>)}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" busy={busy} disabled={!company.trim() || !industry}>{submitLabel} <ArrowRight className="size-4" /></Button>
        {secondary}
      </div>
    </form>
  );
}

function ShareStep({ sites }) {
  const live = sites.find((s) => s.published);
  const url = live ? (live.custom_domain ? `https://${live.custom_domain}` : live.deploy_url || live.url) : null;
  const copy = async () => { try { await navigator.clipboard.writeText(url); toast.success("Link copied."); } catch { toast.error("Couldn't copy. Select the link and copy it."); } };
  return (
    <div className="max-w-xl space-y-4">
      <p className="text-sm text-muted">Send the link to a few people who might buy, or post it on your WhatsApp status. The first person who fills the form shows up here straight away.</p>
      {url ? (
        <>
          <div className="flex items-center gap-2 rounded-lg bg-surface-2 py-1 pl-3 pr-1">
            <span className="min-w-0 flex-1 truncate font-mono text-sm text-strong">{url.replace(/^https?:\/\//, "")}</span>
            <IconButton label="Copy link" onClick={copy}><Copy className="size-4" /></IconButton>
          </div>
          <div className="flex flex-wrap gap-2">
            <a className="btn-primary" href={`https://wa.me/?text=${encodeURIComponent(url)}`} target="_blank" rel="noreferrer">Share on WhatsApp</a>
            <a className="btn-ghost" href={url} target="_blank" rel="noreferrer">Send yourself a test lead</a>
          </div>
        </>
      ) : <Link to="/app/websites" className="btn-primary">Publish your page first</Link>}
      <p className="flex items-center gap-2 text-xs text-muted"><span className="relative flex size-2"><span className="absolute inline-flex size-full animate-ping rounded-full bg-warm/60" /><span className="relative inline-flex size-2 rounded-full bg-warm" /></span>Listening for your first lead…</p>
    </div>
  );
}

export function FirstLeadPath({ status, sites, onStatus, launch, website }) {
  const [skipped, setSkipped] = useState(readSkipped);
  const [chosen, setChosen] = useState(null);
  const [showLaunch, setShowLaunch] = useState(false);
  const d = Object.fromEntries(status.steps.map((s) => [s.key, s.done]));
  const anySite = (sites || []).length > 0;
  const steps = [
    { key: "profile", title: "Tell us about your business", done: d.profile, summary: status.template?.label },
    { key: "page", title: "Make your page and put it online", done: d.publish, summary: "Live" },
    { key: "voice", title: "Try your call assistant", done: d.voice || skipped.includes("voice"), summary: d.voice ? "Tested" : "Skipped" },
    { key: "lead", title: "Get your first lead", done: d.lead },
  ];
  const current = steps.find((s) => !s.done)?.key;
  const openKey = chosen && !steps.find((s) => s.key === chosen)?.done ? chosen : current;
  const doneCount = steps.filter((s) => s.done).length;
  const skip = (k) => { const v = [...new Set([...skipped, k])]; setSkipped(v); try { localStorage.setItem(SKIP_KEY, JSON.stringify(v)); } catch { /* storage blocked */ } setChosen(null); };

  return (
    <section aria-labelledby="path-h" className="max-w-3xl">
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <h2 id="path-h" className="text-sm font-semibold text-strong">Your path to the first lead</h2>
        <span className="text-xs tabular-nums text-muted">{doneCount} of {steps.length}</span>
      </div>
      <div className="mb-2 h-0.5 overflow-hidden rounded-full bg-surface-2"><div className="h-full bg-strong transition-[width] duration-700" style={{ width: `${(doneCount / steps.length) * 100}%` }} /></div>
      <ol>
        {steps.map((s, i) => (
          <PathStep key={s.key} n={i + 1} title={s.title} done={s.done} open={openKey === s.key} summary={s.summary} onOpen={() => setChosen(s.key)}>
            {s.key === "profile" && <ProfileForm status={status} onSaved={(st) => { onStatus(st); setChosen(null); }} />}
            {s.key === "page" && (
              showLaunch ? launch : (
                <div className="max-w-xl space-y-4">
                  <p className="text-sm text-muted">{anySite ? "Your page is ready. Publish it and it gets a link you can share." : "A landing page with a lead form is the fastest way to a first lead. About a minute, already written for your business."}</p>
                  <div className="flex flex-wrap gap-2">
                    <Link to="/app/websites" className="btn-primary">{anySite ? "Open and publish" : "Make my page"}</Link>
                    {!anySite && <button type="button" className="btn-ghost" onClick={() => setShowLaunch(true)}><Sparkles className="size-4" /> {website ? `Let AIMVA do it from ${website.replace(/^https?:\/\//, "").replace(/\/$/, "")}` : "Let AIMVA do it from my website"}</button>}
                  </div>
                </div>
              )
            )}
            {s.key === "voice" && (
              <div className="max-w-xl space-y-4">
                <p className="text-sm text-muted">Your assistant calls every new lead back within a minute, in their language. Hear it once in your browser, no phone needed.</p>
                <div className="flex flex-wrap gap-2">
                  <Link to="/app/voice" className="btn-primary">Have a practice call</Link>
                  <button type="button" className="btn-subtle" onClick={() => skip("voice")}>Skip for now</button>
                </div>
              </div>
            )}
            {s.key === "lead" && <ShareStep sites={sites || []} />}
          </PathStep>
        ))}
      </ol>
    </section>
  );
}

/* ---- Brand basics, asked once at sign-up so every picture, page and ad starts on-brand. Feeds the Brand kit. -- */
const VOICES = [["friendly", "Friendly"], ["professional", "Professional"], ["bold", "Bold"], ["playful", "Playful"], ["luxury", "Premium"]];
const DEFAULT_COLORS = ["#1e1913", "#a34d22", "#f7f4ee"];

export function BrandBasicsForm({ company, onSaved, onSkip }) {
  const [kit, setKit] = useState(null);
  const [logo, setLogo] = useState(null);
  const [colors, setColors] = useState(DEFAULT_COLORS);
  const [voice, setVoice] = useState("friendly");
  const [tagline, setTagline] = useState("");
  const [audience, setAudience] = useState("");
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    get("/api/brand").then((k) => {
      setKit(k);
      if (k.colors?.length) setColors(k.colors.slice(0, 3));
      if (k.voice) setVoice(k.voice);
      setTagline(k.tagline || ""); setAudience(k.audience || "");
      if (k.logos?.[0]) setLogo(k.logos[0]);
    }).catch(() => setKit({}));
  }, []);

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file); form.append("kind", "logo");
      const r = await api("/api/brand/assets", { method: "POST", form });
      setLogo(r.asset);
      if (r.suggested_colors?.length) { setColors(r.suggested_colors.slice(0, 3)); toast.success("Colours picked from your logo. Change any you like."); }
    } catch (e) { toast.error(e.message); } finally { setUploading(false); }
  };
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const k = kit || {};
      await put("/api/brand", { name: k.name || company || "", tagline: tagline.trim(), colors, voice, voice_notes: k.voice_notes || "",
        style: k.style || [], audience: audience.trim(), avoid: k.avoid || "" });
      toast.success("Brand saved. New pictures, pages and ads will use it.", { id: "brand-saved" });
      onSaved?.();
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  const chip = (on) => cx("h-8 rounded-full px-3 text-sm transition", on ? "bg-strong text-white" : "bg-surface-2 text-ink hover:bg-line-strong/40");
  if (!kit) return <div className="h-40 max-w-xl animate-pulse rounded-lg bg-surface-2" />;
  return (
    <form onSubmit={save} className="max-w-xl space-y-6">
      <div>
        <span className="label">Logo <span className="font-normal text-faint">(optional)</span></span>
        <label className={cx("flex cursor-pointer items-center gap-4 rounded-xl border border-dashed border-line-strong p-3 transition hover:bg-surface-2/60", uploading && "pointer-events-none opacity-70")}>
          <span className="grid size-14 shrink-0 place-items-center overflow-hidden rounded-lg bg-surface-2">
            {uploading ? <Loader2 className="size-5 animate-spin text-muted" /> : logo ? <img src={logo.url} alt="" className="size-full object-contain" /> : <ImageUp className="size-5 text-muted" />}
          </span>
          <span className="text-sm"><span className="font-medium text-strong">{logo ? "Change logo" : "Upload your logo"}</span><span className="block text-xs text-muted">PNG, JPG or SVG. We'll pick your colours from it.</span></span>
          <input type="file" accept="image/*" className="sr-only" onChange={(e) => upload(e.target.files?.[0])} />
        </label>
      </div>
      <div>
        <span className="label">Brand colours</span>
        <div className="flex items-center gap-2">
          {colors.map((c, i) => (
            <label key={i} className="relative size-10 cursor-pointer overflow-hidden rounded-lg ring-1 ring-line-strong" style={{ background: c }} title={c}>
              <input type="color" value={c} aria-label={`Colour ${i + 1}`} className="absolute inset-0 cursor-pointer opacity-0"
                onChange={(e) => setColors(colors.map((x, j) => (j === i ? e.target.value : x)))} />
            </label>
          ))}
          <span className="ml-1 text-xs text-muted">Click a colour to change it.</span>
        </div>
      </div>
      <div>
        <span className="label">How should you sound?</span>
        <div className="flex flex-wrap gap-1.5">{VOICES.map(([v, l]) => <button key={v} type="button" aria-pressed={voice === v} onClick={() => setVoice(v)} className={chip(voice === v)}>{l}</button>)}</div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Who do you sell to?"><input className="input" value={audience} onChange={(e) => setAudience(e.target.value)} maxLength={300} placeholder="Young families in Hyderabad" /></Field>
        <Field label="Tagline (optional)"><input className="input" value={tagline} onChange={(e) => setTagline(e.target.value)} maxLength={200} placeholder="Homes that grow with you" /></Field>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" busy={busy}>Save my brand <ArrowRight className="size-4" /></Button>
        {onSkip && <button type="button" className="btn-subtle" onClick={onSkip}>Do this later</button>}
      </div>
    </form>
  );
}
