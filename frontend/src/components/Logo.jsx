import { Link } from "react-router-dom";
import clsx from "clsx";

/** The AIMVA mark and name. Its own file so public pages can show it without loading the app shell. */
export function Logo({ className, to = "/" }) {
  return (
    <Link to={to} className={clsx("flex items-center gap-2.5", className)} aria-label="AIMVA home">
      <img src="/logo.svg" alt="" className="size-8" />
      <span className="font-display text-lg font-bold tracking-tight text-strong">AIMVA</span>
    </Link>
  );
}
