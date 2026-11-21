import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowUpRight, CheckCircle2, ChevronDown, Globe2, Lightbulb, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button, Spinner, cx } from "./ui";
import { get, post } from "../lib/api";
import { useIsClient } from "../lib/auth";

const asList = (v) => (Array.isArray(v) ? v : (v || "").split("\n").map((x) => x.trim()).filter(Boolean));

/** Live review of a brief (debounced): score, the playbook for the industry and the questions that matter most. */
export function useBriefReview(brief) {
  const [review, setReview] = useState(null);
  const isClient = useIsClient();  // the brief coach is for people who can edit the page
  const key = JSON.stringify({ ...brief, features: asList(brief.features) });
  useEffect(() => {
    if (isClient) return undefined;
    const t = setTimeout(async () => {
      try { setReview(await post("/api/sites/review-brief", JSON.parse(key))); } catch { /* coach is optional */ }
    }, 450);
    return () => clearTimeout(t);
  }, [key, isClient]);
  return review;
}

const LEVEL = {
  thin: ["Thin brief", "The page will be generic. Answer a couple of questions below.", "bg-danger"],
  ok: ["Good brief", "One or two more answers will make it stronger.", "bg-warm"],
  ready: ["Great brief", "Enough real detail for a page you won't need to fix.", "bg-lavender0"],
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
            {applied ? <span className="ml-auto text-xs font-semibold text-brand">Applied</span>
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
  ready: [ShieldCheck, "Ready to launch", "text-brand bg-lavender"],
  review: [AlertTriangle, "Worth a quick look before launch", "text-warm bg-warm-soft"],
  blocked: [XCircle, "Fix before you can publish", "text-danger bg-danger/10"],
};
const ICON = { blocker: [XCircle, "text-danger"], warning: [AlertTriangle, "text-warm"], tip: [Lightbulb, "text-brand"] };

/** Six marks out of 10. A page passes at an average of 8 with nothing under 7. */
function ScoreParts({ score }) {
  return (
    <div className="@container px-4 pb-3">
      <div className="grid gap-x-6 gap-y-2.5 @md:grid-cols-2">
        {score.parts.map((p) => (
          <div key={p.key} className="min-w-0">
            <div className="flex items-baseline justify-between gap-2 text-xs">
              <span className="truncate text-muted">{p.label}</span>
              <span className={cx("font-semibold tabular-nums", p.score >= 8 ? "text-strong" : p.score >= 7 ? "text-warm" : "text-danger")}>{p.score}/10</span>
            </div>
            <div className="mt-1 h-1 overflow-hidden rounded-full bg-ink/[0.06]">
              <div className={cx("h-full rounded-full transition-[width] duration-300", p.score >= 8 ? "bg-brand" : p.score >= 7 ? "bg-warm" : "bg-danger")} style={{ width: `${p.score * 10}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** The automatic quality pass on a generated page: what passed, and the few things worth a human look. */
// Ready-to-send asks for the page editor's box. The ones for what this page is missing come first, so each tap moves the
// score; then a few that make most enquiry pages better. Nothing here asks the writer to invent reviews or numbers.
const FIX_PROMPTS = {
  offer_top: "Put my offer in the headline at the top",
  h1_length: "Make the main headline shorter, under 10 words",
  headline: "Rewrite the headline so it says what I offer and for whom",
  cta: "Add one clear button that says what happens next",
  cta_top: "Add the main button to the first screen, next to the headline",
  cta_twice: "Add the main button again lower down, after the benefits",
  phone: "Add a tap-to-call phone button at the top",
  contact: "Add a tap-to-call phone button at the top",
  name: "Show my business name clearly at the top",
  placeholders: "Replace any placeholder text with real details from my brief",
  claims: "Remove numbers and claims I never gave you",
  testimonials: "Remove the customer reviews I never gave you",
  risky: "Tone down promises that sound too good to be true",
  small_text: "Make the small text bigger and easier to read on phones",
};
const IDEAS = [
  [/how it works|step 1|3 steps|three steps/i, "Add a 3-step 'how it works' section"],
  [/faq|frequently asked|questions/i, "Add 4 short questions customers ask, with answers"],
  [/timings|opening hours|open (?:mon|daily|every)/i, "Add our timings and how to reach us"],
  [/wa\.me|whatsapp/i, "Add a WhatsApp chat button"],
  [null, "Keep a call-back button stuck to the bottom on phones"],
  [null, "Make the page shorter: keep only what helps someone enquire"],
];

function Suggestions({ failed, html, onSuggest }) {
  const fixes = [...new Set(failed.map((c) => FIX_PROMPTS[c.key]).filter(Boolean))];
  const ideas = IDEAS.filter(([has]) => !has || !has.test(html || "")).map(([, t]) => t);
  const list = [...fixes, ...ideas.filter((t) => !fixes.includes(t))].slice(0, 5);
  if (!list.length) return null;
  return (
    <div className="mt-5 px-1">
      <h3 className="text-sm font-semibold text-strong">Ideas to make it better</h3>
      <p className="mt-0.5 text-xs text-muted">Tap one to put it in the box below. Change it if you like, then press Enter.</p>
      <ul className="mt-3 space-y-1.5">
        {list.map((t, i) => (
          <li key={t}>
            <button type="button" onClick={() => onSuggest(t)}
              className="group flex w-full items-start gap-2.5 rounded-xl bg-surface-2/60 px-3 py-2.5 text-left text-sm text-ink transition hover:bg-lavender">
              <Sparkles className={cx("mt-0.5 size-4 shrink-0", i < fixes.length ? "text-warm" : "text-brand")} />
              <span className="min-w-0 flex-1">{t}{i < fixes.length && <span className="block text-xs text-muted">Raises your score</span>}</span>
              <ArrowUpRight className="mt-0.5 size-4 shrink-0 text-faint transition group-hover:text-strong" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ReadinessPanel({ siteId, version, onFixed, inPanel, html, onSuggest }) {
  const [audit, setAudit] = useState(null);
  const [open, setOpen] = useState(false);
  const first = useRef(true);
  useEffect(() => {
    let live = true;
    get(`/api/sites/${siteId}/audit`).then((a) => {
      if (!live) return;
      setAudit(a);
      if (first.current) { setOpen(inPanel || a.readiness.status !== "ready"); first.current = false; }
    }).catch(() => {});
    return () => { live = false; };
  }, [siteId, version]);
  if (!audit) return <div className="mb-4 flex h-12 items-center gap-2 rounded-2xl bg-surface-2/60 px-4 text-sm text-muted"><Spinner className="size-4" /> Checking the page…</div>;
  const { readiness: r, checks } = audit;
  const [Icon, label, tone] = STATUS[r.status];
  // The page score adds a few checks of its own (offer near the top, a button on the first screen, brand words).
  const extra = (audit.page_score?.todo || []).filter((t) => !checks.some((c) => c.key === t.key)).map((t) => ({ ...t, ok: false, fix: "" }));
  const failed = [...checks.filter((c) => !c.ok), ...extra].sort((a, b) => ["blocker", "warning", "tip"].indexOf(a.level) - ["blocker", "warning", "tip"].indexOf(b.level));
  const passed = checks.length - failed.length;
  const fixable = failed.filter((c) => c.autofix).length;
  const fixAll = async () => {
    try {
      const out = await post(`/api/sites/${siteId}/autofix`);
      setAudit({ checks: out.checks, readiness: out.readiness, page_score: out.page_score });
      onFixed?.(out.site);
      toast.success(out.fixed.length ? `Fixed ${out.fixed.length} thing${out.fixed.length === 1 ? "" : "s"}. Undo from Versions if you don't like it.` : "Nothing left to fix automatically.");
    } catch (e) {
      toast.error(e.message);
    }
  };
  return (
    <>
    <div className={cx("rounded-2xl bg-surface-2/60", !inPanel && "mb-4")}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <span className={cx("inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold", tone)}><Icon className="size-3.5" /> {label}</span>
        <span className="text-sm text-muted">{audit.page_score ? `Score ${audit.page_score.average}/10` : `${r.score}/100`} · {passed} of {checks.length} checks passed</span>
        <ChevronDown className={cx("ml-auto size-4 text-muted transition", open && "rotate-180")} />
      </button>
      {open && audit.page_score && <ScoreParts score={audit.page_score} />}
      {open && fixable > 0 && (
        <div className="flex flex-wrap items-center gap-3 px-4 pb-3">
          <Button type="button" size="sm" onClick={fixAll}><Sparkles className="size-3.5" /> Fix {fixable} automatically</Button>
          <span className="text-xs text-muted">Saved as a new version. Your wording and brand colours stay as they are.</span>
        </div>
      )}
      {open && (
        <ul className="space-y-2 px-4 pb-4">
          {failed.length === 0 && <li className="flex items-center gap-2 text-sm text-ink"><CheckCircle2 className="size-4 text-brand" /> Contact form, phone, mobile layout, SEO, no placeholders and no invented claims. Good to go.</li>}
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
    {onSuggest && <Suggestions failed={failed} html={html} onSuggest={onSuggest} />}
    </>
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
        className={cx("grid size-8 place-items-center rounded-full transition", state?.rating === 1 ? "bg-lavender text-brand" : "text-faint hover:bg-ink/[0.05] hover:text-strong")}>
        <ThumbsUp className="size-3.5" />
      </button>
      <button type="button" onClick={() => send(-1)} aria-label="Needs work" aria-pressed={state?.rating === -1}
        className={cx("grid size-8 place-items-center rounded-full transition", state?.rating === -1 ? "bg-danger/10 text-danger" : "text-faint hover:bg-ink/[0.05] hover:text-strong")}>
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
