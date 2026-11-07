import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, Globe2, Lightbulb, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button, Spinner, cx } from "./ui";
import { get, post } from "../lib/api";

const asList = (v) => (Array.isArray(v) ? v : (v || "").split("\n").map((x) => x.trim()).filter(Boolean));

/** Live review of a brief (debounced): score, the playbook for the industry and the questions that matter most. */
export function useBriefReview(brief) {
  const [review, setReview] = useState(null);
  const key = JSON.stringify({ ...brief, features: asList(brief.features) });
  useEffect(() => {
    const t = setTimeout(async () => {
      try { setReview(await post("/api/sites/review-brief", JSON.parse(key))); } catch { /* coach is optional */ }
    }, 450);
    return () => clearTimeout(t);
  }, [key]);
  return review;
}

const LEVEL = {
  thin: ["Thin brief", "The page will be generic. Answer a couple of questions below.", "bg-rose-400"],
  ok: ["Good brief", "One or two more answers will make it stronger.", "bg-amber-400"],
  ready: ["Great brief", "Enough real detail for a page you won't need to fix.", "bg-emerald-500"],
};
const INLINE = { offer: "e.g. Free first consultation", audience: "e.g. Working parents nearby", phone: "e.g. +91 98765 43210", address: "Area, city" };

function QuickAnswer({ m, onAnswer }) {
  const [v, setV] = useState("");
  const submit = () => { if (v.trim()) { onAnswer(m.field, v.trim()); setV(""); } };
  return (
    <div className="mt-1.5 flex gap-2">
      <input className="input h-9" value={v} onChange={(e) => setV(e.target.value)} placeholder={INLINE[m.field]} maxLength={m.field === "phone" ? 30 : 160}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }} aria-label={m.question} />
      <button type="button" className="btn-ghost btn-sm h-9" onClick={submit} disabled={!v.trim()}>Add</button>
    </div>
  );
}

