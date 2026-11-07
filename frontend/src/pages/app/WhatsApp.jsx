import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { SaveTemplateButton, TemplateGallery, useTemplateTracker, useTemplates } from "../../components/Templates";
import { Link } from "react-router-dom";
import { Check, CheckCheck, FlaskConical, LayoutTemplate, MessageCircle, Plus, Send } from "lucide-react";
import { Button, Card, Empty, Field, Modal, Notice, PageHeader, Spinner, cx } from "../../components/ui";
import { get, post } from "../../lib/api";
import { timeAgo, useAction, useApi } from "../../lib/hooks";


export default function WhatsApp() {
  const { data: convos, reload, loading } = useApi("/api/whatsapp/conversations", []);
  const { data: integrations } = useApi("/api/integrations", []);
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
  const connected = integrations.find((i) => i.provider === "whatsapp")?.connected;

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
      <PageHeader icon={MessageCircle} tone="green" title="WhatsApp" subtitle="Chat with leads, send scheduling messages and capture enquiries."
        actions={<>
          <Button variant="ghost" onClick={() => setSim(true)}><FlaskConical className="size-4" /> Simulate inbound</Button>
          <Button onClick={() => setNewChat(true)}><Plus className="size-4" /> New chat</Button>
        </>} />
      {!connected && (
        <Notice tone="green" icon={MessageCircle} action={<Link to="/app/settings?tab=integrations" className="btn-ghost btn-sm">Connect number</Link>}>
          Sandbox mode: messages are saved but not delivered. Connect a WhatsApp Cloud API number to send for real.
        </Notice>
      )}
      <Card className="grid h-[640px] grid-cols-1 overflow-hidden p-0 sm:p-0 md:grid-cols-[300px_1fr]">
        <div className={cx("overflow-y-auto border-r border-line", active && "hidden md:block")}>
          {loading ? <div className="grid h-40 place-items-center"><Spinner /></div> : convos.length === 0 ? (
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
                        {m.direction === "out" && (m.status === "read" ? <CheckCheck className="size-3 text-sky-600" /> : m.status === "delivered" ? <CheckCheck className="size-3" /> : m.status === "failed" ? "failed" : m.status === "simulated" ? "sandbox" : <Check className="size-3" />)}
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
