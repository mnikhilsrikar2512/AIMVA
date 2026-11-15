// Leads report: who asked, where from, who to call first, then everyone (respecting the filters on screen).
import { cap, createReport, dateTime, day, inr, num, pct } from "./kit";
import { parseServerDate } from "../hooks";

const STAGES = ["new", "contacted", "qualified", "won", "lost"];
const STAGE_COLOR = { new: [15, 40, 47], contacted: [0, 105, 107], qualified: [161, 92, 0], won: [0, 163, 164], lost: [169, 184, 187] };

export async function leadsReport({ leads, business, filters = {}, filename }) {
  const filtered = Object.entries(filters).filter(([, v]) => v);
  const period = filtered.length
    ? `Filtered: ${filtered.map(([k, v]) => (k === "q" ? `“${v}”` : `${k} ${v}`)).join(", ")} · as of ${day(new Date())}`
    : `All leads as of ${day(new Date())}`;
  const r = await createReport({ title: "Leads report", business, period });
  r.header();

  const total = leads.length;
  const hot = leads.filter((l) => l.score >= 70);
  const hotWaiting = hot.filter((l) => l.stage === "new" || l.stage === "contacted").sort((a, b) => b.score - a.score);
  const won = leads.filter((l) => l.stage === "won");
  const wonValue = won.reduce((s, l) => s + (l.value || 0), 0);
  const avgScore = total ? Math.round(leads.reduce((s, l) => s + (l.score || 0), 0) / total) : 0;
  const bySource = Object.entries(leads.reduce((m, l) => ({ ...m, [l.source]: (m[l.source] || 0) + 1 }), {})).sort((a, b) => b[1] - a[1]);
  const now = Date.now(), wk = 7 * 86400000;
  const at = (l) => parseServerDate(l.created_at).getTime();
  const thisWeek = leads.filter((l) => now - at(l) < wk).length, lastWeek = leads.filter((l) => now - at(l) >= wk && now - at(l) < 2 * wk).length;

  r.kpis([
    { label: "Leads", value: num(total), note: thisWeek || lastWeek ? `${thisWeek} in the last 7 days` : null },
    { label: "Hot (score 70+)", value: num(hot.length) },
    { label: "Average score", value: total ? avgScore : "—" },
    { label: "Won", value: num(won.length), note: wonValue ? `${inr(wonValue)} in deals` : null, tone: "good" },
  ]);

  r.section("At a glance");
  const top = bySource[0];
  const stale = leads.filter((l) => l.stage === "new" && now - at(l) > 2 * 86400000).length;
  r.takeaways([
    top && total ? `${cap(top[0])} brought the most leads: ${top[1]} of ${total} (${pct(top[1], total)}%).` : "",
    hotWaiting.length ? `${hotWaiting.length} hot lead${hotWaiting.length === 1 ? " is" : "s are"} still ${hotWaiting.every((l) => l.stage === "new") ? "marked new" : "waiting for a reply"}. Call ${hotWaiting.length === 1 ? "them" : "them"} first: they are listed below.` : hot.length ? "Every hot lead has been followed up." : "",
    stale ? `${stale} lead${stale === 1 ? " has" : "s have"} been marked new for more than 2 days.` : "",
    thisWeek !== lastWeek && (thisWeek || lastWeek) ? `${thisWeek} lead${thisWeek === 1 ? "" : "s"} came in the last 7 days, ${thisWeek > lastWeek ? "up" : "down"} from ${lastWeek} the week before.` : "",
    won.length ? `${won.length} won (${pct(won.length, total)}% of leads)${wonValue ? `, worth ${inr(wonValue)}` : ""}.` : "",
  ]);

  r.section("Where they are and where they came from");
  r.barsPair(
    { title: "By stage", items: STAGES.map((s) => ({ label: cap(s), value: leads.filter((l) => l.stage === s).length, color: STAGE_COLOR[s] })) },
    { title: "By source", items: bySource.slice(0, 6).map(([s, n]) => ({ label: cap(s), value: n })) },
  );

  r.section("Call these first", hotWaiting.length ? "Hot leads (score 70+) that are new or waiting for a reply, highest score first." : null);
  r.table({
    columns: [{ label: "Name" }, { label: "Phone" }, { label: "Source" }, { label: "Score", align: "right" }, { label: "Stage" }, { label: "Arrived" }],
    rows: hotWaiting.map((l) => [l.name || l.email || "—", l.phone || "—", cap(l.source), String(l.score), cap(l.stage), dateTime(l.created_at)]),
    empty: hot.length ? "No hot lead is waiting. Nice work." : "No hot leads yet.",
  });

  r.section(`All leads (${total})`, filtered.length ? "Only the leads that match the filters on screen." : "Newest first.");
  r.table({
    columns: [{ label: "Name" }, { label: "Phone" }, { label: "Source" }, { label: "Score", align: "right" }, { label: "Stage" }, { label: "Arrived" }],
    rows: [...leads].sort((a, b) => at(b) - at(a)).map((l) => [l.name || l.email || "—", l.phone || l.email || "—", cap(l.source), String(l.score), cap(l.stage), dateTime(l.created_at)]),
  });
  r.save(filename);
}