export function BriefCoach({ review, brief, onAnswer, onGoTo, onApplyPlaybook }) {
  const [open, setOpen] = useState(true);
  if (!review) return null;
  const [label, text, bar] = LEVEL[review.level];
  const p = review.playbook;
  const applied = brief.cta === p.cta && JSON.stringify(brief.form_fields) === JSON.stringify(p.form_fields);
  return (
    <div className="rounded-2xl bg-surface-2/60 p-4">
      <button type="button" className="flex w-full items-center gap-3 text-left" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Lightbulb className="size-4 shrink-0 text-brand" />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2 text-sm font-semibold text-strong">{label} · {review.score}%</span>
          <span className="mt-1.5 block h-1.5 w-full overflow-hidden rounded-full bg-ink/[0.07]">
            <span className={cx("block h-full rounded-full transition-all duration-500", bar)} style={{ width: `${review.score}%` }} />
          </span>
        </span>
        <ChevronDown className={cx("size-4 text-muted transition", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-3 space-y-3 text-sm">
          <p className="text-xs text-muted">{text}</p>
          <div className="flex flex-wrap items-center gap-2 rounded-xl bg-surface px-3 py-2.5">
            <span className="text-xs text-muted"><b className="text-strong">{p.label} playbook:</b> “{p.cta}” button, form asks {p.form_fields.join(", ").replace(/_/g, " ")}.</span>
            {applied ? <span className="ml-auto text-xs font-semibold text-emerald-600">Applied</span>
              : <button type="button" className="btn-ghost btn-sm ml-auto" onClick={() => onApplyPlaybook(p)}>Use this structure</button>}
          </div>
          {review.missing.length > 0 && (
            <ul className="space-y-2.5">
              {review.missing.slice(0, 4).map((m) => (
                <li key={m.field}>
                  <p className="flex flex-wrap items-baseline gap-x-2">
                    <span className={cx("font-medium", m.importance === "high" ? "text-strong" : "text-ink")}>{m.question}</span>
                    <span className="text-xs text-faint">{m.why}</span>
                  </p>
                  {INLINE[m.field] ? <QuickAnswer m={m} onAnswer={onAnswer} />
                    : <button type="button" className="mt-1 text-xs font-semibold text-brand hover:underline" onClick={() => onGoTo(m)}>Add it →</button>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** Paste an existing website to pre-fill the brief with real facts. */
export function ImportBar({ onImported }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    if (!url.trim()) return;
    setBusy(true);
    try {
      const r = await post("/api/sites/import", { url: url.trim() });
      onImported(r.brief);
      toast.success(`Filled ${r.fields.length} details from your website. Check them before generating.`);
      setUrl("");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-lavender/50 p-3 sm:flex-row sm:items-center">
      <span className="flex items-center gap-2 text-sm font-medium text-strong"><Globe2 className="size-4 text-brand" /> Have a website?</span>
      <input className="input h-10 bg-surface sm:flex-1" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="yourbusiness.com — we'll pull your details"
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); go(); } }} maxLength={500} aria-label="Your website address" />
      <Button type="button" variant="ghost" size="sm" className="h-10" busy={busy} onClick={go}>Import</Button>
    </div>
  );
}

const STATUS = {
  ready: [ShieldCheck, "Ready to launch", "text-emerald-700 bg-emerald-50"],
  review: [AlertTriangle, "Worth a quick look before launch", "text-amber-800 bg-amber-50"],
  blocked: [XCircle, "Fix before you can publish", "text-rose-700 bg-rose-50"],
};
const ICON = { blocker: [XCircle, "text-rose-500"], warning: [AlertTriangle, "text-amber-500"], tip: [Lightbulb, "text-sky-500"] };

/** The automatic quality pass on a generated page: what passed, and the few things worth a human look. */
export function ReadinessPanel({ siteId, version, onFixed }) {
  const [audit, setAudit] = useState(null);
  const [open, setOpen] = useState(false);
  const first = useRef(true);
  useEffect(() => {
    let live = true;
    get(`/api/sites/${siteId}/audit`).then((a) => {
      if (!live) return;
      setAudit(a);
      if (first.current) { setOpen(a.readiness.status !== "ready"); first.current = false; }
    }).catch(() => {});
    return () => { live = false; };
  }, [siteId, version]);
  if (!audit) return <div className="mb-4 flex h-12 items-center gap-2 rounded-2xl bg-surface-2/60 px-4 text-sm text-muted"><Spinner className="size-4" /> Checking the page…</div>;
  const { readiness: r, checks } = audit;
  const [Icon, label, tone] = STATUS[r.status];
  const failed = checks.filter((c) => !c.ok).sort((a, b) => ["blocker", "warning", "tip"].indexOf(a.level) - ["blocker", "warning", "tip"].indexOf(b.level));
  const passed = checks.length - failed.length;
  const fixable = failed.filter((c) => c.autofix).length;
  const fixAll = async () => {
    try {
      const out = await post(`/api/sites/${siteId}/autofix`);
      setAudit({ checks: out.checks, readiness: out.readiness });
      onFixed?.(out.site);
      toast.success(out.fixed.length ? `Fixed ${out.fixed.length} thing${out.fixed.length === 1 ? "" : "s"}. Undo from Versions if you don't like it.` : "Nothing left to fix automatically.");
    } catch (e) {
      toast.error(e.message);
    }
  };
  return (
    <div className="mb-4 rounded-2xl bg-surface-2/60">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <span className={cx("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold", tone)}><Icon className="size-3.5" /> {label}</span>
        <span className="text-sm text-muted">{r.score}/100 · {passed} of {checks.length} checks passed</span>
        <ChevronDown className={cx("ml-auto size-4 text-muted transition", open && "rotate-180")} />
      </button>
      {open && fixable > 0 && (
        <div className="flex flex-wrap items-center gap-3 px-4 pb-3">
          <Button type="button" size="sm" onClick={fixAll}><Sparkles className="size-3.5" /> Fix {fixable} automatically</Button>
          <span className="text-xs text-muted">Saved as a new version. Your wording and brand colours stay as they are.</span>
        </div>
      )}
      {open && (
        <ul className="space-y-2 px-4 pb-4">
          {failed.length === 0 && <li className="flex items-center gap-2 text-sm text-ink"><CheckCircle2 className="size-4 text-emerald-500" /> Contact form, phone, mobile layout, SEO, no placeholders and no invented claims. Good to go.</li>}
          {failed.map((c) => {
            const [I, color] = ICON[c.level];
            return (
              <li key={c.key} className="flex gap-2.5 text-sm">
                <I className={cx("mt-0.5 size-4 shrink-0", color)} />
                <span><span className="font-medium text-strong">{c.detail || c.message}</span>{c.fix && <span className="block text-xs text-muted">{c.fix}</span>}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export const REASONS = [["wrong_facts", "Wrong facts"], ["off_brand", "Off-brand"], ["low_quality", "Low quality"], ["text_errors", "Text errors"],
  ["not_what_i_asked", "Not what I asked"], ["too_generic", "Too generic"]];

/** Thumbs up/down on a generated item; a thumbs-down asks why (it tunes the prompts and playbooks). */
export function Rate({ kind, id, initial, className }) {
  const [state, setState] = useState(initial || null);
  const [asking, setAsking] = useState(false);
  useEffect(() => { setState(initial || null); }, [initial]);
  const send = async (rating, reason = "") => {
    try {
      setState(await post("/api/feedback", { kind, id, rating, reason }));
      setAsking(rating < 0 && !reason);
      if (rating > 0 || reason) toast.success("Thanks, that helps AIMVA get it right first time.");
    } catch (e) {
      toast.error(e.message);
    }
  };
  return (
    <div className={cx("flex flex-wrap items-center gap-1", className)}>
      <button type="button" onClick={() => send(1)} aria-label="Good result" aria-pressed={state?.rating === 1}
        className={cx("grid size-8 place-items-center rounded-full transition", state?.rating === 1 ? "bg-emerald-50 text-emerald-600" : "text-faint hover:bg-ink/[0.05] hover:text-strong")}>
        <ThumbsUp className="size-3.5" />
      </button>
      <button type="button" onClick={() => send(-1)} aria-label="Needs work" aria-pressed={state?.rating === -1}
        className={cx("grid size-8 place-items-center rounded-full transition", state?.rating === -1 ? "bg-rose-50 text-rose-600" : "text-faint hover:bg-ink/[0.05] hover:text-strong")}>
        <ThumbsDown className="size-3.5" />
      </button>
      {asking && (
        <span className="flex basis-full flex-wrap gap-1 pt-1">
          {REASONS.map(([v, l]) => (
            <button key={v} type="button" onClick={() => send(-1, v)} className="rounded-full bg-surface-2 px-2.5 py-1 text-xs font-medium text-ink hover:bg-lavender">{l}</button>
          ))}
        </span>
      )}
    </div>
  );
}

/** "Improve prompt": rewrites a short idea into a detailed, brand-aware prompt the user can still edit (with undo). */
export function EnhanceButton({ prompt, kind = "image", useBrand, onEnhanced }) {
  const [busy, setBusy] = useState(false);
  const [previous, setPrevious] = useState(null);
  const go = async () => {
    setBusy(true);
    try {
      const r = await post("/api/content/enhance", { prompt, kind, use_brand: !!useBrand });
      setPrevious(prompt);
      onEnhanced(r);
      toast.success(r.source === "ai" ? "Prompt improved by your AI writer. Edit anything you like." : "Prompt improved. Edit anything you like.");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="inline-flex items-center gap-2">
      <button type="button" className="btn-ghost btn-sm" onClick={go} disabled={busy || prompt.trim().length < 3}>
        {busy ? <Spinner className="size-3.5" /> : <Sparkles className="size-3.5 text-brand" />} Improve prompt
      </button>
      {previous !== null && (
        <button type="button" className="text-xs font-medium text-muted hover:text-strong" onClick={() => { onEnhanced({ prompt: previous }); setPrevious(null); }}>Undo</button>
      )}
    </span>
  );
}
