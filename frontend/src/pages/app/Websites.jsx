import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { rise, stagger } from "../../components/Motion";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, ChevronDown, Code2, ExternalLink, FileText, Globe, History, MoreHorizontal, Plus, RefreshCw, Rocket, ShieldCheck, Trash2 } from "lucide-react";
import { Button, Card, Chip, Empty, Field, Modal, PageHeader, Spinner, Tabs, cx, ListSkeleton, JobProgress } from "../../components/ui";
import { del, get, patch, post } from "../../lib/api";
import { timeAgo, useAction, useApi } from "../../lib/hooks";
import { useAuth } from "../../lib/auth";
import { useOnboarding } from "../../components/AppLayout";
import { LibraryImagePicker } from "../../components/GenControls";
import PublishDialog from "../../components/PublishDialog";
import { ACCEPT_IMAGES, DocumentPicker, ReferenceDropzone, UploadTile } from "../../components/References";
import { BriefCoach, ImportBar, Rate, ReadinessPanel, useBriefReview } from "../../components/Quality";
import { DECORS, DirectionsButton, LayoutPicker } from "../../components/Designs";
import VisualEditor from "../../components/VisualEditor";
import { SaveTemplateButton, TemplateStrip, useTemplateTracker } from "../../components/Templates";

const TEMPLATE_KEYS = ["page_type", "layout", "decor", "look", "theme", "font", "sections", "form_fields", "contact_mode", "cta", "form_title",
  "offer", "headline", "subheadline", "features"];
const pick = (o, keys) => Object.fromEntries(keys.filter((k) => o[k] !== undefined).map((k) => [k, o[k]]));

const BLANK = {
  business: "", industry: "", audience: "", offer: "", headline: "", subheadline: "", cta: "Get a free quote",
  features: "", contact_mode: "voice_agent", voice_agent_id: null, country_code: "+91", phone: "", whatsapp: "", primary: "#6366f1", accent: "#22d3ee", hero_image: "", use_ai: true,
  writer: "auto", page_type: "lead_gen", layout: "auto", decor: "auto", look: "modern", theme: "light", font: "jakarta", language: "English",
  sections: ["features"], about: "", testimonials: [], faqs: [], pricing: [], gallery: [],
  form_fields: ["name", "phone", "email", "message"], form_title: "", thank_you: "Thanks! We'll be in touch shortly.",
  whatsapp_button: true, include_logo: false, contact_email: "", address: "", seo_title: "", seo_description: "",
  meta_pixel_id: "", ga4_id: "", references: [],
  location_line: "", palette: "auto", chips: "", stats: [], price_from: "", price_note: "", configurations: [], amenities: "",
  distances: [], approvals: "", announcement: "", map_url: "", brochure: null, gallery_captions: [],
};
const PALETTES = [["auto", "Auto"], ["brand", "My colours"], ["emerald", "Emerald & gold"], ["navy", "Navy & gold"], ["charcoal", "Charcoal"],
  ["forest", "Forest"], ["plum", "Plum"], ["slate", "Slate"]];
const PAGE_TYPES = [["lead_gen", "Lead generation"], ["product", "Product"], ["service", "Service"], ["event", "Event"],
  ["real_estate", "Real estate"], ["restaurant", "Restaurant"], ["portfolio", "Portfolio"], ["app", "App / SaaS"]];
const LOOKS = [["modern", "Modern"], ["minimal", "Minimal"], ["bold", "Bold"], ["elegant", "Elegant"], ["playful", "Playful"], ["corporate", "Corporate"]];
const FONTS = [["jakarta", "Jakarta (friendly)"], ["inter", "Inter (clean)"], ["serif", "Playfair (classic)"], ["rounded", "Nunito (rounded)"], ["grotesk", "Space Grotesk (tech)"]];
const SECTIONS = [["features", "Features"], ["about", "About"], ["gallery", "Gallery"], ["testimonials", "Testimonials"],
  ["pricing", "Pricing"], ["faq", "FAQ"], ["contact_info", "Contact details"]];
const FORM_FIELDS = [["name", "Name"], ["phone", "Phone"], ["email", "Email"], ["message", "Message"], ["city", "City"],
  ["budget", "Budget"], ["preferred_date", "Preferred date"], ["company", "Company"]];

function Pills({ options, value, onChange, multi }) {
  const on = (v) => (multi ? value.includes(v) : value === v);
  const toggle = (v) => onChange(multi ? (on(v) ? value.filter((x) => x !== v) : [...value, v]) : v);
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(([v, l]) => (
        <button key={v} type="button" onClick={() => toggle(v)} aria-pressed={on(v)}
          className={cx("rounded-full px-3 py-1.5 text-xs font-medium transition", on(v) ? "bg-strong text-white" : "bg-surface-2 text-ink hover:bg-lavender")}>
          {l}
        </button>
      ))}
    </div>
  );
}

function ListEditor({ items, onChange, blank, render, addLabel, max }) {
  return (
    <div className="space-y-2">
      {items.map((it, i) => (
        <div key={i} className="relative rounded-2xl bg-surface-2/60 p-3 pr-10">
          {render(it, (patch) => onChange(items.map((x, j) => (j === i ? { ...x, ...patch } : x))))}
          <button type="button" aria-label="Remove" onClick={() => onChange(items.filter((_, j) => j !== i))}
            className="absolute right-2 top-2 grid size-7 place-items-center rounded-full text-muted hover:bg-white hover:text-rose-600"><Trash2 className="size-3.5" /></button>
        </div>
      ))}
      {items.length < max && <button type="button" className="btn-ghost btn-sm" onClick={() => onChange([...items, { ...blank }])}><Plus className="size-3.5" /> {addLabel}</button>}
    </div>
  );
}

