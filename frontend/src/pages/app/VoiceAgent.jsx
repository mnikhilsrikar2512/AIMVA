import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { SaveTemplateButton, TemplateStrip, useTemplateTracker } from "../../components/Templates";
import { AudioLines, Bot, Mic, MicOff, Phone, PhoneOff, Plus, Save, Send, Trash2, User as UserIcon } from "lucide-react";
import { Button, Card, Chip, Empty, Field, Modal, PageHeader, Spinner, Tabs, cx, ListSkeleton } from "../../components/ui";
import { LoadError } from "../../components/LoadError";
import { del, get, post, put } from "../../lib/api";
import { timeAgo, useAction, useApi } from "../../lib/hooks";
import { speakWithPulse, useMicLevel } from "../../lib/audio";

const VoiceOrb = lazy(() => import("../../components/VoiceOrb"));

const SpeechRecognition = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);

function sentimentTone(s) {
  if (s == null) return "slate";
  return s > 0.2 ? "green" : s < -0.2 ? "rose" : "amber";
}

function AgentEditor({ agent, languages, onSaved, onDelete }) {
  const [a, setA] = useState(agent);
  const [busy, run] = useAction();
  useEffect(() => { setA(agent); }, [agent]);
  const set = (k) => (e) => setA((x) => ({ ...x, [k]: e.target.value }));
  const tpl = useTemplateTracker("voice");
  const script = () => ({ language: a.language, greeting: a.greeting, instructions: a.instructions, questions: a.questions.map((q) => q.trim()).filter(Boolean) });
  return (
    <div className="space-y-4">
      <TemplateStrip module="voice" title="Start from a call script" onApply={(t) => {
        tpl.apply(t);
        const p = t.payload;
        setA((x) => ({ ...x, greeting: p.greeting, instructions: p.instructions, questions: p.questions, language: languages?.[p.language] ? p.language : x.language }));
      }} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Agent name"><input className="input" value={a.name} onChange={set("name")} /></Field>
        <Field label="Language">
          <select className="input" value={a.language} onChange={set("language")}>
            {Object.entries(languages || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Greeting"><textarea className="input" rows={2} value={a.greeting} onChange={set("greeting")} /></Field>
      <Field label="Personality & instructions" hint="How the assistant should sound and behave when it writes its replies.">
        <textarea className="input" rows={3} value={a.instructions} onChange={set("instructions")} />
      </Field>
      <Field label="Qualification questions" hint="One per line, asked in order. Include name and phone/email so a lead can be created.">
        <textarea className="input" rows={5} value={a.questions.join("\n")} onChange={(e) => setA((x) => ({ ...x, questions: e.target.value.split("\n") }))} />
      </Field>
      <Field label="Human handoff number" hint="Phone calls transfer here when the caller asks for a person or sounds upset.">
        <input className="input" value={a.handoff_number} onChange={set("handoff_number")} placeholder="+91…" />
      </Field>
      <div className="flex gap-2">
        <Button busy={busy} onClick={() => run(async () => { const out = await put(`/api/voice/agents/${a.id}`, { ...a, questions: a.questions.map((q) => q.trim()).filter(Boolean) }); tpl.track(script()); onSaved(out); }, "Agent saved")}>
          <Save className="size-4" /> Save
        </Button>
        <SaveTemplateButton module="voice" getPayload={script} label="Save script as template" className="h-10" />
        <Button variant="danger" onClick={() => confirm("Delete this agent and its call history?") && onDelete()}><Trash2 className="size-4" /></Button>
      </div>
    </div>
  );
}

const PHASE_LABEL = {
  idle: "Ready", listening: "Listening to you…", thinking: "Thinking…", speaking: "Agent speaking", ended: "Call ended",
};

function SentimentMeter({ value, average }) {
  // -1..1 mapped onto a red → amber → green track
  const pct = value == null ? 50 : Math.round(((Math.max(-1, Math.min(1, value)) + 1) / 2) * 100);
  const label = value == null ? "Waiting for the caller" : value > 0.2 ? "Calm / positive" : value < -0.2 ? "Upset" : "Neutral";
  return (
    <div className="w-full max-w-[220px]">
      <div className="relative h-1.5 rounded-full bg-gradient-to-r from-rose-500 via-amber-400 to-emerald-400">
        <span className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-bg shadow transition-[left] duration-700"
          style={{ left: `${pct}%` }} />
      </div>
      <p className="mt-2 text-center text-xs text-muted">
        Caller mood: <span className="font-semibold text-ink">{label}</span>
        {value != null && <span className="text-faint"> ({value > 0 ? "+" : ""}{value})</span>}
      </p>
      {average != null && value != null && <p className="text-center text-xs text-faint">Call average {average > 0 ? "+" : ""}{average}</p>}
    </div>
  );
}

function OrbStage({ level, phase, sentiment, size = "h-56" }) {
  return (
    <Suspense fallback={<div className={cx(size, "w-full")} />}>
      <VoiceOrb level={level} state={phase} sentiment={sentiment} className={cx(size, "w-full")} />
    </Suspense>
  );
}

function TestCall({ agent, onEnded }) {
  const [call, setCall] = useState(null);
  const [messages, setMessages] = useState([]);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [text, setText] = useState("");
  const [voiceOn, setVoiceOn] = useState(true);
  const [busy, run] = useAction();
  const recRef = useRef(null);
  const endRef = useRef(null);
  const level = useRef(0);
  const stopSpeech = useRef(null);
  useMicLevel(listening, level);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  useEffect(() => () => { recRef.current?.abort(); stopSpeech.current?.(); }, []);

  const lastUser = [...messages].reverse().find((m) => m.role === "user" && m.sentiment != null);
  // The orb shows how the caller feels right now (latest reply); the call average is shown alongside.
  const sentiment = lastUser ? lastUser.sentiment : null;
  const active = call?.status === "active";
  const phase = !call ? "idle" : !active && !speaking ? "ended" : listening ? "listening" : busy ? "thinking" : speaking ? "speaking" : "idle";

  const speak = (t) => {
    stopSpeech.current?.();
    stopSpeech.current = speakWithPulse(t, {
      voiceOn, lang: agent.language, levelRef: level,
      onStart: () => setSpeaking(true), onEnd: () => setSpeaking(false),
    });
  };

  const start = () => run(async () => {
    const d = await post(`/api/voice/agents/${agent.id}/calls`);
    setCall(d.call);
    setMessages([{ role: "agent", text: d.reply }]);
    speak(d.reply);
  });

  const send = (t) => {
    if (!t.trim() || !call) return;
    setText("");
    stopSpeech.current?.();
    setMessages((m) => [...m, { role: "user", text: t }]);
    run(async () => {
      const d = await post(`/api/voice/calls/${call.id}/turn`, { text: t });
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { ...copy[copy.length - 1], sentiment: d.sentiment };
        return [...copy, { role: "agent", text: d.reply }];
      });
      setCall(d.call);
      speak(d.reply);
      if (d.status !== "active") onEnded?.();
    });
  };

  const listen = () => {
    if (!SpeechRecognition) return;
    if (listening) { recRef.current?.stop(); return; }
    stopSpeech.current?.();
    const rec = new SpeechRecognition();
    rec.lang = agent.language;
    rec.interimResults = false;
    rec.onresult = (e) => send(e.results[0][0].transcript);
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    rec.start();
    setListening(true);
  };

  const end = () => run(async () => { stopSpeech.current?.(); setCall(await post(`/api/voice/calls/${call.id}/end`)); onEnded?.(); });

  if (!call) {
    return (
      <div className="flex flex-col items-center pb-8 text-center">
        <OrbStage level={level} phase="idle" sentiment={null} size="h-52" />
        <p className="font-semibold text-strong">Test {agent.name} in your browser</p>
        <p className="mt-1 max-w-sm text-sm text-muted">{SpeechRecognition ? "Talk with your microphone or type." : "This browser can't listen to your microphone (Firefox), so type your replies, or open AIMVA in Chrome, Edge or Safari to talk."} The orb moves with whoever is speaking and changes colour with the caller's mood.</p>
        <label className="mt-4 flex items-center gap-2 text-sm text-muted"><input type="checkbox" className="accent-cyan-400" checked={voiceOn} onChange={(e) => setVoiceOn(e.target.checked)} /> Speak replies aloud</label>
        <Button className="mt-5" busy={busy} onClick={start}><Phone className="size-4" /> Start test call</Button>
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,240px)_1fr]">
      <div className="flex flex-col items-center rounded-2xl border border-line bg-bg/40 p-3 md:h-[520px] md:justify-center">
        <OrbStage level={level} phase={phase} sentiment={sentiment} size="h-48 md:h-64" />
        <p className="mb-3 flex items-center gap-2 text-sm font-medium text-strong" aria-live="polite">
          <span className={cx("size-2 rounded-full", phase === "listening" ? "animate-pulse bg-rose-400" : phase === "speaking" ? "animate-pulse bg-cyan-300" : phase === "thinking" ? "animate-pulse bg-violet-300" : phase === "ended" ? "bg-slate-500" : "bg-emerald-400")} />
          {PHASE_LABEL[phase]}
        </p>
        <SentimentMeter value={sentiment} average={call.sentiment} />
      </div>

      <div className="flex h-[520px] min-w-0 flex-col">
        <div className="mb-3 flex items-center justify-between">
          <Chip tone={active ? "green" : call.status === "handoff" ? "amber" : "slate"}>{active ? "Live" : call.status}</Chip>
          {active ? <Button size="sm" variant="danger" onClick={end}><PhoneOff className="size-3.5" /> End</Button>
            : <Button size="sm" variant="ghost" onClick={() => { setCall(null); setMessages([]); }}>New call</Button>}
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto rounded-2xl bg-surface-2/60 p-4">
          {messages.map((m, i) => (
            <motion.div key={i} className={cx("flex gap-2", m.role === "user" && "flex-row-reverse")}
              initial={{ opacity: 0, y: 8, x: m.role === "user" ? 14 : -14 }} animate={{ opacity: 1, y: 0, x: 0 }} transition={{ type: "spring", stiffness: 320, damping: 26 }}>
              <div className={cx("grid size-7 shrink-0 place-items-center rounded-full", m.role === "agent" ? "bg-cyan-500/15 text-cyan-600" : "bg-violet-500/15 text-violet-600")}>
                {m.role === "agent" ? <Bot className="size-4" /> : <UserIcon className="size-4" />}
              </div>
              <div className={cx("max-w-[80%] rounded-2xl px-3.5 py-2 text-sm", m.role === "agent" ? "bg-surface-2 text-ink" : "bg-brand/25 text-strong")}>
                {m.text}
                {m.sentiment != null && <span className={cx("ml-2 text-xs", m.sentiment > 0.2 ? "text-emerald-600" : m.sentiment < -0.2 ? "text-rose-600" : "text-faint")}>{m.sentiment > 0 ? "+" : ""}{m.sentiment}</span>}
              </div>
            </motion.div>
          ))}
          {!active && call.lead_id && <p className="text-center text-xs text-emerald-600">Lead #{call.lead_id} created from this call.</p>}
          <div ref={endRef} />
        </div>
        {active && (
          <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); send(text); }}>
            {SpeechRecognition && (
              <Button type="button" variant={listening ? "primary" : "ghost"} onClick={listen} aria-label={listening ? "Stop talking" : "Talk"}>
                {listening ? <MicOff className="size-4" /> : <Mic className="size-4" />}
              </Button>
            )}
            <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder={listening ? "Listening…" : "Type a reply…"} />
            <Button type="submit" disabled={!text.trim() || busy}><Send className="size-4" /></Button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function VoiceAgent() {
  const { data: agents, setData: setAgents, loading, error: agentsError, reload: reloadAgents } = useApi("/api/voice/agents", []);
  const { data: languages } = useApi("/api/voice/languages");
  const { data: calls, reload: reloadCalls } = useApi("/api/voice/calls", []);
  const [selId, setSelId] = useState(null);
  const [tab, setTab] = useState("test");
  const [dialTo, setDialTo] = useState("");
  const [viewCall, setViewCall] = useState(null);
  const [busy, run] = useAction();
  const agent = agents.find((a) => a.id === selId) || agents[0];

  const create = () => run(async () => {
    const a = await post("/api/voice/agents", { name: `Agent ${agents.length + 1}` });
    setAgents((x) => [...x, a]);
    setSelId(a.id);
    setTab("configure");
  }, "Agent created");

  return (
    <div>
      <PageHeader icon={AudioLines} tone="cyan" title="Calls" subtitle="Your call assistant greets every lead, asks your questions and hands over to you when it matters."
        actions={<Button variant="ghost" onClick={create} busy={busy}><Plus className="size-4" /> New agent</Button>} />
      {loading ? <ListSkeleton /> : agentsError && !agents.length ? (
        <LoadError error={agentsError} what="your call assistant" onRetry={reloadAgents} />
      ) : !agent ? (
        <Empty icon={AudioLines} preview="chat" title="Your call assistant starts here" text="It greets every new lead, asks your questions and books the visit. Try it in your browser first, no phone needed."
          action={<Button onClick={create}><Plus className="size-4" /> Set up the assistant</Button>} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
          <div className="space-y-2">
            {agents.map((a) => (
              <button key={a.id} onClick={() => setSelId(a.id)} className={cx("flex w-full items-center gap-3 rounded-2xl p-3 text-left transition", agent.id === a.id ? "bg-surface shadow-[var(--shadow-soft)]" : "hover:bg-ink/[0.04]")}>
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-cyan-50 text-cyan-600"><Bot className="size-4" /></span>
                <div className="min-w-0"><p className="truncate text-sm font-semibold text-strong">{a.name}</p><p className="text-xs text-faint">{languages?.[a.language] || a.language}</p></div>
              </button>
            ))}
          </div>
          <div className="space-y-6">
            <Card>
              <div className="mb-5"><Tabs value={tab} onChange={setTab} tabs={[{ value: "test", label: "Test call" }, { value: "configure", label: "Configure" }, { value: "phone", label: "Phone call" }]} /></div>
              {tab === "test" && <TestCall key={agent.id} agent={agent} onEnded={reloadCalls} />}
              {tab === "configure" && <AgentEditor agent={agent} languages={languages}
                onSaved={(a) => setAgents((x) => x.map((y) => (y.id === a.id ? a : y)))}
                onDelete={() => run(async () => { await del(`/api/voice/agents/${agent.id}`); setAgents((x) => x.filter((y) => y.id !== agent.id)); setSelId(null); })} />}
              {tab === "phone" && (
                <div className="max-w-md space-y-4">
                  <p className="text-sm text-muted">Place a real outbound call from your Twilio number. Connect it in Settings → Accounts first.</p>
                  <Field label="Phone number (E.164)"><input className="input" value={dialTo} onChange={(e) => setDialTo(e.target.value)} placeholder="+919876543210" /></Field>
                  <Button busy={busy} onClick={() => run(async () => { await post(`/api/voice/agents/${agent.id}/dial`, { to: dialTo }); reloadCalls(); }, "Calling…")}><Phone className="size-4" /> Call now</Button>
                </div>
              )}
            </Card>
            <Card className="p-0 sm:p-0">
              <h2 className="border-b border-line px-5 py-4 font-semibold text-strong">Call history</h2>
              {calls.filter((c) => c.agent_id === agent.id).length === 0 ? <p className="px-5 py-6 text-sm text-muted">No calls yet.</p> : (
                <ul>
                  {calls.filter((c) => c.agent_id === agent.id).map((c) => (
                    <li key={c.id}>
                      <button onClick={() => setViewCall(c)} className="flex w-full items-center gap-3 border-b border-line px-5 py-3 text-left text-sm last:border-0 hover:bg-ink/[0.03]">
                        {c.channel === "phone" ? <Phone className="size-4 text-faint" /> : <AudioLines className="size-4 text-faint" />}
                        <span className="flex-1 text-ink">{c.to_number || "Browser test"} · {c.transcript.length} turns</span>
                        <Chip tone={sentimentTone(c.sentiment)}>{c.sentiment > 0 ? "+" : ""}{c.sentiment}</Chip>
                        <Chip tone={c.status === "completed" ? "green" : c.status === "handoff" ? "amber" : "slate"}>{c.status}</Chip>
                        <span className="hidden w-16 text-right text-xs text-faint sm:block">{timeAgo(c.created_at)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
      <Modal open={!!viewCall} onClose={() => setViewCall(null)} title="Call transcript">
        {viewCall && (
          <div className="space-y-2 text-sm">
            {viewCall.transcript.map((t, i) => (
              <p key={i}><b className={t.role === "agent" ? "text-cyan-600" : "text-violet-600"}>{t.role === "agent" ? "Agent" : "Caller"}:</b> <span className="text-ink">{t.text}</span></p>
            ))}
            {Object.keys(viewCall.answers).length > 0 && (
              <div className="mt-4 rounded-2xl bg-surface-2/60 p-3">
                <p className="mb-2 font-semibold text-strong">Captured answers</p>
                {Object.entries(viewCall.answers).map(([q, a]) => <p key={q} className="text-muted">{q} <span className="text-ink">{a}</span></p>)}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
