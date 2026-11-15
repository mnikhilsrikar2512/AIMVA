import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, CheckCircle2, ExternalLink, PartyPopper, Rocket, Server, XCircle } from "lucide-react";
import { Button, Field, Modal, Spinner, cx } from "./ui";
import { get, post } from "../lib/api";
import { useApi } from "../lib/hooks";

const toSlug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 50);
const TARGETS = [["aimva", "AIMVA hosting", "Free, instant"], ["netlify", "Netlify", "Your Netlify account"], ["vercel", "Vercel", "Your Vercel account"]];

export default function PublishDialog({ site, open, onClose, onPublished, beforePublish }) {
  const navigate = useNavigate();
  const { data: integrations } = useApi("/api/integrations", []);
  const connected = new Set(integrations.filter((i) => i.connected).map((i) => i.provider));
  const [f, setF] = useState(null);
  const [checks, setChecks] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(null);

  useEffect(() => {
    if (!open) return;
    const brief = site.brief || {};
    setF({
      name: site.name, slug: toSlug(site.slug.replace(/-[0-9a-f]{4}$/, "")) || toSlug(site.name),
      target: site.deploy_target && site.published ? site.deploy_target : "aimva", custom_domain: site.custom_domain || "",
      seo_title: brief.seo_title || site.name, seo_description: brief.seo_description || brief.subheadline || brief.offer || "",
    });
    setDone(null);
    setError("");
    setChecks(null);
    (async () => {
      try {
        await beforePublish?.();  // save unsaved HTML edits so checks see them
        setChecks(await get(`/api/sites/${site.id}/checks`));
      } catch (e) {
        setError(e.message);
      }
    })();
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open || !f) return null;
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: k === "slug" ? toSlug(e.target.value) : e.target.value }));
  const blockers = (checks || []).filter((c) => c.level === "blocker" && !c.ok);
  const origin = window.location.origin.replace(":5173", ":8000");

  const launch = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const out = await post(`/api/sites/${site.id}/publish`, f);
      setDone(out);
      onPublished?.(out);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={done ? "Your page is live" : "Publish your page"} wide>
      {done ? (
        <div className="space-y-5 text-center">
          <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-lavender text-brand"><PartyPopper className="size-7" /></div>
          <div>
            <p className="font-semibold text-strong">{done.name} is published</p>
            <a href={done.deploy_url || done.url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 break-all text-sm text-brand hover:underline">
              {(done.deploy_url || done.url).replace(/^https?:\/\//, "")} <ExternalLink className="size-3.5" />
            </a>
            {done.custom_domain && <p className="mt-2 text-xs text-muted">Point <b>{done.custom_domain}</b> at it from Hosting to use your own domain.</p>}
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            <a className="btn-primary" href={done.deploy_url || done.url} target="_blank" rel="noreferrer"><ExternalLink className="size-4" /> Open live page</a>
            <Button variant="ghost" onClick={() => navigate("/app/hosting")}><Server className="size-4" /> Go to Hosting</Button>
            <Button variant="subtle" onClick={onClose}>Done</Button>
          </div>
        </div>
      ) : (
        <form onSubmit={launch} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Page name"><input className="input" value={f.name} onChange={set("name")} required minLength={2} maxLength={120} /></Field>
            <Field label="Web address" hint={<span className="break-all">{origin}/s/<b>{f.slug || "…"}</b></span>}>
              <input className="input font-mono text-sm" value={f.slug} onChange={set("slug")} required maxLength={50} pattern="[a-z0-9](?:[a-z0-9\-]{0,48}[a-z0-9])?" />
            </Field>
          </div>
          <div>
            <p className="label">Where to host it</p>
            <div className="grid gap-2 sm:grid-cols-3" role="radiogroup">
              {TARGETS.map(([v, l, note]) => {
                const ok = v === "aimva" || connected.has(v);
                return (
                  <button key={v} type="button" role="radio" aria-checked={f.target === v} disabled={!ok} onClick={() => setF((x) => ({ ...x, target: v }))}
                    className={cx("rounded-2xl px-4 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50",
                      f.target === v ? "bg-lavender ring-2 ring-brand/60" : "bg-surface-2/70 hover:bg-surface-2")}>
                    <span className="block text-sm font-semibold text-strong">{l}</span>
                    <span className="block text-xs text-muted">{ok ? note : "Connect in Settings first"}</span>
                  </button>
                );
              })}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="SEO title" hint="≤ 70 characters"><input className="input" value={f.seo_title} onChange={set("seo_title")} maxLength={70} /></Field>
            <Field label="Custom domain (optional)" hint="e.g. offers.yourbrand.com"><input className="input" value={f.custom_domain} onChange={set("custom_domain")} maxLength={253} /></Field>
          </div>
          <Field label="Search description" hint="≤ 170 characters"><input className="input" value={f.seo_description} onChange={set("seo_description")} maxLength={170} /></Field>

          <div className="rounded-2xl bg-surface-2/60 p-4">
            <p className="mb-2 text-sm font-semibold text-strong">Pre-launch checks</p>
            {!checks ? <Spinner className="size-4 text-muted" /> : (
              <ul className="space-y-1.5 text-sm">
                {checks.map((c) => (
                  <li key={c.key} className="flex items-center gap-2">
                    {c.ok ? <CheckCircle2 className="size-4 text-brand" /> : c.level === "blocker" ? <XCircle className="size-4 text-danger" /> : <AlertTriangle className="size-4 text-warm" />}
                    <span className={cx(c.ok ? "text-ink" : c.level === "blocker" ? "font-medium text-danger" : "text-warm")}>{c.message}</span>
                    {!c.ok && c.key === "title" && f.seo_title && <span className="text-xs text-faint">(fixed by the SEO title above)</span>}
                    {!c.ok && c.key === "description" && f.seo_description && <span className="text-xs text-faint">(fixed by the description above)</span>}
                  </li>
                ))}
              </ul>
            )}
            {blockers.length > 0 && <p className="mt-2 text-xs text-danger">Fix the red items (e.g. add a lead form with a phone or email field) before publishing.</p>}
          </div>
          {error && <p className="rounded-xl bg-danger/10 px-4 py-2 text-sm text-danger">{error}</p>}
          <div className="flex justify-end">
            <Button type="submit" busy={busy} disabled={!checks || blockers.length > 0}><Rocket className="size-4" /> {site.published ? "Republish" : "Publish now"}</Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
