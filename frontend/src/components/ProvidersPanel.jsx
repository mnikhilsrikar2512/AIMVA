import { useMemo, useState } from "react";
import { CheckCircle2, ExternalLink, FileJson, Image as ImageIcon, PenLine, Plus, Star, Trash2, Video, Zap } from "lucide-react";
import { toast } from "sonner";
import { Button, Card, Chip, Empty, Field, Modal, Spinner, Tabs, cx, ListSkeleton } from "./ui";
import { del, patch, post } from "../lib/api";
import { LoadError } from "./LoadError";
import { useAction, useApi } from "../lib/hooks";

const KINDS = [
  { value: "text", label: "AI writing", icon: PenLine, hint: "Writes landing pages, ad copy, voice replies and insights." },
  { value: "image", label: "Images", icon: ImageIcon, hint: "Extra image models you can pick in Image Generation." },
  { value: "video", label: "Video", icon: Video, hint: "Extra video models, including self-hosted ComfyUI / FreeVideo." },
];

function AddProvider({ open, onClose, presets, onAdded }) {
  const [kind, setKind] = useState("text");
  const [presetId, setPresetId] = useState(null);
  const [f, setF] = useState({});
  const [busy, setBusy] = useState(false);
  const preset = presets.find((p) => p.id === presetId);
  const list = presets.filter((p) => p.kind === kind);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  const choose = (p) => {
    setPresetId(p.id);
    setF({ name: p.label, base_url: p.base_url, model: p.model, api_key: "", workflow: "", is_default: kind === "text" });
  };

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const c = await post("/api/providers", { preset: preset.id, ...f, workflow: f.workflow || null });
      toast.success(`${c.name} connected`);
      onAdded(c);
      setPresetId(null);
      onClose();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={() => { setPresetId(null); onClose(); }} title={preset ? `Connect ${preset.label}` : "Add an AI provider"} wide>
      {!preset ? (
        <div className="space-y-5">
          <Tabs value={kind} onChange={setKind} tabs={KINDS.map((k) => ({ value: k.value, label: k.label }))} />
          <p className="text-sm text-muted">{KINDS.find((k) => k.value === kind).hint}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {list.map((p) => (
              <button key={p.id} onClick={() => choose(p)}
                className="flex items-center justify-between gap-3 rounded-2xl bg-surface-2/70 px-4 py-3 text-left transition hover:bg-lavender">
                <span>
                  <span className="block text-sm font-semibold text-strong">{p.label}</span>
                  <span className="block text-xs text-muted">{p.key_optional ? "No key needed for local servers" : p.model || "Any model"}</span>
                </span>
                <Plus className="size-4 shrink-0 text-faint" />
              </button>
            ))}
          </div>
        </div>
      ) : (
        <form onSubmit={save} className="space-y-4">
          <button type="button" className="text-xs font-semibold text-brand hover:underline" onClick={() => setPresetId(null)}>← All providers</button>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name"><input className="input" value={f.name} onChange={set("name")} maxLength={80} /></Field>
            <Field label="Model" hint="Type any model name the provider supports.">
              <input className="input font-mono text-xs" list="preset-models" value={f.model} onChange={set("model")} placeholder="model-name" />
              <datalist id="preset-models">{preset.models.map((m) => <option key={m} value={m} />)}</datalist>
            </Field>
          </div>
          <Field label="API address" hint={preset.base_url ? "Pre-filled. Change it only for proxies or self-hosted servers." : "Base URL of the OpenAI-compatible API, e.g. https://api.example.com/v1"}>
            <input className="input font-mono text-xs" value={f.base_url} onChange={set("base_url")} placeholder="https://…" required />
          </Field>
          <Field label={preset.key_optional ? "API key (optional)" : "API key"}
            hint={<a href={preset.docs} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-brand hover:underline">Where do I get this? <ExternalLink className="size-3" /></a>}>
            <input className="input font-mono" type="password" autoComplete="off" value={f.api_key} onChange={set("api_key")} required={!preset.key_optional} />
          </Field>
          {preset.needs_workflow && (
            <Field label="ComfyUI workflow (API format)"
              hint={<>In ComfyUI choose <b>Save (API format)</b> and paste the JSON. Put <code>{"{{prompt}}"}</code> where the prompt goes; optional: <code>{"{{negative_prompt}} {{seed}} {{width}} {{height}} {{duration}}"}</code>.</>}>
              <textarea className="input font-mono text-xs" rows={7} value={f.workflow} onChange={set("workflow")} placeholder='{"6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}"}}, …}' required />
            </Field>
          )}
          {kind === "text" && (
            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" className="size-4 accent-violet-500" checked={!!f.is_default} onChange={set("is_default")} />
              Use as my default AI writer
            </label>
          )}
          <p className="text-xs text-faint">AIMVA checks the key with the provider before saving. Keys are encrypted and never shown again.</p>
          <Button type="submit" busy={busy}><Zap className="size-4" /> Test & connect</Button>
        </form>
      )}
    </Modal>
  );
}

