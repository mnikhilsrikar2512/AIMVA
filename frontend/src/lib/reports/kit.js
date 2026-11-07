// A small kit for AIMVA's PDF reports. Every report is drawn on purpose with jsPDF (text, lines, rectangles), never a
// picture or print of the web page. jsPDF and the fonts load only when someone downloads a PDF.
// Noto Sans (a Latin + ₹ subset in src/assets) is embedded because the PDF's built-in fonts can't draw ₹.
import { downloadBlob } from "../exporters";
import { parseServerDate } from "../hooks";

export const BRAND = [163, 77, 34];
const INK = [30, 25, 19], BODY = [56, 48, 42], MUTED = [103, 93, 82], LINE = [226, 218, 207], PANEL = [249, 245, 239];
const TINT = [236, 214, 200]; // pale brand, for chart tracks and second series

/* ---- numbers and dates, in the app's Indian format --------------------------------------------------- */
export const num = (v) => (v === null || v === undefined || Number.isNaN(Number(v)) ? "—" : Math.round(Number(v)).toLocaleString("en-IN"));
export const inr = (v) => (v === null || v === undefined || Number.isNaN(Number(v)) ? "—" : `₹${Math.round(Number(v)).toLocaleString("en-IN")}`);
export const inrShort = (v) => {
  const n = Number(v) || 0;
  if (n >= 1e7) return `₹${+(n / 1e7).toFixed(1)} Cr`;
  if (n >= 1e5) return `₹${+(n / 1e5).toFixed(1)} L`;
  if (n >= 1e3) return `₹${+(n / 1e3).toFixed(1)}k`;
  return `₹${Math.round(n)}`;
};
export const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);
const asDate = (d) => (d instanceof Date ? d : typeof d === "string" && d.length > 10 ? parseServerDate(d) : new Date(`${d}T00:00:00`));
export const day = (d) => asDate(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
export const dayShort = (d) => asDate(d).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
export const dateTime = (d) => { const x = asDate(d); return x.toLocaleString("en-IN", { day: "numeric", month: "short", ...(x.getFullYear() !== new Date().getFullYear() && { year: "numeric" }), hour: "numeric", minute: "2-digit" }); };
export const periodLabel = (days) => {
  const end = new Date(), start = new Date(Date.now() - (Number(days) - 1) * 86400000);
  return `Last ${days} days · ${dayShort(start)} – ${day(end)}`;
};
export const cap = (s) => (s ? String(s).charAt(0).toUpperCase() + String(s).slice(1) : "");

/* ---- loading ----------------------------------------------------------------------------------------- */
let fontsB64 = null;
async function loadFonts() {
  if (fontsB64) return fontsB64;
  const [{ default: reg }, { default: bold }] = await Promise.all([import("../../assets/NotoSans-400Regular.ttf?url"), import("../../assets/NotoSans-700Bold.ttf?url")]);
  const b64 = async (url) => {
    const bytes = new Uint8Array(await (await fetch(url)).arrayBuffer());
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(bin);
  };
  fontsB64 = await Promise.all([b64(reg), b64(bold)]);
  return fontsB64;
}

/**
 * const r = await createReport({ title, business, period });  ...draw...  r.save("AIMVA Leads 2026-11-07.pdf")
 * Methods draw at the current position (r.y) and move it down; each starts a new page when it would not fit.
 */
export async function createReport({ title, business, period, landscape = false }) {
  const [{ jsPDF }, { autoTable }, [reg, bold]] = await Promise.all([import("jspdf"), import("jspdf-autotable"), loadFonts()]);
  const doc = new jsPDF({ orientation: landscape ? "landscape" : "portrait", unit: "pt", format: "a4" });
  doc.addFileToVFS("NotoSans-Regular.ttf", reg); doc.addFont("NotoSans-Regular.ttf", "Noto", "normal");
  doc.addFileToVFS("NotoSans-Bold.ttf", bold); doc.addFont("NotoSans-Bold.ttf", "Noto", "bold");
  doc.setProperties({ title: `${title} · ${business}`, creator: "AIMVA" });
  const W = doc.internal.pageSize.getWidth(), H = doc.internal.pageSize.getHeight(), M = 48, FOOT = 40;
  const r = { doc, W, H, M, y: M, inner: W - 2 * M };
  const font = (style, size, color) => { doc.setFont("Noto", style); doc.setFontSize(size); doc.setTextColor(...color); };
  r.font = font;

  r.fits = (h) => r.y + h <= H - FOOT - 8;
  r.ensure = (h) => { if (!r.fits(h)) { doc.addPage(); r.y = M; } };
  r.gap = (h = 16) => { r.y += h; };

  /* Cover header: wordmark, report name, business, period, when it was made. */
  r.header = () => {
    font("bold", 10, BRAND); doc.text("AIMVA", M, r.y + 2);
    font("normal", 8.5, MUTED); doc.text(`Generated ${day(new Date())}, ${new Date().toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}`, W - M, r.y + 2, { align: "right" });
    r.y += 34;
    font("bold", 24, INK); doc.text(title, M, r.y);
    r.y += 22;
    font("normal", 12, BODY); doc.text(business || "", M, r.y);
    if (period) { r.y += 16; font("normal", 9.5, MUTED); doc.text(period, M, r.y); }
    r.y += 16;
    doc.setDrawColor(...BRAND); doc.setLineWidth(1.5); doc.line(M, r.y, M + 36, r.y);
    doc.setDrawColor(...LINE); doc.setLineWidth(0.6); doc.line(M + 40, r.y, W - M, r.y);
    r.y += 26;
  };

  r.section = (heading, sub) => {
    r.ensure(sub ? 130 : 116); // keep a heading with the start of what follows
    font("bold", 13, INK); doc.text(heading, M, r.y);
    r.y += sub ? 14 : 16;
    if (sub) { font("normal", 9, MUTED); doc.text(sub, M, r.y); r.y += 16; }
  };

  /* 3–5 big numbers in a row on a soft panel. items: [{ label, value, note? }] */
  r.kpis = (items) => {
    const list = items.filter(Boolean).slice(0, 5); if (!list.length) return;
    const h = list.some((k) => k.note) ? 66 : 54;
    r.ensure(h + 8);
    doc.setFillColor(...PANEL); doc.roundedRect(M, r.y, r.inner, h, 8, 8, "F");
    const cw = r.inner / list.length;
    list.forEach((k, i) => {
      const x = M + 16 + i * cw;
      font("bold", 17, INK); doc.text(String(k.value), x, r.y + 24, { maxWidth: cw - 20 });
      font("normal", 8.5, MUTED); doc.text(k.label, x, r.y + 39, { maxWidth: cw - 20 });
      if (k.note) { font("normal", 8, k.tone === "bad" ? [176, 48, 48] : k.tone === "good" ? [33, 120, 74] : MUTED); doc.text(k.note, x, r.y + 52, { maxWidth: cw - 20 }); }
    });
    r.y += h + 18;
  };

  /* Plain-English findings with a brand dot. Empty strings are skipped. */
  r.takeaways = (lines) => {
    const list = lines.filter(Boolean); if (!list.length) return;
    font("normal", 10.5, BODY);
    for (const line of list) {
      const wrapped = doc.splitTextToSize(line, r.inner - 16);
      r.ensure(wrapped.length * 14 + 6);
      doc.setFillColor(...BRAND); doc.circle(M + 3, r.y - 3.5, 2.2, "F");
      font("normal", 10.5, BODY); doc.text(wrapped, M + 14, r.y);
      r.y += wrapped.length * 14 + 6;
    }
    r.y += 10;
  };

  /* Fit a label in a width; keep a trailing "(Meta)" so similar names stay distinguishable. */
  const fit = (text, w) => {
    text = String(text);
    if (doc.getTextWidth(text) <= w) return text;
    const tail = (text.match(/\s*\([^)]*\)$/) || [""])[0];
    let head = text.slice(0, text.length - tail.length);
    while (head.length > 1 && doc.getTextWidth(`${head}…${tail}`) > w) head = head.slice(0, -1);
    return `${head.trimEnd()}…${tail}`;
  };

  /* Horizontal bars. Draws at (x, y) within width w and returns its height; does not move r.y. */
  const bars = ({ title: t, items, fmt = num, color = BRAND }, x, y, w) => {
    let yy = y;
    if (t) { font("bold", 10, INK); doc.text(t, x, yy); yy += 14; }
    if (!items.length) { font("normal", 9, MUTED); doc.text("Nothing yet.", x, yy + 2); return yy + 10 - y; }
    const max = Math.max(...items.map((i) => i.value), 1), labelW = w > 300 ? Math.min(210, w * 0.4) : Math.min(110, w * 0.3);
    font("bold", 9, INK);
    const valueW = Math.max(28, ...items.map((it) => doc.getTextWidth(String(it.display ?? fmt(it.value))))) + 10, barW = w - labelW - valueW;
    for (const it of items) {
      font("normal", 9, BODY); doc.text(fit(it.label, labelW - 8), x, yy + 8);
      doc.setFillColor(...PANEL); doc.roundedRect(x + labelW, yy, barW, 10, 2, 2, "F");
      const bw = Math.max(it.value > 0 ? 3 : 0, (it.value / max) * barW);
      if (bw) { doc.setFillColor(...(it.color || color)); doc.roundedRect(x + labelW, yy, bw, 10, 2, 2, "F"); }
      font("bold", 9, INK); doc.text(String(it.display ?? fmt(it.value)), x + labelW + barW + 8, yy + 8);
      yy += 17;
    }
    return yy - y;
  };
  r.bars = (opts) => { const h = 14 + Math.max(1, opts.items.length) * 17; r.ensure(h + 10); r.y += bars(opts, M, r.y, r.inner) + 14; };
  /* Two bar charts side by side. */
  r.barsPair = (a, b) => {
    const h = 14 + Math.max(1, a.items.length, b.items.length) * 17; r.ensure(h + 10);
    const half = (r.inner - 28) / 2;
    const ha = bars(a, M, r.y, half), hb = bars(b, M + half + 28, r.y, half);
    r.y += Math.max(ha, hb) + 16;
  };

  /* A line over time with labelled axes. points: [{ label, value }] */
  r.line = ({ title: t, points, fmt = num, height = 150 }) => {
    r.ensure(height + 46);
    if (t) { font("bold", 10, INK); doc.text(t, M, r.y); r.y += 12; }
    const top = r.y + 6, axisW = 34, x0 = M + axisW, x1 = W - M, y1 = top + height, plotH = height;
    const rawMax = Math.max(...points.map((p) => p.value), 0);
    const step = rawMax <= 4 ? 1 : Math.ceil(rawMax / 4 / Math.pow(10, Math.floor(Math.log10(rawMax / 4)))) * Math.pow(10, Math.floor(Math.log10(rawMax / 4)));
    const max = Math.max(step * 4, 1);
    for (let i = 0; i <= 4; i++) {
      const yy = y1 - (i / 4) * plotH;
      doc.setDrawColor(...LINE); doc.setLineWidth(0.5); doc.line(x0, yy, x1, yy);
      font("normal", 7.5, MUTED); doc.text(fmt((max / 4) * i), x0 - 6, yy + 2.5, { align: "right" });
    }
    const n = points.length, xs = (i) => x0 + (n <= 1 ? (x1 - x0) / 2 : (i / (n - 1)) * (x1 - x0)), ys = (v) => y1 - (v / max) * plotH;
    if (n > 1) {
      doc.setDrawColor(...BRAND); doc.setLineWidth(1.6); doc.setLineJoin("round");
      for (let i = 1; i < n; i++) doc.line(xs(i - 1), ys(points[i - 1].value), xs(i), ys(points[i].value));
    }
    points.forEach((p, i) => { if (p.value > 0) { doc.setFillColor(...BRAND); doc.circle(xs(i), ys(p.value), 1.8, "F"); } });
    const every = Math.max(1, Math.ceil(n / 7));
    font("normal", 7.5, MUTED);
    points.forEach((p, i) => { if (i % every === 0 || i === n - 1) doc.text(p.label, xs(i), y1 + 12, { align: i === 0 ? "left" : i === n - 1 ? "right" : "center" }); });
    r.y = y1 + 30;
  };

  /* Side-by-side boxes for "best" and "needs attention". items: [{ title, text, tone: "good" | "bad" }] */
  r.callouts = (items) => {
    const list = items.filter(Boolean); if (!list.length) return;
    const w = (r.inner - 16 * (list.length - 1)) / list.length;
    font("normal", 9.5, BODY);
    const heights = list.map((c) => 30 + doc.splitTextToSize(c.text, w - 26).length * 13);
    const h = Math.max(...heights); r.ensure(h + 10);
    list.forEach((c, i) => {
      const x = M + i * (w + 16), accent = c.tone === "bad" ? [176, 48, 48] : [33, 120, 74];
      doc.setFillColor(...PANEL); doc.roundedRect(x, r.y, w, h, 6, 6, "F");
      doc.setFillColor(...accent); doc.rect(x, r.y + 8, 3, h - 16, "F");
      font("bold", 8.5, accent); doc.text(c.title.toUpperCase(), x + 14, r.y + 18);
      font("normal", 9.5, BODY); doc.text(doc.splitTextToSize(c.text, w - 26), x + 14, r.y + 33);
    });
    r.y += h + 20;
  };

  /* columns: [{ label, align?: "right", width? }]; rows: arrays of strings */
  r.table = ({ columns, rows, empty = "Nothing here yet." }) => {
    r.ensure(60);
    autoTable(doc, {
      startY: r.y, margin: { left: M, right: M, top: M, bottom: FOOT + 12 },
      head: [columns.map((c) => c.label)],
      body: rows.length ? rows : [[{ content: empty, colSpan: columns.length, styles: { halign: "center", textColor: MUTED } }]],
      styles: { font: "Noto", fontSize: 9, cellPadding: { top: 5, bottom: 5, left: 6, right: 6 }, textColor: INK, lineColor: LINE, lineWidth: { bottom: 0.5 }, overflow: "linebreak", valign: "middle" },
      headStyles: { font: "Noto", fontStyle: "bold", fillColor: BRAND, textColor: 255, fontSize: 8.5 },
      alternateRowStyles: { fillColor: PANEL },
      columnStyles: Object.fromEntries(columns.map((c, i) => [i, { ...(c.align ? { halign: c.align } : {}), ...(c.width ? { cellWidth: c.width } : {}) }])),
    });
    r.y = doc.lastAutoTable.finalY + 22;
  };

  r.note = (text) => { font("normal", 8.5, MUTED); const l = doc.splitTextToSize(text, r.inner); r.ensure(l.length * 11 + 4); doc.text(l, M, r.y); r.y += l.length * 11 + 10; };

  /* Footer on every page, then download. */
  r.save = (filename) => {
    const pages = doc.getNumberOfPages();
    for (let i = 1; i <= pages; i++) {
      doc.setPage(i);
      doc.setDrawColor(...LINE); doc.setLineWidth(0.5); doc.line(M, H - FOOT + 4, W - M, H - FOOT + 4);
      font("normal", 8, MUTED);
      doc.text(`AIMVA · ${business || ""} · ${title}`, M, H - FOOT + 18);
      doc.text(`Page ${i} of ${pages}`, W - M, H - FOOT + 18, { align: "right" });
    }
    downloadBlob(doc.output("blob"), filename);
  };
  return r;
}
