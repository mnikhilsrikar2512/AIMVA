// Calls (design.md v3 7.3): one prompt writes the call assistant's script for this business; the script fills the
// canvas as the call it will make, and the changes panel takes every change after that. Lines can also be edited in
// place. "Turn on" lets the assistant call back anyone who leaves a number.
import { useEffect, useRef, useState } from "react";
import { useUrlView } from "../../lib/nav";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Mic, MicOff, MoreHorizontal, Phone, PhoneOff, Plus, Send, X } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../../components/shadcn/dropdown-menu";
import { Tooltip } from "../../components/shadcn/tooltip";
import { Button, Field, ListSkeleton, Modal, PageHeader, cx } from "../../components/ui";
import { LoadError } from "../../components/LoadError";
import { ModulePrompt } from "../../components/ModulePrompt";
import { ChangesPanel, CompareText, ModuleFrame, ToolbarTitle, usePanelOpen } from "../../components/ModuleChanges";
import { get, patch, post, put } from "../../lib/api";
import { timeAgo, useAction, useApi } from "../../lib/hooks";
import { speakWithPulse, useMicLevel } from "../../lib/audio";

const SpeechRecognition = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
const SCRIPT = ["name", "language", "greeting", "instructions", "questions", "handoff_number"];
const STATUS = { completed: "Finished", handoff: "Handed to you", active: "On the call", scheduled: "Waiting for 9 am", failed: "Didn't connect" };

/** A line of the script that becomes a text box when clicked (edit directly, design.md 7.3). */
function EditLine({ value, onSave, label, multiline, className, onRemove }) {
  const [draft, setDraft] = useState(null);
  const save = () => { const v = (draft ?? "").trim(); setDraft(null); if (v && v !== value) onSave(v); };
  if (draft !== null) {
    const Tag = multiline ? "textarea" : "input";
    return (
      <Tag autoFocus aria-label={label} value={draft} rows={multiline ? 3 : undefined} onChange={(e) => setDraft(e.target.value)} onBlur={save}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); save(); } if (e.key === "Escape") setDraft(null); }}
        className={cx("block w-full resize-y rounded-md bg-surface px-2 py-1 text-strong ring-2 ring-brand/40 focus:outline-none", className)} />
    );
  }
  return (
    <span className="group flex items-start gap-1">
      <button type="button" onClick={() => setDraft(value || "")} title="Click to edit"
        className={cx("min-w-0 flex-1 rounded-md px-2 py-1 text-left hover:bg-surface-2", !value && "text-muted", className)}>{value || "Add…"}</button>
      {onRemove && (
        <Tooltip content="Remove"><button type="button" aria-label={`Remove: ${value}`} onClick={onRemove}
          className="mt-1 grid size-6 shrink-0 place-items-center rounded text-muted opacity-0 hover:text-danger focus:opacity-100 group-hover:opacity-100"><X className="size-3.5" /></button></Tooltip>
      )}
    </span>
  );
}

