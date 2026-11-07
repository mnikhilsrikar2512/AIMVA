import { Link } from "react-router-dom";
import { Palette } from "lucide-react";
import { cx } from "./ui";

const CORNERS = [
  ["top-left", "Top left"], ["top-right", "Top right"],
  ["bottom-left", "Bottom left"], ["bottom-right", "Bottom right"],
];

function Toggle({ checked, onChange, disabled, label }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx("relative h-6 w-10 shrink-0 rounded-full transition disabled:opacity-40", checked ? "bg-strong" : "bg-ink/15")}>
      <span className={cx("absolute top-0.5 size-5 rounded-full bg-white shadow transition-all", checked ? "left-[18px]" : "left-0.5")} />
    </button>
  );
}

/**
 * Brand Kit options shared by the image and video generators.
 * value: { use_brand, add_logo, logo_position, start_image_id }
 */
export default function BrandControls({ brand, value, onChange, mode = "image", freeModel = false }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  if (!brand) return null;
  if (!brand.is_set_up) {
    return (
      <Link to="/app/brand" className="flex items-center gap-3 rounded-2xl bg-lavender/60 px-4 py-3 text-sm transition hover:bg-lavender">
        <Palette className="size-4 text-brand" />
        <span className="flex-1"><b className="text-strong">Set up your Brand Kit</b><span className="block text-xs text-muted">Logo, colours and style, applied automatically.</span></span>
      </Link>
    );
  }
  const logo = brand.logos.find((l) => l.is_primary) || brand.logos[0];
  return (
    <div className="space-y-3 rounded-2xl bg-surface-2/60 p-4">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-strong">Use my Brand Kit</p>
          <div className="mt-1 flex items-center gap-1.5">
            {brand.colors.slice(0, 5).map((c) => <span key={c} className="size-3.5 rounded-full ring-1 ring-white" style={{ background: c }} />)}
            <span className="truncate text-xs text-muted">{brand.style.slice(0, 3).join(", ") || "colours & guardrails"}</span>
          </div>
        </div>
        <Toggle label="Use my Brand Kit" checked={value.use_brand} onChange={(v) => set("use_brand", v)} />
      </div>

      {mode === "image" && (
        <div className="border-t border-line pt-3">
          <div className="flex items-center gap-3">
            {logo ? <img src={logo.url} alt="" className="size-8 rounded-lg bg-white object-contain p-1" /> : <span className="size-8 rounded-lg bg-white" />}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-strong">Add my logo</p>
              <p className="text-xs text-muted">{logo ? "Your real logo is placed on the finished image." : <>Upload a logo in <Link className="text-brand underline" to="/app/brand">Brand Kit</Link>.</>}</p>
            </div>
            <Toggle label="Add my logo" disabled={!logo} checked={value.add_logo && !!logo} onChange={(v) => set("add_logo", v)} />
          </div>
          {value.add_logo && logo && freeModel && (
            <p className="mt-3 text-xs text-muted">Free models stamp a small pollinations.ai mark bottom-right, so a top corner works best. Connect fal.ai for clean images.</p>
          )}
          {value.add_logo && logo && (
            <div className="mt-3 grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Logo position">
              {CORNERS.map(([v, l]) => (
                <button key={v} type="button" role="radio" aria-checked={value.logo_position === v} onClick={() => set("logo_position", v)}
                  className={cx("rounded-full px-3 py-1.5 text-xs font-medium transition", value.logo_position === v ? "bg-strong text-white" : "bg-surface text-muted hover:text-strong")}>
                  {l}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {mode === "video" && brand.images.length > 0 && (
        <div className="border-t border-line pt-3">
          <p className="text-sm font-semibold text-strong">Start from a brand image</p>
          <p className="mb-2 text-xs text-muted">Animate one of your product photos (optional).</p>
          <div className="flex gap-2 overflow-x-auto pb-1">
            <button type="button" onClick={() => set("start_image_id", null)}
              className={cx("grid size-14 shrink-0 place-items-center rounded-xl text-xs font-medium", !value.start_image_id ? "bg-strong text-white" : "bg-surface text-muted")}>None</button>
            {brand.images.map((im) => (
              <button key={im.id} type="button" onClick={() => set("start_image_id", im.id)} aria-label={`Start from ${im.filename}`}
                className={cx("size-14 shrink-0 overflow-hidden rounded-xl ring-2 transition", value.start_image_id === im.id ? "ring-strong" : "ring-transparent")}>
                <img src={im.url} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
