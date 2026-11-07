// Results report: what was spent, what it brought, which campaign is best and which needs attention, the week ahead.
import { cap, createReport, inr, inrShort, num, pct, periodLabel } from "./kit";

const change = (v, word) => (v === null || v === undefined ? null : `${v >= 0 ? "+" : ""}${v}% ${word}`);
const shortName = (n, biz) => (biz && n.startsWith(`${biz} - `) ? n.slice(biz.length + 3) : n);
const roi = (c) => (c.period_spend > 0 ? `${(c.revenue / c.period_spend).toFixed(1)}×` : "—");

export async function resultsReport({ data, days, business, filename }) {
  const k = data.kpis;
  const campaigns = [...(data.products || []).flatMap((p) => p.campaigns.map((c) => ({ ...c, product: p.name }))), ...(data.unassigned?.campaigns || [])]
    .sort((a, b) => (b.period_spend || 0) - (a.period_spend || 0));
  const r = await createReport({ title: "Results report", business, period: periodLabel(days) });
  r.header();

  r.kpis([
    { label: "Spent on ads", value: inr(k.spend), note: change(k.spend_change, "vs period before") },
    { label: "Leads", value: num(k.leads), note: change(k.leads_change, "vs period before"), tone: k.leads_change > 0 ? "good" : k.leads_change < 0 ? "bad" : null },
    { label: "Cost per lead", value: k.cpl ? inr(k.cpl) : "—" },
    { label: "Sales won", value: inr(k.revenue), note: k.won ? `${k.won} deal${k.won === 1 ? "" : "s"}` : null, tone: "good" },
    { label: "Return on spend", value: k.spend > 0 ? `${(k.revenue / k.spend).toFixed(1)}×` : "—" },
  ]);

  const withLeads = campaigns.filter((c) => c.leads > 0 && c.period_spend > 0);
  const best = withLeads.length ? [...withLeads].sort((a, b) => a.cpl - b.cpl)[0] : null;
  const wasting = campaigns.filter((c) => c.period_spend > 0 && !c.leads).sort((a, b) => b.period_spend - a.period_spend)[0];
  const worst = wasting || (withLeads.length > 1 ? [...withLeads].sort((a, b) => b.cpl - a.cpl)[0] : null);
  const topSpend = campaigns[0];

  r.section("At a glance");
  r.takeaways([
    topSpend && k.spend > 0 ? `“${topSpend.name}” took ${pct(topSpend.period_spend, k.spend)}% of the spend (${inr(topSpend.period_spend)}) and brought ${topSpend.leads} lead${topSpend.leads === 1 ? "" : "s"}.` : "",
    best ? `Cheapest leads: “${best.name}” at ${inr(best.cpl)} a lead${data.account_cpl && best.cpl < data.account_cpl ? `, below your usual ${inr(data.account_cpl)}` : ""}.` : "",
    wasting ? `“${wasting.name}” spent ${inr(wasting.period_spend)} with no leads.` : "",
    k.revenue > 0 && k.spend > 0 ? `Every ₹1 spent brought back ₹${(k.revenue / k.spend).toFixed(2)} in won sales.` : k.spend > 0 && !k.won ? "No sale is marked won yet in this period. Mark won leads in Leads to see the return." : "",
    k.hot ? `${k.hot} hot lead${k.hot === 1 ? " is" : "s are"} waiting for a call.` : "",
  ]);

  if (best || worst) {
    r.callouts([
      best && { title: "Best campaign", tone: "good", text: `${best.name}\n${inr(best.cpl)} a lead · ${best.leads} leads from ${inr(best.period_spend)}` },
      worst && worst !== best && { title: "Needs attention", tone: "bad", text: `${worst.name}\n${worst.leads ? `${inr(worst.cpl)} a lead · ${worst.leads} leads` : "No leads"} from ${inr(worst.period_spend)}` },
    ]);
  }

  r.section("Spend by campaign");
  r.bars({ items: campaigns.filter((c) => c.period_spend > 0).slice(0, 8).map((c) => ({ label: shortName(c.name, business), value: c.period_spend, display: `${inrShort(c.period_spend)} · ${c.leads} lead${c.leads === 1 ? "" : "s"}` })), fmt: inrShort });

  r.section("Every campaign", "Sorted by spend in this period.");
  r.table({
    columns: [{ label: "Campaign" }, { label: "Platform" }, { label: "Status" }, { label: "Spent", align: "right" }, { label: "Leads", align: "right" }, { label: "Cost per lead", align: "right" }, { label: "Won", align: "right" }, { label: "ROI", align: "right" }],
    rows: campaigns.map((c) => [c.name, cap(c.platform), cap(c.status), inr(c.period_spend), num(c.leads), c.leads ? inr(c.cpl) : "—", c.period_spend > 0 || c.revenue ? inr(c.revenue || 0) : "—", roi(c)]),
  });

  const p = data.plan;
  if (p) {
    r.section("Next 7 days", "If spending and results keep their current pace.");
    r.kpis([
      { label: "Expected leads", value: p.leads_next_7 ? p.leads_next_7.toFixed(p.leads_next_7 < 10 ? 1 : 0) : "0" },
      { label: "Expected spend", value: inr(p.spend_next_7), note: p.planned_budget_7 ? `Budgets allow ${inr(p.planned_budget_7)}` : null },
      { label: "Cost per lead", value: p.cpl_next_7 && p.leads_next_7 ? inr(p.cpl_next_7) : "—" },
    ]);
  }

  const recs = (data.recommendations || []).slice(0, 4);
  if (recs.length) {
    r.section("What to do next");
    r.takeaways(recs.map((x) => `${x.title}. ${x.why || ""}`.trim()));
  }
  r.save(filename);
}
