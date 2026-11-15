import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { rise, stagger } from "./Motion";
import { Link } from "react-router-dom";
import {
  AudioLines, CalendarClock, Check, ChevronDown, ChevronUp, Copy, FileText, Flag, IndianRupee, Languages, Mail, Megaphone,
  MessageCircle, Phone, PhoneCall, RefreshCw, Send, StickyNote, UserPlus, X,
} from "lucide-react";
import { toast } from "sonner";
import { Button, Chip, Spinner, cx } from "./ui";
import { del, get, patch, post } from "../lib/api";
import { parseServerDate, timeAgo } from "../lib/hooks";
import { useLeadEvents } from "../lib/live";
import { useIsClient } from "../lib/auth";
import { FollowUps } from "./Agents";

const STAGES = ["new", "contacted", "qualified", "won", "lost"];
const STAGE_STYLE = {
  new: "border-brand bg-lavender0/15 text-brand",
  contacted: "border-brand/40 bg-lavender0/15 text-brand",
  qualified: "border-warm/40 bg-warm-soft0/15 text-warm",
  won: "border-brand bg-lavender0/15 text-brand",
  lost: "border-danger/40 bg-danger/100/15 text-danger",
};
const SOURCE_TONE = { website: "pink", meta: "blue", google: "green", linkedin: "cyan", whatsapp: "green", voice: "violet", manual: "slate" };
const KIND = {
  created: { icon: UserPlus, color: "text-muted bg-surface-2/15" },
  form: { icon: FileText, color: "text-brand bg-lavender0/15" },
  ad: { icon: Megaphone, color: "text-brand bg-lavender0/15" },
  whatsapp: { icon: MessageCircle, color: "text-brand bg-lavender0/15" },
  call: { icon: AudioLines, color: "text-brand bg-lavender0/15" },
  stage: { icon: Flag, color: "text-warm bg-warm-soft0/15" },
  value: { icon: IndianRupee, color: "text-warm bg-warm-soft0/15" },
  note: { icon: StickyNote, color: "text-muted bg-surface-2/15" },
};
const FILTERS = [
  { value: "all", label: "All" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "call", label: "Calls" },
  { value: "form", label: "Forms & ads" },
  { value: "note", label: "Notes" },
];
// Drafts come from the server in the lead's own language; these only pick what the message is for.
const INTENTS = [
  { value: "auto", label: "Reply" },
  { value: "visit", label: "Ask for a visit", icon: CalendarClock },
  { value: "pricing", label: "Share pricing" },
  { value: "follow_up", label: "Follow up" },
];
const LANGUAGES = [
  ["en", "English"], ["hi-IN", "Hindi"], ["hi-Latn", "Hinglish"], ["bn-IN", "Bengali"], ["ta-IN", "Tamil"], ["te-IN", "Telugu"],
  ["gu-IN", "Gujarati"], ["kn-IN", "Kannada"], ["ml-IN", "Malayalam"], ["mr-IN", "Marathi"], ["pa-IN", "Punjabi"], ["od-IN", "Odia"], ["ur-IN", "Urdu"],
];
const typing = (el) => el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));

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
      {done ? <Check className="size-3.5 text-brand" /> : <Copy className="size-3.5" />}
    </button>
  );
}

function waitedText(iso) {
  const t = timeAgo(iso);
  return t === "just now" ? "Waiting, just now" : `Waiting ${t.replace(" ago", "")}`;
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
            item.kind === "whatsapp" ? (inbound ? "bg-surface-2 text-ink" : "bg-lavender text-brand") : "bg-ink/[0.03] text-muted"
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
                  <p key={i}><b className={t.role === "agent" ? "text-brand" : "text-brand"}>{t.role === "agent" ? "Agent" : "Lead"}:</b> <span className="text-ink">{t.text}</span></p>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </motion.li>
  );
}

