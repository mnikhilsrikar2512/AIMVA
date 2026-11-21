import { useEffect, useState } from "react";
import { BookOpen, Check, Download } from "lucide-react";
import { toast } from "sonner";
import { Button, Card, Field } from "./ui";
import { get, put } from "../lib/api";

// The rest of the brand book. Name, tagline, colours, voice, style, audience and avoid are edited in the kit above,
// so they are not repeated here (one place per fact, or the two would fight).
// Fonts are left out on purpose (owner 2026-11-21: "a bit excess"): they still come from the page's design.
const TEXT = [
  ["what", "What you do", "We build 2 and 3 BHK flats near the metro", true],
  ["offer", "Your offer right now", "Free site visit this weekend"],
  ["area", "Where you work", "Kukatpally and Miyapur, Hyderabad"],
  ["phone", "Phone customers call", "+91 98xxxxxx10"],
];
const LISTS = [
  ["languages", "Languages your customers speak", "Telugu, Hindi, English"],
  ["say", "Words you like", "trusted, on time, near metro"],
  ["never_say", "Words you never use", "cheap, guaranteed returns"],
];
const KEYS = [...TEXT, ...LISTS].map(([k]) => k);
const asText = (v) => (Array.isArray(v) ? v.join(", ") : v || "");

export function BrandBook({ refreshKey }) {
  const [book, setBook] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);

  const load = (b) => { setBook(b); setForm(Object.fromEntries(KEYS.map((k) => [k, asText(b[k])]))); };
  useEffect(() => { get("/api/brand/book").then(load).catch(() => setBook(false)); }, [refreshKey]);

  if (book === false) return null;
  if (!book) return <Card className="h-40 animate-pulse" />;
  const dirty = KEYS.some((k) => form[k] !== asText(book[k]));
  const pct = Math.round((book.complete || 0) * 100);

  const save = async () => {
    setSaving(true);
    try {
      // Only changed fields go up: an unchanged field we found ourselves must not turn into a frozen owner edit.
      const changes = Object.fromEntries(KEYS.filter((k) => form[k] !== asText(book[k])).map((k) => [k, form[k]]));
      load(await put("/api/brand/book", changes));
      toast.success("Brand book saved. Everything you make now follows it.");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="mt-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-base font-bold text-strong"><BookOpen className="size-4" /> Brand book</h2>
          <p className="mt-0.5 max-w-xl text-sm text-muted">
            One page that says how your business looks and sounds. Your pages, ads, pictures and WhatsApp replies all follow it.
            We filled in what we already know. Change anything and yours wins.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a href="/api/brand/book.md" download="brand-book.md" className="btn-ghost btn-sm" title="Download to share with a designer">
            <Download className="size-4" /> Download
          </a>
          <Button size="sm" onClick={save} busy={saving} disabled={!dirty}>{dirty ? "Save" : <><Check className="size-4" /> Saved</>}</Button>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Brand book filled in">
          <div className="h-full rounded-full bg-brand transition-[width] duration-300" style={{ width: `${pct}%` }} />
        </div>
        <span className="text-xs text-muted">{pct}% filled in</span>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        {TEXT.map(([k, label, ph, wide]) => (
          <Field key={k} label={label} className={wide ? "sm:col-span-2" : ""}>
            {wide
              ? <textarea className="input" rows={2} value={form[k]} placeholder={ph} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
              : <input className="input" value={form[k]} placeholder={ph} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />}
          </Field>
        ))}
        {LISTS.map(([k, label, ph]) => (
          <Field key={k} label={label} hint="Separate with commas." className={k === "languages" ? "sm:col-span-2" : ""}>
            <input className="input" value={form[k]} placeholder={ph} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
          </Field>
        ))}
      </div>
    </Card>
  );
}
