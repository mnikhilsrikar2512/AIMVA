// /start (design.md 3.1–3.3): the idea, at most two questions for what's missing, then the reveal.
// One question per screen. Nothing on screen says what was understood or how; the reveal shows the result.
// No entrance animation: the only motion is the progress line while real work runs.
import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check, Link2 } from "lucide-react";
import { toast } from "sonner";
import { Logo } from "../components/Logo";
import { Button, Field, cx } from "../components/ui";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "../components/shadcn/sheet";
import { get, patch, post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useAgentEvents, LiveProvider } from "../lib/live";
import { MODULE_LABEL, MODULE_ROUTES } from "../lib/projects";
import { UI_LANGS, readUiLang, saveUiLang, setupCopy } from "../lib/setupCopy";

const LANGS = [["te-IN", "Telugu"], ["hi-IN", "Hindi"], ["en", "English"], ["hi-Latn", "Hinglish"], ["ta-IN", "Tamil"], ["kn-IN", "Kannada"],
  ["ml-IN", "Malayalam"], ["mr-IN", "Marathi"], ["bn-IN", "Bengali"], ["gu-IN", "Gujarati"], ["pa-IN", "Punjabi"], ["od-IN", "Odia"], ["ur-IN", "Urdu"]];
const MAX_LANGS = 5;
const GAP_ORDER = ["customer_languages", "customer_area", "reply_owner", "ads_today"];
function Pill({ on, children, onClick, disabled }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick} disabled={disabled}
      className={cx("inline-flex h-9 items-center gap-1.5 rounded-full px-4 text-sm transition-colors disabled:opacity-40",
        on ? "bg-lavender font-medium text-brand ring-1 ring-brand" : "bg-surface text-ink ring-1 ring-line-strong hover:ring-strong/30")}>
      {on && <Check className="size-3.5" strokeWidth={2.5} />}{children}
    </button>
  );
}

/** One gap question. `value` is the answer so far; Enter or the arrow continues. */
function GapStep({ gap, value, onChange, t }) {
  if (gap === "customer_languages") {
    const picked = value || [];
    return (
      <div className="flex flex-wrap gap-2" role="group" aria-label="Languages">
        {LANGS.map(([code, name]) => {
          const on = picked.includes(code);
          return <Pill key={code} on={on} disabled={!on && picked.length >= MAX_LANGS}
            onClick={() => onChange(on ? picked.filter((c) => c !== code) : [...picked, code])}>{name}</Pill>;
        })}
      </div>
    );
  }
  if (gap === "customer_area") {
    return (
      <div className="space-y-3">
        <input className="input max-w-md" value={value || ""} onChange={(e) => onChange(e.target.value)} maxLength={200} autoFocus
          placeholder="Kukatpally, Hyderabad" aria-label="City or area" />
        <div className="flex flex-wrap gap-2">
          {["All of India", "Online only"].map((v) => <Pill key={v} on={value === v} onClick={() => onChange(value === v ? "" : v)}>{t.areas[v]}</Pill>)}
        </div>
      </div>
    );
  }
  const options = Object.entries(gap === "reply_owner" ? t.reply : t.ads);
  return (
    <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t[gap]}>
      {options.map(([v, l]) => <Pill key={v} on={value === v} onClick={() => onChange(v)}>{l}</Pill>)}
    </div>
  );
}

/** The first module's real progress: the Launch job's steps decide the width, and only the result finishes it. */
function useJob(jobId) {
  const [job, setJob] = useState(null);
  useAgentEvents((d) => { if (jobId && d.job?.id === jobId) setJob(d.job); });
  useEffect(() => {
    if (!jobId) return undefined;
    let stop = false;
    const tick = () => get(`/api/agents/jobs/${jobId}`).then((j) => { if (!stop) setJob(j); }).catch(() => {});
    tick();
    const t = setInterval(() => { if (!stop) tick(); }, 3000);
    return () => { stop = true; clearInterval(t); };
  }, [jobId]);
  const running = !job || job.status === "queued" || job.status === "running";
  return { job, running };
}