/** A practice call in the browser: talk with the microphone or type. Nothing is dialled. */
function TestCall({ agent, onEnded }) {
  const [call, setCall] = useState(null);
  const [messages, setMessages] = useState([]);
  const [listening, setListening] = useState(false);
  const [text, setText] = useState("");
  const [busy, run] = useAction();
  const recRef = useRef(null);
  const endRef = useRef(null);
  const level = useRef(0);
  const stopSpeech = useRef(null);
  useMicLevel(listening, level);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [messages]);
  useEffect(() => () => { recRef.current?.abort(); stopSpeech.current?.(); }, []);
  const active = call?.status === "active";
  const speak = (t) => { stopSpeech.current?.(); stopSpeech.current = speakWithPulse(t, { voiceOn: true, lang: agent.language, levelRef: level }); };
  const start = () => run(async () => { const d = await post(`/api/voice/agents/${agent.id}/calls`); setCall(d.call); setMessages([{ role: "agent", text: d.reply }]); speak(d.reply); });
  const send = (t) => {
    if (!t.trim() || !call) return;
    setText(""); stopSpeech.current?.();
    setMessages((m) => [...m, { role: "user", text: t }]);
    run(async () => {
      const d = await post(`/api/voice/calls/${call.id}/turn`, { text: t });
      setMessages((m) => [...m, { role: "agent", text: d.reply }]);
      setCall(d.call); speak(d.reply);
      if (d.status !== "active") onEnded?.();
    });
  };
  const listen = () => {
    if (!SpeechRecognition) return;
    if (listening) { recRef.current?.stop(); return; }
    stopSpeech.current?.();
    const rec = new SpeechRecognition();
    rec.lang = agent.language; rec.interimResults = false;
    rec.onresult = (e) => send(e.results[0][0].transcript);
    rec.onend = () => setListening(false); rec.onerror = () => setListening(false);
    recRef.current = rec; rec.start(); setListening(true);
  };
  const end = () => run(async () => { stopSpeech.current?.(); setCall(await post(`/api/voice/calls/${call.id}/end`)); onEnded?.(); });
  if (!call) {
    return (
      <div>
        <p className="text-sm text-muted">{SpeechRecognition ? "Talk with your microphone or type your answers." : "This browser can't listen to the microphone, so type your answers."} Nothing is dialled.</p>
        <Button className="mt-4" variant="ghost" busy={busy} onClick={start}><Phone className="size-4" /> Start the practice call</Button>
      </div>
    );
  }
  return (
    <div className="flex h-[min(60vh,520px)] flex-col">
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto rounded-md bg-surface-2/60 p-3">
        {messages.map((m, i) => (
          <div key={i} className={cx("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <p className={cx("max-w-[80%] rounded-2xl px-3.5 py-2 text-sm", m.role === "agent" ? "rounded-bl-sm bg-surface text-ink" : "rounded-br-sm bg-accent-soft text-strong")}>{m.text}</p>
          </div>
        ))}
        {!active && call.lead_id && <p className="text-center text-xs text-muted">This call made a lead.</p>}
        <div ref={endRef} />
      </div>
      {active ? (
        <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          {SpeechRecognition && <Button type="button" variant="ghost" onClick={listen} aria-label={listening ? "Stop talking" : "Talk"}>{listening ? <MicOff className="size-4" /> : <Mic className="size-4" />}</Button>}
          <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder={listening ? "Listening…" : "Type your answer"} aria-label="Your answer" />
          <Button type="submit" variant="ghost" disabled={!text.trim() || busy} aria-label="Send"><Send className="size-4" /></Button>
          <Button type="button" variant="danger" onClick={end} aria-label="End the call"><PhoneOff className="size-4" /></Button>
        </form>
      ) : <Button className="mt-3 self-start" variant="ghost" onClick={() => { setCall(null); setMessages([]); }}>Practise again</Button>}
    </div>
  );
}

export default function VoiceAgent() {
  const { data: agents, setData: setAgents, loading, error, reload } = useApi("/api/voice/agents", []);
  const { data: languages } = useApi("/api/voice/languages", {});
  const { data: calls, reload: reloadCalls } = useApi("/api/voice/calls", []);
  const { data: integrations } = useApi("/api/integrations", []);
  const [params] = useSearchParams();
  const given = useRef(params.get("prompt") || "");
  const [selId, setSelId] = useState(null);
  const agent = agents.find((a) => a.id === selId) || agents[0] || null;
  const { data: versions, setData: setVersions, reload: reloadVersions, loading: vLoading } = useApi(agent ? `/api/versions/call_script/${agent.id}` : null, []);
  const [view, setView, , , setUrl] = useUrlView(null);  // prompt | work, in the address (plan S7)
  const [busy, setBusy] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [panelOpen, togglePanel] = usePanelOpen();
  const [comparing, setComparing] = useState(null);
  const [practice, setPractice] = useState(false);
  const [dial, setDial] = useState(null);
  const [viewCall, setViewCall] = useState(null);
  const phoneLine = integrations.find((i) => i.provider === "twilio")?.connected;

  useEffect(() => {  // first visit: the prompt; once a script was written from one, the script
    if (loading || view || (agent && vLoading)) return;
    setView(given.current || !agent || !versions.length ? "prompt" : "work");
    if (params.get("prompt")) setUrl({ prompt: null }, { replace: true });
  }, [loading, vLoading, agent?.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  const replaced = (a) => { setAgents((all) => (all.some((x) => x.id === a.id) ? all.map((x) => (x.id === a.id ? a : x)) : [...all, a])); setSelId(a.id); reloadVersions(); };
  const write = async (prompt) => {
    setBusy(true);
    try { replaced(await post("/api/calls/script", { prompt, agent_id: agent?.id ?? null })); setView("work"); }
    catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };
  const change = async (request) => {
    setBusy(true);
    try { replaced(await post(`/api/calls/script/change${agent ? `?agent_id=${agent.id}` : ""}`, { request })); return true; }
    catch (e) { toast.error(e.message); return false; } finally { setBusy(false); }
  };
  const save = async (fields) => {
    try { replaced(await put(`/api/voice/agents/${agent.id}`, { ...Object.fromEntries(SCRIPT.map((k) => [k, agent[k]])), ...fields })); }
    catch (e) { toast.error(e.message); }
  };
  const restore = async (v) => { try { replaced(await post(`/api/versions/${v.id}/restore`)); toast(`Back to v${v.number}.`); } catch (e) { toast.error(e.message); } };
  const compare = async (v) => {
    setComparing({ v, before: null });
    try { const d = await get(`/api/versions/${v.id}`); setComparing({ v, before: d.data }); } catch (e) { toast.error(e.message); setComparing(null); }
  };
  const plain = (s) => s && ({ Speaks: languages[s.language] || s.language, "First words": s.greeting, Questions: (s.questions || []).map((q, i) => `${i + 1}. ${q}`).join("\n"),
    "How it talks": s.instructions, "Hands over to": s.handoff_number || "Nobody yet" });
  const setEnabled = async (enabled) => {
    setSwitching(true);
    try { const a = await patch(`/api/voice/agents/${agent.id}/enabled`, { enabled }); setAgents((all) => all.map((x) => (x.id === a.id ? a : x))); toast(enabled ? "Call-backs are on." : "Call-backs are off."); }
    catch (e) { toast.error(e.message); } finally { setSwitching(false); }
  };

  if (view === null) return <><PageHeader title="Calls" /><ListSkeleton /></>;
  if (error && !agents.length) return <><PageHeader title="Calls" /><LoadError error={error} what="your call assistant" onRetry={reload} /></>;

  if (view === "prompt") {
    return (
      <div>
        <PageHeader title="Calls" />
        <ModulePrompt moduleKey="calls" given={given.current} busy={busy} submitLabel="Write the call" onSubmit={write}
          outcome="You'll get the call your assistant makes to every new lead: what it says first and what it asks. Nobody is called until you turn it on."
          secondary={agent && <button type="button" className="font-medium text-brand hover:underline" onClick={() => setView("work")}>Use the current script instead</button>} />
      </div>
    );
  }

  const mine = calls.filter((c) => c.agent_id === agent?.id);
  const toolbar = (
    <>
      <ToolbarTitle status={agent?.enabled ? "On" : "Off"}>
        {agents.length > 1 ? (
          <select className="rounded-md bg-transparent pr-6 text-sm font-medium text-strong hover:bg-surface-2" value={agent?.id} onChange={(e) => setSelId(Number(e.target.value))} aria-label="Assistant">
            {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        ) : agent?.name}
      </ToolbarTitle>
      <Button variant="ghost" size="sm" onClick={() => setPractice(true)}><Phone className="size-3.5" /> Practise a call</Button>
      <DropdownMenu>
        <Tooltip content="More"><DropdownMenuTrigger asChild><button type="button" className="btn-subtle btn-sm w-8 px-0" aria-label="More"><MoreHorizontal className="size-4" /></button></DropdownMenuTrigger></Tooltip>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => setDial("")}><Phone className="size-4" /> Call a number now</DropdownMenuItem>
          {agent?.enabled && <DropdownMenuItem onSelect={() => setEnabled(false)}>Turn call-backs off</DropdownMenuItem>}
          <DropdownMenuItem onSelect={() => setView("prompt")}><Plus className="size-4" /> Write it again from one line</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {agent && !agent.enabled && <Button variant="accent" size="sm" busy={switching} onClick={() => setEnabled(true)}>Turn on</Button>}
    </>
  );

  return (
    <>
      <PageHeader title="Calls" />
      <ModuleFrame toolbar={toolbar} panel={
        <ChangesPanel open={panelOpen} onToggle={togglePanel} versions={versions} loading={vLoading} onSend={agent ? change : null} sending={busy}
          placeholder="Change anything: “ask for their budget”, “speak Hindi first”" onRestore={restore} onCompare={compare} />
      }>
        {agent && (
          <div className="max-w-2xl">
            {!phoneLine && (
              <p className="mb-6 text-sm text-muted">
                <span className="mr-2 inline-block size-1.5 rounded-full bg-warm align-middle" aria-hidden />
                Real calls go out once your phone line is connected. Until then, practise in the browser.{" "}
                <Link to="/app/settings?tab=integrations" className="font-medium text-brand hover:underline">Connect a phone line</Link>
              </p>
            )}
            <dl className="mb-6 grid grid-cols-[8rem_1fr] items-center gap-y-1 text-sm">
              <dt className="text-muted">Speaks</dt>
              <dd>
                <select className="rounded-md bg-transparent px-2 py-1 text-strong hover:bg-surface-2" value={agent.language} aria-label="Language"
                  onChange={(e) => save({ language: e.target.value })}>
                  {Object.entries(languages).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  {!languages[agent.language] && <option value={agent.language}>{agent.language}</option>}
                </select>
                <span className="text-xs text-muted">and switches to the caller's language</span>
              </dd>
              <dt className="text-muted">Hands over to</dt>
              <dd><EditLine label="Phone number to hand over to" value={agent.handoff_number} onSave={(v) => save({ handoff_number: v })} /></dd>
            </dl>

            <h2 className="mb-2 text-xs font-medium text-muted">The call</h2>
            <ol className="space-y-1 border-l-2 border-line pl-3 text-[15px] leading-relaxed">
              <li><EditLine label="What it says first" value={agent.greeting} multiline onSave={(v) => save({ greeting: v })} className="text-strong" /></li>
              {agent.questions.map((q, i) => (
                <li key={`${i}-${q}`} className="flex items-start gap-1">
                  <span className="w-5 shrink-0 pt-1 text-right text-xs tabular-nums text-muted">{i + 1}</span>
                  <span className="min-w-0 flex-1"><EditLine label={`Question ${i + 1}`} value={q}
                    onSave={(v) => save({ questions: agent.questions.map((x, j) => (j === i ? v : x)) })}
                    onRemove={agent.questions.length > 1 ? () => save({ questions: agent.questions.filter((_, j) => j !== i) }) : undefined} /></span>
                </li>
              ))}
            </ol>
            <button type="button" className="mt-2 pl-9 text-sm font-medium text-brand hover:underline" onClick={() => save({ questions: [...agent.questions, "Is there anything else we should know?"] })}>Add a question</button>

            <h2 className="mb-2 mt-8 text-xs font-medium text-muted">How it talks</h2>
            <EditLine label="How it talks" value={agent.instructions} multiline onSave={(v) => save({ instructions: v })} className="text-sm text-ink" />

            <h2 className="mb-1 mt-10 text-xs font-medium text-muted">Recent calls</h2>
            {mine.length === 0 ? <p className="text-sm text-muted">No calls yet. Practise one to hear how it sounds.</p> : (
              <ul className="border-t border-line text-sm">
                {mine.slice(0, 20).map((c) => (
                  <li key={c.id}>
                    <button type="button" onClick={() => setViewCall(c)} className="flex w-full items-center gap-3 border-b border-line py-2.5 text-left hover:bg-surface-2/60">
                      <span className="flex-1 truncate text-strong">{c.to_number || "Practice call"}</span>
                      <span className="text-xs text-muted">{STATUS[c.status] || c.status}</span>
                      <span className="w-16 text-right text-xs tabular-nums text-muted">{timeAgo(c.created_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </ModuleFrame>
      <CompareText open={!!comparing} onClose={() => setComparing(null)} title={comparing ? `v${comparing.v.number} and now` : ""}
        before={plain(comparing?.before)} after={plain(agent)} />
      <Modal open={practice} onClose={() => setPractice(false)} title="Practise a call">
        {agent && practice && <TestCall agent={agent} onEnded={reloadCalls} />}
      </Modal>
      <Modal open={dial !== null} onClose={() => setDial(null)} title="Call a number now">
        <form className="space-y-4" onSubmit={async (e) => {
          e.preventDefault();
          try {
            const c = await post(`/api/voice/agents/${agent.id}/dial`, { to: dial });
            reloadCalls(); setDial(null);
            toast(c?.scheduled_for ? "Outside calling hours. It goes out at 9 am their time." : "Calling…");
          } catch (err) { toast.error(err.message); }
        }}>
          <p className="text-sm text-muted">Calls only go out 9 am to 9 pm in the other person's time.</p>
          <Field label="Phone number with country code"><input className="input" type="tel" inputMode="tel" value={dial || ""} onChange={(e) => setDial(e.target.value)} placeholder="+919876543210" required /></Field>
          <Button type="submit" variant="ghost">Call now</Button>
        </form>
      </Modal>
      <Modal open={!!viewCall} onClose={() => setViewCall(null)} title="Call">
        {viewCall && (
          <div className="space-y-2 text-sm">
            {viewCall.transcript.map((t, i) => <p key={i}><span className="font-medium text-strong">{t.role === "agent" ? "Assistant" : "Caller"}:</span> <span className="text-ink">{t.text}</span></p>)}
            {Object.keys(viewCall.answers || {}).length > 0 && (
              <dl className="mt-4 border-t border-line pt-3">
                {Object.entries(viewCall.answers).map(([q, a]) => <div key={q} className="py-1"><dt className="text-muted">{q}</dt><dd className="text-strong">{a}</dd></div>)}
              </dl>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}
