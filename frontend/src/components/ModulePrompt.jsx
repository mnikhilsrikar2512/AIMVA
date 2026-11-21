// Every module starts from one prompt (design.md 5.1): the first visit shows only the prompt, already written from
// the business profile, with one line saying what will come out. Pressing Enter as is works.
import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { get } from "../lib/api";
import { Button, cx } from "./ui";

const AUTO_KEY = "aimva_autorun";
/** Home calls this before opening a module with ?prompt=: that module then runs the sentence without a second press. */
export function markAutoRun(prompt) { try { sessionStorage.setItem(AUTO_KEY, prompt); } catch { /* storage blocked */ } }
function takeAutoRun() {
  try { const v = sessionStorage.getItem(AUTO_KEY); sessionStorage.removeItem(AUTO_KEY); return v; } catch { return null; }
}

/** The pre-written prompt for a module key, unless the page was opened with one (?prompt= from Home or the reveal). */
export function useModulePrompt(key, given) {
  const [state, setState] = useState({ prompt: given || "", line: "", loading: !given });
  useEffect(() => {
    let live = true;
    get(`/api/modules/${key}/prompt`)
      .then((d) => { if (live) setState((s) => ({ prompt: s.prompt || d.prompt || "", line: d.outcome_line || "", loading: false })); })
      .catch(() => { if (live) setState((s) => ({ ...s, loading: false })); });
    return () => { live = false; };
  }, [key]);
  return [state, (prompt) => setState((s) => ({ ...s, prompt }))];
}

/**
 * The empty state of a module. `outcome` says what you'll get. `onSubmit(prompt)` runs it. `secondary` is a quiet
 * second way in (fill in the details yourself). The run button is the screen's one Vivid Cyan action (design.md v3 7.3).
 */
export function ModulePrompt({ moduleKey, given, outcome, submitLabel, onSubmit, busy, secondary, className, disabled, note }) {
  const [{ prompt, line, loading }, setPrompt] = useModulePrompt(moduleKey, given);
  const ref = useRef(null);
  useEffect(() => {  // cursor at the end of the written prompt
    const el = ref.current;
    if (el && !loading) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
  }, [loading]);
  const submit = (e) => { e?.preventDefault(); if (prompt.trim() && !busy && !disabled) onSubmit(prompt.trim()); };
  // Asked from Home: run it straight away instead of asking twice (plan S3). Only the exact sentence Home sent, once.
  useEffect(() => {
    if (loading || !given || disabled || busy || takeAutoRun() !== given) return;
    onSubmit(given.trim());
  }, [loading]);  // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <form onSubmit={submit} className={cx("max-w-3xl", className)}>
      <div className="rounded-[10px] bg-surface ring-1 ring-line-strong focus-within:ring-2 focus-within:ring-brand/50">
        <textarea ref={ref} rows={3} className="block w-full resize-none rounded-t-[10px] bg-transparent px-4 py-3.5 text-base text-strong placeholder:text-muted focus:outline-none"
          value={prompt} onChange={(e) => setPrompt(e.target.value)} maxLength={1000} disabled={busy || loading} aria-label="What should it make?"
          placeholder={loading ? "" : "Say what you want, the way you'd tell a friend."}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) submit(e); }} />
        <div className="flex items-center justify-end px-3 pb-3">
          <Button type="submit" variant="accent" busy={busy} disabled={!prompt.trim() || loading || disabled}>{submitLabel} <ArrowRight className="size-4" /></Button>
        </div>
      </div>
      <p className="mt-3 text-sm text-muted">{outcome || line}</p>
      {note && <p role="status" className="mt-2 text-sm text-warm">{note}</p>}
      {secondary && <div className="mt-6 text-sm">{secondary}</div>}
    </form>
  );
}
