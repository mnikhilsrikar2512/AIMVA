// Use cases: an index, and one page per audience (the problem, how AIMVA handles it, the flow, a way in).
import { Link, Navigate, useParams } from "react-router-dom";
import { ArrowRight, Check } from "lucide-react";
import { FinalCta, Heading, MarketingLayout, signupHref, useSeo } from "../../components/marketing/Site";
import { USE_CASES, useCase } from "../../components/marketing/useCases";
import { useAuth } from "../../lib/auth";
import SampleGallery from "../../components/marketing/SampleGallery";

export function UseCasesIndex() {
  useSeo("Use cases", "How clinics, builders, coaches, restaurants, solo founders and agencies use AIMVA to get leads and reply to every one of them.");
  return (
    <MarketingLayout from="use-cases">
      <section className="mx-auto max-w-6xl px-4 pb-10 pt-8 sm:px-6 sm:pt-14 lg:pt-20">
        <Heading as="h1" label="Use cases" title="Same tools, arranged for how you work." sub="Pick the one that sounds like you. Onboarding starts with that answer already chosen." />
      </section>
      <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
        <ul className="divide-y divide-line border-y border-line">
          {USE_CASES.map((u) => (
            <li key={u.slug}>
              <Link to={`/use-cases/${u.slug}`} className="group grid gap-3 py-8 md:grid-cols-[0.8fr_1.2fr_auto] md:items-center md:gap-10">
                <p className="serif-moment text-2xl text-strong sm:text-3xl">{u.short}</p>
                <p className="text-[15px] leading-relaxed text-muted">{u.lede}</p>
                <ArrowRight className="hidden size-5 text-warm transition duration-300 group-hover:translate-x-1.5 group-hover:text-brand md:block" />
              </Link>
            </li>
          ))}
        </ul>
      </section>
      <section className="border-t border-line">
        <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
          <Heading label="Made with AIMVA" title="Pages it made for businesses like these."
            sub="Four sample businesses, four short briefs, four different layouts, straight from the page builder. Open one to scroll the real page; its form is switched off." />
          <SampleGallery />
        </div>
      </section>
      <FinalCta from="use-cases" />
    </MarketingLayout>
  );
}

export function UseCasePage() {
  const { slug } = useParams();
  const u = useCase(slug);
  const { user } = useAuth();
  useSeo(u?.short, u?.lede);
  if (!u) return <Navigate to="/use-cases" replace />;
  const from = `use-case-${u.slug}`;
  return (
    <MarketingLayout from={from}>
      <section className="mx-auto max-w-6xl px-4 pb-16 pt-8 sm:px-6 sm:pt-14 lg:pt-20">
        <Link to="/use-cases" className="text-sm font-medium text-muted hover:text-strong">Use cases</Link>
        <h1 className="serif-moment mt-3 max-w-3xl text-[36px] leading-[1.05] text-strong sm:text-6xl">{u.title}</h1>
        <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted">{u.lede}</p>
        <Link to={user ? "/app" : signupHref(from, u.signup)} className="mk-go btn-primary mt-8 h-12 px-7 text-[15px]">{user ? "Open app" : "Start free"} <ArrowRight className="size-4" /></Link>
      </section>

      <section className="border-t border-line">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 sm:py-20 lg:grid-cols-[0.8fr_1.2fr]">
          <Heading label="The problem" title="What usually goes wrong" />
          <ul className="divide-y divide-line border-y border-line">
            {u.problem.map((p) => <li key={p} className="py-5 text-[17px] leading-relaxed text-ink">{p}</li>)}
          </ul>
        </div>
      </section>

      <section className="border-t border-line">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 sm:py-20 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <Heading label="How AIMVA handles it" title="The flow, start to finish" />
            <Link to="/tour" className="mt-6 inline-flex items-center gap-1.5 text-[15px] font-semibold text-warm hover:underline">See it in the product tour <ArrowRight className="size-4" /></Link>
          </div>
          <ol className="space-y-9">
            {u.how.map(([t, d], k) => (
              <li key={t} className="grid grid-cols-[2.5rem_1fr] gap-3">
                <span className="font-display text-2xl font-bold tabular-nums text-warm">{k + 1}</span>
                <div><p className="text-lg font-semibold text-strong">{t}</p><p className="mt-1.5 text-[15px] leading-relaxed text-muted">{d}</p></div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {u.examples && (
        <section className="border-t border-line">
          <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-20">
            <Heading label="Starting points" title="Your first page and call script, already written" sub="These are the real templates AIMVA starts from. Everything can be changed." />
            <ul className="mt-12 divide-y divide-line border-y border-line">
              {u.examples.map((x) => (
                <li key={x.name} className="grid gap-4 py-7 md:grid-cols-[0.7fr_1fr_1.2fr_auto] md:items-start md:gap-8">
                  <p className="font-semibold text-strong">{x.name}</p>
                  <div className="text-sm"><p className="text-muted">Page offer</p><p className="mt-1 text-strong">{x.offer}</p><p className="mt-2 inline-flex items-center gap-1.5 text-xs text-muted"><Check className="size-3.5 text-warm" /> Button: {x.cta}</p></div>
                  <div className="text-sm"><p className="text-muted">Call assistant opens with</p><p className="mt-1 italic text-ink">“{x.greeting}”</p></div>
                  {!user && <Link to={signupHref(from, `${u.signup}&industry=${x.industry}`)} className="btn-ghost btn-sm self-start whitespace-nowrap">Start with this <ArrowRight className="size-3.5" /></Link>}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <section className="border-t border-line">
        <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
          <p className="text-sm font-semibold text-muted">Other use cases</p>
          <div className="mt-4 flex flex-wrap gap-x-8 gap-y-3">
            {USE_CASES.filter((o) => o.slug !== u.slug).map((o) => <Link key={o.slug} to={`/use-cases/${o.slug}`} className="inline-flex items-center gap-1.5 text-lg font-semibold text-strong hover:text-warm">{o.short} <ArrowRight className="size-4" /></Link>)}
          </div>
        </div>
      </section>
      <FinalCta from={from} />
    </MarketingLayout>
  );
}
