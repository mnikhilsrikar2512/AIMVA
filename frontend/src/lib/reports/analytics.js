// Analytics report: the trend, where leads come from, how pages turn visits into leads, where the money went.
import { cap, createReport, dayShort, inr, inrShort, num, pct, periodLabel } from "./kit";
import { get } from "../api";

export async function analyticsReport({ data, days, business, filename }) {
  const k = data.kpis;
  // Pages and their leads live in Results and Leads; fetch them so the report can show visits → leads per page.
  const [overview, leads] = await Promise.all([get(`/api/command/overview?days=${days}`).catch(() => null), get("/api/leads").catch(() => [])]);
  const pages = overview ? [...overview.products.flatMap((p) => p.pages), ...overview.unassigned.pages] : [];
  const slug = (u) => (u || "").split("/s/")[1] || "";
  const pageRows = pages.map((p) => {
    const n = leads.filter((l) => l.source === "website" && l.source_ref && l.source_ref === slug(p.url)).length;
    return { name: p.name, live: p.published, visits: p.visits || 0, leads: n };
  }).sort((a, b) => b.visits - a.visits);

  const r = await createReport({ title: "Analytics report", business, period: periodLabel(days) });
  r.header();
  r.kpis([
    { label: "Leads", value: num(k.leads), note: k.leads_change === null || k.leads_change === undefined ? null : `${k.leads_change >= 0 ? "+" : ""}${k.leads_change}% vs period before`, tone: k.leads_change > 0 ? "good" : k.leads_change < 0 ? "bad" : null },
    { label: "Hot leads", value: num(k.hot_leads), note: `Average score ${k.avg_score ?? "—"}` },
    { label: "Cost per lead", value: k.cpl ? inr(k.cpl) : "—", note: k.spend ? `${inr(k.spend)} spent` : null },
    { label: "Calls answered", value: num(k.calls) },
    { label: "Page conversion", value: k.site_visits ? `${k.conversion}%` : "—", note: k.site_visits ? `${num(k.site_visits)} visits` : null },
  ]);

  const series = data.series || [];
  const busiest = series.reduce((b, s) => (s.leads > (b?.leads || 0) ? s : b), null);
  const activeDays = series.filter((s) => s.leads > 0).length;
  const src = [...(data.by_source || [])].sort((a, b) => b.count - a.count);
  const totalSrc = src.reduce((s, x) => s + x.count, 0);
  const bestPage = pageRows.filter((p) => p.visits >= 20).sort((a, b) => b.leads / b.visits - a.leads / a.visits)[0];
  const funnel = Object.fromEntries((data.funnel || []).map((f) => [f.stage, f.count]));
  const reached = (funnel.qualified || 0) + (funnel.won || 0);

  r.section("At a glance");
  r.takeaways([
    src[0] && totalSrc ? `${cap(src[0].source)} is the top source: ${src[0].count} of ${totalSrc} leads (${pct(src[0].count, totalSrc)}%).` : "",
    busiest && busiest.leads > 1 ? `The busiest day was ${dayShort(busiest.date)} with ${busiest.leads} leads. Leads came in on ${activeDays} of the last ${series.length} days.` : "",
    k.leads_change !== null && k.leads_change !== undefined ? `Leads are ${k.leads_change >= 0 ? "up" : "down"} ${Math.abs(k.leads_change)}% on the ${days} days before.` : "",
    bestPage && bestPage.leads ? `“${bestPage.name}” turns ${((bestPage.leads / bestPage.visits) * 100).toFixed(1)}% of visitors into leads (${bestPage.leads} from ${num(bestPage.visits)} visits).` : "",
    k.leads ? `${reached} of ${k.leads} leads (${pct(reached, k.leads)}%) reached qualified or won.` : "",
  ]);

  r.section("Leads per day");
  r.line({ points: series.map((s) => ({ label: dayShort(s.date), value: s.leads })) });

  r.section("Where leads come from, and how far they get");
  r.barsPair(
    { title: "Top sources", items: src.slice(0, 6).map((s) => ({ label: cap(s.source), value: s.count, display: `${s.count} · ${pct(s.count, totalSrc)}%` })) },
    { title: "Pipeline", items: (data.funnel || []).map((f) => ({ label: cap(f.stage), value: f.count })) },
  );

  r.section("Pages: visits to leads", "Visits since each page went live, and the leads its form brought.");
  r.table({
    columns: [{ label: "Page" }, { label: "Status" }, { label: "Visits", align: "right" }, { label: "Leads", align: "right" }, { label: "Conversion", align: "right" }],
    rows: pageRows.map((p) => [p.name, p.live ? "Live" : "Draft", num(p.visits), num(p.leads), p.visits ? `${((p.leads / p.visits) * 100).toFixed(1)}%` : "—"]),
    empty: "No pages yet.",
  });

  const camps = [...(data.campaigns || [])].sort((a, b) => b.spend - a.spend);
  if (camps.length) {
    r.section("Where the money went");
    r.bars({ items: camps.filter((c) => c.spend > 0).slice(0, 8).map((c) => ({ label: business && c.name.startsWith(`${business} - `) ? c.name.slice(business.length + 3) : c.name, value: c.spend, display: inrShort(c.spend) })), fmt: inrShort });
    r.table({
      columns: [{ label: "Campaign" }, { label: "Platform" }, { label: "Spent", align: "right" }, { label: "Clicks", align: "right" }, { label: "Click rate", align: "right" }],
      rows: camps.map((c) => [c.name, cap(c.platform), inr(c.spend), num(c.clicks), c.impressions ? `${((c.clicks / c.impressions) * 100).toFixed(1)}%` : "—"]),
    });
  }
  r.save(filename);
}
