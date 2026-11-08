import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { SaveTemplateButton, TemplateGallery, useTemplateTracker, useTemplates } from "../../components/Templates";
import { Link, useSearchParams } from "react-router-dom";
import { BadgeCheck, Check, CheckCheck, FlaskConical, LayoutTemplate, MessageCircle, Plus, Send } from "lucide-react";
import { Button, Card, Empty, Field, Modal, Notice, PageHeader, Spinner, cx } from "../../components/ui";
import { get, patch, post } from "../../lib/api";
import { timeAgo, useAction, useApi } from "../../lib/hooks";
import { useAuth } from "../../lib/auth";
import { LoadError, LoadErrorBar } from "../../components/LoadError";


export default function WhatsApp() {
  const { data: convos, reload, loading, error: convosError } = useApi("/api/whatsapp/conversations", []);
  const { data: integrations, reload: reloadIntegrations, loading: integLoading, error: integError } = useApi("/api/integrations", []);
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const approvedOpen = params.get("templates") === "1";
  const setApprovedOpen = (open) => setParams((p) => { const n = new URLSearchParams(p); open ? n.set("templates", "1") : n.delete("templates"); return n; });
  const [active, setActive] = useState(null);
  const [messages, setMessages] = useState([]);
  const waTemplates = useTemplates("whatsapp");
  const tpl = useTemplateTracker("whatsapp");
  const [gallery, setGallery] = useState(false);
  const firstName = () => (active?.contact_name || "").split(" ")[0] || "there";
  const applyTemplate = (t) => {
    const body = t.payload.body.replaceAll("{name}", firstName());
    tpl.apply({ ...t, payload: { body } });
    setText(body);
  };
  const seen = useRef(new Set());  // messages already there when the chat opened don't animate
  const shownFor = useRef(null);
  const [text, setText] = useState("");
  const [newChat, setNewChat] = useState(false);
  const [sim, setSim] = useState(false);
  const [busy, run] = useAction();
  const endRef = useRef(null);
  const waInteg = integrations.find((i) => i.provider === "whatsapp");
  const connected = waInteg?.connected;

  useEffect(() => {
    if (!active) return;
    let stop = false;
    const load = () => get(`/api/whatsapp/messages/${active.contact}`).then((m) => {
      if (stop) return;
      if (shownFor.current !== active.contact) { shownFor.current = active.contact; seen.current = new Set(m.map((x) => x.id)); }
      setMessages(m);
    }).catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => { stop = true; clearInterval(t); };
  }, [active]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = (body, to = active?.contact, name = active?.contact_name) => run(async () => {
    const m = await post("/api/whatsapp/send", { to, body, name: name || "" });
    tpl.track({ body });
    setText("");
    if (active?.contact === m.contact) setMessages((x) => [...x, m]);
    else setActive({ contact: m.contact, contact_name: m.contact_name });
    reload();
  });

  return (
    <div>
      <PageHeader title="WhatsApp" subtitle={connected ? "Answer leads, follow up, and see what the concierge sent for you." : undefined}
        actions={<>
          {connected && <Button variant="ghost" onClick={() => setApprovedOpen(true)}><BadgeCheck className="size-4" /> Approved templates</Button>}
          {user?.can_simulate && <Button variant="ghost" onClick={() => setSim(true)}><FlaskConical className="size-4" /> Simulate inbound</Button>}
          <Button onClick={() => setNewChat(true)}><Plus className="size-4" /> New chat</Button>
        </>} />
      {integError && <LoadErrorBar what="your WhatsApp connection" onRetry={reloadIntegrations} />}
      {!connected && !integLoading && !integError && (
        <Notice tone="green" icon={MessageCircle} action={<Link to="/app/settings?tab=integrations" className="btn-ghost btn-sm">Connect number</Link>}>
          Not connected yet, so messages here are saved but not delivered. Connect your WhatsApp Business number to send for real.
        </Notice>
      )}
      <Card className="grid h-[640px] grid-cols-1 overflow-hidden p-0 sm:p-0 md:grid-cols-[300px_1fr]">
        <div className={cx("overflow-y-auto border-r border-line", active && "hidden md:block")}>
          {loading ? <div className="grid h-40 place-items-center"><Spinner /></div> : convosError && convos.length === 0 ? (
            <LoadError compact error={convosError} what="your chats" onRetry={reload} />
          ) : convos.length === 0 ? (
            <Empty compact icon={MessageCircle} title="No chats yet" text="When someone messages your business number, the chat opens here." action={<Button size="sm" variant="ghost" onClick={() => setNewChat(true)}><Plus className="size-4" /> New chat</Button>} />
          ) : convos.map((c) => (
            <button key={c.contact} onClick={() => setActive(c)} className={cx("flex w-full gap-3 border-b border-line px-4 py-3 text-left hover:bg-ink/[0.03]", active?.contact === c.contact && "bg-ink/[0.05]")}>
              <div className="grid size-10 shrink-0 place-items-center rounded-full bg-emerald-500/15 font-semibold text-emerald-600">{(c.contact_name || "#")[0].toUpperCase()}</div>
              <div className="min-w-0 flex-1">
                <div className="flex justify-between gap-2"><p className="truncate text-sm font-semibold text-strong">{c.contact_name || `+${c.contact}`}</p><span className="shrink-0 text-xs text-faint">{timeAgo(c.created_at)}</span></div>
                <p className="truncate text-xs text-muted">{c.direction === "out" && "You: "}{c.body}</p>
              </div>
            </button>
          ))}
        </div>
        <div className={cx("flex min-h-0 flex-col", !active && "hidden md:flex")}>
          {!active ? <div className="grid flex-1 place-items-center text-sm text-muted">Select a conversation</div> : (
            <>
              <div className="flex items-center gap-3 border-b border-line px-4 py-3">
                <button className="btn-subtle btn-sm md:hidden" onClick={() => setActive(null)}>←</button>
                <div><p className="text-sm font-semibold text-strong">{active.contact_name || `+${active.contact}`}</p><p className="text-xs text-faint">+{active.contact}</p></div>
              </div>
              <div className="flex-1 space-y-2 overflow-y-auto bg-[radial-gradient(rgba(148,163,184,0.06)_1px,transparent_1px)] p-4 [background-size:16px_16px]">
                {messages.map((m) => (
                  <motion.div key={m.id} className={cx("flex", m.direction === "out" ? "justify-end" : "justify-start")}
                    initial={seen.current.has(m.id) ? false : { opacity: 0, y: 10, x: m.direction === "out" ? 16 : -16, scale: 0.96 }}
                    animate={{ opacity: 1, y: 0, x: 0, scale: 1 }} transition={{ type: "spring", stiffness: 320, damping: 26 }}>
                    <div className={cx("max-w-[75%] rounded-2xl px-3.5 py-2 text-sm", m.direction === "out" ? "rounded-br-sm bg-emerald-600/80 text-white" : "rounded-bl-sm bg-surface-2 text-ink")}>
                      <p className="whitespace-pre-wrap">{m.body}</p>
                      <p className="mt-1 flex items-center justify-end gap-1 text-xs opacity-70">
                        {timeAgo(m.created_at)}
                        {m.direction === "out" && (m.status === "read" ? <CheckCheck className="size-3 text-sky-600" /> : m.status === "delivered" ? <CheckCheck className="size-3" /> : m.status === "failed" ? "failed" : m.status === "simulated" ? "sandbox" : m.status === "own_app" ? "from your phone" : <Check className="size-3" />)}
                      </p>
                    </div>
                  </motion.div>
                ))}
                <div ref={endRef} />
              </div>
              <div className="border-t border-line p-3">
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {waTemplates.templates.slice(0, 5).map((t) => (
                    <button key={t.ref} onClick={() => applyTemplate(t)} title={t.payload.body}
                      className={cx("chip cursor-pointer hover:text-ink", t.source === "suggested" ? "border-amber-300 text-amber-800" : t.source === "mine" ? "border-emerald-300 text-emerald-800" : "border-line text-muted")}>{t.name}</button>
                  ))}
                  <button onClick={() => setGallery(true)} className="chip cursor-pointer border-line text-brand"><LayoutTemplate className="size-3" /> All templates</button>
                  {text.trim().length >= 5 && <SaveTemplateButton module="whatsapp" className="h-6 px-2 text-xs"
                    getPayload={() => ({ body: active?.contact_name ? text.replaceAll(firstName(), "{name}") : text })} />}
                </div>
                <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); text.trim() && send(text); }}>
                  <textarea className="input h-10 resize-none" rows={1} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a message"
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); text.trim() && send(text); } }} />
                  <Button type="submit" busy={busy} disabled={!text.trim()}><Send className="size-4" /></Button>
                </form>
              </div>
            </>
          )}
        </div>
      </Card>
      <ApprovedTemplates open={approvedOpen && !!connected} onClose={() => setApprovedOpen(false)} meta={waInteg?.meta || {}} onSaved={reloadIntegrations} />
      <TemplateGallery module="whatsapp" open={gallery} onClose={() => setGallery(false)} onApply={applyTemplate} data={waTemplates} />
      <ChatModal open={newChat} onClose={() => setNewChat(false)} title="New chat" submitLabel="Send"
        onSubmit={async (f) => { await send(f.body, f.phone, f.name); setNewChat(false); }} />
      <ChatModal open={sim} onClose={() => setSim(false)} title="Simulate inbound message" submitLabel="Receive"
        onSubmit={async (f) => {
          await run(() => post("/api/whatsapp/simulate-inbound", { from: f.phone, body: f.body, name: f.name }), "Message received, lead created");
          setSim(false); reload();
        }} />
    </div>
  );
}

