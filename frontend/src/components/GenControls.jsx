import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, Dices, Plus } from "lucide-react";
import { Field, cx } from "./ui";
import { useApi } from "../lib/hooks";
import { useAuth } from "../lib/auth";
import { ACCEPT_IMAGES, UploadTile } from "./References";

export const STYLES = [
  ["", "No style preset"], ["photographic", "Photographic"], ["cinematic", "Cinematic"], ["illustration", "Illustration"],
  ["3d_render", "3D render"], ["flat", "Flat design"], ["minimal_product", "Minimal product"], ["watercolor", "Watercolour"],
  ["anime", "Anime"], ["neon", "Neon"],
];

/** Provider select (built-ins + the user's own) and a free-text model field with suggestions. */
export function ProviderPicker({ kind, value, onChange, models: forcedModels, modelHint }) {
  const { user } = useAuth();
  const { data: options } = useApi(`/api/providers/options?kind=${kind}`, []);
  // Customers pick from AIMVA's engines by plain names; only the platform owner sees model ids and extra providers.
  if (!user?.is_admin) return <EnginePicker options={options} value={value} onChange={onChange} />;
  const current = options.find((o) => o.ref === value.provider) || options.find((o) => o.available) || options[0];
  const suggestions = forcedModels || current?.models || [];
  const pick = (ref) => {
    const o = options.find((x) => x.ref === ref);
    onChange({ provider: ref, model: o?.model || "" });
  };
  return (
    <div className="space-y-3">
      <Field label="Provider">
        <select className="input" value={current?.ref || ""} onChange={(e) => pick(e.target.value)}>
          {options.map((o) => (
            <option key={o.ref} value={o.ref} disabled={!o.available}>
              {o.name}{o.free ? " · free" : ""}{!o.available ? " (connect first)" : ""}
            </option>
          ))}
        </select>
      </Field>
      {current?.adapter !== "comfyui" && (
        <Field label="Model" hint={modelHint || "Pick a suggestion or type any model name this provider offers."}>
          <input className="input font-mono text-xs" list={`models-${kind}`} value={value.model ?? current?.model ?? ""}
            onChange={(e) => onChange({ provider: current?.ref, model: e.target.value })} placeholder={current?.model} />
          <datalist id={`models-${kind}`}>{suggestions.map((m) => <option key={m} value={m} />)}</datalist>
        </Field>
      )}
      <Link to="/app/settings?tab=providers" className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline">
        <Plus className="size-3" /> Add another provider or API key
      </Link>
    </div>
  );
}

function EnginePicker({ options, value, onChange }) {
  const usable = options.filter((o) => o.available);
  const current = usable.find((o) => o.ref === value.provider) || usable[0];
  if (!current) return <p className="text-sm text-muted">This isn't switched on for your account yet.</p>;
  const choices = current.choices || [];
  return (
    <div className="space-y-3">
      {usable.length > 1 && (
        <Field label="Engine">
          <select className="input" value={current.ref} onChange={(e) => { const o = usable.find((x) => x.ref === e.target.value); onChange({ provider: o.ref, model: o.model }); }}>
            {usable.map((o) => <option key={o.ref} value={o.ref}>{o.name}</option>)}
          </select>
        </Field>
      )}
      {choices.length > 1 && (
        <Field label="Style of model">
          <select className="input" value={value.model || current.model} onChange={(e) => onChange({ provider: current.ref, model: e.target.value })}>
            {choices.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        </Field>
      )}
    </div>
  );
}

export function Advanced({ children, label = "Advanced options" }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-2xl bg-surface-2/60">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold text-strong">
        {label}<ChevronDown className={cx("size-4 text-muted transition", open && "rotate-180")} />
      </button>
      {open && <div className="space-y-3 px-4 pb-4">{children}</div>}
    </div>
  );
}

export function SeedField({ value, onChange }) {
  return (
    <Field label="Seed" hint="Same seed + same prompt ≈ same result. Leave empty for random.">
      <div className="flex gap-2">
        <input className="input" type="number" min="0" max="2147483647" value={value ?? ""} placeholder="Random"
          onChange={(e) => onChange(e.target.value === "" ? null : Math.max(0, Math.min(2147483647, Number(e.target.value))))} />
        <button type="button" className="btn-ghost h-11 px-3" aria-label="Random seed"
          onClick={() => onChange(Math.floor(Math.random() * 2147483647))}><Dices className="size-4" /></button>
      </div>
    </Field>
  );
}

/** Pick an image from uploads, the Brand Kit or earlier generations, or upload a new one.
 *  value: "ref:<id>" | "brand:<id>" | "asset:<id>" | "" */
export function LibraryImagePicker({ label, hint, value, onChange }) {
  const { data: brand } = useApi("/api/brand");
  const { data: assets } = useApi("/api/content/assets?kind=image", []);
  const { data: refs, setData: setRefs } = useApi("/api/references?kind=image", []);
  const items = [
    ...refs.map((r) => ({ ref: r.ref, url: r.url, tag: "Upload" })),
    ...(brand?.images || []).map((i) => ({ ref: `brand:${i.id}`, url: i.url, tag: "Brand" })),
    ...(brand?.logos || []).map((i) => ({ ref: `brand:${i.id}`, url: i.url, tag: "Logo" })),
    ...assets.filter((a) => a.url).slice(0, 18).map((a) => ({ ref: `asset:${a.id}`, url: a.url, tag: "" })),
  ];
  return (
    <div>
      <p className="label">{label}</p>
      <div className="flex gap-2 overflow-x-auto pb-1">
        <button type="button" onClick={() => onChange("")}
          className={cx("grid size-14 shrink-0 place-items-center rounded-xl text-xs font-medium", !value ? "bg-strong text-white" : "bg-surface text-muted")}>None</button>
        <UploadTile accept={ACCEPT_IMAGES} className="size-14" onUploaded={(r) => { setRefs((all) => [r, ...all]); onChange(r.ref); }} />
        {items.map((i) => (
          <button key={i.ref} type="button" onClick={() => onChange(i.ref)} aria-label={`Use ${i.tag || "generated"} image`}
            className={cx("relative size-14 shrink-0 overflow-hidden rounded-xl bg-white ring-2 transition", value === i.ref ? "ring-strong" : "ring-transparent")}>
            <img src={i.url} alt="" className="h-full w-full object-cover" loading="lazy" />
            {i.tag && <span className="absolute bottom-0.5 left-0.5 rounded bg-black/55 px-1 text-xs text-white">{i.tag}</span>}
          </button>
        ))}
      </div>
      {hint && <p className="mt-1 text-xs text-faint">{hint}</p>}
    </div>
  );
}
