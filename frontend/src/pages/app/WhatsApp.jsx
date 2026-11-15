import { useEffect, useRef, useState } from "react";
import { SaveTemplateButton, TemplateGallery, useTemplateTracker, useTemplates } from "../../components/Templates";
import { Link, useSearchParams } from "react-router-dom";
import { BadgeCheck, Check, CheckCheck, FlaskConical, LayoutTemplate, MessageCircle, MoreHorizontal, PanelRightClose, PanelRightOpen, Plus, Send } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../../components/shadcn/dropdown-menu";
import { Tooltip } from "../../components/shadcn/tooltip";
import { Button, Empty, Field, Modal, PageHeader, Spinner, cx } from "../../components/ui";
import { get, patch, post } from "../../lib/api";
import { toast } from "sonner";
import { timeAgo, useAction, useApi } from "../../lib/hooks";
import { useAuth } from "../../lib/auth";
import { LoadError, LoadErrorBar } from "../../components/LoadError";
import { useModulePrompt } from "../../components/ModulePrompt";
import { put } from "../../lib/api";

/**
 * The replies panel (design.md v3: the changes panel for WhatsApp replies). The owner's own instructions for the
 * automatic replies, written from the business profile the first time, editable any time, and the switch.
 * Before it's on, the instructions and Turn on are the whole story (design.md 7.3, WhatsApp row).
 */
function RepliesPanel({ open, onToggle }) {
  const { data: agents, setData, error, reload } = useApi("/api/agents", []);
  const [{ prompt: suggested, line, loading }] = useModulePrompt("whatsapp");
  const a = Array.isArray(agents) ? agents.find((x) => x.kind === "concierge") : null;
  const saved = a?.config?.brief || "";
  const [brief, setBrief] = useState(null);  // null = untouched, shows what's saved (or the suggestion)
  const [busy, setBusy] = useState("");
  const [kept, setKept] = useState(true);    // false when the server didn't keep the instructions
  const value = brief ?? (saved || suggested || "");
  const dirty = brief !== null && brief.trim() !== (saved || "").trim();

  const save = async (patch, what) => {
    setBusy(what);
    try {
      const next = await put("/api/agents/concierge", patch);
      setData((all) => all.map((x) => (x.kind === "concierge" ? next : x)));
      // A server that drops the instructions keeps the owner's words on screen instead of snapping back.
      if (patch.config) { const ok = next?.config?.brief === patch.config.brief; setKept(ok); if (ok) setBrief(null); }
      return next;
    } catch (err) { toast.error(err.message); return null; } finally { setBusy(""); }
  };
  const brieflyPatch = () => (value.trim() && (dirty || !saved) ? { config: { brief: value.trim().slice(0, 1000) } } : {});

  if (!open) {
    return (
      <aside aria-label="Replies" className="hidden w-12 shrink-0 flex-col items-center border-l border-line pt-2 lg:flex">
        <button type="button" className="btn-subtle btn-sm w-8 px-0" onClick={onToggle} aria-label="Open the replies panel" title="Replies"><PanelRightOpen className="size-4" /></button>
      </aside>
    );
  }
  return (
    <aside aria-label="Replies" className="flex w-full shrink-0 flex-col border-line lg:w-[360px] lg:border-l">
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-line pl-4 pr-2">
        <h2 className="text-sm font-semibold text-strong">Automatic replies</h2>
        <span className="flex items-center gap-1">
          {a && (
            <span role="radiogroup" aria-label="Automatic replies" className={cx("flex rounded-full bg-surface-2 p-0.5", busy === "switch" && "opacity-60")}>
              {[["off", "Off"], ["on", "On"]].map(([v, l]) => (
                <button key={v} type="button" role="radio" aria-checked={(a.enabled ? "on" : "off") === v} disabled={!!busy}
                  onClick={() => save(v === "on" ? { enabled: true, mode: "auto", ...brieflyPatch() } : { enabled: false }, "switch")}
                  className={cx("rounded-full px-2.5 py-0.5 text-xs font-medium", (a.enabled ? "on" : "off") === v ? "bg-surface text-strong shadow-sm" : "text-muted hover:text-ink")}>{l}</button>
              ))}
            </span>
          )}
          <button type="button" className="btn-subtle btn-sm hidden w-8 px-0 lg:inline-flex" onClick={onToggle} aria-label="Fold the replies panel" title="Fold"><PanelRightClose className="size-4" /></button>
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {error && !a ? <LoadErrorBar what="your reply settings" onRetry={reload} /> : !a || loading ? <div className="h-28 rounded-md bg-surface-2/60" aria-label="Loading" /> : (
          <>
            <label htmlFor="reply-brief" className="text-xs font-medium text-muted">How should replies sound, and what should they do?</label>
            <textarea id="reply-brief" rows={7} maxLength={1000} value={value} onChange={(e) => setBrief(e.target.value)}
              className="mt-2 block w-full resize-y rounded-md bg-surface-2/60 px-3 py-2.5 text-sm leading-relaxed text-strong focus:bg-surface focus:outline-none focus:ring-2 focus:ring-brand/40"
              placeholder="Reply within a minute in their language, share our prices, and book a visit." />
            <p className="mt-2 text-xs text-muted">
              {a.enabled ? "On. New enquiries get a reply in their own language within a minute, then follow-ups on day 2 and day 7." : line || "Nothing is sent until you turn it on."}
            </p>
            {!kept && <p role="status" className="mt-2 text-xs text-warm">Saved here, but this server doesn't keep reply instructions yet. Replies use the standard wording until it's updated.</p>}
            {a.last_run_at && <p className="mt-4 text-xs text-muted">Last sent {timeAgo(a.last_run_at)}</p>}
          </>
        )}
      </div>
      {a && (
        <div className="flex items-center justify-end gap-2 border-t border-line p-3">
          {dirty && <button type="button" className="btn-subtle btn-sm" onClick={() => setBrief(null)}>Undo</button>}
          {a.enabled
            ? <Button size="sm" busy={busy === "brief"} disabled={!dirty || !value.trim()} onClick={() => save({ config: { brief: value.trim().slice(0, 1000) } }, "brief")}>Save</Button>
            : <Button size="sm" variant="accent" busy={busy === "switch"} disabled={!value.trim()} onClick={() => save({ enabled: true, mode: "auto", config: { brief: value.trim().slice(0, 1000) } }, "switch")}>Turn on</Button>}
        </div>
      )}
    </aside>
  );
}