function ProgressLine({ steps = [], running }) {
  // Six steps is the Launch job's usual length; the line never reaches the end until the job is done.
  const done = steps.filter((s) => s.status !== "running").length;
  const pct = running ? Math.min(90, 8 + (done / 6) * 82) : 100;
  return (
    <span className="block h-0.5 w-32 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-label="Making it now" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <span className="block h-full bg-brand transition-[width] duration-500" style={{ width: `${pct}%` }} />
    </span>
  );
}

function EditDetails({ open, onClose, start, onSaved }) {
  const [f, setF] = useState({ name: "", area: "", langs: [] });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) setF({ name: start.profile.name || "", area: start.profile.area || start.profile.city || "", langs: start.profile.customer_languages || [] });
  }, [open, start]);
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (f.name.trim().length >= 2 && f.name.trim() !== start.profile.name) await patch(`/api/projects/${start.project_id}`, { name: f.name.trim() });
      await post("/api/onboarding/answers", { answers: { customer_area: f.area.trim(), ...(f.langs.length ? { customer_languages: f.langs } : {}) } });
      onSaved({ name: f.name.trim() || start.profile.name, area: f.area.trim(), customer_languages: f.langs });
      onClose();
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  return (
    <Sheet open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <SheetContent className="max-w-[400px]">
        <div className="border-b border-line px-5 py-4 pr-12">
          <SheetTitle>Business details</SheetTitle>
          <SheetDescription className="sr-only">Change your business name, area and customer languages.</SheetDescription>
        </div>
        <form onSubmit={save} className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <Field label="Business name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} maxLength={160} /></Field>
          <Field label="Where your customers are"><input className="input" value={f.area} onChange={(e) => setF({ ...f, area: e.target.value })} maxLength={200} placeholder="Kukatpally, Hyderabad" /></Field>
          <div>
            <span className="label">Languages your customers speak</span>
            <GapStep gap="customer_languages" value={f.langs} onChange={(langs) => setF({ ...f, langs })} />
          </div>
          <Button type="submit" busy={busy}>Save</Button>
        </form>
      </SheetContent>
    </Sheet>
  );
}

