import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { MarketingLayout, useSeo } from "../../components/marketing/Site";

export default function NotFound() {
  useSeo("Page not found", "This page doesn't exist.");
  return (
    <MarketingLayout from="404">
      <section className="mx-auto max-w-2xl px-4 py-32 text-center sm:px-6">
        <p className="text-sm font-semibold text-warm">404</p>
        <h1 className="serif-moment mt-3 text-5xl text-strong">This page isn't here.</h1>
        <p className="mt-4 text-lg text-muted">The link may be old, or the address has a typo.</p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link to="/" className="btn-primary h-11 px-6">Go to the home page <ArrowRight className="size-4" /></Link>
          <Link to="/tour" className="btn-subtle h-11 px-5">Take the product tour</Link>
        </div>
      </section>
    </MarketingLayout>
  );
}
