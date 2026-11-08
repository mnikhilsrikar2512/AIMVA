import {
  AudioLines, BarChart3, Compass, Gauge, Globe, Image, LayoutDashboard, Linkedin, MessageCircle, Megaphone,
  Palette, Search, Server, Settings, ShieldCheck, Users, Video, Facebook,
} from "lucide-react";

// Single source of truth for the app's modules. The rail follows the journey (make → reach → see);
// pages left out of the rail (`rail: false`) are still one keystroke away in the Ctrl/Cmd+K palette.
// `client: true` marks what a view-only client of an agency can see.
export const NAV = [
  { group: "Overview", items: [
    { to: "/app", label: "Home", icon: LayoutDashboard, end: true, client: true, keywords: "dashboard activity" },
    { to: "/app/leads", label: "Leads", icon: Users, client: true, desc: "Everyone who asked, from every channel", keywords: "crm sheets sync" },
  ]},
  { group: "Make", items: [
    { to: "/app/websites", label: "Pages", icon: Globe, client: true, desc: "Landing pages with lead forms", keywords: "website builder landing" },
    { to: "/app/images", label: "Pictures", icon: Image, desc: "Ad pictures from a sentence", keywords: "image generation creative" },
    { to: "/app/videos", label: "Videos", icon: Video, desc: "Short promo videos", keywords: "video generation" },
    { to: "/app/brand", label: "Brand kit", icon: Palette, rail: false, desc: "Logos, colours and voice", keywords: "logo colours" },
    { to: "/app/hosting", label: "Domains and deploys", icon: Server, rail: false, desc: "Publish, domains, Netlify, Vercel", keywords: "hosting domain" },
  ]},
  { group: "Reach", items: [
    { to: "/app/ads/meta", match: "/app/ads", label: "Campaigns", icon: Megaphone, desc: "Meta, Google and LinkedIn ads", keywords: "ads facebook instagram" },
    { to: "/app/ads/google", label: "Google campaigns", icon: Search, rail: false, keywords: "ads google search" },
    { to: "/app/ads/linkedin", label: "LinkedIn campaigns", icon: Linkedin, rail: false, keywords: "ads linkedin b2b" },
    { to: "/app/voice", label: "Calls", icon: AudioLines, desc: "Your AI call assistant", keywords: "voice agent phone" },
    { to: "/app/whatsapp", label: "WhatsApp", icon: MessageCircle, desc: "Business inbox and scheduling", keywords: "chat message" },
  ]},
  { group: "See", items: [
    { to: "/app/command", label: "Results", icon: Compass, client: true, desc: "Spend, leads and sales per campaign", keywords: "command center roi" },
    { to: "/app/analytics", label: "Analytics", icon: BarChart3, client: true, desc: "Charts and insights", keywords: "kpi charts" },
  ]},
  { group: "Account", items: [
    { to: "/app/settings", label: "Settings", icon: Settings, desc: "Accounts, brand, team", keywords: "integrations connect" },
    { to: "/app/console", label: "Team console", icon: ShieldCheck, staff: true, desc: "Customers, support actions and the team's log", keywords: "admin support customers staff" },
    { to: "/app/owner", label: "Quality and usage", icon: Gauge, quality: true },  // Owner, Management, Development
  ]},
];

// AIMVA team roles (backend app/staff.py) that see the quality and usage numbers.
export const QUALITY_ROLES = ["owner", "manager", "developer"];
export const canSeeQuality = (user) => QUALITY_ROLES.includes(user?.staff_role);

/** The items a person may see: team-only and client-view filters applied. */
export function visibleNav(user) {
  const isClient = user?.workspace?.role === "client";
  const allowed = (it) => (!it.owner || user?.is_admin) && (!it.staff || user?.staff_role) && (!it.quality || canSeeQuality(user));
  return NAV.map((g) => ({ ...g, items: g.items.filter((it) => allowed(it) && (!isClient || it.client || it.staff || it.quality)) }))
    .filter((g) => g.items.length);
}

export const FEATURES = [
  { title: "AI Voice Agent", icon: AudioLines, tone: "cyan", to: "/app/voice",
    text: "Multi-lingual voice calls that qualify leads, read sentiment in real time and hand off to a human when it matters.",
    tags: ["Multi-lingual", "Sentiment AI", "Human handoff"] },
  { title: "Content Creation", icon: Image, tone: "violet", to: "/app/images",
    text: "Generate on-brand marketing images and videos in seconds with state-of-the-art open models.",
    tags: ["Image gen", "Video gen", "Brand kit"] },
  { title: "Campaign Management", icon: Megaphone, tone: "green", to: "/app/ads/meta",
    text: "Build Meta, Google and LinkedIn campaigns with lead forms and AI ad copy from one place.",
    tags: ["Meta", "Google", "LinkedIn"] },
  { title: "Web Dev & Hosting", icon: Globe, tone: "pink", to: "/app/websites",
    text: "Generate a landing page from a brief and publish it instantly, or deploy to Netlify or Vercel.",
    tags: ["AI builder", "1-click deploy", "Custom domains"] },
  { title: "Lead Syncing", icon: Users, tone: "amber", to: "/app/leads",
    text: "Every lead lands in one CRM, deduplicated and scored, then syncs to Google Sheets or OneDrive.",
    tags: ["Google Sheets", "OneDrive", "Dedupe"] },
  { title: "AI Analytics", icon: BarChart3, tone: "blue", to: "/app/analytics",
    text: "Live dashboards, predictive lead scores and AI insights that tell you where to put your budget.",
    tags: ["Lead score", "ROI", "Insights"] },
];