function AiStatus({ ai, writer, writers }) {
  if (writer && writer !== "auto" && writer !== "builtin:gemini") {
    return <span className="text-emerald-600">Written by {writers.find((w) => w.ref === writer)?.name || "your chosen AI"}.</span>;
  }
  if (writers.some((w) => w.is_default) && writer === "auto") return <span className="text-emerald-600">Using your default AI writer.</span>;
  if (ai?.source === "yours") return <span className="text-emerald-600">Using your Gemini key.</span>;
  if (ai?.source === "server") return <span className="text-emerald-600">Using AIMVA's shared Gemini key.</span>;
  if (ai?.free) return (
    <span>
      <span className="text-emerald-600">Using AIMVA free AI, no key needed.</span> It's shared and limited, so when it's busy the built-in template is used.
    </span>
  );
  return (
    <span>
      No AI writer connected yet, so the built-in template is used.{" "}
      <Link to="/app/settings?tab=providers" className="font-semibold text-brand hover:underline">Add one</Link>
    </span>
  );
}

const asLines = (v) => (Array.isArray(v) ? v.join("\n") : v || "");
const fromLines = (v) => v.split("\n").map((x) => x.trim()).filter(Boolean);

const ADD_SECTION = { about: "about", pricing: "pricing", testimonials: "testimonials" };

