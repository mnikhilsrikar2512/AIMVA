import { createContext, forwardRef, useContext, useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./shadcn/dialog";
import { Tabs as RTabs, TabsList, TabsTrigger } from "./shadcn/tabs";
import { Tooltip } from "./shadcn/tooltip";
import { useLocation } from "react-router-dom";
import { NAV } from "../lib/modules";
import { parseServerDate } from "../lib/hooks";
import { Loader2 } from "lucide-react";
import clsx from "clsx";
import { Mascot } from "./Mascot";

export const cx = clsx;

export function Spinner({ className }) {
  return <Loader2 className={cx("animate-spin", className || "size-4")} />;
}

/**
 * Button with guardrails: while `busy` (or while a promise returned by onClick is pending) it is disabled, shows a
 * spinner and says "Still working…" after 8 seconds, so a slow server never looks like a dead button and repeated
 * clicks can't fire the action twice.
 */
export const Button = forwardRef(function Button({ variant = "primary", size, busy, children, className, onClick, ...props }, ref) {
  const [self, setSelf] = useState(false);
  const [slow, setSlow] = useState(false);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);
  const working = busy || self;
  useEffect(() => {
    if (!working) { setSlow(false); return; }
    const t = setTimeout(() => setSlow(true), 8000);
    return () => clearTimeout(t);
  }, [working]);
  const handle = onClick && ((e) => {
    if (working) { e.preventDefault(); return; }
    const out = onClick(e);
    if (out && typeof out.then === "function") {
      setSelf(true);
      out.finally?.(() => { if (alive.current) setSelf(false); });
    }
  });
  return (
    <button
      ref={ref}
      className={cx(`btn-${variant}`, size === "sm" && "btn-sm", className)}
      {...props}
      onClick={handle}
      disabled={working || props.disabled}
      aria-busy={working || undefined}
    >
      {working && <Spinner />}
      {working && slow ? <span>Still working…</span> : children}
    </button>
  );
});

/**
 * Icon-only button for familiar secondary actions (delete, edit, copy, refresh, download, more, open). Always has
 * a tooltip and a screen-reader label. Main actions keep their words.
 */
export function IconButton({ label, children, className, danger, busy, onClick, href, ...props }) {
  const cls = cx("btn-subtle btn-sm w-8 px-0", danger && "hover:!text-danger hover:!bg-danger/10", className);
  const el = href
    ? <a href={href} aria-label={label} className={cls} {...props}>{children}</a>
    : <Button variant="subtle" size="sm" aria-label={label} busy={busy} onClick={onClick} className={cx("w-8 px-0", danger && "hover:!text-danger hover:!bg-danger/10", className)} {...props}>{busy ? null : children}</Button>;
  return <Tooltip content={label}>{el}</Tooltip>;
}

/** Rows that look like the list that is loading, so the page has its shape straight away. */
export function ListSkeleton({ rows = 5, className }) {
  return (
    <div className={cx("border-t border-line", className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 border-b border-line px-1 py-3" style={{ opacity: 1 - i * 0.14 }}>
          <span className="size-8 shrink-0 animate-pulse rounded-md bg-surface-2" />
          <span className="flex-1 space-y-1.5">
            <span className="block h-2.5 animate-pulse rounded-full bg-surface-2" style={{ width: `${62 - (i % 3) * 12}%` }} />
            <span className="block h-2 w-1/3 animate-pulse rounded-full bg-surface-2/70" />
          </span>
          <span className="h-2.5 w-10 animate-pulse rounded-full bg-surface-2" />
        </div>
      ))}
    </div>
  );
}

/**
 * Progress for jobs that take seconds to minutes (pictures, pages, videos). It says what is being made (never how,
 * and no guessed step narration: design.md 5.1 and 10), counts the time and says what to expect, so a long wait
 * never looks frozen. The bar eases towards 92% and only the real result finishes it.
 */