function Reveal({ start, setStart }) {
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const { job, running } = useJob(start.job_id);
  const first = start.modules[0];
  const failed = job?.status === "failed";
  const siteId = job?.result?.site_id;
  const where = [start.profile.area, start.profile.city].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i).join(", ");
  const title = [start.profile.name, where].filter(Boolean).join(", ") || "Your workspace";
  const openFirst = () => {
    if (first?.key === "page") navigate(siteId ? `/app/websites?site=${siteId}` : "/app/websites", { replace: true });
    else navigate(MODULE_ROUTES[first?.key] || "/app", { replace: true });
  };
  const state = (m, i) => {
    if (i === 0 && start.job_id) {
      if (failed) return <span className="text-sm text-danger">Didn't finish. Open it to try again.</span>;
      if (running) return <span className="flex items-center gap-3 text-sm text-muted">Making it now <ProgressLine steps={job?.steps} running /></span>;
      return <span className="text-sm text-brand">Ready</span>;
    }
    if (m.key === "campaigns" && start.modules.some((x) => x.key === "page")) return <span className="text-sm text-muted">After your page is live</span>;
    return <span className="text-sm text-muted">Ready when you are</span>;
  };
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <p className="text-sm text-muted">{title}</p>
        <button type="button" className="text-sm font-medium text-brand hover:underline" onClick={() => setEditing(true)}>Edit details</button>
      </div>
      <h1 className="serif-moment mt-6 text-[30px] leading-tight text-strong sm:text-[40px]">Your workspace</h1>
      <ul className="mt-8 border-t border-line">
        {start.modules.map((m, i) => (
          <li key={m.key} className="border-b border-line">
            <button type="button" onClick={() => (i === 0 ? openFirst() : navigate(MODULE_ROUTES[m.key] || "/app", { replace: true }))}
              className="flex w-full flex-col gap-1 py-4 text-left hover:bg-surface-2/50 sm:flex-row sm:items-center sm:gap-6">
              <span className="flex items-center gap-3 sm:w-44 sm:shrink-0">
                <span aria-hidden className={cx("size-2 rounded-full", i === 0 ? "bg-brand" : "ring-1 ring-line-strong")} />
                <span className="text-[15px] font-medium text-strong">{MODULE_LABEL[m.key] || m.key}</span>
              </span>
              <span className="min-w-0 flex-1 pl-5 text-sm text-ink sm:pl-0">{m.line}</span>
              <span className="pl-5 sm:shrink-0 sm:pl-0">{state(m, i)}</span>
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
        <p className="text-sm text-muted">Leads and Results are always in the menu.</p>
        <button type="button" className="text-sm font-medium text-brand hover:underline" onClick={() => { navigate("/app", { replace: true }); setTimeout(() => window.dispatchEvent(new CustomEvent("aimva:palette")), 300); }}>All tools</button>
      </div>
      <div className="mt-10 flex justify-end">
        <Button variant="accent" onClick={openFirst} disabled={first?.key === "page" && start.job_id && running}>
          {first?.key === "page" ? "Open my page" : `Open ${(MODULE_LABEL[first?.key] || "it").toLowerCase()}`}
        </Button>
      </div>
      <EditDetails open={editing} onClose={() => setEditing(false)} start={start}
        onSaved={(p) => setStart((s) => ({ ...s, profile: { ...s.profile, ...p } }))} />
    </div>
  );
}

function StartFlow() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const isNew = params.get("new") === "1";
  const [lang, setLang] = useState(readUiLang);
  const t = setupCopy(lang);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const [idea, setIdea] = useState("");
  const [link, setLink] = useState("");
  const [showLink, setShowLink] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [start, setStart] = useState(null);      // the /api/start reply
  const [gapIndex, setGapIndex] = useState(-1);  // -1: idea screen; 0..n-1: a gap; n: the reveal
  const [answers, setAnswers] = useState({});
  const [saving, setSaving] = useState(false);
  const field = useRef(null);
  useEffect(() => { document.title = "Start · AIMVA"; return () => { document.title = "AIMVA"; }; }, []);

  const gaps = start ? GAP_ORDER.filter((g) => start.gaps.includes(g)).slice(0, 2) : [];
  const total = 1 + (start ? gaps.length : 2);
  const step = gapIndex < 0 ? 1 : Math.min(gapIndex + 2, total);
  const revealing = start && gapIndex >= gaps.length;

  const submit = async (e) => {
    e?.preventDefault();
    if (!idea.trim() && !link.trim()) { field.current?.focus(); return; }
    setBusy(true);
    setError("");
    try {
      const d = await post("/api/start", { idea: idea.trim(), link: link.trim() });
      setStart(d);
      const g = GAP_ORDER.filter((x) => d.gaps.includes(x)).slice(0, 2);
      setAnswers(g.includes("customer_languages") ? { customer_languages: d.profile.customer_languages || [] } : {});
      setGapIndex(0);
      setUser({ ...user, industry: d.profile.industry || user.industry || "other" });  // set up: sign-ins now go to the app
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };
  const next = async (skip = false) => {
    const gap = gaps[gapIndex];
    const v = answers[gap];
    const has = Array.isArray(v) ? v.length > 0 : !!(v && String(v).trim());
    if (!skip && has) {
      setSaving(true);
      try {
        await post("/api/onboarding/answers", { answers: { [gap]: typeof v === "string" ? v.trim() : v } });
        if (gap === "customer_languages") setStart((s) => ({ ...s, profile: { ...s.profile, customer_languages: v } }));
        if (gap === "customer_area") setStart((s) => ({ ...s, profile: { ...s.profile, area: v.trim() } }));
      } catch (err) { toast.error(err.message); setSaving(false); return; }
      setSaving(false);
    }
    setGapIndex((i) => i + 1);
  };
  useEffect(() => {
    if (!start || revealing || gapIndex < 0) return undefined;
    const onKey = (e) => { if (e.key === "Enter" && !e.shiftKey && !(e.target instanceof HTMLTextAreaElement)) { e.preventDefault(); next(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className="min-h-dvh bg-bg">
      <header className="flex h-14 items-center justify-between px-4 sm:px-8">
        <Logo to="/app" />
        {!revealing && (
          <span className="flex items-center gap-3 text-sm text-muted">
            <select className="h-8 rounded-md bg-transparent px-1 text-sm text-ink hover:bg-surface-2 focus:bg-surface-2 focus:outline-none" aria-label={t.language}
              value={lang} onChange={(e) => { setLang(e.target.value); saveUiLang(e.target.value); }}>
              {UI_LANGS.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
            </select>
            <span>
              {step} {t.of} {total}
              {gapIndex < 0 && <> · <button type="button" className="font-medium text-brand hover:underline" onClick={() => navigate(isNew ? "/app/projects" : "/app", { replace: true })}>{isNew ? t.cancel : t.skip}</button></>}
            </span>
          </span>
        )}
      </header>
      <main className="mx-auto max-w-3xl px-4 pb-16 pt-[12vh] sm:px-8">
        {gapIndex < 0 && (
          <form onSubmit={submit}>
            <h1 className="serif-moment text-[30px] leading-tight text-strong sm:text-[40px]">{t.idea}</h1>
            <div className="mt-8 rounded-[10px] bg-surface ring-1 ring-line-strong focus-within:ring-2 focus-within:ring-brand/50">
              <textarea ref={field} className="block min-h-[120px] w-full resize-none rounded-t-[10px] bg-transparent px-4 py-3.5 text-base text-strong placeholder:text-muted focus:outline-none"
                value={idea} onChange={(e) => setIdea(e.target.value)} maxLength={1000} autoFocus disabled={busy} aria-label="Your idea"
                onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e); }}
                placeholder={t.ideaPlaceholder} />
              <div className="flex items-center gap-2 px-3 pb-3">
                {showLink ? (
                  <input className="input h-9 flex-1" value={link} onChange={(e) => setLink(e.target.value)} maxLength={500} disabled={busy} autoFocus
                    placeholder="yourwebsite.com or instagram.com/yourpage" aria-label="Website or Instagram link" inputMode="url" />
                ) : (
                  <button type="button" className="btn-subtle btn-sm" onClick={() => setShowLink(true)}><Link2 className="size-4" /> {t.addLink}</button>
                )}
                <Button type="submit" variant="accent" className="ml-auto w-10 px-0" disabled={busy || (!idea.trim() && !link.trim())} aria-label="Continue">
                  <ArrowRight className="size-4" />
                </Button>
              </div>
            </div>
            {busy ? (
              <div className="mt-3" role="status">
                <span className="block h-0.5 w-full overflow-hidden rounded-full bg-surface-2"><span className="block h-full w-1/3 animate-pulse bg-brand" /></span>
                <p className="mt-2 text-sm text-muted">{t.settingUp}</p>
              </div>
            ) : error ? (
              <p role="alert" className="mt-3 text-sm text-danger">{error}</p>
            ) : (
              <p className="mt-3 text-sm text-muted">{t.ideaHint}</p>
            )}
          </form>
        )}

        {start && !revealing && gapIndex >= 0 && (
          <div>
            <h1 className="serif-moment text-[30px] leading-tight text-strong sm:text-[40px]">{t[gaps[gapIndex]]}</h1>
            <div className="mt-8"><GapStep key={gaps[gapIndex]} gap={gaps[gapIndex]} value={answers[gaps[gapIndex]]} onChange={(v) => setAnswers((a) => ({ ...a, [gaps[gapIndex]]: v }))} t={t} /></div>
            <div className="mt-10 flex items-center gap-3">
              {gapIndex > 0 && <button type="button" className="btn-subtle" onClick={() => setGapIndex((i) => i - 1)}><ArrowLeft className="size-4" /> {t.back}</button>}
              <button type="button" className="btn-subtle ml-auto" onClick={() => next(true)}>{t.skip}</button>
              <Button busy={saving} onClick={() => next()}>{t.continue} <ArrowRight className="size-4" /></Button>
            </div>
          </div>
        )}

        {revealing && <Reveal start={start} setStart={setStart} />}
      </main>
    </div>
  );
}

export default function Start() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  // Accounts that are already set up skip /start (design.md 3, owner decision 2026-11-15), unless starting a new project.
  // Decided once on arrival: finishing the idea screen sets the account up, and that must not bounce the reveal away.
  const [skip] = useState(() => !!user?.industry && params.get("new") !== "1");
  if (skip) return <Navigate to="/app" replace />;
  return <LiveProvider><StartFlow /></LiveProvider>;
}
