// Home's one box (plan S1, S2, S4; 2026-11-21): "What do you need today?" in the owner's language, four starters
// written from what the business is missing, and three plain choices when a sentence points nowhere. It never says how
// a sentence was read (quiet-intelligence rule); the screen it opens is the answer.
import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowUp, Globe, Image as ImageIcon, Megaphone, Video } from "lucide-react";
import { post } from "../lib/api";
import { moduleHref } from "../lib/projects";
import { readUiLang } from "../lib/setupCopy";
import { markAutoRun } from "./ModulePrompt";
import { cx } from "./ui";

// Claude translations: need a native speaker's check before launch, like the rest of setupCopy.
const WORDS = {
  en: { placeholder: "What do you need today?", hint: "Ask in any language, the way you'd tell a friend.", which: "What should I make?" },
  hi: { placeholder: "आज आपको क्या चाहिए?", hint: "किसी भी भाषा में लिखिए, जैसे किसी दोस्त से कहते हैं।", which: "क्या बनाऊँ?" },
  te: { placeholder: "ఈ రోజు మీకు ఏం కావాలి?", hint: "ఏ భాషలోనైనా, స్నేహితుడికి చెప్పినట్టు రాయండి.", which: "ఏం చేయాలి?" },
  ta: { placeholder: "இன்று உங்களுக்கு என்ன வேண்டும்?", hint: "எந்த மொழியிலும், நண்பரிடம் சொல்வது போல எழுதுங்கள்.", which: "எதைச் செய்யட்டும்?" },
};

const CHOICES = [
  { module: "pictures", label: "A picture", icon: ImageIcon },
  { module: "page", label: "A website page", icon: Globe },
  { module: "campaigns", label: "An ad", icon: Megaphone },
  { module: "videos", label: "A short video", icon: Video },
];

// The next festival worth a poster, by month (approximate; good enough to suggest, never to schedule).
const FESTIVALS = [
  [0, "Sankranti"], [1, "Valentine's Day"], [2, "Holi"], [3, "Ugadi"], [4, "summer"], [5, "monsoon"],
  [6, "monsoon"], [7, "Independence Day"], [8, "Ganesh Chaturthi"], [9, "Dussehra"], [10, "Christmas"], [11, "New Year"],
];
const festival = (d = new Date()) => FESTIVALS[(d.getMonth() + (d.getDate() > 20 ? 1 : 0)) % 12][1];

/** Up to four starters, from what is missing first. Each is a sentence the box sends as if typed. */
export function starters({ hasPage, waiting, modules }) {
  const out = [];
  const has = (k) => !modules?.length || modules.includes(k);
  if (waiting > 0) out.push({ text: `Reply to ${waiting === 1 ? "the customer" : `the ${waiting} customers`} waiting`, to: "/app/leads" });
  if (!hasPage && has("page")) out.push({ text: "Make my website page" });
  const f = festival();
  out.push({ text: `A ${f} offer poster` });
  if (has("campaigns")) out.push({ text: "Run a ₹500 ad this week" });
  if (hasPage && out.length < 4) out.push({ text: "How are my ads doing?" });
  if (out.length < 4) out.push({ text: "A 15-second video of my shop" });
  return out.slice(0, 4);
}

export function AskBox({ hasPage, waiting = 0, modules = [] }) {
  const navigate = useNavigate();
  const lang = readUiLang();
  const w = WORDS[lang] || WORDS.en;
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [unsure, setUnsure] = useState(null);  // the sentence, while the three choices are showing
  const ref = useRef(null);
  const chips = useMemo(() => starters({ hasPage, waiting, modules }), [hasPage, waiting, modules]);

  const open = (module, prompt) => {
    if (["pictures", "page", "campaigns", "videos", "calls"].includes(module)) markAutoRun(prompt);
    navigate(moduleHref(module, prompt));
  };
  const ask = async (sentence) => {
    const q = (sentence ?? text).trim();
    if (!q || busy) return;
    setBusy(true);
    try {
      const r = await post("/api/route", { text: q });
      if (r.sure === false) { setUnsure(q); setText(q); return; }
      open(r.module, r.prompt);
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };

  return (
    <section aria-label="Ask AIMVA" className="max-w-3xl">
      <form onSubmit={(e) => { e.preventDefault(); ask(); }}
        className="flex items-end gap-2 rounded-[14px] bg-surface p-2 pl-4 ring-1 ring-line-strong focus-within:ring-2 focus-within:ring-brand/50">
        <textarea ref={ref} rows={1} value={text} maxLength={1000} disabled={busy} aria-label={w.placeholder} placeholder={w.placeholder}
          onChange={(e) => { setText(e.target.value); setUnsure(null); e.target.style.height = "auto"; e.target.style.height = `${Math.min(e.target.scrollHeight, 132)}px`; }}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }}
          className="block max-h-[132px] min-h-[40px] flex-1 resize-none bg-transparent py-2 text-base text-strong placeholder:text-muted focus:outline-none" />
        <button type="submit" disabled={!text.trim() || busy} aria-label="Ask"
          className={cx("grid size-10 shrink-0 place-items-center rounded-[10px] bg-accent text-accent-ink transition-opacity disabled:opacity-40", busy && "animate-pulse")}>
          <ArrowUp className="size-5" strokeWidth={2.2} />
        </button>
      </form>

      {unsure ? (
        <div className="mt-3" role="group" aria-label={w.which}>
          <p className="mb-2 text-sm text-muted">{w.which}</p>
          <div className="flex flex-wrap gap-2">
            {CHOICES.filter((c) => !modules?.length || modules.includes(c.module) || c.module === "pictures").map((c) => (
              <button key={c.module} type="button" onClick={() => open(c.module, unsure)}
                className="inline-flex h-9 items-center gap-2 rounded-full bg-surface-2 px-3.5 text-sm font-medium text-strong hover:bg-lavender">
                <c.icon className="size-4 text-muted" /> {c.label}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
          <p className="mt-2 px-1 text-xs text-muted">{w.hint}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {chips.map((c) => (
              <button key={c.text} type="button" disabled={busy}
                onClick={() => (c.to ? navigate(c.to) : ask(c.text))}
                className="h-8 rounded-full px-3 text-sm text-ink ring-1 ring-line hover:bg-surface-2 hover:ring-line-strong">
                {c.text}
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
