import { useCallback, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Bookmark, Check, LayoutTemplate, Search, Sparkles, Trash2, Wand2, X } from "lucide-react";
import { toast } from "sonner";
import { Button, Chip, Field, Modal, Spinner, cx } from "./ui";
import { del, post } from "../lib/api";
import { useApi } from "../lib/hooks";
import { rise, stagger } from "./Motion";

const INDUSTRY = { real_estate: "Real estate", healthcare: "Healthcare", education: "Education", saas: "SaaS", retail: "Retail",
  restaurant: "Restaurant", services: "Services", other: "General" };
const SOURCE = { builtin: ["violet", "AIMVA"], platform: ["blue", "AIMVA pick"], mine: ["green", "Yours"], suggested: ["amber", "Suggested"] };
const clip = (s, n = 90) => (s && s.length > n ? `${s.slice(0, n - 1)}…` : s || "");

/** One line that tells templates apart at a glance, per module. */
export function summary(module, p) {
  switch (module) {
    case "image": return [clip(p.prompt), [p.style, p.size].filter(Boolean).join(" · ")];
    case "video": return [clip(p.prompt), [p.camera?.replace("_", " "), p.aspect_ratio].filter(Boolean).join(" · ")];
    case "website": return [`“${p.cta}” button${p.offer ? ` · ${p.offer}` : ""}`, [p.layout, p.look, p.theme].filter(Boolean).join(" · ")];
    case "ads": return [clip(p.creative?.headline || p.creative?.text), [p.platform !== "any" && p.platform, p.objective, p.daily_budget && `₹${p.daily_budget}/day`].filter(Boolean).join(" · ")];
    case "voice": return [clip(p.greeting), `${p.questions?.length || 0} questions`];
    case "whatsapp": return [clip(p.body, 120), ""];
    default: return ["", ""];
  }
}

export function useTemplates(module) {
  const { data, loading, reload, setData, error } = useApi(`/api/templates?module=${module}`, { templates: [] });
  return { templates: data?.templates || [], industry: data?.industry, loading, reload, setData, error };
}

/** Remembers which template was applied, and reports what was changed when the result is used. */
export function useTemplateTracker(module) {
  const applied = useRef(null);
  const apply = useCallback((t) => { applied.current = t; }, []);
  const track = useCallback((final) => {
    const t = applied.current;
    if (!t) return;
    applied.current = null;
    post("/api/templates/use", { ref: t.ref, module, applied: t.payload, final }).catch(() => {});
  }, [module]);
  return { apply, track, current: applied };
}

