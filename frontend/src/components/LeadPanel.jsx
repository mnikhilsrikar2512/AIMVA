import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { rise, stagger } from "./Motion";
import { Link } from "react-router-dom";
import {
  AudioLines, CalendarClock, Check, Copy, FileText, Flag, IndianRupee, Mail, Megaphone, MessageCircle,
  Phone, PhoneCall, Send, StickyNote, UserPlus, X,
} from "lucide-react";
import { toast } from "sonner";
import { Button, Chip, Spinner, cx } from "./ui";
import { get, patch, post } from "../lib/api";
import { parseServerDate, timeAgo } from "../lib/hooks";
import { useLeadEvents } from "../lib/live";
import { FollowUps } from "./Agents";

const STAGES = ["new", "contacted", "qualified", "won", "lost"];
const STAGE_STYLE = {
  new: "border-sky-500/40 bg-sky-500/15 text-sky-700",
  contacted: "border-violet-500/40 bg-violet-500/15 text-violet-700",
  qualified: "border-amber-500/40 bg-amber-500/15 text-amber-700",
  won: "border-emerald-500/40 bg-emerald-500/15 text-emerald-700",
  lost: "border-rose-500/40 bg-rose-500/15 text-rose-700",
};
const SOURCE_TONE = { website: "pink", meta: "blue", google: "green", linkedin: "cyan", whatsapp: "green", voice: "violet", manual: "slate" };
const KIND = {
  created: { icon: UserPlus, color: "text-slate-600 bg-slate-500/15" },
  form: { icon: FileText, color: "text-pink-600 bg-pink-500/15" },
  ad: { icon: Megaphone, color: "text-sky-600 bg-sky-500/15" },
  whatsapp: { icon: MessageCircle, color: "text-emerald-600 bg-emerald-500/15" },
  call: { icon: AudioLines, color: "text-violet-600 bg-violet-500/15" },
  stage: { icon: Flag, color: "text-amber-600 bg-amber-500/15" },
  value: { icon: IndianRupee, color: "text-amber-600 bg-amber-500/15" },
  note: { icon: StickyNote, color: "text-slate-600 bg-slate-500/15" },
};
const FILTERS = [
  { value: "all", label: "All" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "call", label: "Calls" },
  { value: "form", label: "Forms & ads" },
  { value: "note", label: "Notes" },
];
const QUICK_MESSAGES = [
  { label: "Schedule visit", icon: CalendarClock, text: (n) => `Hi ${n}! Thanks for your interest. Would you like to schedule a visit? Reply with a day and time that suits you.` },
  { label: "Follow up", text: (n) => `Hi ${n}, just following up on your enquiry. Do you have any questions I can help with?` },
  { label: "Share pricing", text: (n) => `Hi ${n}, happy to share pricing options that fit your budget. When is a good time to talk?` },
];

function CopyButton({ value }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className="btn-subtle btn-sm h-7 px-2"
      aria-label="Copy"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setDone(true);
          setTimeout(() => setDone(false), 1200);
        } catch {
          toast.error("Couldn't copy");
        }
      }}
    >
      {done ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
    </button>
  );
}