export default function LeadPanel({ leadId, onClose, onChanged, onDelete, startReply = false, ids = [], onNavigate }) {
  const [lead, setLead] = useState(null);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [composer, setComposer] = useState(null); // "whatsapp" | "note" | null
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");
  const [draft, setDraft] = useState(null);  // {text, language_name, intent, needs_template, template, note}
  const [intent, setIntent] = useState("auto");
  const isClient = useIsClient();  // view-only: no calls, messages, notes or edits
  const pos = ids.indexOf(leadId);
  const go = (step) => {
    const id = ids[pos + step];
    if (id && onNavigate) onNavigate(id, composer === "whatsapp");
  };

  const fetchDraft = async (want = "auto") => {
    setIntent(want);
    setBusy("draft");
    try {
      const d = await post(`/api/leads/${leadId}/reply-draft`, { intent: want });
      setDraft(d);
      setText(d.needs_template ? "" : d.text);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy("");
    }
  };
  const openWhatsApp = () => { setComposer("whatsapp"); setText(""); setDraft(null); fetchDraft("auto"); };
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
    setDraft(null);
    setFilter("all");
    load();
    if (startReply && !isClient) openWhatsApp();
    const t = setInterval(load, 15000); // pick up new WhatsApp replies / call results
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leadId]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") return onClose();
      if (typing(document.activeElement) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "j") { e.preventDefault(); go(1); }
      if (e.key === "k") { e.preventDefault(); go(-1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  useEffect(() => { if (!typing(document.activeElement)) panelRef.current?.focus(); }, [leadId]);

  const act = async (key, fn, success) => {
    setBusy(key);
    try {
      const out = await fn();
      if (out?.timeline) setLead(out);
      else await load();
      onChanged?.();
      if (success) toast.success(typeof success === "function" ? success(out) : success);
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

  const nextHint = ids[pos + 1] ? " Press J for the next lead." : "";
  // Without a connected business number (or outside the 24-hour window) the message goes from the owner's own WhatsApp.
  const ownAppFirst = composer === "whatsapp" && !!draft && (draft.needs_template || !draft.connected);
  const submitComposer = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    if (ownAppFirst) return sendFromOwnApp();
    const ok = composer === "whatsapp"
      ? await act("send", () => post(`/api/leads/${lead.id}/reply`, { text, intent }), `Sent.${nextHint}`)
      : await act("note", () => post(`/api/leads/${lead.id}/notes`, { body: text }), "Note added");
    if (ok) { setText(""); setComposer(null); setDraft(null); }
  };
  // Opens the business's own WhatsApp with the draft filled in. Opened synchronously from the click so browsers
  // don't block it; AIMVA then records it on the lead (it can't see the message leave the phone).
  const sendFromOwnApp = async () => {
    const number = draft?.wa_number;
    if (!number || !text.trim()) return;
    window.open(`https://wa.me/${number}?text=${encodeURIComponent(text.trim())}`, "_blank", "noopener");
    const ok = await act("own", () => post(`/api/leads/${lead.id}/reply`, { text, intent, own_app: true }), `Opened in your WhatsApp and noted here.${nextHint}`);
    if (ok) { setText(""); setComposer(null); setDraft(null); }
  };
  const sendTemplate = async () => {
    const ok = await act("send", () => post(`/api/leads/${lead.id}/reply`, { template: true, intent }), `Approved template sent.${nextHint}`);
    if (ok) { setComposer(null); setDraft(null); }
  };
  const changeLanguage = async (code) => {
    const ok = await act("lang", () => patch(`/api/leads/${lead.id}`, { language: code }));
    if (ok && composer === "whatsapp") fetchDraft(intent);
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
                <div className="grid size-12 shrink-0 place-items-center rounded-full bg-surface-2 text-lg font-semibold text-strong ring-1 ring-line">
                  {(lead.name || lead.email || "#")[0].toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-lg font-bold text-strong">{lead.name || lead.email || lead.phone}</h2>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                    <Chip tone={SOURCE_TONE[lead.source] || "slate"}>{lead.source}</Chip>
                    {lead.opted_out && <Chip tone="rose">Opted out</Chip>}
                    {lead.needs_reply ? <span className="font-semibold text-warm">{waitedText(lead.waiting_since)}</span> : <span>Added {timeAgo(lead.created_at)}</span>}
                    {isClient ? (lead.language_name && <span className="inline-flex items-center gap-1"><Languages className="size-3.5 text-faint" aria-hidden />{lead.language_name}</span>) : <label className="inline-flex items-center gap-1" title="The language replies are drafted in">
                      <Languages className="size-3.5 text-faint" aria-hidden />
                      <select aria-label="Language this lead writes in" className="cursor-pointer bg-transparent text-xs text-muted hover:text-ink"
                        value={lead.language || "en"} disabled={busy === "lang"} onChange={(e) => changeLanguage(e.target.value)}>
                        {LANGUAGES.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
                      </select>
                    </label>}
                  </div>
                </div>
                <div className="text-right">
                  <p className={cx("font-display text-2xl font-bold", lead.score >= 70 ? "text-brand" : lead.score >= 40 ? "text-warm" : "text-muted")}>{lead.score}</p>
                  <p className="text-xs text-faint">lead score</p>
                </div>
                <div className="-mr-2 -mt-1 flex items-center">
                  {ids.length > 1 && pos >= 0 && <>
                    <button className="btn-subtle btn-sm px-1.5" onClick={() => go(-1)} disabled={pos <= 0} aria-label="Previous lead (K)" title="Previous lead (K)"><ChevronUp className="size-4" /></button>
                    <button className="btn-subtle btn-sm px-1.5" onClick={() => go(1)} disabled={pos >= ids.length - 1} aria-label="Next lead (J)" title="Next lead (J)"><ChevronDown className="size-4" /></button>
                  </>}
                  <button className="btn-subtle btn-sm" onClick={onClose} aria-label="Close"><X className="size-4" /></button>
                </div>
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

              {/* Quick actions (the agency's team only: a client's view is read-only) */}
              {!isClient && <>
              {lead.opted_out && (
                <div className="mt-4 rounded-xl bg-danger/100/10 p-3 text-xs text-ink">
                  <p><span className="font-semibold">They asked not to be contacted.</span> AIMVA won't WhatsApp or call them, and their follow-ups are cancelled. If they reply START, messages resume by themselves.</p>
                  <button className="mt-1.5 font-semibold text-muted underline hover:text-ink" disabled={busy === "optin"}
                    onClick={() => window.confirm("Only resume if the customer asked you to contact them again. Resume messages and calls?")
                      && act("optin", () => del(`/api/leads/${lead.id}/opt-out`), "Messages and calls resumed.")}>
                    They asked to hear from us again
                  </button>
                </div>
              )}
              <div className="mt-4 grid grid-cols-3 gap-2">
                <Button variant="ghost" size="sm" className="h-10" disabled={!lead.phone || lead.opted_out} busy={busy === "call"}
                  title={lead.phone ? "Have your AI voice agent call this lead (calls go out 9 am to 9 pm their time)" : "No phone number"}
                  onClick={() => act("call", () => post(`/api/leads/${lead.id}/call`, {}), (out) => out?.call_note || "AI agent is calling…")}>
                  <PhoneCall className="size-4" /> AI call
                </Button>
                <Button variant={composer === "whatsapp" ? "primary" : "ghost"} size="sm" className="h-10" disabled={!lead.phone || lead.opted_out}
                  onClick={() => (composer === "whatsapp" ? (setComposer(null), setDraft(null)) : openWhatsApp())}>
                  <MessageCircle className="size-4" /> WhatsApp
                </Button>
                <Button variant={composer === "note" ? "primary" : "ghost"} size="sm" className="h-10"
                  onClick={() => { setComposer(composer === "note" ? null : "note"); setText(""); }}>
                  <StickyNote className="size-4" /> Note
                </Button>
              </div>
              {!lead.phone && <p className="mt-2 text-xs text-faint">Add a phone number to call or WhatsApp this lead.</p>}
              {lead.phone && !lead.opted_out && (
                <button className="mt-2 text-xs text-faint underline hover:text-ink" disabled={busy === "optout"}
                  onClick={() => window.confirm("Stop all WhatsApp messages and calls to this person?")
                    && act("optout", () => post(`/api/leads/${lead.id}/opt-out`, {}), "They won't be messaged or called again.")}>
                  They asked not to be contacted
                </button>
              )}
              </>}
              <div className="mt-3"><FollowUps key={lead.id} leadId={lead.id} /></div>

              {composer === "whatsapp" && draft?.needs_template && (
                <div className="mt-3 space-y-2 rounded-xl bg-warm-soft px-3 py-2.5 text-sm text-ink">
                  <p>{draft.note}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    {draft.template
                      ? <Button size="sm" busy={busy === "send"} onClick={sendTemplate}><Send className="size-3.5" /> Send approved template</Button>
                      : <Link to="/app/whatsapp?templates=1" className="btn-ghost btn-sm">Add your template</Link>}
                  </div>
                </div>
              )}
              {composer && !isClient && (
                <form onSubmit={submitComposer} className="mt-3 space-y-2">
                  {composer === "whatsapp" && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      {INTENTS.map((q) => (
                        <button type="button" key={q.value} onClick={() => fetchDraft(q.value)} disabled={busy === "draft"}
                          className={cx("chip cursor-pointer", intent === q.value ? "border-line-strong text-strong" : "border-line text-muted hover:text-ink")}>{q.label}</button>
                      ))}
                      {busy === "draft" && <Spinner className="size-3.5" />}
                    </div>
                  )}
                  <textarea className="input" rows={3} autoFocus value={text} onChange={(e) => setText(e.target.value)}
                    placeholder={composer === "whatsapp" ? `Message ${firstName} on WhatsApp…` : "Add a private note…"}
                    onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submitComposer(e); }} />
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 text-xs text-faint">
                      {composer === "whatsapp" && draft && <>
                        <span>In {draft.language_name}</span>
                        <button type="button" className="inline-flex items-center gap-1 text-brand-2 hover:underline" onClick={() => fetchDraft(intent)} disabled={busy === "draft"}>
                          <RefreshCw className="size-3" /> Redraft
                        </button>
                        <span aria-hidden>·</span>
                      </>}
                      ⌘/Ctrl + Enter to send
                    </span>
                    {ownAppFirst ? (
                      <Button type="button" size="sm" busy={busy === "own"} disabled={!text.trim()} onClick={sendFromOwnApp}
                        title="Opens WhatsApp on this device with the message filled in. You press send.">
                        <MessageCircle className="size-3.5" /> Send from my WhatsApp
                      </Button>
                    ) : (
                      <span className="flex items-center gap-1">
                        {composer === "whatsapp" && draft?.wa_number && (
                          <Button type="button" size="sm" variant="ghost" busy={busy === "own"} disabled={!text.trim()} onClick={sendFromOwnApp}
                            title="Send from your own WhatsApp instead"><Phone className="size-3.5" /><span className="sr-only">Send from my WhatsApp</span></Button>
                        )}
                        <Button type="submit" size="sm" busy={busy === "send" || busy === "note"} disabled={!text.trim()}>
                          <Send className="size-3.5" /> {composer === "whatsapp" ? "Send" : "Save note"}
                        </Button>
                      </span>
                    )}
                  </div>
                </form>
              )}

              {/* Stage + value */}
              {isClient ? (
                <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted">
                  <span className="inline-flex items-center gap-1.5">Stage <span className={cx("chip px-3 py-1 capitalize", STAGE_STYLE[lead.stage])}>{lead.stage}</span></span>
                  <span>Deal value <span className="font-medium text-strong">{lead.value ? `₹${Number(lead.value).toLocaleString("en-IN")}` : "not set"}</span></span>
                </div>
              ) : <>
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
              {onDelete && <button type="button" onClick={() => onDelete(lead)} className="mt-3 block text-xs text-muted underline-offset-2 hover:text-danger hover:underline">Delete this lead</button>}
              </>}
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
            {!isClient && <div className="border-t border-line px-5 py-3 text-xs text-faint">
              Need a full chat? <Link to="/app/whatsapp" className="text-brand-2 hover:underline">Open WhatsApp inbox</Link>
            </div>}
          </>
        )}
      </motion.aside>
    </div>
  );
}