const PANEL_KEY = "aimva_replies_panel";

export default function WhatsApp() {
  const { data: convos, reload, loading, error: convosError } = useApi("/api/whatsapp/conversations", []);
  const { data: integrations, reload: reloadIntegrations, loading: integLoading, error: integError } = useApi("/api/integrations", []);
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const approvedOpen = params.get("templates") === "1";
  const setApprovedOpen = (open) => setParams((p) => { const n = new URLSearchParams(p); open ? n.set("templates", "1") : n.delete("templates"); return n; });
  const [panelOpen, setPanelOpen] = useState(() => { try { return localStorage.getItem(PANEL_KEY) !== "folded"; } catch { return true; } });
  const togglePanel = () => setPanelOpen((o) => { try { localStorage.setItem(PANEL_KEY, o ? "folded" : "open"); } catch { /* private window */ } return !o; });
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
    const load = () => get(`/api/whatsapp/messages/${active.contact}`).then((m) => { if (!stop) setMessages(m); }).catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => { stop = true; clearInterval(t); };
  }, [active]);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [messages]);

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
      <PageHeader title="WhatsApp"
        actions={<>
          {(connected || user?.can_simulate) && (
            <DropdownMenu>
              <Tooltip content="More"><DropdownMenuTrigger asChild><button type="button" className="btn-subtle w-9 px-0" aria-label="More"><MoreHorizontal className="size-4" /></button></DropdownMenuTrigger></Tooltip>
              <DropdownMenuContent align="end">
                {connected && <DropdownMenuItem onSelect={() => setApprovedOpen(true)}><BadgeCheck className="size-4" /> Approved templates</DropdownMenuItem>}
                {/* A test tool for the team that runs AIMVA; owners never see it. */}
                {user?.can_simulate && <DropdownMenuItem onSelect={() => setSim(true)}><FlaskConical className="size-4" /> Test an incoming message</DropdownMenuItem>}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          <Button onClick={() => setNewChat(true)}><Plus className="size-4" /> New chat</Button>
        </>} />
      {integError && <LoadErrorBar what="your WhatsApp connection" onRetry={reloadIntegrations} />}
      {!connected && !integLoading && !integError && (
        <p className="mb-4 text-sm text-muted">
          <span className="mr-2 inline-block size-1.5 rounded-full bg-warm align-middle" aria-hidden />
          Your number isn't connected, so messages here are saved but not delivered.{" "}
          <Link to="/app/settings?tab=integrations" className="font-medium text-brand hover:underline">Connect your number</Link>
        </p>
      )}
      {/* Edge to edge, no card: chats, the open chat, and the replies panel. */}
      <div className="-mx-4 flex flex-col border-y border-line sm:-mx-6 lg:-mx-8 lg:h-[calc(100dvh-13rem)] lg:min-h-[520px] lg:flex-row">
        <div className="flex min-h-[520px] min-w-0 flex-1 lg:min-h-0">
          <div className={cx("w-full shrink-0 overflow-y-auto border-line md:w-[300px] md:border-r", active && "hidden md:block")}>
            {loading ? <div className="grid h-40 place-items-center"><Spinner /></div> : convosError && convos.length === 0 ? (
              <LoadError compact error={convosError} what="your chats" onRetry={reload} />
            ) : convos.length === 0 ? (
              <Empty compact icon={MessageCircle} title="No chats yet" text="When someone messages your business number, the chat opens here." action={<Button size="sm" variant="ghost" onClick={() => setNewChat(true)}><Plus className="size-4" /> New chat</Button>} />
            ) : convos.map((c) => (
              <button key={c.contact} onClick={() => setActive(c)} className={cx("flex w-full gap-3 border-b border-line px-4 py-3 text-left hover:bg-surface-2/60 sm:pl-6 lg:pl-8", active?.contact === c.contact && "bg-accent-soft/60 hover:bg-accent-soft/60")}>
                <div className="grid size-9 shrink-0 place-items-center rounded-full bg-surface-2 text-sm font-semibold text-strong">{(c.contact_name || "#")[0].toUpperCase()}</div>
                <div className="min-w-0 flex-1">
                  <div className="flex justify-between gap-2"><p className="truncate text-sm font-medium text-strong">{c.contact_name || (String(c.contact).startsWith("+") ? c.contact : `+${c.contact}`)}</p><span className="shrink-0 text-xs text-muted">{timeAgo(c.created_at)}</span></div>
                  <p className="truncate text-xs text-muted">{c.direction === "out" && "You: "}{c.body}</p>
                </div>
              </button>
            ))}
          </div>
          <div className={cx("flex min-h-0 min-w-0 flex-1 flex-col", !active && "hidden md:flex")}>
            {!active ? <div className="grid flex-1 place-items-center text-sm text-muted">Pick a chat to read it</div> : (
              <>
                <div className="flex h-11 shrink-0 items-center gap-3 border-b border-line px-4">
                  <button className="btn-subtle btn-sm md:hidden" onClick={() => setActive(null)} aria-label="Back to chats">←</button>
                  <p className="text-sm font-medium text-strong">{active.contact_name || (String(active.contact).startsWith("+") ? active.contact : `+${active.contact}`)}</p>
                  <p className="text-xs text-muted">{String(active.contact).startsWith("+") ? active.contact : `+${active.contact}`}</p>
                </div>
                <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4">
                  {messages.map((m) => (
                    <div key={m.id} className={cx("flex", m.direction === "out" ? "justify-end" : "justify-start")}>
                      <div className={cx("max-w-[75%] rounded-2xl px-3.5 py-2 text-sm", m.direction === "out" ? "rounded-br-sm bg-accent-soft text-strong" : "rounded-bl-sm bg-surface-2 text-ink")}>
                        <p className="whitespace-pre-wrap">{m.body}</p>
                        <p className="mt-1 flex items-center justify-end gap-1 text-xs text-muted">
                          {timeAgo(m.created_at)}
                          {m.direction === "out" && (m.status === "read" ? <CheckCheck className="size-3 text-brand" /> : m.status === "delivered" ? <CheckCheck className="size-3" /> : m.status === "failed" ? <span className="text-danger">· not sent</span> : m.status === "simulated" ? "· not delivered" : m.status === "own_app" ? "· from your phone" : <Check className="size-3" />)}
                        </p>
                      </div>
                    </div>
                  ))}
                  <div ref={endRef} />
                </div>
                <div className="border-t border-line p-3">
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {waTemplates.templates.slice(0, 4).map((t) => (
                      <button key={t.ref} onClick={() => applyTemplate(t)} title={t.payload.body}
                        className="rounded-full bg-surface-2 px-2.5 py-1 text-xs text-ink hover:bg-accent-soft">{t.name}</button>
                    ))}
                    <button onClick={() => setGallery(true)} className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium text-brand hover:bg-surface-2"><LayoutTemplate className="size-3" /> All</button>
                    {text.trim().length >= 5 && <SaveTemplateButton module="whatsapp" className="h-6 px-2 text-xs"
                      getPayload={() => ({ body: active?.contact_name ? text.replaceAll(firstName(), "{name}") : text })} />}
                  </div>
                  <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); text.trim() && send(text); }}>
                    <textarea className="input min-h-10 resize-none" rows={1} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a message" aria-label="Message"
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); text.trim() && send(text); } }} />
                    <Button type="submit" busy={busy} disabled={!text.trim()} aria-label="Send"><Send className="size-4" /></Button>
                  </form>
                </div>
              </>
            )}
          </div>
        </div>
        <div className="border-t border-line lg:hidden" />
        <RepliesPanel open={panelOpen} onToggle={togglePanel} />
      </div>
      <ApprovedTemplates open={approvedOpen && !!connected} onClose={() => setApprovedOpen(false)} meta={waInteg?.meta || {}} onSaved={reloadIntegrations} />
      <TemplateGallery module="whatsapp" open={gallery} onClose={() => setGallery(false)} onApply={applyTemplate} data={waTemplates} />
      <ChatModal open={newChat} onClose={() => setNewChat(false)} title="New chat" submitLabel="Send"
        onSubmit={async (f) => { await send(f.body, f.phone, f.name); setNewChat(false); }} />
      <ChatModal open={sim} onClose={() => setSim(false)} title="Test an incoming message" submitLabel="Receive"
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
