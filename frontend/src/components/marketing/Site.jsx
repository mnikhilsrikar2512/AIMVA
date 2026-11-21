// The public site's frame: a top bar that always has a background, a footer, and per-page title/description.
// Kept free of the app shell (no AppLayout, no ui.jsx) so the landing page stays small and fast on phones.
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { ArrowRight, Menu, X } from "lucide-react";
import clsx from "clsx";
import { Logo } from "../Logo";
import { useAuth } from "../../lib/auth";
import { USE_CASES } from "./useCases";
import { LEGAL_PAGES } from "./legal";
import "./marketing.css";

export const cx = clsx;

/** Page title and meta description, restored when the page unmounts. */
export function useSeo(title, description) {
  useEffect(() => {
    const prev = document.title;
    document.title = title ? `${title} · AIMVA` : "AIMVA: from ad to sale, in one calm place";
    let meta = document.querySelector('meta[name="description"]');
    if (!meta) { meta = document.createElement("meta"); meta.name = "description"; document.head.appendChild(meta); }
    const prevDesc = meta.content;
    if (description) meta.content = description;
    return () => { document.title = prev; meta.content = prevDesc; };
  }, [title, description]);
}

export const signupHref = (from, extra = "") => `/signup?from=${encodeURIComponent(from)}${extra}`;

const LINKS = [
  { to: "/tour", label: "Product tour" },
  { to: "/use-cases", label: "Use cases" },
  { to: "/#features", label: "Features" },
  { to: "/#faq", label: "FAQ" },
];

function TopBar({ from }) {
  const { user } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on(); window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  useEffect(() => { setOpen(false); }, [location.pathname, location.hash]);
  useEffect(() => {
    if (!open) return;
    const esc = (e) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open]);

  const actions = user ? (
    <Link to="/app" className="mk-go btn-primary">Open app <ArrowRight className="size-4" /></Link>
  ) : (
    <>
      <Link to="/login" className="btn-subtle">Log in</Link>
      <Link to={signupHref(from)} className="btn-primary">Start free</Link>
    </>
  );

  return (
    // Always a background (never see-through over the page); a hairline appears once you scroll.
    <header className={cx("sticky top-0 z-40 border-b bg-bg transition-colors",
      scrolled || open ? "border-line-strong" : "border-transparent")}>
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-2 px-4 sm:h-16 sm:gap-4 sm:px-6">
        <Logo />
        <nav className="hidden items-center gap-1 text-sm font-medium md:flex" aria-label="Main">
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} end className={({ isActive }) => cx("mk-nav rounded-full px-3 py-1.5 transition hover:text-strong",
              isActive && !l.to.includes("#") ? "text-strong" : "text-muted")}>{l.label}</NavLink>
          ))}
        </nav>
        <div className="hidden items-center gap-1 md:flex">{actions}</div>
        {/* Phones and tablets: the one action that matters stays in reach next to the menu. */}
        <div className="ml-auto md:hidden">
          {user ? <Link to="/app" className="btn-primary btn-sm">Open app</Link> : !open && <Link to={signupHref(from)} className="btn-primary btn-sm">Start free</Link>}
        </div>
        <button type="button" className="btn-subtle btn-sm px-2 md:hidden" aria-expanded={open} aria-controls="site-menu" aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen((v) => !v)}>
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </div>
      {open && (
        <div id="site-menu" className="border-t border-line bg-bg px-4 pb-6 pt-2 md:hidden">
          <nav className="flex flex-col" aria-label="Main">
            {LINKS.map((l) => <Link key={l.to} to={l.to} className="border-b border-line py-3.5 text-[15px] font-medium text-strong">{l.label}</Link>)}
          </nav>
          <div className="mt-5 flex flex-col gap-2 [&>a]:h-11 [&>a]:justify-center">{actions}</div>
        </div>
      )}
    </header>
  );
}

