// The reply moment: a lead writes in their own language and the WhatsApp hello comes back in the same one, while the
// mascot calls her back beside it (owner 2026-11-21: "i dont like the orb"). He sits in a call card, talks (his voice
// shows as bars that move with his words) and looks at you between sentences. No WebGL, so nothing heavy loads.
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView } from "framer-motion";
import { Phone } from "lucide-react";
import { ease } from "../Motion";
import { Mascot } from "../Mascot";
import { prefersReducedMotion } from "./device";
import { cx } from "./Site";

// Example conversation. Names and business are examples.
const TALK = [
  { code: "te", label: "తెలుగు", name: "Telugu",
    lead: "నమస్తే, శనివారం ఉచిత చెకప్ దొరుకుతుందా?",
    reply: "నమస్తే లక్ష్మి గారు, Smile Studio Dental కి మెసేజ్ చేసినందుకు ధన్యవాదాలు. శనివారం కుదురుతుంది. ఉదయం 11 గంటలకా, సాయంత్రం 4 గంటలకా?" },
  { code: "hi", label: "हिन्दी", name: "Hindi",
    lead: "नमस्ते, क्या शनिवार को फ्री चेक-अप हो सकता है?",
    reply: "नमस्ते लक्ष्मी जी, Smile Studio Dental से संपर्क करने के लिए धन्यवाद। हाँ, शनिवार ठीक है। सुबह 11 बजे या शाम 4 बजे?" },
  { code: "hl", label: "Hinglish", name: "Hinglish",
    lead: "Hi, Saturday ko free check-up ho sakta hai kya?",
    reply: "Hi Lakshmi ji, haan bilkul! Saturday ko 11 baje ya shaam 4 baje, kaunsa time theek rahega?" },
  { code: "en", label: "English", name: "English",
    lead: "Hi, is the free check-up available this Saturday?",
    reply: "Hi Lakshmi, thanks for writing to Smile Studio Dental. Yes, Saturday works. Would 11 am or 4 pm suit you?" },
];
const HOLD = 7000;

/** Word-like pulses while he speaks, with a short pause between sentences. Only runs while on screen. */
function useSpeech(on) {
  const [bars, setBars] = useState(() => Array(14).fill(0.15));
  const [talking, setTalking] = useState(false);
  useEffect(() => {
    if (!on) { setTalking(false); return undefined; }
    let t, n = 0;
    const word = () => {
      n += 1;
      const pause = n % 9 === 0;
      setTalking(!pause);
      setBars((b) => b.map(() => (pause ? 0.12 : 0.2 + Math.random() * 0.8)));
      t = setTimeout(word, pause ? 1100 : 130 + Math.random() * 180);
    };
    word();
    return () => clearTimeout(t);
  }, [on]);
  return [bars, talking];
}

function CallCard({ on, still }) {
  const [bars, talking] = useSpeech(on && !still);
  const [secs, setSecs] = useState(14);
  useEffect(() => { if (!on || still) return undefined; const t = setInterval(() => setSecs((s) => s + 1), 1000); return () => clearInterval(t); }, [on, still]);
  return (
    <div className="relative overflow-hidden rounded-3xl bg-[#0f2a30] px-5 pb-5 pt-6 text-white shadow-[0_30px_70px_-30px_rgba(15,40,47,0.7)]">
      <div aria-hidden className="pointer-events-none absolute -top-24 left-1/2 size-72 -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgba(94,230,240,0.28),transparent)]" />
      <div className="relative flex justify-center">
        {/* soft rings while he speaks, like sound leaving */}
        {!still && talking && [0, 1].map((k) => (
          <span key={k} aria-hidden className="absolute left-1/2 top-[44%] size-40 -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#5EE6F0]/30" style={{ animation: `mk-ring 2.4s ${k * 1.2}s ease-out infinite` }} />
        ))}
        <Mascot mood={talking ? "happy" : "hello"} size={150} watch={!talking} label="AIMVA's assistant on a call" />
      </div>
      <div className="relative mt-3 flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-sm"><span className="grid size-7 place-items-center rounded-full bg-[#5EE6F0]/15 text-[#5EE6F0]"><Phone className="size-3.5" /></span>
          <span><b className="font-semibold">Calling Lakshmi back</b><span className="block text-xs text-white/60">0:{String(secs % 60).padStart(2, "0")} · in English</span></span></span>
        <span className="flex h-7 items-center gap-[3px]" aria-hidden>
          {bars.map((h, k) => <span key={k} className="w-[3px] rounded-full bg-[#5EE6F0] transition-[height] duration-150" style={{ height: `${Math.round(h * 100)}%` }} />)}
        </span>
      </div>
    </div>
  );
}

