import { useState } from "react";
import { BarChart3, Eye, Lightbulb, MousePointerClick, TrendingUp, Users, Wallet } from "lucide-react";
import { Area, AreaChart, Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, PageHeader, Spinner, Stat, StatStrip, Tabs } from "../../components/ui";
import { useApi } from "../../lib/hooks";
import { DownloadMenu } from "../../components/DownloadMenu";
import { useLeadEvents } from "../../lib/live";
import { useAuth } from "../../lib/auth";
import { ChartTooltip } from "./Dashboard";
import { LoadError } from "../../components/LoadError";

// Storm Green to deep cyan steps (flat, no gradients). Each source also has its name in the legend, so colour is never the only signal.
const COLORS = { website: "#0f282f", meta: "#00696b", google: "#2f8a8c", linkedin: "#5fa9ab", whatsapp: "#00a3a4", voice: "#52656a", manual: "#a9b8bb" };
const axis = { tick: { fill: "#52656a", fontSize: 12 }, axisLine: false, tickLine: false };

export default function Analytics() {
  const { user } = useAuth();
  const business = user?.workspace?.name || user?.company || user?.name || "";
  const [days, setDays] = useState("30");
  const { data, loading, reload, error } = useApi(`/api/analytics/overview?days=${days}`);
  const { data: insights, reload: reloadInsights } = useApi("/api/analytics/insights");
  useLeadEvents(() => { reload(); reloadInsights(); });
  const k = data?.kpis;

  return (
    <div>
      <PageHeader icon={BarChart3} tone="blue" title="Analytics" subtitle="Performance across every channel, with AI recommendations."
        actions={<div className="flex flex-wrap gap-2">
          <DownloadMenu name="Analytics" disabled={!k || (!k.leads && !k.spend && !data.series.some((x) => x.leads > 0))}
            excel={() => [
              { name: "Leads per day", columns: [{ key: "date", label: "Date" }, { key: "leads", label: "Leads" }], rows: data.series },
              { name: "Sources", columns: [{ key: "source", label: "Source" }, { key: "count", label: "Leads" }], rows: data.by_source },
              { name: "Pipeline", columns: [{ key: "stage", label: "Stage" }, { key: "count", label: "Leads" }], rows: data.funnel },
            ]}
            pdf={async (filename) => (await import("../../lib/reports/analytics")).analyticsReport({ data, days, business, filename })} />
          <Tabs value={days} onChange={setDays} tabs={[{ value: "7", label: "7d" }, { value: "30", label: "30d" }, { value: "90", label: "90d" }]} />
        </div>} />
      {!k && error ? <Card><LoadError error={error} what="your numbers" onRetry={reload} /></Card>
        : !k ? <div className="grid h-60 place-items-center"><Spinner className="size-6" /></div> : (
        <div className="space-y-6">
          <StatStrip>
            <Stat label={`Leads (${days}d)`} value={k.leads} icon={Users} tone="amber" sub={`${k.hot_leads} hot · avg score ${k.avg_score}`} />
            <Stat label="Cost per lead" value={k.cpl ? `₹${k.cpl.toLocaleString("en-IN")}` : "—"} icon={Wallet} tone="green" sub={`₹${k.spend.toLocaleString("en-IN")} total spend`} />
            <Stat label="ROI" value={k.roi != null ? `${k.roi}%` : "—"} icon={TrendingUp} tone="violet" sub={`₹${k.won_value.toLocaleString("en-IN")} won`} />
            <Stat label="Site conversion" value={k.site_visits ? `${k.conversion}%` : "—"} icon={MousePointerClick} tone="pink" sub={<span className="inline-flex items-center gap-1"><Eye className="size-3" /> {k.site_visits} visits</span>} />
          </StatStrip>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <h2 className="mb-4 font-semibold text-strong">Leads per day</h2>
              <div className="h-64">
                <ResponsiveContainer>
                  <AreaChart data={data.series} margin={{ left: -20, right: 8, top: 4 }}>
                                        <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} minTickGap={24} {...axis} />
                    <YAxis allowDecimals={false} {...axis} />
                    <Tooltip content={<ChartTooltip />} />
                    <Area type="monotone" dataKey="leads" name="leads" stroke="#00696b" strokeWidth={2} fill="#dafafa" fillOpacity={0.6} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card>
              <h2 className="mb-4 font-semibold text-strong">Lead sources</h2>
              {data.by_source.length === 0 ? <p className="text-sm text-muted">No leads yet.</p> : (
                <>
                  {/* The list below carries the same numbers as text, so the drawing is hidden from screen readers. */}
                  <div className="h-44" aria-hidden="true">
                    <ResponsiveContainer>
                      <PieChart accessibilityLayer={false}>
                        <Pie rootTabIndex={-1} data={data.by_source} dataKey="count" nameKey="source" innerRadius={50} outerRadius={75} paddingAngle={3} stroke="none">
                          {data.by_source.map((s) => <Cell key={s.source} fill={COLORS[s.source] || "#a9b8bb"} />)}
                        </Pie>
                        <Tooltip content={<ChartTooltip />} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <ul className="mt-3 space-y-1.5 text-sm">
                    {data.by_source.map((s) => (
                      <li key={s.source} className="flex items-center justify-between">
                        <span className="flex items-center gap-2 text-muted"><span className="size-2.5 rounded-full" style={{ background: COLORS[s.source] }} />{s.source}</span>
                        <span className="font-semibold text-strong">{s.count}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card>
              <h2 className="mb-4 font-semibold text-strong">Pipeline funnel</h2>
              <div className="h-56">
                <ResponsiveContainer>
                  <BarChart data={data.funnel} layout="vertical" margin={{ left: 10 }}>
                    <XAxis type="number" hide allowDecimals={false} />
                    <YAxis type="category" dataKey="stage" width={72} {...axis} />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                    <Bar dataKey="count" name="leads" radius={[0, 6, 6, 0]} fill="#00696b" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card>
              <h2 className="mb-4 font-semibold text-strong">Campaign spend</h2>
              {data.campaigns.length === 0 ? <p className="text-sm text-muted">No campaigns yet.</p> : (
                <div className="h-56">
                  <ResponsiveContainer>
                    <BarChart data={data.campaigns} margin={{ left: -12 }}>
                      <XAxis dataKey="name" {...axis} />
                      <YAxis {...axis} tickFormatter={(v) => (v >= 1000 ? `${+(v / 1000).toFixed(1)}k` : v)} />
                      <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                      <Bar dataKey="spend" name="Spend (₹)" radius={[6, 6, 0, 0]} fill="#0f282f" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
            <Card>
              <div className="mb-4 flex items-center gap-2"><Lightbulb className="size-4 text-warm" /><h2 className="font-semibold text-strong">AI recommendations</h2></div>
              <ol className="space-y-3">
                {(insights?.items || []).map((t, i) => (
                  <li key={i} className="flex gap-3 text-sm text-ink"><span className="grid size-6 shrink-0 place-items-center rounded-full bg-warm-soft0/15 text-xs font-bold text-warm">{i + 1}</span>{t}</li>
                ))}
              </ol>
              <p className="mt-4 text-xs text-faint">Source: {insights?.source === "ai" ? "your AI writer" : "rule engine"}</p>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