function Footer({ from }) {
  const { user } = useAuth();
  const col = (title, links) => (
    <div>
      <p className="text-sm font-semibold text-strong">{title}</p>
      <ul className="mt-1.5 text-sm text-muted sm:mt-3 sm:space-y-2">{links.map(([to, label]) => <li key={to}><Link to={to} className="block py-2 hover:text-strong sm:inline sm:py-0">{label}</Link></li>)}</ul>
    </div>
  );
  return (
    <footer className="border-t border-line">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-x-6 gap-y-8 px-4 py-10 sm:gap-10 sm:px-6 sm:py-14 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div className="col-span-2 md:col-span-1">
          <Logo />
          <p className="mt-4 max-w-xs text-sm leading-relaxed text-muted">Pages, ads, calls and WhatsApp replies, and every lead in one list. Free while in early access.</p>
        </div>
        {col("Product", [["/tour", "Product tour"], ["/#features", "Features"], ["/#faq", "Questions"]])}
        {col("Use cases", USE_CASES.map((u) => [`/use-cases/${u.slug}`, u.short]))}
        {col("Account", user ? [["/app", "Open app"]] : [["/login", "Log in"], [signupHref(from), "Start free"]])}
      </div>
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-2 px-4 text-xs text-faint sm:px-6" style={{ paddingBottom: "max(2.5rem, env(safe-area-inset-bottom))" }}>
        <span>© {new Date().getFullYear()} AIMVA</span>
        <nav aria-label="Legal" className="flex flex-wrap gap-x-4">
          {LEGAL_PAGES.map((p) => <Link key={p.to} to={p.to} className="py-1 hover:text-strong">{p.label}</Link>)}
        </nav>
      </div>
    </footer>
  );
}

/** Wrap every public page. `from` names the page for sign-up links (?from=…). */
export function MarketingLayout({ from, children }) {
  const { hash, pathname } = useLocation();
  // Same-page anchors (/#faq) after navigation: scroll once the page has rendered.
  useEffect(() => {
    if (!hash) { window.scrollTo(0, 0); return; }
    const t = setTimeout(() => document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
    return () => clearTimeout(t);
  }, [hash, pathname]);
  return (
    <div className="mk min-h-dvh overflow-x-clip bg-bg text-ink">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">Skip to content</a>
      <TopBar from={from} />
      <main id="main">{children}</main>
      <Footer from={from} />
    </div>
  );
}

/** Section heading: small terracotta label, big serif line, optional sub. */
export function Heading({ label, title, sub, center = false, as: H = "h2" }) {
  return (
    <div className={cx("max-w-2xl", center && "mx-auto text-center")}>
      {label && <p className="text-sm font-semibold text-warm">{label}</p>}
      <H className="serif-moment mt-2 text-[30px] leading-[1.1] text-strong sm:text-[44px]">{title}</H>
      {sub && <p className="mt-3 text-base leading-relaxed text-muted sm:mt-4 sm:text-lg">{sub}</p>}
    </div>
  );
}

/** The closing call to action, used once at the bottom of each page. */
export function FinalCta({ from, title = "Your next lead could be in today.", text = "Create a free account, answer a few questions, and your first page is written for you." }) {
  const { user } = useAuth();
  return (
    <section className="border-t border-line">
      <div className="mx-auto max-w-3xl px-4 py-16 text-center sm:px-6 sm:py-24">
        <h2 className="serif-moment text-[30px] leading-tight text-strong sm:text-5xl">{title}</h2>
        <p className="mx-auto mt-4 max-w-lg text-base text-muted sm:text-lg">{text}</p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link to={user ? "/app" : signupHref(from)} className="mk-go btn-primary h-12 px-7 text-[15px]">{user ? "Open app" : "Start free"} <ArrowRight className="size-4" /></Link>
          {from !== "tour" && <Link to="/tour" className="btn-subtle h-12 px-5 text-[15px]">Take the product tour</Link>}
        </div>
        <p className="mt-5 text-sm text-faint">Free while in early access. No card needed.</p>
      </div>
    </section>
  );
}