function dayLabel(iso) {
  const d = parseServerDate(iso);
  const today = new Date();
  const yest = new Date(Date.now() - 86400000);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yest.toDateString()) return "Yesterday";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function TimelineItem({ item }) {
  const [open, setOpen] = useState(false);
  const k = KIND[item.kind] || KIND.note;
  const inbound = item.kind === "whatsapp" && item.meta.direction === "in";
  const transcript = item.meta?.transcript || [];
  return (
    <motion.li variants={rise} className="relative flex gap-3 pb-5 last:pb-0">
      <span className="absolute left-[15px] top-8 bottom-0 w-px bg-line" aria-hidden />
      <span className={cx("relative grid size-8 shrink-0 place-items-center rounded-full", k.color)}><k.icon className="size-4" /></span>
      <div className="min-w-0 flex-1 pt-1">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-sm font-medium text-strong">{item.title}</p>
          <span className="shrink-0 text-xs text-faint" title={parseServerDate(item.at).toLocaleString()}>{timeAgo(item.at)}</span>
        </div>
        {item.kind === "call" && (
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Chip tone={item.meta.sentiment > 0.2 ? "green" : item.meta.sentiment < -0.2 ? "rose" : "amber"}>
              Sentiment {item.meta.sentiment > 0 ? "+" : ""}{item.meta.sentiment}
            </Chip>
            <Chip>{item.meta.turns} turns</Chip>
          </div>
        )}
        {item.body && (
          <p className={cx(
            "mt-1.5 whitespace-pre-wrap rounded-xl px-3 py-2 text-sm",
            item.kind === "whatsapp" ? (inbound ? "bg-surface-2 text-ink" : "bg-emerald-50 text-emerald-900") : "bg-ink/[0.03] text-muted"
          )}>{item.body}</p>
        )}
        {transcript.length > 0 && (
          <>
            <button className="mt-1.5 text-xs font-medium text-brand-2 hover:underline" onClick={() => setOpen((o) => !o)}>
              {open ? "Hide transcript" : "Show transcript"}
            </button>
            {open && (
              <div className="mt-2 space-y-1 rounded-2xl bg-surface-2/60 p-3 text-xs">
                {transcript.map((t, i) => (
                  <p key={i}><b className={t.role === "agent" ? "text-cyan-600" : "text-violet-600"}>{t.role === "agent" ? "Agent" : "Lead"}:</b> <span className="text-ink">{t.text}</span></p>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </motion.li>
  );
}

export default function LeadPanel({ leadId, onClose, onChanged }) {
  const [lead, setLead] = useState(null);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [composer, setComposer] = useState(null); // "whatsapp" | "note" | null
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");
  const panelRef = useRef(null);
  useLeadEvents((d) => { if (d.lead.id === leadId) load(); });

  const load = async () => {
    try {
      setLead(await get(`/api/leads/${leadId}`));
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    setLead(null);
    setComposer(null);
    setFilter("all");
    load();
    const t = setInterval(load, 15000); // pick up new WhatsApp replies / call results
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leadId]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const act = async (key, fn, success) => {
    setBusy(key);
    try {
      const out = await fn();
      if (out?.timeline) setLead(out);
      else await load();
      onChanged?.();
      if (success) toast.success(success);
      return true;
    } catch (e) {
      toast.error(e.message);
      return false;
    } finally {
      setBusy("");
    }
  };

  const firstName = (lead?.name || "there").split(" ")[0];
  const items = (lead?.timeline || []).filter((i) =>
    filter === "all" ? true : filter === "form" ? ["form", "ad", "created"].includes(i.kind) : filter === "note" ? ["note", "stage", "value"].includes(i.kind) : i.kind === filter
  );
  const groups = items.reduce((acc, i) => {
    const d = dayLabel(i.at);
    (acc[d] ||= []).push(i);
    return acc;
  }, {});

  const submitComposer = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    const ok = composer === "whatsapp"
      ? await act("send", () => post("/api/whatsapp/send", { to: lead.phone, body: text, name: lead.name }), "WhatsApp message sent")
      : await act("note", () => post(`/api/leads/${lead.id}/notes`, { body: text }), "Note added");
    if (ok) { setText(""); setComposer(null); }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Lead details">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px] animate-[fade_150ms_ease-out]" onClick={onClose} />
      <motion.aside
        ref={panelRef}
        tabIndex={-1}
        initial={{ x: "100%" }} animate={{ x: 0 }} transition={{ type: "spring", stiffness: 340, damping: 34 }}
        className="relative flex h-full w-full max-w-[520px] flex-col border-l border-line bg-surface shadow-2xl outline-none"
      >
        {!lead ? (
          <div className="grid flex-1 place-items-center text-muted">{error ? <p className="text-sm">{error}</p> : <Spinner className="size-6" />}</div>
        ) : (
          <>
            {/* Header */}
            <div className="border-b border-line p-5">
              <div className="flex items-start gap-3">
                <div className="grid size-12 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-brand to-brand-2 text-lg font-bold text-white">
                  {(lead.name || lead.email || "#")[0].toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-lg font-bold text-strong">{lead.name || lead.email || lead.phone}</h2>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                    <Chip tone={SOURCE_TONE[lead.source] || "slate"}>{lead.source}</Chip>
                    <span>Added {timeAgo(lead.created_at)}</span>
                  </div>
                </div>
                <div className="text-right">
                  <p className={cx("font-display text-2xl font-bold", lead.score >= 70 ? "text-emerald-600" : lead.score >= 40 ? "text-amber-600" : "text-slate-600")}>{lead.score}</p>
                  <p className="text-xs text-faint">lead score</p>
                </div>
                <button className="btn-subtle btn-sm -mr-2 -mt-1" onClick={onClose} aria-label="Close"><X className="size-4" /></button>
              </div>

              {/* Contact */}
              <div className="mt-4 space-y-1.5 text-sm">
                {lead.phone && (
                  <div className="flex items-center gap-2"><Phone className="size-4 text-faint" /><a href={`tel:${lead.phone}`} className="flex-1 text-ink hover:text-strong">{lead.phone}</a><CopyButton value={lead.phone} /></div>
                )}
                {lead.email && (
                  <div className="flex items-center gap-2"><Mail className="size-4 text-faint" /><a href={`mailto:${lead.email}`} className="flex-1 truncate text-ink hover:text-strong">{lead.email}</a><CopyButton value={lead.email} /></div>
                )}
              </div>

              {/* Quick actions */}
              <div className="mt-4 grid grid-cols-3 gap-2">
                <Button variant="ghost" size="sm" className="h-10" disabled={!lead.phone} busy={busy === "call"}
                  title={lead.phone ? "Have your AI voice agent call this lead" : "No phone number"}
                  onClick={() => act("call", () => post(`/api/leads/${lead.id}/call`, {}), "AI agent is calling…")}>
                  <PhoneCall className="size-4" /> AI call
                </Button>
                <Button variant={composer === "whatsapp" ? "primary" : "ghost"} size="sm" className="h-10" disabled={!lead.phone}
                  onClick={() => { setComposer(composer === "whatsapp" ? null : "whatsapp"); setText(""); }}>
                  <MessageCircle className="size-4" /> WhatsApp
                </Button>
                <Button variant={composer === "note" ? "primary" : "ghost"} size="sm" className="h-10"
                  onClick={() => { setComposer(composer === "note" ? null : "note"); setText(""); }}>
                  <StickyNote className="size-4" /> Note
                </Button>
              </div>
              {!lead.phone && <p className="mt-2 text-xs text-faint">Add a phone number to call or WhatsApp this lead.</p>}
              <div className="mt-3"><FollowUps key={lead.id} leadId={lead.id} /></div>

              {composer && (
                <form onSubmit={submitComposer} className="mt-3 space-y-2">
                  {composer === "whatsapp" && (
                    <div className="flex flex-wrap gap-1.5">
                      {QUICK_MESSAGES.map((q) => (
                        <button type="button" key={q.label} onClick={() => setText(q.text(firstName))}
                          className="chip cursor-pointer border-line text-muted hover:text-ink">{q.label}</button>
                      ))}
                    </div>
                  )}
                  <textarea className="input" rows={3} autoFocus value={text} onChange={(e) => setText(e.target.value)}
                    placeholder={composer === "whatsapp" ? `Message ${firstName} on WhatsApp…` : "Add a private note…"}
                    onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submitComposer(e); }} />
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-faint">⌘/Ctrl + Enter to send</span>
                    <Button type="submit" size="sm" busy={busy === "send" || busy === "note"} disabled={!text.trim()}>
                      <Send className="size-3.5" /> {composer === "whatsapp" ? "Send" : "Save note"}
                    </Button>
                  </div>
                </form>
              )}

              {/* Stage + value */}
              <div className="mt-4">
                <p className="label">Stage</p>
                <div className="flex flex-wrap gap-1.5">
                  {STAGES.map((s) => (
                    <button key={s} disabled={busy === "stage"}
                      onClick={() => s !== lead.stage && act("stage", () => patch(`/api/leads/${lead.id}`, { stage: s }), `Moved to ${s}`)}
                      className={cx("chip cursor-pointer px-3 py-1 capitalize transition", s === lead.stage ? STAGE_STYLE[s] : "border-line text-muted hover:border-line-strong hover:text-ink")}>
                      {s === lead.stage && <Check className="size-3" />}{s}
                    </button>
                  ))}
                </div>
              </div>
              <label className="mt-3 flex items-center gap-2 text-sm text-muted">
                Deal value
                <input type="number" min="0" className="input h-8 w-36 text-xs" defaultValue={lead.value || ""} placeholder="0" key={lead.value}
                  onBlur={(e) => {
                    const v = Number(e.target.value) || 0;
                    if (v !== lead.value) act("value", () => patch(`/api/leads/${lead.id}`, { value: v }), "Value updated");
                  }} />
              </label>
            </div>

            {/* Timeline */}
            <div className="flex items-center gap-1.5 overflow-x-auto border-b border-line px-5 py-3">
              {FILTERS.map((f) => (
                <button key={f.value} onClick={() => setFilter(f.value)}
                  className={cx("whitespace-nowrap rounded-lg px-2.5 py-1 text-xs font-medium transition", filter === f.value ? "bg-ink/[0.06] text-strong" : "text-muted hover:text-ink")}>
                  {f.label}
                </button>
              ))}
            </div>
            <div className="flex-1 overflow-y-auto p-5">
              {items.length === 0 ? (
                <p className="py-10 text-center text-sm text-muted">Nothing here yet.</p>
              ) : Object.entries(groups).map(([day, list]) => (
                <section key={day} className="mb-6 last:mb-0">
                  <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-faint">{day}</p>
                  <motion.ol variants={stagger} initial="hidden" animate="show">{list.map((i) => <TimelineItem key={i.id} item={i} />)}</motion.ol>
                </section>
              ))}
            </div>
            <div className="border-t border-line px-5 py-3 text-xs text-faint">
              Need a full chat? <Link to="/app/whatsapp" className="text-brand-2 hover:underline">Open WhatsApp inbox</Link>
            </div>
          </>
        )}
      </motion.aside>
    </div>
  );
}
