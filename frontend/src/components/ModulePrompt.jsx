// Every module starts from one prompt (design.md 5.1): the first visit shows only the prompt, already written from
// the business profile, with one line saying what will come out. Pressing Enter as is works.
import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { get } from "../lib/api";
import { Button, cx } from "./ui";
import { Mascot } from "./Mascot";

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
  // When something finishes making, he is pleased for a moment (owner: "react when the result is shown").
  const [done, setDone] = useState(false);
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && !busy) { setDone(true); const t = setTimeout(() => setDone(false), 3200); wasBusy.current = false; return () => clearTimeout(t); }
    wasBusy.current = !!busy;
    return undefined;
  }, [busy]);
  const submit = (e) => { e?.preventDefault(); if (prompt.trim() && !busy && !disabled) onSubmit(prompt.trim()); };
  // Asked from Home: run it straight away instead of asking twice (plan S3). Only the exact sentence Home sent, once.
  useEffect(() => {
    if (loading || !given || disabled || busy || takeAutoRun() !== given) return;
    onSubmit(given.trim());
  }, [loading]);  // eslint-disable-line react-hooks/exhaustive-deps
  // Chat-style (owner 2026-11-21: "keep this at the bottom, not on the top"): what you'll get sits above, the box is
  // pinned to the bottom of the screen where people expect to type. On phones it clears the bottom tab bar.
  return (
    <form onSubmit={submit} className={cx("mx-auto flex min-h-[calc(100dvh-8rem)] max-w-3xl flex-col md:min-h-[calc(100dvh-9.5rem)]", className)}>
      <div className="flex flex-1 flex-col justify-end gap-3 pb-5">
        <div className="flex items-end gap-3">
          {busy ? <Mascot mood="busy" size={64} arrive="pop" /> : done ? <Mascot mood="cheer" size={64} arrive="hop" /> : <Mascot watch mood="idle" size={64} />}
          <p className="max-w-xl rounded-2xl rounded-bl-md bg-surface-2/80 px-4 py-3 text-sm text-ink" role={busy || done ? "status" : undefined}>
            {busy ? "On it…" : done ? "Here it is." : (outcome || line || "Tell me what you want, the way you'd tell a friend.")}
          </p>
        </div>
        {note && <p role="status" className="text-sm text-warm">{note}</p>}
        {secondary && <div className="text-sm">{secondary}</div>}
      </div>
      <div className="sticky bottom-2 z-10 rounded-[14px] bg-surface shadow-lg ring-1 ring-line-strong focus-within:ring-2 focus-within:ring-brand/50 md:bottom-4">
        <textarea ref={ref} rows={2} className="block max-h-48 w-full resize-none rounded-t-[14px] bg-transparent px-4 py-3.5 text-base text-strong placeholder:text-muted focus:outline-none [field-sizing:content]"
          value={prompt} onChange={(e) => setPrompt(e.target.value)} maxLength={1000} disabled={busy || loading} aria-label="What should it make?"
          placeholder={loading ? "" : "Say what you want, the way you'd tell a friend."}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) submit(e); }} />
        <div className="flex items-center justify-end gap-3 px-3 pb-3">
          <span className="mr-auto hidden text-xs text-faint sm:block">Enter to send · Shift + Enter for a new line</span>
          <Button type="submit" variant="accent" busy={busy} disabled={!prompt.trim() || loading || disabled}>{submitLabel} <ArrowRight className="size-4" /></Button>
        </div>
      </div>
    </form>
  );
}