function ConnectionRow({ c, onChange, onRemove }) {
  const [model, setModel] = useState(c.model);
  const [busy, run] = useAction();
  const [wf, setWf] = useState(null);
  return (
    <div className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 font-semibold text-strong">
          {c.name}
          {c.is_default && <Chip tone="violet">Default</Chip>}
          {c.adapter === "comfyui" && <Chip tone={c.has_workflow ? "green" : "amber"}>{c.has_workflow ? "Workflow set" : "No workflow"}</Chip>}
        </p>
        <p className="truncate font-mono text-xs text-faint">{c.base_url}</p>
      </div>
      {c.adapter !== "comfyui" && (
        <div className="flex items-center gap-2">
          <input className="input h-9 w-52 font-mono text-xs" list={`m-${c.id}`} value={model} onChange={(e) => setModel(e.target.value)} aria-label="Model" />
          <datalist id={`m-${c.id}`}>{c.models.map((m) => <option key={m} value={m} />)}</datalist>
          {model !== c.model && <Button size="sm" busy={busy} onClick={() => run(async () => onChange(await patch(`/api/providers/${c.id}`, { model })), "Model saved")}>Save</Button>}
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        <Button size="sm" variant="ghost" busy={busy} onClick={() => run(async () => toast.success((await post(`/api/providers/${c.id}/test`)).message))}>Test</Button>
        {c.kind === "text" && !c.is_default && (
          <Button size="sm" variant="ghost" onClick={() => run(async () => onChange(await patch(`/api/providers/${c.id}`, { is_default: true })), "Default writer updated")}><Star className="size-3.5" /> Make default</Button>
        )}
        {c.adapter === "comfyui" && <Button size="sm" variant="ghost" onClick={() => setWf("")}><FileJson className="size-3.5" /> Workflow</Button>}
        <Button size="sm" variant="danger" aria-label={`Remove ${c.name}`} onClick={() => confirm(`Remove ${c.name}?`) && run(async () => { await del(`/api/providers/${c.id}`); onRemove(c.id); }, "Removed")}>
          <Trash2 className="size-3.5" />
        </Button>
      </div>
      <Modal open={wf !== null} onClose={() => setWf(null)} title="Replace ComfyUI workflow">
        <textarea className="input font-mono text-xs" rows={10} value={wf || ""} onChange={(e) => setWf(e.target.value)} placeholder="Paste API-format JSON with {{prompt}}" />
        <Button className="mt-4" busy={busy} onClick={() => run(async () => { onChange(await patch(`/api/providers/${c.id}`, { workflow: wf })); setWf(null); }, "Workflow saved")}>Save workflow</Button>
      </Modal>
    </div>
  );
}

export default function ProvidersPanel() {
  const { data: presets } = useApi("/api/providers/presets", []);
  const { data: conns, setData, loading, error, reload } = useApi("/api/providers", []);
  const [adding, setAdding] = useState(false);
  const grouped = useMemo(() => KINDS.map((k) => ({ ...k, items: conns.filter((c) => c.kind === k.value) })), [conns]);
  const replace = (c) => setData((all) => all.map((x) => (x.id === c.id ? c : c.is_default && x.kind === c.kind ? { ...x, is_default: false } : x)));

  if (loading) return <ListSkeleton />;
  if (error && !conns.length) return <LoadError error={error} what="your AI providers" onRetry={reload} />;
  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-3 rounded-2xl bg-lavender/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-semibold text-strong">Bring any AI provider</p>
          <p className="text-sm text-muted">OpenAI, Claude, Groq, OpenRouter, Ollama, Replicate, Stability, any fal.ai model, your own ComfyUI or any OpenAI-compatible API.</p>
        </div>
        <Button onClick={() => setAdding(true)}><Plus className="size-4" /> Add provider</Button>
      </div>
      {conns.length === 0 ? (
        <Empty icon={Zap} preview="icon" title="Nothing extra needed" text="AIMVA already works with the free image model, fal.ai and Gemini. Add your own keys only if you want more choice." action={<Button variant="ghost" onClick={() => setAdding(true)}><Plus className="size-4" /> Add provider</Button>} />
      ) : grouped.filter((g) => g.items.length).map((g) => (
        <section key={g.value}>
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-faint"><g.icon className="size-4" /> {g.label}</h2>
          <div className="card divide-y divide-line px-5 sm:px-6">
            {g.items.map((c) => <ConnectionRow key={c.id} c={c} onChange={replace} onRemove={(id) => setData((all) => all.filter((x) => x.id !== id))} />)}
          </div>
        </section>
      ))}
      <p className="flex items-center gap-1.5 text-xs text-faint"><CheckCircle2 className="size-3.5" /> Keys are checked on save, stored encrypted, and only used for your account.</p>
      <AddProvider open={adding} onClose={() => setAdding(false)} presets={presets} onAdded={(c) => setData((all) => [...all.map((x) => (c.is_default && x.kind === c.kind ? { ...x, is_default: false } : x)), c])} />
    </div>
  );
}
