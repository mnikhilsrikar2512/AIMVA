import { CloudOff, RotateCw } from "lucide-react";
import { Button, cx } from "./ui";

// Shown when a list or page couldn't be fetched. Never fall through to an empty state on an error:
// "Your leads will land here" during an outage reads as lost data.
function reason(error) {
  if (!error) return "";
  if (error.status === 403) return "You don't have access to this.";
  if (error.status === 401) return "Your session ended. Sign in again to continue.";
  if (!error.status || error.status >= 500) return "We couldn't reach the server. Your data is safe; this is a connection problem.";
  return error.message || "Something went wrong.";
}

export function LoadError({ error, what = "this", onRetry, compact, className }) {
  const retry = onRetry && error?.status !== 403;
  return (
    <div role="alert" className={cx("flex flex-col items-center justify-center text-center", compact ? "px-4 py-10" : "px-6 py-14", className)}>
      <div className="mb-3 grid size-10 place-items-center rounded-xl bg-surface-2 text-muted"><CloudOff className="size-5" /></div>
      <p className="text-[15px] font-semibold text-strong">Couldn't load {what}</p>
      <p className="mt-1 max-w-sm text-sm text-muted">{reason(error)}</p>
      {retry && <Button size="sm" variant="ghost" className="mt-4" onClick={onRetry}><RotateCw className="size-4" /> Try again</Button>}
    </div>
  );
}

// One-line version for pages that still have (older) data on screen, or for side panels.
export function LoadErrorBar({ what = "some items", onRetry, className }) {
  return (
    <p role="alert" className={cx("mb-3 flex flex-wrap items-center gap-x-2 rounded-lg bg-surface-2 px-3 py-2 text-sm text-muted", className)}>
      <CloudOff className="size-4 shrink-0" /> Couldn't load {what}.
      {onRetry && <button type="button" className="font-medium text-brand hover:underline" onClick={onRetry}>Try again</button>}
    </p>
  );
}