export function JobProgress({ label = "Working on it…", seconds = 20, startedAt, canLeave, className }) {
  const [now, setNow] = useState(Date.now());
  const [t0] = useState(() => (startedAt ? parseServerDate(startedAt).getTime() : Date.now()));
  useEffect(() => { const i = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(i); }, []);
  const el = Math.max(0, (now - t0) / 1000);
  const frac = 1 - Math.exp(-el / (seconds * 0.6));
  const pct = Math.min(92, Math.round(frac * 100));
  const slow = el > seconds * 1.6;
  const fmt = (s) => (s < 60 ? `${Math.floor(s)}s` : `${Math.floor(s / 60)}m ${String(Math.floor(s % 60)).padStart(2, "0")}s`);
  return (
    <div className={cx("w-full", className)} role="status" aria-live="polite">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="flex min-w-0 items-center gap-2 text-strong"><Spinner className="size-3.5 shrink-0 text-muted" /><span className="truncate">{slow ? "Taking a little longer than usual…" : label}</span></span>
        <span className="shrink-0 tabular-nums text-xs text-muted">{fmt(el)}{!slow && ` of about ${fmt(seconds)}`}</span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full bg-brand transition-[width] duration-500 ease-out" style={{ width: `${pct}%` }} />
      </div>
      {canLeave && el > 6 && <p className="mt-2 text-xs text-muted">You can leave this page. It keeps going and lands in your recent work.</p>}
    </div>
  );
}

export function Field({ label, hint, children, className }) {
  return (
    <label className={cx("block", className)}>
      {label && <span className="label">{label}</span>}
      {children}
      {hint && <span className="mt-1 block text-xs text-faint">{hint}</span>}
    </label>
  );
}

export function Card({ className, children, ...props }) {
  return (
    <div className={cx("card card-pad", className)} {...props}>
      {children}
    </div>
  );
}

/**
 * Inside the app frame the page title lives in the header ("Dr. Rao's Dental / Leads", design.md v3 section 4), so a
 * page only hands its title up and keeps its actions here. No subtitles. Outside the frame (the team app) it renders
 * the title itself.
 */
export const PageTitleContext = createContext(null);

export function PageHeader({ icon: Icon, title, subtitle, actions, tone = "violet" }) {
  const setTitle = useContext(PageTitleContext);
  const { pathname } = useLocation();
  useEffect(() => {
    if (!setTitle) return undefined;
    setTitle(typeof title === "string" ? title : null);
    return () => setTitle(null);
  }, [setTitle, title]);
  if (setTitle) {
    return actions ? <div className="mb-6 flex flex-wrap justify-end gap-2">{actions}</div> : null;
  }
  const section = NAV.find((g) => g.items.some((it) => it.to !== "/app" && pathname.startsWith(it.to)))?.group;
  return (
    <div className="mb-5 flex flex-col gap-3 sm:mb-8 sm:gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        {Icon && (
          <p className={cx("mb-2 hidden items-center gap-1.5 text-xs font-semibold uppercase tracking-wider lg:inline-flex", TONES[tone].text)}>
            <Icon className="size-3.5" /> {section || "AIMVA"}
          </p>
        )}
        <h1 className="text-2xl font-bold leading-tight text-strong sm:text-[30px]">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-muted sm:mt-1.5 sm:text-[15px] sm:leading-normal">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2 lg:shrink-0 lg:flex-nowrap">{actions}</div>}
    </div>
  );
}

export const TONES = {
  cyan: { tile: "bg-lavender text-brand", chip: "border-transparent bg-lavender text-brand", dot: "bg-lavender0", text: "text-brand" },
  violet: { tile: "bg-lavender text-brand", chip: "border-transparent bg-lavender text-brand", dot: "bg-brand", text: "text-brand" },  // the brand tone (teal since 2026-11-08); name kept for callers
  green: { tile: "bg-lavender text-brand", chip: "border-transparent bg-lavender text-brand", dot: "bg-lavender0", text: "text-brand" },
  pink: { tile: "bg-lavender text-brand", chip: "border-transparent bg-lavender text-brand", dot: "bg-lavender0", text: "text-brand" },
  amber: { tile: "bg-warm-soft text-warm", chip: "border-transparent bg-warm-soft text-warm", dot: "bg-warm-soft0", text: "text-warm" },
  blue: { tile: "bg-lavender text-brand", chip: "border-transparent bg-lavender text-brand", dot: "bg-lavender0", text: "text-brand" },
  slate: { tile: "bg-surface-2 text-muted", chip: "border-transparent bg-surface-2 text-muted", dot: "bg-surface-2", text: "text-muted" },
  rose: { tile: "bg-danger/10 text-danger", chip: "border-transparent bg-danger/10 text-danger", dot: "bg-danger/100", text: "text-danger" },
};

export function Chip({ tone = "slate", children, className }) {
  return <span className={cx("chip", TONES[tone].chip, className)}>{children}</span>;
}

/**
 * Empty state: no box around it. A faint sketch of what will appear (rows, tiles or a chat), a serif headline that
 * says what goes here, one line on where it comes from, and one action. `secondary` is a quiet second way in.
 * `compact` is for narrow columns (a chat list, a side panel). Filtered-to-nothing lists pass `filtered` and an
 * action that clears the filters instead.
 */
