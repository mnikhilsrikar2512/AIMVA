import { useEffect, useState } from "react";
import { BookOpen, Check, Download, PencilLine } from "lucide-react";
import { toast } from "sonner";
import { Button, Card, Field } from "./ui";
import { get, put } from "../lib/api";

// The rest of the brand book. Name, tagline, colours, voice, style, audience and avoid are edited in the kit above.
// RULE (owner 2026-11-21): ask only what we can't work out ourselves. What you do, offer, area and languages come from
// setup, pages and campaigns, so they are shown, not asked (a quiet "Fix something" opens them if one is wrong). Fonts,
// phone and "words you like" are left to the backend. The one real question: words this business never uses.
const FOUND = [
  ["what", "What you do", true],
  ["offer", "Your offer right now"],
  ["area", "Where you work"],
  ["languages", "Your customers speak"],
];
const ASK = ["never_say", "Words you never use", "cheap, guaranteed returns"];
const KEYS = [...FOUND.map(([k]) => k), ASK[0]];
const asText = (v) => (Array.isArray(v) ? v.join(", ") : v || "");

export function BrandBook({ refreshKey }) {
  const [book, setBook] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [fixing, setFixing] = useState(false);

  const load = (b) => { setBook(b); setForm(Object.fromEntries(KEYS.map((k) => [k, asText(b[k])]))); };
  useEffect(() => { get("/api/brand/book").then(load).catch(() => setBook(false)); }, [refreshKey]);

  if (book === false) return null;
  if (!book) return <Card className="h-40 animate-pulse" />;
  const dirty = KEYS.some((k) => form[k] !== asText(book[k]));

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
          <p className="mt-0.5 max-w-xl text-sm text-muted">How your business looks and sounds. Your pages, ads, pictures and WhatsApp replies all follow it.</p>
        </div>
        <div className="flex items-center gap-2">
          <a href="/api/brand/book.md" download="brand-book.md" className="btn-ghost btn-sm" title="Download to share with a designer">
            <Download className="size-4" /> Download
          </a>
          <Button size="sm" onClick={save} busy={saving} disabled={!dirty}>{dirty ? "Save" : <><Check className="size-4" /> Saved</>}</Button>
        </div>
      </div>

      {fixing ? (
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          {FOUND.map(([k, label, wide]) => (
            <Field key={k} label={label} className={wide ? "sm:col-span-2" : ""}>
              <input className="input" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
            </Field>
          ))}
        </div>
      ) : (
        <dl className="mt-4 divide-y divide-line text-sm">
          {FOUND.filter(([k]) => asText(book[k])).map(([k, label]) => (
            <div key={k} className="flex gap-4 py-2"><dt className="w-40 shrink-0 text-muted">{label}</dt><dd className="min-w-0 text-ink">{asText(book[k])}</dd></div>
          ))}
          <div className="pt-2"><button type="button" className="inline-flex items-center gap-1 text-xs font-medium text-muted hover:text-strong" onClick={() => setFixing(true)}><PencilLine className="size-3.5" /> Fix something</button></div>
        </dl>
      )}

      <Field label={ASK[1]} hint="We keep these out of every ad, page and reply. Separate with commas." className="mt-5">
        <input className="input" value={form[ASK[0]]} placeholder={ASK[2]} onChange={(e) => setForm({ ...form, [ASK[0]]: e.target.value })} />
      </Field>
    </Card>
  );
}
