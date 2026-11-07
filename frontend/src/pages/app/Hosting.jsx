import { useState } from "react";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { CloudUpload, ExternalLink, Globe2, Server } from "lucide-react";
import { Button, Card, Chip, Empty, Field, Modal, PageHeader, Spinner, ListSkeleton } from "../../components/ui";
import { patch, post } from "../../lib/api";
import { useAction, useApi } from "../../lib/hooks";

const TARGETS = [
  { id: "aimva", label: "AIMVA hosting", note: "Instant, free" },
  { id: "netlify", label: "Netlify", note: "Needs Netlify token" },
  { id: "vercel", label: "Vercel", note: "Needs Vercel token" },
];

export default function Hosting() {
  const { data: sites, setData, loading } = useApi("/api/sites", []);
  const { data: integrations } = useApi("/api/integrations", []);
  const [domainSite, setDomainSite] = useState(null);
  const [domain, setDomain] = useState("");
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
        {loading ? <ListSkeleton /> : sites.length === 0 ? (
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
                      <button className="text-left text-muted hover:text-strong" onClick={() => { setDomainSite(s); setDomain(s.custom_domain); }}>
                        {s.custom_domain || <span className="text-brand-2">Add domain</span>}
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
      <Modal open={!!domainSite} onClose={() => setDomainSite(null)} title="Custom domain">
        <div className="space-y-4">
          <Field label="Domain" hint="e.g. offers.yourbrand.com">
            <input className="input" value={domain} onChange={(e) => setDomain(e.target.value.trim().toLowerCase())} />
          </Field>
          <div className="rounded-2xl bg-surface-2/60 p-4 text-sm text-muted">
            <p className="mb-2 font-semibold text-ink">DNS setup</p>
            <p>At your domain registrar (GoDaddy, Google Domains, Cloudflare…), add:</p>
            <pre className="mt-2 overflow-x-auto rounded-lg bg-black/40 p-3 text-xs text-ink">{`Type   Name                  Value
CNAME  ${domain.split(".")[0] || "offers"}  ${domainSite?.deploy_target === "netlify" ? "<your-site>.netlify.app" : domainSite?.deploy_target === "vercel" ? "cname.vercel-dns.com" : "your AIMVA server host"}`}</pre>
            <p className="mt-2 text-xs">For Netlify/Vercel deploys, also add the domain in that provider's dashboard so it issues HTTPS.</p>
          </div>
          <Button busy={busy} onClick={() => run(async () => {
            update(await patch(`/api/sites/${domainSite.id}`, { custom_domain: domain }));
            setDomainSite(null);
          }, "Domain saved")}>Save domain</Button>
        </div>
      </Modal>
    </div>
  );
}