function TemplateCard({ t, module, onUse, onKeep, onDismiss, onDelete, compact }) {
  const [line, meta] = summary(module, t.payload);
  const [tone, label] = SOURCE[t.source];
  return (
    <motion.div variants={rise} layout className={cx("group flex flex-col rounded-2xl bg-surface p-4 ring-1 ring-line transition hover:ring-brand/40 hover:shadow-[var(--shadow-soft)]",
      compact && "w-64 shrink-0")}>
      <div className="flex items-start justify-between gap-2">
        <p className="font-semibold leading-snug text-strong">{t.name}</p>
        {t.recommended && t.source !== "suggested" ? <Chip tone="violet" className="shrink-0">For you</Chip> : <Chip tone={tone} className="shrink-0">{label}</Chip>}
      </div>
      {t.description && <p className="mt-1 text-xs text-muted">{t.description}</p>}
      {t.reason && <p className="mt-2 rounded-xl bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900"><Sparkles className="mr-1 inline size-3" />{t.reason}</p>}
      {!compact && <p className="mt-2 text-xs italic text-ink">{line}</p>}
      <div className="mt-2 flex flex-wrap gap-1">
        {meta && <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-muted">{meta}</span>}
        {t.industries.slice(0, 2).map((i) => <span key={i} className="rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-muted">{INDUSTRY[i] || i}</span>)}
      </div>
      <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-3">
        <Button type="button" size="sm" onClick={() => onUse(t)}><Wand2 className="size-3.5" /> Use</Button>
        {t.source === "suggested" && onKeep && <Button type="button" size="sm" variant="ghost" onClick={() => onKeep(t)}><Bookmark className="size-3.5" /> Keep</Button>}
        {t.source === "suggested" && onDismiss && <button type="button" className="grid size-8 place-items-center rounded-full text-faint hover:bg-ink/[0.05] hover:text-strong" onClick={() => onDismiss(t)} aria-label="Dismiss"><X className="size-3.5" /></button>}
        {t.source === "mine" && onDelete && <button type="button" className="ml-auto grid size-8 place-items-center rounded-full text-faint opacity-0 transition hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100" onClick={() => onDelete(t)} aria-label={`Delete ${t.name}`}><Trash2 className="size-3.5" /></button>}
        {t.uses > 0 && <span className="ml-auto text-xs text-faint">used {t.uses}×</span>}
      </div>
    </motion.div>
  );
}

const TABS = [["for", "For you"], ["all", "All"], ["mine", "Mine"], ["suggested", "Suggested"]];

export function TemplateGallery({ module, open, onClose, onApply, data }) {
  const { templates, reload, setData, error } = data;
  const [tab, setTab] = useState("for");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const counts = { mine: templates.filter((t) => t.source === "mine").length, suggested: templates.filter((t) => t.source === "suggested").length };
  const list = templates.filter((t) => (tab === "all" ? true : tab === "for" ? t.recommended || t.source === "suggested" || t.source === "mine" : t.source === tab))
    .filter((t) => !q || `${t.name} ${t.description} ${JSON.stringify(t.payload)}`.toLowerCase().includes(q.toLowerCase()));
  const remove = (t) => setData((d) => ({ ...d, templates: d.templates.filter((x) => x.ref !== t.ref) }));
  const keep = async (t) => { try { await post(`/api/templates/${t.id}/accept`); toast.success("Saved to your templates"); reload(); } catch (e) { toast.error(e.message); } };
  const dismiss = async (t) => { try { await post(`/api/templates/${t.id}/dismiss`); remove(t); } catch (e) { toast.error(e.message); } };
  const delMine = async (t) => { if (!confirm(`Delete “${t.name}”?`)) return; try { await del(`/api/templates/${t.id}`); remove(t); toast.success("Deleted"); } catch (e) { toast.error(e.message); } };
  const suggest = async () => {
    setBusy(true);
    try {
      const r = await post("/api/templates/suggest", { module });
      toast(r.message);
      await reload();
      if (r.new.length) setTab("suggested");
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Templates" wide="xl">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1">
          {TABS.map(([v, l]) => (
            <button type="button" key={v} onClick={() => setTab(v)} className={cx("relative rounded-full px-3 py-1.5 text-xs font-semibold transition-colors", tab === v ? "text-white" : "text-muted hover:text-strong")}>
              {tab === v && <motion.span layoutId={`tpl-tab-${module}`} className="absolute inset-0 rounded-full bg-strong" transition={{ type: "spring", stiffness: 420, damping: 34 }} />}
              <span className="relative">{l}{counts[v] ? ` ${counts[v]}` : ""}</span>
            </button>
          ))}
        </div>
        <label className="relative ml-auto min-w-[180px] flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <input className="input h-9 pl-9 text-sm" placeholder="Search templates" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <Button type="button" size="sm" variant="ghost" busy={busy} onClick={suggest}><Sparkles className="size-3.5" /> Suggest templates for me</Button>
      </div>
      {list.length === 0 ? (
        <div className="grid h-40 place-items-center text-center text-sm text-muted">
          {error && !templates.length ? <span>Templates didn't load. <button type="button" className="font-medium text-brand hover:underline" onClick={reload}>Try again</button></span> :
            tab === "suggested" ? "No suggestions yet. Click “Suggest templates for me”: AIMVA learns from what you use and change." :
            tab === "mine" ? "Save any form as a template with “Save as template”." : "No templates match."}
        </div>
      ) : (
        <motion.div variants={stagger} initial="hidden" animate="show" className="grid max-h-[60vh] grid-cols-[minmax(0,1fr)] gap-3 overflow-y-auto p-0.5 sm:grid-cols-2 lg:grid-cols-3">
          <AnimatePresence initial={false}>
            {list.map((t) => <TemplateCard key={t.ref} t={t} module={module} onUse={(x) => { onApply(x); onClose(); }} onKeep={keep} onDismiss={dismiss} onDelete={delMine} />)}
          </AnimatePresence>
        </motion.div>
      )}
      <p className="mt-4 text-xs text-faint">Picking a template fills the form. Everything stays editable, and the template itself never changes.</p>
    </Modal>
  );
}

/** "Start from a template" row shown above each module's form. */
export function TemplateStrip({ module, onApply, title = "Start from a template", className }) {
  const data = useTemplates(module);
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState(null);
  const top = useMemo(() => data.templates.slice(0, 8), [data.templates]);
  const suggested = data.templates.filter((t) => t.source === "suggested").length;
  const use = (t) => { setPicked(t.ref); onApply(t); toast.success(`“${t.name}” applied. Change anything you like.`); };
  return (
    <div className={cx("min-w-0", className)}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-faint"><LayoutTemplate className="size-3.5" /> {title}</p>
        <button type="button" className="text-xs font-semibold text-brand hover:underline" onClick={() => setOpen(true)}>
          Browse all{suggested ? ` · ${suggested} suggested` : ""}
        </button>
      </div>
      {data.loading ? <div className="flex h-16 items-center"><Spinner className="size-4 text-faint" /></div> : data.error && !data.templates.length ? (
        <p className="py-3 text-sm text-muted">Templates didn't load. <button type="button" className="font-medium text-brand hover:underline" onClick={data.reload}>Try again</button></p>
      ) : (
        <motion.div variants={stagger} initial="hidden" animate="show" className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1.5">
          {top.map((t) => {
            const [line] = summary(module, t.payload);
            return (
              <motion.button key={t.ref} variants={rise} type="button" onClick={() => use(t)} title={line}
                className={cx("relative flex w-48 shrink-0 flex-col items-start justify-start rounded-2xl p-3 text-left ring-1 transition",
                  picked === t.ref ? "bg-lavender ring-brand/60" : "bg-surface ring-line hover:ring-brand/40")}>
                {picked === t.ref && <Check className="absolute right-2.5 top-2.5 size-3.5 text-brand" />}
                <span className="block pr-4 text-sm font-semibold leading-snug text-strong">{t.name}</span>
                <span className="mt-0.5 line-clamp-2 block text-xs leading-snug text-muted">{t.reason || t.description}</span>
                {(t.recommended || t.source !== "builtin") && <span className={cx("mt-1.5 inline-block rounded-full px-1.5 py-0.5 text-xs font-semibold",
                  t.source === "suggested" ? "bg-amber-100 text-amber-800" : t.source === "mine" ? "bg-emerald-100 text-emerald-800" : "bg-violet-100 text-violet-700")}>
                  {t.source === "suggested" ? "Suggested" : t.source === "mine" ? "Yours" : "For you"}</span>}
              </motion.button>
            );
          })}
        </motion.div>
      )}
      <TemplateGallery module={module} open={open} onClose={() => setOpen(false)} onApply={use} data={data} />
    </div>
  );
}

/** Save the current form as a reusable template. */
export function SaveTemplateButton({ module, getPayload, className, label = "Save as template" }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", description: "" });
  const [busy, setBusy] = useState(false);
  const save = async (e) => {
    e.preventDefault();
    e.stopPropagation();  // this form can sit inside a page's form (websites, ads): don't submit that one too
    setBusy(true);
    try {
      await post("/api/templates", { module, ...f, payload: getPayload() });
      toast.success("Template saved. Find it under Templates → Mine.");
      setOpen(false);
      setF({ name: "", description: "" });
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  return (
    <>
      <Button type="button" size="sm" variant="subtle" className={className} onClick={() => setOpen(true)}><Bookmark className="size-3.5" /> {label}</Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Save as template">
        <form onSubmit={save} className="space-y-4">
          <Field label="Name"><input className="input" required minLength={2} maxLength={120} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoFocus placeholder="e.g. Weekend site visit" /></Field>
          <Field label="Description (optional)"><input className="input" maxLength={400} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <p className="text-xs text-faint">Saves the current settings. Your business name is kept as written; use {"{business}"} to fill it in automatically.</p>
          <div className="flex justify-end"><Button type="submit" busy={busy}>Save template</Button></div>
        </form>
      </Modal>
    </>
  );
}