export default function ReplyScene() {
  const ref = useRef(null);
  const near = useInView(ref, { margin: "200px 0px" });
  const visible = useInView(ref, { amount: 0.35 });
  const [still] = useState(prefersReducedMotion);
  const [i, setI] = useState(0);
  const [typing, setTyping] = useState(false);
  const [held, setHeld] = useState(false);
  const t = TALK[i];

  // The lead's message lands, the reply "types" for a moment, then arrives in the same language.
  useEffect(() => {
    if (still) return;
    setTyping(true);
    const a = setTimeout(() => setTyping(false), 1300);
    return () => clearTimeout(a);
  }, [i, still]);
  useEffect(() => {
    if (still || !visible || held) return;
    const n = setTimeout(() => setI((v) => (v + 1) % TALK.length), HOLD);
    return () => clearTimeout(n);
  }, [i, visible, held, still]);

  return (
    <div ref={ref} className="mt-8 grid items-center gap-8 sm:mt-12 md:grid-cols-[0.9fr_1.1fr] md:gap-12"
      onPointerEnter={(e) => e.pointerType === "mouse" && setHeld(true)} onPointerLeave={() => setHeld(false)}>
      {/* The mascot on the call */}
      <div className="mx-auto w-full max-w-[300px] md:max-w-[340px]">
        {near ? <CallCard on={visible} still={still} /> : <div className="aspect-[4/5] rounded-3xl bg-[#0f2a30]" />}
      </div>

      {/* WhatsApp thread */}
      <div className="w-full max-w-md justify-self-center md:justify-self-start">
        <div className="flex flex-wrap gap-1" role="group" aria-label="Language the lead writes in">
          {TALK.map((x, n) => (
            <button key={x.code} type="button" aria-pressed={n === i} onClick={() => setI(n)}
              className={cx("relative h-9 rounded-full px-3.5 text-sm font-medium transition-colors", n === i ? "text-white" : "text-muted hover:text-strong")}>
              {n === i && <motion.span layoutId="reply-pill" className="absolute inset-0 rounded-full bg-strong" transition={{ type: "spring", stiffness: 420, damping: 34 }} />}
              <span className="relative">{x.label}</span>
            </button>
          ))}
        </div>
        <div className="mt-4 rounded-2xl p-3 sm:p-4" style={{ background: "linear-gradient(180deg, #e9eeeb, #e2ebe6)" }} aria-live="polite">
          <p className="pb-2 text-center text-xs text-muted">Example conversation</p>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={t.code} initial={still ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: 0.15 } }} className="space-y-2">
              <motion.p initial={still ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease }}
                className="mr-10 w-fit rounded-2xl rounded-tl-md bg-surface px-3.5 py-2.5 text-[15px] leading-relaxed text-strong shadow-[var(--shadow-soft)]">
                <span className="block text-xs font-semibold text-warm">Lakshmi R.</span>{t.lead}
              </motion.p>
              {typing && !still ? (
                <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="ml-auto flex w-fit gap-1 rounded-2xl rounded-tr-md bg-[#d7f2e3] px-4 py-3.5" aria-label="Replying">
                  {[0, 1, 2].map((d) => <span key={d} className="size-1.5 rounded-full bg-brand" style={{ animation: `mk-type 1s ${d * 0.15}s infinite` }} />)}
                </motion.p>
              ) : (
                <motion.div initial={still ? false : { opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ type: "spring", stiffness: 300, damping: 26 }}
                  className="ml-10 rounded-2xl rounded-tr-md bg-[#d7f2e3] px-3.5 py-2.5 text-[15px] leading-relaxed text-strong">
                  {t.reply}
                  <span className="mt-1 flex items-center justify-end gap-1 text-xs text-muted">Replied in {t.name}
                    <svg viewBox="0 0 18 12" className="h-3 w-4 text-[#34b7f1]" aria-hidden><path d="M1 6.5 4.5 10 11 2M7 9l1 1 6.5-8" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  </span>
                </motion.div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-muted">Calls are in English today. Hindi, Telugu and Tamil voices are coming.</p>
      </div>
    </div>
  );
}