export function Empty({ icon: Icon, title, text, action, secondary, preview = "rows", compact, filtered, className }) {
  const big = !(filtered || compact) && preview !== "icon";
  // Owner 2026-11-21: not centred. Full-size empty lists keep the words on the page's left edge and the mascot to
  // their right, pointing back at the next step; compact and filtered ones stay a small centred note.
  if (big) return (
    <div className={cx("flex items-center gap-6 py-12 sm:py-14", className)}>
      <div className="min-w-0">
        <p className="text-lg font-semibold text-strong">{title}</p>
        {text && <p className="mt-1.5 max-w-md text-sm text-muted">{text}</p>}
        {(action || secondary) && <div className="mt-5 flex flex-wrap items-center gap-2">{action}{secondary}</div>}
      </div>
      {/* Owner 2026-11-21: words line up with the page; he stands to their right, pointing back at them. */}
      <Mascot mood="pointing" size={104} arrive="hop" className="hidden shrink-0 -scale-x-100 sm:block" />
    </div>
  );
  return (
    <div className={cx("flex flex-col items-center justify-center text-center", compact ? "px-4 py-10" : "px-6 py-14 sm:py-16", className)}>
      {Icon && <div className="mb-4 grid size-10 place-items-center rounded-xl bg-surface-2 text-muted"><Icon className="size-5" /></div>}
      <p className={cx(filtered || compact ? "text-[15px] font-semibold" : "text-lg font-semibold", "text-strong")}>{title}</p>
      {text && <p className="mt-1.5 max-w-sm text-sm text-muted">{text}</p>}
      {(action || secondary) && (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">{action}{secondary}</div>
      )}
    </div>
  );
}

/** Dialog on Radix (via the shadcn-style wrapper): traps focus, returns focus to the opener,
 *  closes on Escape / outside click (topmost dialog only), and names itself with the title.
 *  Same props as before, so every caller keeps working. */
export function Modal({ open, onClose, title, children, wide }) {
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose?.(); }}>
      <DialogContent aria-describedby={undefined}
        className={cx(wide === "xl" ? "sm:max-w-5xl" : wide ? "sm:max-w-3xl" : "sm:max-w-lg")}>
        <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
        <div className="px-5 pb-5 pt-3">{children}</div>
      </DialogContent>
    </Dialog>
  );
}

/** Segmented tabs on Radix: arrow keys move between options. Same props as before. */
export function Tabs({ tabs, value, onChange }) {
  return (
    <RTabs value={value} onValueChange={onChange} activationMode="automatic">
      <TabsList>
        {/* These tabs switch a value, not a panel, so they point at no tabpanel (aria-controls to a missing id is invalid). */}
        {tabs.map((t) => <TabsTrigger key={t.value} value={t.value} aria-controls={undefined}>{t.label}</TabsTrigger>)}
      </TabsList>
    </RTabs>
  );
}

export function Stat({ label, value, sub, icon: Icon, tone = "violet" }) {
  return (
    <div className="min-w-0 px-1 py-2 sm:px-6">
      <p className={cx("flex items-center gap-1.5 text-xs font-semibold", TONES[tone].text)}>
        {Icon && <Icon className="size-3.5" />}{label}
      </p>
      <p className="mt-1 font-display text-2xl font-semibold leading-none tracking-tight text-strong"><span className="tabular-nums">{typeof value === "number" ? value.toLocaleString("en-IN") : value}</span></p>
      {sub && <p className="mt-1.5 text-xs text-muted">{sub}</p>}
    </div>
  );
}

// One calm surface holding several numbers, separated by hairlines instead of separate boxes.
export function StatStrip({ children, className }) {
  return (
    <div className={cx("grid grid-cols-2 gap-y-4 border-y border-line py-3 lg:grid-cols-4 lg:divide-x lg:divide-line", className)}>
      {children}
    </div>
  );
}

export function Notice({ tone = "amber", icon: Icon, children, action }) {
  return (
    <div className={cx("mb-6 flex flex-col gap-3 rounded-2xl border-0 px-5 py-3.5 text-sm sm:flex-row sm:items-center sm:justify-between", TONES[tone].chip)}>
      <div className="flex items-start gap-2.5">
        {Icon && <Icon className="mt-0.5 size-4 shrink-0" />}
        <div>{children}</div>
      </div>
      {action}
    </div>
  );
}