function ChatModal({ open, onClose, title, submitLabel, onSubmit }) {
  const [f, setF] = useState({ phone: "", name: "", body: "" });
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); onSubmit(f); }}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Phone (with country code)"><input className="input" type="tel" inputMode="tel" value={f.phone} onChange={set("phone")} placeholder="+919876543210" required /></Field>
          <Field label="Name"><input className="input" value={f.name} onChange={set("name")} /></Field>
        </div>
        <Field label="Message"><textarea className="input" rows={3} value={f.body} onChange={set("body")} required /></Field>
        <Button type="submit">{submitLabel}</Button>
      </form>
    </Modal>
  );
}

/** WhatsApp only lets a business start a chat (or write after 24 hours of silence) with a template Meta approved.
 *  The business names theirs here; AIMVA sends it to new form and ad leads in the lead's language when one exists. */
function ApprovedTemplates({ open, onClose, meta, onSaved }) {
  const [f, setF] = useState({});
  const [busy, run] = useAction();
  useEffect(() => {
    if (open) setF({ first: meta.first_message_template || "", follow: meta.follow_up_template || "",
      langs: (meta.template_languages || ["en"]).join(", "), withName: meta.template_has_name !== false });
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const clean = (v) => v.trim().toLowerCase();
  const valid = (v) => !v || /^[a-z0-9_]{1,120}$/.test(clean(v));
  return (
    <Modal open={open} onClose={onClose} title="Approved templates">
      <form className="space-y-4" onSubmit={(e) => {
        e.preventDefault();
        run(async () => {
          await patch("/api/integrations/whatsapp/meta", { meta: {
            first_message_template: clean(f.first || ""), follow_up_template: clean(f.follow || ""),
            template_languages: (f.langs || "en").split(",").map((x) => x.trim()).filter(Boolean),
            template_has_name: !!f.withName } });
          onSaved?.(); onClose();
        }, "Saved");
      }}>
        <p className="text-sm text-muted">New leads from your page or ads haven't messaged you yet, so WhatsApp only delivers a template it approved. Copy the names from WhatsApp Manager.</p>
        <Field label="First message to a new lead" hint="For example lead_welcome">
          <input className="input" value={f.first || ""} onChange={(e) => setF({ ...f, first: e.target.value })} placeholder="lead_welcome" aria-invalid={!valid(f.first || "")} />
        </Field>
        <Field label="Follow-up (optional)" hint="Sent on day 2 and day 7 if they haven't replied">
          <input className="input" value={f.follow || ""} onChange={(e) => setF({ ...f, follow: e.target.value })} placeholder="lead_follow_up" aria-invalid={!valid(f.follow || "")} />
        </Field>
        <Field label="Languages you have them in" hint="Language codes, e.g. en, hi, ta. The lead's language is used when you have it.">
          <input className="input" value={f.langs || ""} onChange={(e) => setF({ ...f, langs: e.target.value })} placeholder="en, hi" />
        </Field>
        <label className="flex items-center gap-2 text-sm text-muted">
          <input type="checkbox" checked={!!f.withName} onChange={(e) => setF({ ...f, withName: e.target.checked })} />
          The template starts with the lead's first name ({"{{1}}"})
        </label>
        <Button type="submit" busy={busy} disabled={!valid(f.first || "") || !valid(f.follow || "")}>Save</Button>
      </form>
    </Modal>
  );
}
