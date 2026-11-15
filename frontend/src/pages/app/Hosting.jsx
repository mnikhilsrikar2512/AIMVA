import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, CloudUpload, ExternalLink, Globe2, Server } from "lucide-react";
import { Button, Card, Chip, Empty, Field, Modal, PageHeader, ListSkeleton } from "../../components/ui";
import { LoadError } from "../../components/LoadError";
import { get, patch, post } from "../../lib/api";
import { useAction, useApi } from "../../lib/hooks";

const TARGETS = [
  { id: "aimva", label: "AIMVA hosting", note: "Instant, free" },
  { id: "netlify", label: "Netlify", note: "Needs Netlify token" },
  { id: "vercel", label: "Vercel", note: "Needs Vercel token" },
];

export default function Hosting() {
  const { data: sites, setData, loading, error: sitesError, reload } = useApi("/api/sites", []);
  const { data: integrations } = useApi("/api/integrations", []);
  const [domainSite, setDomainSite] = useState(null);
  const [busy, run] = useAction();
  const [deploying, setDeploying] = useState("");
  const connected = new Set(integrations.filter((i) => i.connected).map((i) => i.provider));
  const update = (s) => setData((all) => all.map((x) => (x.id === s.id ? { ...x, ...s } : x)));

  return (
    <div>
      <PageHeader icon={Server} tone="blue" title="Domains and deploys" subtitle="Put your pages online on AIMVA, your own domain, Netlify or Vercel." />
      <div className="card mb-6 grid gap-y-3 p-4 sm:grid-cols-3 sm:divide-x sm:divide-line sm:p-5">
        {TARGETS.map((t) => (
          <div key={t.id} className="flex items-center justify-between gap-3 px-1 sm:px-5">
            <div>
              <p className="font-semibold text-strong">{t.label}</p>
              <p className="text-xs text-muted">{t.note}</p>
            </div>
            {t.id === "aimva" || connected.has(t.id) ? <Chip tone="green">Ready</Chip> :
              <Link to="/app/settings?tab=integrations" className="btn-ghost btn-sm">Connect</Link>}
          </div>
        ))}
      </div>
      <Card className="p-0 sm:p-0">
        {loading ? <ListSkeleton /> : sitesError && sites.length === 0 ? (
          <LoadError error={sitesError} what="your pages" onRetry={reload} />
        ) : sites.length === 0 ? (
          <Empty icon={Globe2} title="Nothing to put online yet" text="Make a page first. Then publish it here on AIMVA, your own domain, Netlify or Vercel." action={<Link to="/app/websites" className="btn-primary">Make a page</Link>} />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-stack w-full text-sm lg:min-w-[720px]">
              <thead className="text-left text-xs uppercase tracking-wide text-faint">
                <tr className="border-b border-line">
                  <th className="px-5 py-3 font-medium">Site</th><th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Live URL</th><th className="px-5 py-3 font-medium">Domain</th>
                  <th className="px-5 py-3 font-medium">Deploy</th>
                </tr>
              </thead>
              <tbody>
                {sites.map((s) => (
                  <tr key={s.id} className="border-b border-line last:border-0">
                    <td className="px-5 py-4"><p className="font-semibold text-strong">{s.name}</p><p className="text-xs text-faint">{s.visits} visits</p></td>
                    <td className="px-5 py-4">
                      <motion.span key={`${s.published}-${s.deploy_target}`} className="inline-block" initial={{ scale: 0.7, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                        transition={{ type: "spring", stiffness: 380, damping: 18 }}>
                        {s.published ? <Chip tone="green">Live · {s.deploy_target}</Chip> : <Chip>Draft</Chip>}
                      </motion.span>
                    </td>
                    <td className="max-w-[220px] px-5 py-4">
                      {s.published ? <a href={s.deploy_url || s.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 truncate text-brand-2 hover:underline">
                        <span className="truncate">{(s.deploy_url || s.url).replace(/^https?:\/\//, "")}</span><ExternalLink className="size-3 shrink-0" /></a> : <span className="text-faint">—</span>}
                    </td>
                    <td className="px-5 py-4">
                      <button className="text-left text-muted hover:text-strong" onClick={() => setDomainSite(s)}>
                        {s.custom_domain ? <span className="flex flex-col gap-1">{s.custom_domain}
                          {s.domain_verified ? <Chip tone="green">Connected</Chip> : <Chip tone="amber">Not live yet</Chip>}</span>
                          : <span className="text-brand-2">Add domain</span>}
                      </button>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex gap-1.5">
                        {TARGETS.map((t) => (
                          <Button key={t.id} variant="ghost" size="sm" busy={deploying === `${t.id}:${s.id}`}
                            disabled={t.id !== "aimva" && !connected.has(t.id)}
                            onClick={async () => {
                              setDeploying(`${t.id}:${s.id}`);
                              await run(async () => update(await post(`/api/sites/${s.id}/deploy`, { target: t.id })), `Deployed to ${t.label}`);
                              setDeploying("");
                            }}>
                            <CloudUpload className="size-3.5" /> {t.label.split(" ")[0]}
                          </Button>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <DomainDialog site={domainSite} onClose={() => setDomainSite(null)} onChange={update} />
    </div>
  );
}

const PROVIDER_CNAME = { netlify: "<your-site>.netlify.app", vercel: "cname.vercel-dns.com" };

/** Add a domain, show the exact DNS record from the server, and run the DNS check that makes the domain go live. */
function DomainDialog({ site, onClose, onChange }) {
  const [domain, setDomain] = useState("");
  const [info, setInfo] = useState(null); // GET /api/sites/{id}/domain
  const [problem, setProblem] = useState("");
  const [saving, runSave] = useAction();
  const [checking, runCheck] = useAction();
  const provider = PROVIDER_CNAME[site?.deploy_target] && site?.published ? site.deploy_target : null;
  const saved = info?.domain || "";
  const dirty = domain !== saved;

  useEffect(() => {
    if (!site) return;
    setDomain(site.custom_domain || ""); setInfo(null); setProblem("");
    get(`/api/sites/${site.id}/domain`).then(setInfo).catch(() => setProblem("Couldn't load this domain's status. Close and try again."));
  }, [site]);

  const sync = (d) => { setInfo(d); onChange({ id: site.id, custom_domain: d.domain, domain_verified: d.verified }); };

  const save = () => runSave(async () => {
    setProblem("");
    const s = await patch(`/api/sites/${site.id}`, { custom_domain: domain });
    onChange(s);
    setInfo(await get(`/api/sites/${site.id}/domain`));
  }, domain ? "Domain saved" : "Domain removed");

  const check = () => runCheck(async () => {
    setProblem("");
    const d = await post(`/api/sites/${site.id}/domain/verify`);
    sync(d);
    if (d.detail) setProblem(d.detail);
    else if (d.verified) toast.success(`${d.domain} is connected`);
  });

  return (
    <Modal open={!!site} onClose={onClose} title="Custom domain">
      <div className="space-y-4">
        <Field label="Domain" hint="e.g. offers.yourbrand.com">
          <div className="flex gap-2">
            <input className="input" value={domain} onChange={(e) => setDomain(e.target.value.trim().toLowerCase())} />
            <Button variant={dirty ? "primary" : "ghost"} busy={saving} disabled={!dirty} onClick={save}>{domain || !saved ? "Save" : "Remove"}</Button>
          </div>
        </Field>

        {saved && !dirty && info && (provider ? (
          <div className="rounded-2xl bg-surface-2/60 p-4 text-sm text-muted">
            <p className="mb-2 font-semibold text-ink">DNS setup</p>
            <p>At your domain registrar, add this record, then add <b>{saved}</b> in your {provider === "netlify" ? "Netlify" : "Vercel"} dashboard so it issues HTTPS:</p>
            <RecordTable records={[{ type: "CNAME", name: saved.split(".")[0], value: PROVIDER_CNAME[provider] }]} />
          </div>
        ) : info.verified ? (
          <div className="flex items-start gap-2.5 rounded-2xl bg-lavender p-4 text-sm text-brand">
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand" />
            <div>
              <p className="font-semibold">{saved} points to AIMVA.</p>
              {info.published ? <a href={info.url} target="_blank" rel="noreferrer" className="text-brand-2 hover:underline">Open {saved}</a>
                : <p>Publish this site on AIMVA hosting and it will show on your domain.</p>}
              <p className="mt-1 text-xs">The secure (https) certificate is issued on the first visit, which can take a minute.</p>
            </div>
          </div>
        ) : info.setup_issue ? (
          <div className="flex items-start gap-2.5 rounded-2xl bg-warm-soft p-4 text-sm text-warm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warm" /><p>{info.setup_issue}</p>
          </div>
        ) : (
          <div className="rounded-2xl bg-surface-2/60 p-4 text-sm text-muted">
            <p className="mb-2 font-semibold text-ink">DNS setup</p>
            <p>At your domain registrar (GoDaddy, Hostinger, Cloudflare…), add:</p>
            <RecordTable records={info.records} />
            <p className="mt-2 text-xs">Changes can take up to an hour. On Cloudflare, set the record to DNS only (grey cloud).</p>
            {!info.published && <p className="mt-1 text-xs">This site isn't published yet. Publish it on AIMVA hosting so the domain has something to show.</p>}
          </div>
        ))}

        {problem && <p className="rounded-xl bg-warm-soft px-3 py-2 text-sm text-warm">{problem}</p>}

        {saved && !dirty && info?.target_ready && !provider && !info.verified && (
          <Button busy={checking} onClick={check}>Check DNS</Button>
        )}
      </div>
    </Modal>
  );
}

function RecordTable({ records }) {
  return (
    <div className="mt-2 overflow-x-auto rounded-lg bg-black/40 p-3 text-xs text-ink">
      <table className="w-full font-mono">
        <thead className="text-left text-muted"><tr><th className="pr-4 font-normal">Type</th><th className="pr-4 font-normal">Name</th><th className="font-normal">Value</th></tr></thead>
        <tbody>{records.map((r) => (
          <tr key={`${r.type}-${r.value}`}><td className="pr-4">{r.type}</td><td className="pr-4">{r.name}</td><td className="select-all break-all">{r.value}</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}