/** Facts for the Showcase design: every block appears only when its facts are filled in, nothing is invented. */
function ProjectDetails({ b, set, val, docs }) {
  return (
    <div className="space-y-5">
      <p className="rounded-2xl bg-lavender/60 px-4 py-3 text-sm text-ink">
        These fill the <b>Showcase</b> design: a premium page like the best project microsites. Leave anything blank and that block is simply left out.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Location line" hint="Shown above the headline"><input className="input" value={b.location_line} onChange={set("location_line")} maxLength={80} placeholder="Kollur, West Hyderabad" /></Field>
        <Field label="Approvals / registration"><input className="input" value={b.approvals} onChange={set("approvals")} maxLength={80} placeholder="HMDA & RERA approved" /></Field>
        <Field label="Starting price"><input className="input" value={b.price_from} onChange={set("price_from")} maxLength={40} placeholder="₹85 L onwards" /></Field>
        <Field label="Price note"><input className="input" value={b.price_note} onChange={set("price_note")} maxLength={80} placeholder="All inclusive, limited launch offer" /></Field>
        <Field label="Announcement bar" className="sm:col-span-2"><input className="input" value={b.announcement} onChange={set("announcement")} maxLength={140} placeholder="Phase 2 launch: site visits open this weekend" /></Field>
      </div>
      <div><p className="label">Colour palette</p><Pills options={PALETTES} value={b.palette} onChange={(v) => val("palette", v)} /></div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Quick facts under the headline" hint="One per line, up to 5"><textarea className="input" rows={3} value={b.chips} onChange={set("chips")} placeholder={"2 & 3 BHK\nGated community\nReady to move"} /></Field>
        <Field label="Amenities" hint="One per line: icons are picked automatically"><textarea className="input" rows={3} value={b.amenities} onChange={set("amenities")} placeholder={"Swimming pool\nClubhouse\n24x7 security"} /></Field>
      </div>
      <div>
        <p className="label">Key numbers <span className="font-normal text-faint">· shown as a strip under the hero</span></p>
        <ListEditor items={b.stats} onChange={(v) => val("stats", v)} blank={{ value: "", label: "" }} max={5} addLabel="Add number"
          render={(x, up) => (<div className="grid gap-2 sm:grid-cols-[140px_1fr]">
            <input className="input h-9" placeholder="30" value={x.value} maxLength={20} onChange={(e) => up({ value: e.target.value })} />
            <input className="input h-9" placeholder="Acres" value={x.label} maxLength={40} onChange={(e) => up({ label: e.target.value })} />
          </div>)} />
      </div>
      <div>
        <p className="label">Configurations / plans</p>
        <ListEditor items={b.configurations} onChange={(v) => val("configurations", v)} blank={{ name: "", area: "", details: "", price: "" }} max={6} addLabel="Add configuration"
          render={(x, up) => (<div className="grid gap-2 sm:grid-cols-3">
            <input className="input h-9" placeholder="3 BHK" value={x.name} maxLength={60} onChange={(e) => up({ name: e.target.value })} />
            <input className="input h-9" placeholder="1,650 sq ft" value={x.area} maxLength={60} onChange={(e) => up({ area: e.target.value })} />
            <input className="input h-9" placeholder="Price (blank = on request)" value={x.price} maxLength={40} onChange={(e) => up({ price: e.target.value })} />
            <input className="input h-9 sm:col-span-3" placeholder="Details: east facing, 2 car parks…" value={x.details} maxLength={240} onChange={(e) => up({ details: e.target.value })} />
          </div>)} />
      </div>
      <div>
        <p className="label">Nearby places</p>
        <ListEditor items={b.distances} onChange={(v) => val("distances", v)} blank={{ place: "", time: "" }} max={12} addLabel="Add place"
          render={(x, up) => (<div className="grid gap-2 sm:grid-cols-[1fr_120px]">
            <input className="input h-9" placeholder="Outer Ring Road" value={x.place} maxLength={80} onChange={(e) => up({ place: e.target.value })} />
            <input className="input h-9" placeholder="8 min" value={x.time} maxLength={30} onChange={(e) => up({ time: e.target.value })} />
          </div>)} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Google Maps link (optional)"><input className="input" value={b.map_url} onChange={set("map_url")} maxLength={500} placeholder="https://maps.app.goo.gl/…" /></Field>
        <Field label="Brochure" hint="Visitors get it after leaving their details. Upload PDFs under AI writer → reference files.">
          <select className="input" value={b.brochure ?? ""} onChange={(e) => val("brochure", e.target.value ? Number(e.target.value) : null)}>
            <option value="">No brochure (we'll send it on WhatsApp)</option>
            {docs.map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}
          </select>
        </Field>
      </div>
    </div>
  );
}

function BriefForm({ initial = BLANK, onSubmit, busy, submitLabel, coach = true }) {
  const { data: ai } = useApi("/api/integrations/ai/status");
  const { data: writers } = useApi("/api/providers/options?kind=text", []);
  const { data: docs, setData: setDocs } = useApi("/api/references?kind=document", []);
  const [tab, setTab] = useState("content");
  const [b, setB] = useState(() => ({
    ...BLANK, ...initial, features: asLines(initial.features), chips: asLines(initial.chips), amenities: asLines(initial.amenities),
    pricing: (initial.pricing || []).map((p) => ({ ...p, features: asLines(p.features) })),
  }));
  const set = (k) => (e) => setB((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const val = (k, v) => setB((x) => ({ ...x, [k]: v }));
  const libraryHero = /^(asset|brand):\d+$/.test(b.hero_image);
  const review = useBriefReview(b);
  const [gate, setGate] = useState(null);  // questions asked before generating (snapshot, so fields don't vanish while typing)
  const gatePassed = useRef(false);
  const highMissing = (review?.missing || []).filter((m) => m.importance === "high");

  const goTo = (m) => {
    if (ADD_SECTION[m.field]) setB((x) => ({ ...x, sections: [...new Set([...x.sections, ADD_SECTION[m.field]])] }));
    setTab(m.tab);
    setTimeout(() => document.getElementById(`brief-${m.field}`)?.focus(), 60);
  };
  const applyPlaybook = (p) => setB((x) => ({ ...x, page_type: p.page_type, cta: p.cta, form_title: p.form_title,
    form_fields: p.form_fields, sections: p.sections }));
  const applyImport = (data) => setB((x) => {
    const n = { ...x };
    for (const [k, v] of Object.entries(data)) {
      if (k === "features" || k === "amenities") n[k] = v.join("\n");
      else if (k === "faqs") { n.faqs = v; n.sections = [...new Set([...n.sections, "faq"])]; }
      else if (k === "about") { n.about = v; n.sections = [...new Set([...n.sections, "about"])]; }
      else n[k] = v;
    }
    return n;
  });

  const payload = () => ({
    ...b, features: fromLines(b.features), chips: fromLines(b.chips).slice(0, 5), amenities: fromLines(b.amenities).slice(0, 24),
    stats: b.stats.filter((x) => x.value?.trim()), distances: b.distances.filter((x) => x.place?.trim()),
    configurations: b.configurations.filter((x) => x.name?.trim()),
    testimonials: b.testimonials.filter((t) => t.name?.trim() && t.quote?.trim()),
    faqs: b.faqs.filter((f) => f.q?.trim() && f.a?.trim()),
    pricing: b.pricing.filter((p) => p.name?.trim() && p.price?.trim()).map((p) => ({ ...p, features: fromLines(p.features) })),
  });
  const tpl = useTemplateTracker("website");
  const applyTemplate = (t) => {
    tpl.apply(t);
    const p = t.payload;
    // Structure and design come from the template; business details you've typed are only filled where empty.
    setB((x) => ({ ...x, ...pick(p, ["page_type", "layout", "decor", "look", "theme", "font", "sections", "form_fields", "contact_mode", "cta"]),
      form_title: p.form_title || x.form_title, offer: x.offer || p.offer, headline: x.headline || p.headline,
      subheadline: x.subheadline || p.subheadline, features: x.features || (p.features || []).join("\n") }));
  };
  const templatePayload = () => {
    const pl = payload();
    return { ...pick(pl, TEMPLATE_KEYS), offer: "", headline: "", subheadline: "", features: [] };
  };
  const submit = (e) => {
    e?.preventDefault();
    // Ask, don't guess: the facts that change the page most are worth one quick question first.
    if (coach && highMissing.length && !gatePassed.current) { setGate(highMissing); return; }
    setGate(null);
    tpl.track(pick(payload(), TEMPLATE_KEYS));
    onSubmit(payload());
  };

  return (
    <form onSubmit={submit} className="space-y-5">
      {coach && <TemplateStrip module="website" onApply={applyTemplate} title="Start from a page template" />}
      {coach && <ImportBar onImported={applyImport} />}
      <Tabs value={tab} onChange={setTab} tabs={[{ value: "content", label: "Content" }, { value: "design", label: "Design" },
        { value: "project", label: "Project details" }, { value: "sections", label: "Sections" }, { value: "form", label: "Form & SEO" },
        { value: "ai", label: "AI writer" }]} />

      {tab === "content" && (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Business name"><input className="input" value={b.business} onChange={set("business")} required minLength={2} maxLength={120} /></Field>
            <Field label="Industry"><input className="input" value={b.industry} onChange={set("industry")} maxLength={80} placeholder="Real estate, dental, SaaS…" /></Field>
            <Field label="Target audience"><input id="brief-audience" className="input" value={b.audience} onChange={set("audience")} maxLength={160} placeholder="First-time home buyers" /></Field>
            <Field label="Offer"><input id="brief-offer" className="input" value={b.offer} onChange={set("offer")} maxLength={160} placeholder="Free site visit this weekend" /></Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Headline (optional)"><input className="input" value={b.headline} onChange={set("headline")} maxLength={200} /></Field>
            <Field label="Subheadline (optional)"><input className="input" value={b.subheadline} onChange={set("subheadline")} maxLength={300} /></Field>
          </div>
          <Field label="Key features / benefits" hint="One per line (up to 8)"><textarea id="brief-features" className="input" rows={3} value={b.features} onChange={set("features")} /></Field>
          <ContactChoice b={b} val={val} set={set} />
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Button text"><input className="input" value={b.cta} onChange={set("cta")} maxLength={60} /></Field>
            {b.contact_mode !== "voice_agent" && <Field label="Your phone number"><input id="brief-phone" className="input" type="tel" inputMode="tel" autoComplete="tel" value={b.phone} onChange={set("phone")} maxLength={30} /></Field>}
            <Field label="WhatsApp number"><input className="input" value={b.whatsapp} onChange={set("whatsapp")} maxLength={30} placeholder="+91…" /></Field>
            <Field label="Contact email"><input className="input" type="email" value={b.contact_email} onChange={set("contact_email")} maxLength={120} /></Field>
            <Field label="Address" className="sm:col-span-2"><input id="brief-address" className="input" value={b.address} onChange={set("address")} maxLength={200} /></Field>
          </div>
        </div>
      )}

      {tab === "design" && (
        <div className="space-y-4">
          <div><p className="label">Layout</p><LayoutPicker value={b.layout} onChange={(v) => val("layout", v)} /></div>
          <div><p className="label">Background</p><Pills options={DECORS} value={b.decor} onChange={(v) => val("decor", v)} /></div>
          <div><p className="label">Page type</p><Pills options={PAGE_TYPES} value={b.page_type} onChange={(v) => val("page_type", v)} /></div>
          <div><p className="label">Look</p><Pills options={LOOKS} value={b.look} onChange={(v) => val("look", v)} /></div>
          <div className="grid gap-4 sm:grid-cols-[1fr_1fr_auto_auto]">
            <Field label="Theme"><select className="input" value={b.theme} onChange={set("theme")}><option value="light">Light</option><option value="dark">Dark</option></select></Field>
            <Field label="Fonts"><select className="input" value={b.font} onChange={set("font")}>{FONTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
            <Field label="Primary"><input type="color" className="input w-16 p-1" value={b.primary} onChange={set("primary")} /></Field>
            <Field label="Accent"><input type="color" className="input w-16 p-1" value={b.accent} onChange={set("accent")} /></Field>
          </div>
          <LibraryImagePicker label="Hero image" value={libraryHero ? b.hero_image : ""} onChange={(v) => val("hero_image", v)}
            hint="Pick from your library (embedded into the page) or paste an https:// link below." />
          <input className="input" value={libraryHero ? "" : b.hero_image} onChange={set("hero_image")} placeholder="https://… (optional)" maxLength={1000} />
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-ink">
            <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-violet-500" checked={b.include_logo} onChange={set("include_logo")} /> Show my Brand Kit logo</label>
            <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-violet-500" checked={b.whatsapp_button} onChange={set("whatsapp_button")} /> Floating WhatsApp button</label>
          </div>
        </div>
      )}

      {tab === "project" && <ProjectDetails b={b} set={set} val={val} docs={docs} />}

      {tab === "sections" && (
        <div className="space-y-5">
          <div><p className="label">Sections after the hero</p><Pills multi options={SECTIONS} value={b.sections} onChange={(v) => val("sections", v)} /></div>
          {b.sections.includes("about") && <Field label="About"><textarea id="brief-about" className="input" rows={3} value={b.about} onChange={set("about")} maxLength={2000} /></Field>}
          {b.sections.includes("gallery") && (
            <div>
              <p className="label">Gallery (up to 8)</p>
              <GalleryPicker value={b.gallery} onChange={(v) => val("gallery", v)} />
            </div>
          )}
          {b.sections.includes("testimonials") && (
            <div>
              <p className="label">Testimonials <span className="font-normal text-faint">· only real ones you enter are shown</span></p>
              <ListEditor items={b.testimonials} onChange={(v) => val("testimonials", v)} blank={{ name: "", quote: "" }} max={6} addLabel="Add testimonial"
                render={(t, up) => (<div className="grid gap-2 sm:grid-cols-[160px_1fr]">
                  <input className="input h-9" placeholder="Name" value={t.name} maxLength={80} onChange={(e) => up({ name: e.target.value })} />
                  <input className="input h-9" placeholder="What they said" value={t.quote} maxLength={400} onChange={(e) => up({ quote: e.target.value })} />
                </div>)} />
            </div>
          )}
          {b.sections.includes("pricing") && (
            <div>
              <p className="label">Pricing plans</p>
              <ListEditor items={b.pricing} onChange={(v) => val("pricing", v)} blank={{ name: "", price: "", features: "", highlight: false }} max={4} addLabel="Add plan"
                render={(pl, up) => (<div className="space-y-2">
                  <div className="grid gap-2 sm:grid-cols-[1fr_140px_auto]">
                    <input className="input h-9" placeholder="Plan name" value={pl.name} maxLength={60} onChange={(e) => up({ name: e.target.value })} />
                    <input className="input h-9" placeholder="Price" value={pl.price} maxLength={40} onChange={(e) => up({ price: e.target.value })} />
                    <label className="flex items-center gap-1.5 text-xs text-ink"><input type="checkbox" checked={pl.highlight} onChange={(e) => up({ highlight: e.target.checked })} /> Highlight</label>
                  </div>
                  <textarea className="input" rows={2} placeholder="What's included (one per line)" value={pl.features} onChange={(e) => up({ features: e.target.value })} />
                </div>)} />
            </div>
          )}
          {b.sections.includes("faq") && (
            <div>
              <p className="label">FAQ</p>
              <ListEditor items={b.faqs} onChange={(v) => val("faqs", v)} blank={{ q: "", a: "" }} max={10} addLabel="Add question"
                render={(f, up) => (<div className="space-y-2">
                  <input className="input h-9" placeholder="Question" value={f.q} maxLength={200} onChange={(e) => up({ q: e.target.value })} />
                  <textarea className="input" rows={2} placeholder="Answer" value={f.a} maxLength={800} onChange={(e) => up({ a: e.target.value })} />
                </div>)} />
            </div>
          )}
        </div>
      )}

      {tab === "form" && (
        <div className="space-y-4">
          <div><p className="label">Lead form fields <span className="font-normal text-faint">· must include phone or email</span></p>
            <Pills multi options={FORM_FIELDS} value={b.form_fields} onChange={(v) => val("form_fields", v)} /></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Form title (optional)"><input className="input" value={b.form_title} onChange={set("form_title")} maxLength={80} placeholder={b.cta} /></Field>
            <Field label="Thank-you message"><input className="input" value={b.thank_you} onChange={set("thank_you")} maxLength={200} /></Field>
            <Field label="SEO title" hint="Shown in Google and browser tabs (≤ 70 chars)"><input className="input" value={b.seo_title} onChange={set("seo_title")} maxLength={70} /></Field>
            <Field label="SEO description" hint="≤ 170 characters"><input className="input" value={b.seo_description} onChange={set("seo_description")} maxLength={170} /></Field>
            <Field label="Meta Pixel ID (optional)" hint="Digits only, from Events Manager"><input className="input font-mono" value={b.meta_pixel_id} onChange={set("meta_pixel_id")} inputMode="numeric" pattern="\d{6,20}" maxLength={20} /></Field>
            <Field label="Google Analytics 4 ID (optional)" hint="Looks like G-XXXXXXX"><input className="input font-mono" value={b.ga4_id} onChange={(e) => val("ga4_id", e.target.value.toUpperCase())} pattern="G-[A-Z0-9]{4,15}" maxLength={17} /></Field>
          </div>
        </div>
      )}

      {tab === "ai" && (
        <div className="space-y-4">
          <div className="rounded-2xl bg-surface-2/60 px-4 py-3 text-sm">
            <label className="flex cursor-pointer items-center gap-2 font-medium text-strong">
              <input type="checkbox" className="size-4 accent-violet-500" checked={b.use_ai} onChange={set("use_ai")} />
              Write the page with AI
            </label>
            {b.use_ai && <p className="mt-1 pl-6 text-xs text-muted"><AiStatus ai={ai} writer={b.writer} writers={writers} /></p>}
          </div>
          {b.use_ai && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="AI writer">
                <select className="input" value={b.writer} onChange={set("writer")}>
                  <option value="auto">Default</option>
                  {writers.filter((w) => w.available).map((w) => <option key={w.ref} value={w.ref}>{w.name}</option>)}
                </select>
              </Field>
              <Field label="Language" hint="The AI writes the page in this language."><input className="input" value={b.language} onChange={set("language")} maxLength={40} list="langs" />
                <datalist id="langs">{["English", "Hindi", "Telugu", "Tamil", "Kannada", "Marathi", "Spanish", "Arabic", "French"].map((l) => <option key={l} value={l} />)}</datalist>
              </Field>
            </div>
          )}
          {b.use_ai && (
            <div className="space-y-2">
              <p className="label">Reference material (optional)</p>
              <p className="text-xs text-muted">Brochures, price lists, menus, notes… The AI reads them and uses the facts on your page.</p>
              <DocumentPicker docs={docs} value={b.references} onChange={(v) => val("references", v)}
                onDeleted={(id) => { setDocs((all) => all.filter((d) => d.id !== id)); val("references", b.references.filter((x) => x !== id)); }} />
              <ReferenceDropzone onUploaded={(r) => {
                if (r.kind === "document") { setDocs((all) => [r, ...all]); setB((x) => ({ ...x, references: [...x.references, r.id].slice(0, 10) })); }
              }} hint="PDF, Word (.docx), .txt, .md, .csv for the writer · images go to your library for the hero/gallery" />
            </div>
          )}
          <p className="text-xs text-faint">The AI never invents reviews, prices or awards: only the testimonials, plans and FAQs you enter are used.</p>
        </div>
      )}

      {coach && <BriefCoach review={review} brief={b} onAnswer={val} onGoTo={goTo} onApplyPlaybook={applyPlaybook} />}

      <div className="flex items-center justify-between gap-3 border-t border-line pt-4">
        <p className="hidden text-xs text-faint sm:block">Everything except the business name is optional.</p>
        <div className="ml-auto flex flex-wrap justify-end gap-2">
          <SaveTemplateButton module="website" getPayload={templatePayload} label="Save layout as template" />
          {b.business.trim().length >= 2 && <DirectionsButton getBrief={payload} onPick={(d) => { setB((x) => ({ ...x, ...d })); toast.success("Design picked. Generate when you're ready."); }} />}
          <Button type="submit" busy={busy}>{submitLabel}</Button>
        </div>
      </div>
      {busy && <JobProgress className="mt-4" seconds={35} steps={["Reading your brief…", "Writing the headline and offer…", "Laying out the sections…", "Picking colours and pictures…", "Adding the lead form…", "Checking it on phones…"]} />}

      <Modal open={!!gate} onClose={() => setGate(null)} title="Two seconds before we generate">
        <p className="mb-4 text-sm text-muted">These details change the page the most. Add them now and you won't need to fix the page later.</p>
        <div className="space-y-3">
          {(gate || []).map((m, i) => (
            <Field key={m.field} label={m.question} hint={m.why}>
              <input className="input" value={b[m.field] || ""} onChange={(e) => val(m.field, e.target.value)} maxLength={m.field === "phone" ? 30 : 200} autoFocus={i === 0} />
            </Field>
          ))}
        </div>
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <Button variant="subtle" type="button" onClick={() => { gatePassed.current = true; submit(); }}>Generate anyway</Button>
          <Button type="button" onClick={() => { gatePassed.current = true; submit(); }}>Generate</Button>
        </div>
      </Modal>
    </form>
  );
}

const CONTACT_MODES = [["voice_agent", "AIMVA voice agent calls them back"], ["own_phone", "Show my phone number"], ["both", "Both"]];

/** Leads can be called back by the AIMVA voice agent (no business number needed), reach the business's own phone, or both. */
function ContactChoice({ b, val, set }) {
  const { data: agents } = useApi("/api/voice/agents", []);
  const { data: integrations } = useApi("/api/integrations", []);
  const twilio = integrations.some((i) => i.provider === "twilio" && i.connected);
  const voice = b.contact_mode !== "own_phone";
  return (
    <div className="rounded-2xl bg-surface-2/60 p-4">
      <p className="label">How should leads reach you?</p>
      <Pills options={CONTACT_MODES} value={b.contact_mode} onChange={(v) => val("contact_mode", v)} />
      {voice && (
        <div className="mt-3 space-y-3">
          <p className="text-xs text-muted">Visitors tap <b className="text-ink">Request a call back</b> and your voice agent rings them within a minute to qualify them. The form asks for their number; yours stays private.</p>
          <div className="grid gap-3 sm:grid-cols-[1fr_120px]">
            <Field label="Voice agent">
              {agents.length ? (
                <select className="input" value={b.voice_agent_id ?? ""} onChange={(e) => val("voice_agent_id", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">{agents[0].name} (default)</option>
                  {agents.slice(1).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              ) : <Link to="/app/voice" className="flex h-11 items-center text-sm font-semibold text-brand hover:underline">Create your voice agent →</Link>}
            </Field>
            <Field label="Country code" hint="For local numbers"><input className="input" value={b.country_code} onChange={set("country_code")} maxLength={5} pattern="\+\d{1,4}" /></Field>
          </div>
          {!twilio && <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">Call backs are logged on each lead now. <Link to="/app/settings" className="font-semibold underline">Connect Twilio</Link> so the agent dials them automatically.</p>}
        </div>
      )}
    </div>
  );
}

function GalleryPicker({ value, onChange }) {
  const { data: brand } = useApi("/api/brand");
  const { data: assets } = useApi("/api/content/assets?kind=image", []);
  const { data: refs, setData: setRefs } = useApi("/api/references?kind=image", []);
  const items = [...refs.map((r) => ({ ref: r.ref, url: r.url })), ...(brand?.images || []).map((i) => ({ ref: `brand:${i.id}`, url: i.url })),
    ...assets.filter((a) => a.url).slice(0, 24).map((a) => ({ ref: `asset:${a.id}`, url: a.url }))];
  return (
    <div className="grid grid-cols-5 gap-2 sm:grid-cols-8">
      <UploadTile accept={ACCEPT_IMAGES} className="aspect-square" onUploaded={(r) => {
        setRefs((all) => [r, ...all]);
        if (value.length < 8) onChange([...value, r.ref]);
      }} />
      {items.map((i) => {
        const on = value.includes(i.ref);
        return (
          <button key={i.ref} type="button" onClick={() => onChange(on ? value.filter((x) => x !== i.ref) : value.length < 8 ? [...value, i.ref] : value)}
            className={cx("aspect-square overflow-hidden rounded-xl ring-2 transition", on ? "ring-strong" : "ring-transparent opacity-80 hover:opacity-100")} aria-pressed={on}>
            <img src={i.url} alt="" className="h-full w-full object-cover" loading="lazy" />
          </button>
        );
      })}
    </div>
  );
}

function Versions({ site, onRestore }) {
  const [open, setOpen] = useState(false);
  const { data: versions, reload } = useApi(open ? `/api/sites/${site.id}/versions` : null, []);
  const [busy, run] = useAction();
  useEffect(() => { if (open) reload(); }, [open, site.html, reload]);
  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}><History className="size-4" /> <span className="hidden sm:inline">Versions</span></Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Version history">
        <p className="mb-3 text-sm text-muted">Every generation and edit is kept. Restoring creates a new version, so nothing is lost.</p>
        <ul className="divide-y divide-line">
          {versions.map((v) => (
            <li key={v.id} className="flex items-center justify-between gap-3 py-3">
              <div>
                <p className="text-sm font-semibold text-strong">Version {v.number} · {v.note}</p>
                <p className="text-xs text-faint">{timeAgo(v.created_at)}{v.generator ? ` · ${v.generator === "ai" ? "AI" : v.generator}` : ""}</p>
              </div>
              {v.current ? <Chip tone="green">Current</Chip> : (
                <Button size="sm" variant="ghost" busy={busy} onClick={() => run(async () => { onRestore(await post(`/api/sites/${site.id}/versions/${v.id}/restore`)); setOpen(false); }, `Restored version ${v.number}`)}>Restore</Button>
              )}
            </li>
          ))}
        </ul>
      </Modal>
    </>
  );
}

function Editor({ site, onClose, onChange, feedback }) {
  const ed = useRef(null);
  const navigate = useNavigate();
  const [pageSlug, setPageSlug] = useState("");  // "" = home page
  const [base, setBase] = useState(site.html);  // what the editor loaded; changes only when the page is replaced from outside
  const [rev, setRev] = useState(0);
  const [pagesOpen, setPagesOpen] = useState(false);
  const [adding, setAdding] = useState(null);  // {title, about}
  const pages = site.pages || [];
  const current = pages.find((p) => p.slug === pageSlug);
  const htmlOf = (s, slug) => (slug ? s.pages?.find((p) => p.slug === slug)?.html : s.html) ?? s.html;
  const show = (s, slug) => { setPageSlug(slug); setBase(htmlOf(s, slug)); setRev((r) => r + 1); };
  const switchTo = async (slug) => { setPagesOpen(false); if (slug === pageSlug) return; await flush(); show(site, slug); };
  const [showBrief, setShowBrief] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [menu, setMenu] = useState(false);
  const [code, setCode] = useState(null);  // HTML being edited by hand
  const [checks, setChecks] = useState(false);
  const [busy, run] = useAction();

  // Regenerate, restore, HTML edits and whole-page AI edits replace the page: reload the editor with it.
  const replaced = (s) => { onChange(s); show(s, pageSlug); };
  const autosave = async (html) => onChange(await patch(pageSlug ? `/api/sites/${site.id}/pages/${pageSlug}` : `/api/sites/${site.id}`,
    pageSlug ? { html } : { html, note: "Edited visually" }));
  const addPage = (e) => { e.preventDefault(); run(async () => {
    await flush();
    const s = await post(`/api/sites/${site.id}/pages`, adding);
    onChange(s);
    setAdding(null);
    show(s, s.pages[s.pages.length - 1].slug);
  }, "Page added. It uses your design, and the menu links it on the live site."); };
  const removePage = () => { if (!current || !confirm(`Delete the “${current.title}” page?`)) return; run(async () => {
    const s = await del(`/api/sites/${site.id}/pages/${current.slug}`);
    onChange(s);
    show(s, "");
  }, "Page deleted"); };
  const renamePage = () => { const t = current && prompt("Page name (shown in the menu)", current.title); if (!t || t.trim().length < 2) return;
    run(async () => onChange(await patch(`/api/sites/${site.id}/pages/${current.slug}`, { title: t.trim() })), "Renamed"); };
  const flush = () => ed.current?.flush();
  const close = async () => { try { await flush(); } catch { if (!confirm("Your last change wasn't saved. Leave anyway?")) return; } onClose(); };
  const liveUrl = site.deploy_url || site.url;

  const left = (
    <>
      <button className="btn-subtle btn-sm shrink-0" onClick={close}><ArrowLeft className="size-4" /> <span className="hidden sm:inline">My pages</span></button>
      <h2 className="hidden truncate text-base font-bold text-strong md:block">{site.name}</h2>
      <div className="relative">
        <button type="button" className="btn-ghost btn-sm" aria-expanded={pagesOpen} onClick={() => setPagesOpen((o) => !o)}>
          <FileText className="size-4" /> <span className="max-w-[9rem] truncate">{current ? current.title : "Home"}</span> <ChevronDown className="size-3.5" />
        </button>
        {pagesOpen && (
          <div className="card absolute left-0 top-11 z-10 w-60 p-1.5 text-sm" onMouseLeave={() => setPagesOpen(false)}>
            {[{ slug: "", title: "Home" }, ...pages].map((p) => (
              <button key={p.slug || "home"} type="button" onClick={() => switchTo(p.slug)}
                className={cx("flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left hover:bg-surface-2", p.slug === pageSlug ? "font-semibold text-strong" : "text-ink")}>
                <FileText className="size-4 text-muted" /> <span className="truncate">{p.title}</span>
              </button>
            ))}
            <div className="my-1 border-t border-line" />
            <button type="button" className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left font-medium text-brand hover:bg-surface-2"
              onClick={() => { setPagesOpen(false); setAdding({ title: "", about: "" }); }}><Plus className="size-4" /> Add a page</button>
            {current && (
              <>
                <button type="button" className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-ink hover:bg-surface-2" onClick={() => { setPagesOpen(false); renamePage(); }}>Rename “{current.title}”</button>
                <button type="button" className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-rose-600 hover:bg-surface-2" onClick={() => { setPagesOpen(false); removePage(); }}><Trash2 className="size-4" /> Delete this page</button>
              </>
            )}
          </div>
        )}
      </div>
      {site.published ? <Chip tone="green">Live</Chip> : <Chip>Draft</Chip>}
      <span className="hidden lg:inline-flex"><Rate kind="site" id={site.id} initial={feedback?.[site.id]} /></span>
    </>
  );
  const right = (
    <>
      <Button variant="ghost" size="sm" className="hidden md:inline-flex" onClick={async () => { await flush(); setChecks(true); }}>Checks</Button>
      <Versions site={site} onRestore={replaced} />
      <div className="relative">
        <button type="button" className="btn-subtle btn-sm" aria-label="More" aria-expanded={menu} onClick={() => setMenu((m) => !m)}><MoreHorizontal className="size-4" /></button>
        {menu && (
          <div className="card absolute right-0 top-11 z-10 w-56 p-1.5 text-sm" onMouseLeave={() => setMenu(false)}>
            {[
              [RefreshCw, "Start over from brief", async () => { await flush(); setShowBrief(true); }],
              [Code2, "Edit HTML code", async () => { await flush(); setCode(htmlOf(site, pageSlug)); }],
              [ShieldCheck, "Launch checks", async () => { await flush(); setChecks(true); }],
              ...(site.published ? [[ExternalLink, "Open live page", () => window.open(liveUrl, "_blank", "noopener")],
                [Globe, "Domains & deploys", async () => { await flush(); navigate("/app/hosting"); }]] : []),
            ].map(([I, l, fn]) => (
              <button key={l} type="button" className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-ink hover:bg-surface-2"
                onClick={() => { setMenu(false); fn(); }}><I className="size-4 text-muted" /> {l}</button>
            ))}
          </div>
        )}
      </div>
      <Button size="sm" onClick={() => setPublishing(true)}><Rocket className="size-4" /> {site.published ? "Republish" : "Publish"}</Button>
    </>
  );

  return (
    <>
      <VisualEditor key={rev} ref={ed} html={base} siteId={site.id} page={pageSlug} onSave={autosave} onPageReplaced={replaced} left={left} right={right} />
      <Modal open={!!adding} onClose={() => setAdding(null)} title="Add a page">
        <form onSubmit={addPage} className="space-y-4">
          <div className="flex flex-wrap gap-1.5">
            {["About us", "Pricing", "Gallery", "Contact", "FAQ", "Location"].map((t) => (
              <button key={t} type="button" onClick={() => setAdding((a) => ({ ...a, title: t }))}
                className={cx("rounded-full px-3 py-1.5 text-xs font-medium", adding?.title === t ? "bg-strong text-white" : "bg-surface-2 text-ink hover:bg-lavender")}>{t}</button>
            ))}
          </div>
          <Field label="Page name" hint="Shown in the menu at the top of every page.">
            <input className="input" autoFocus required minLength={2} maxLength={60} value={adding?.title || ""} onChange={(e) => setAdding((a) => ({ ...a, title: e.target.value }))} />
          </Field>
          <Field label="What should be on it? (optional)" hint="AI drafts it in your page's design. You can click anything to change it after.">
            <textarea className="input" rows={3} maxLength={600} value={adding?.about || ""} onChange={(e) => setAdding((a) => ({ ...a, about: e.target.value }))}
              placeholder="e.g. Our story: family builders in Hyderabad since 1998, 40+ projects delivered" />
          </Field>
          <div className="flex justify-end"><Button type="submit" busy={busy}>Add page</Button></div>
        </form>
      </Modal>
      <Modal open={checks} onClose={() => setChecks(false)} title="Launch checks">
        <ReadinessPanel siteId={site.id} version={site.html} />
      </Modal>
      <Modal open={code !== null} onClose={() => setCode(null)} title="Edit HTML code" wide="xl">
        <p className="mb-3 text-sm text-muted">For developers. Saving creates a new version, so you can always go back.</p>
        <textarea className="input h-[60vh] font-mono text-xs" value={code || ""} onChange={(e) => setCode(e.target.value)} spellCheck={false} aria-label="Page HTML" />
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="subtle" onClick={() => setCode(null)}>Cancel</Button>
          <Button busy={busy} disabled={code === htmlOf(site, pageSlug)} onClick={() => run(async () => {
            replaced(await patch(pageSlug ? `/api/sites/${site.id}/pages/${pageSlug}` : `/api/sites/${site.id}`, pageSlug ? { html: code } : { html: code, note: "Edited HTML" }));
            setCode(null);
          }, "Saved as a new version")}>Save code</Button>
        </div>
      </Modal>
      <Modal open={showBrief} onClose={() => setShowBrief(false)} title="Start over from the brief (your current page is kept in Versions)" wide>
        <BriefForm initial={{ ...BLANK, ...site.brief }} busy={busy} submitLabel="Rebuild page" coach={false}
          onSubmit={(b) => run(async () => {
            replaced(await post(`/api/sites/${site.id}/regenerate`, b));
            setShowBrief(false);
          }, "Rebuilt: the previous page is in Versions")} />
      </Modal>
      <PublishDialog site={site} open={publishing} onClose={() => setPublishing(false)} beforePublish={flush}
        onPublished={(s) => onChange({ ...site, ...s })} />
    </>
  );
}

/** Scaled-down live render of a page that always fills its card's width. */
function Thumb({ s }) {
  const box = useRef(null);
  const [scale, setScale] = useState(0.3);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setScale(e.contentRect.width / 1280));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={box} className="h-full w-full">
      {/* Owner-only preview: works for drafts and doesn't inflate the visit count. */}
      <iframe title={s.name} src={`/api/sites/${s.id}/preview?v=${encodeURIComponent(s.updated_at || "")}`} loading="lazy"
        sandbox="allow-same-origin" style={{ transform: `scale(${scale})` }}
        className="pointer-events-none h-[800px] w-[1280px] origin-top-left" tabIndex={-1} />
    </div>
  );
}

function SiteCard({ s, onOpen, onDelete }) {
  return (
    <motion.div variants={rise} whileHover={{ y: -3 }} transition={{ type: "spring", stiffness: 300, damping: 24 }} className="card flex flex-col overflow-hidden hover:shadow-[var(--shadow-lift)]">
      <button className="relative block h-44 overflow-hidden bg-white text-left" onClick={onOpen} aria-label={`Open ${s.name}`}>
        <Thumb s={s} />
      </button>
      <div className="flex flex-1 flex-col p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate font-semibold text-strong">{s.name}</p>
          {s.published ? <Chip tone="green">Live</Chip> : <Chip>Draft</Chip>}
        </div>
        <p className="mt-1 text-xs text-faint">Updated {timeAgo(s.updated_at)} · {s.visits} visits</p>
        <div className="mt-auto flex gap-2 pt-4">
          <Button variant="ghost" size="sm" onClick={onOpen}><Code2 className="size-3.5" /> Edit</Button>
          {s.published && <a className="btn-ghost btn-sm" href={s.deploy_url || s.url} target="_blank" rel="noreferrer"><ExternalLink className="size-3.5" /> Live</a>}
          <Button variant="danger" size="sm" className="ml-auto" aria-label={`Delete ${s.name}`} onClick={onDelete}><Trash2 className="size-3.5" /></Button>
        </div>
      </div>
    </motion.div>
  );
}

export default function Websites() {
  const { data: sites, reload, loading } = useApi("/api/sites", []);
  const { data: feedback } = useApi("/api/feedback?kind=site", {});
  const [tab, setTab] = useState("create");
  const [current, setCurrent] = useState(null);  // the page being worked on in Create
  const [formKey, setFormKey] = useState(0);
  const [q, setQ] = useState("");
  const [busy, run] = useAction();
  const { user } = useAuth();
  const onboarding = useOnboarding()?.data;
  const tpl = onboarding?.template?.site;
  const { data: brandKit } = useApi("/api/brand");
  const fromBrand = brandKit?.is_set_up ? {
    ...(brandKit.name && { business: brandKit.name }), ...(brandKit.tagline && { subheadline: brandKit.tagline }),
    ...(brandKit.colors[0] && { primary: brandKit.colors[0] }), ...(brandKit.colors[1] && { accent: brandKit.colors[1] }),
  } : {};
  const starter = { ...BLANK, business: user.workspace?.name || user.company || "", industry: onboarding?.template?.label || "", ...(onboarding?.industry && tpl ? tpl : {}), ...fromBrand };

  const startNew = () => { setCurrent(null); setFormKey((k) => k + 1); setTab("create"); };
  const open = (id) => run(async () => { setCurrent(await get(`/api/sites/${id}`)); });
  const filtered = sites.filter((s) => s.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <div>
      <PageHeader icon={Globe} tone="pink" title="Pages" subtitle="Landing pages with a lead form built in."
        actions={<Button onClick={startNew}><Plus className="size-4" /> New page</Button>} />
      <div className="mb-6"><Tabs value={tab} onChange={setTab} tabs={[{ value: "create", label: "Create" }, { value: "history", label: `History${sites.length ? ` (${sites.length})` : ""}` }]} /></div>

      {current && <Editor key={current.id} site={current} feedback={feedback} onChange={(s) => { setCurrent(s); reload(); }}
        onClose={() => { setCurrent(null); setTab("history"); }} />}
      {tab === "create" && (
        <Card className="mx-auto max-w-4xl">
          <h2 className="mb-1 text-lg font-bold text-strong">New landing page</h2>
          <p className="mb-5 text-sm text-muted">Fill in what you know. Your earlier pages stay safe in History.</p>
          <BriefForm key={`${formKey}-${onboarding ? 1 : 0}-${brandKit ? 1 : 0}`} initial={starter} busy={busy} submitLabel="Generate page" onSubmit={(b) => run(async () => {
            const s = await post("/api/sites", b);
            setCurrent(s);
            reload();
            if (s.auto_fixed?.length) toast(`Page Fixer tidied ${s.auto_fixed.length} thing${s.auto_fixed.length === 1 ? "" : "s"}`, { description: s.auto_fixed.join(" · ") });
          }, "Page ready. Click anything on it to change it.")} />
        </Card>
      )}

      {tab === "history" && (
        loading ? <ListSkeleton /> : sites.length === 0 ? (
          <Empty icon={Globe} title="Your pages will live here" text="A landing page with a lead form is the fastest way to your first lead. It takes about a minute."
            action={<Button onClick={startNew}><Plus className="size-4" /> Make your first page</Button>} />
        ) : (
          <>
            <input className="input mb-4 max-w-sm" placeholder="Search pages" value={q} onChange={(e) => setQ(e.target.value)} />
            <motion.div variants={stagger} initial="hidden" animate="show" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.map((s) => (
                <SiteCard key={s.id} s={s} onOpen={() => open(s.id)} onDelete={() => {
                  if (confirm(`Delete "${s.name}" and all its versions? This removes the live page too.`)) run(async () => {
                    await del(`/api/sites/${s.id}`);
                    if (current?.id === s.id) setCurrent(null);
                    reload();
                  }, "Deleted");
                }} />
              ))}
            </motion.div>
          </>
        )
      )}
    </div>
  );
}
