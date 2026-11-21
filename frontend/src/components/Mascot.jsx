// AIMVA's mascot (owner 2026-11-21: "it should show emotions", "mischievous, taunting, but friendly", and then "the
// expressions should come from one mascot, not by changing the mascot"). So he is ONE picture split into three layers,
// the body and his two detached glass hands, with the eyes drawn on the visor. Every mood is the same body: the eyes
// close for a beat and open in the new shape, and the hands move to the new gesture. Nothing is ever swapped for a
// different drawing. Rules from the plan: calm by default, motion only to say something, still for reduced motion,
// never cheeky about money, errors or customers waiting.
import { AnimatePresence, MotionConfig, motion, useAnimationControls, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import cx from "clsx";

// The drawing space (owner's art, upscaled 4x so he stays sharp up to about 600px wide). BOX is the part his body
// fills: `size` is that box's width; hands may reach outside it without pushing the layout around.
const W = 1080, H = 900;
const BOX = { x: 240, y: 165, w: 600, h: 720 };
const EYES = [[459.6, 363.3], [598.5, 352.2]];
const HAND = { l: { x: 219, y: 542, w: 127, h: 176 }, r: { x: 721, y: 514, w: 120, h: 174 } };
const GLOW = "#8BF6F1";
const EYE_SCALE = 1.41;  // owner 2026-11-21: "make the eyes big"
const LOOK = 0.9;        // how far the eyes travel, in canvas units per pointer unit

// One eye per face, drawn around (0,0). `side` is -1 for the left eye, 1 for the right, so shapes can mirror.
const oval = (rx, ry, dx = 0, dy = 0) => <ellipse cx={dx} cy={dy} rx={rx} ry={ry} fill={GLOW} />;
const arc = (d) => <path d={d} fill="none" stroke={GLOW} strokeWidth="13" strokeLinecap="round" />;
const FACES = {
  hello: () => oval(19, 30),
  happy: () => arc("M-24 10 Q0 -28 24 10"),
  cheer: () => arc("M-26 12 Q0 -32 26 12"),
  thinking: (side) => (side < 0 ? oval(17, 24, 10, -12) : oval(17, 13, 10, -14)),
  sorry: (s0) => { const side = -s0; return <path d={`M${-22 * side} 2 L${22 * side} -16 Q${24 * side} 24 0 26 Q${-24 * side} 24 ${-22 * side} 2Z`} fill={GLOW} />; },
  surprised: () => <circle r="27" fill={GLOW} />,
  wink: (side) => (side < 0 ? oval(19, 30) : arc("M-22 6 Q0 -22 22 6")),
  cheeky: (side) => (
    <g transform="translate(9 0)">
      <path d="M-21 0 L21 0 Q23 26 0 27 Q-23 26 -21 0Z" fill={GLOW} />
      {side > 0 && arc("M-20 -22 L18 -30")}
    </g>
  ),
  pointing: () => oval(18, 26, 12, 6),  // looking right, at the words and the button beside him
  sleepy: () => arc("M-20 4 Q0 14 20 4"),
  shy: () => arc("M-22 2 Q0 16 22 2"),  // eyes politely shut while you type a password
  focused: () => <path d="M-20 -6 L20 -6 Q22 20 0 22 Q-22 20 -20 -6Z" fill={GLOW} />,  // concentrating while he works
  confused: (side) => (side < 0 ? oval(15, 22) : oval(19, 30, 0, -6)),
};

// Moods without their own eyes borrow one.
const FACE_OF = { idle: "hello", calm: "happy", busy: "focused", data: "pointing", sit: "sleepy", peek: "surprised" };

// Where each hand rests for a mood (canvas units, from the hand's resting place). Rotation is about the wrist.
const REST = { x: 0, y: 0, rotate: 0 };
const HANDS = {
  hello: { r: { x: 30, y: -190, rotate: -12 } },
  happy: { l: { x: -10, y: -40, rotate: -12 }, r: { x: 10, y: -40, rotate: 12 } },
  cheer: { l: { x: -40, y: -230, rotate: -25 }, r: { x: 40, y: -230, rotate: 25 } },
  thinking: { l: { x: 135, y: -105, rotate: 30 } },
  sorry: { l: { x: 100, y: -30, rotate: 25 }, r: { x: -100, y: -30, rotate: -25 } },
  surprised: { l: { x: -30, y: -130, rotate: -30 }, r: { x: 30, y: -130, rotate: 30 } },
  wink: { r: { x: 20, y: -80, rotate: 18 } },
  cheeky: { r: { x: -170, y: -150, rotate: -35 } },
  pointing: { r: { x: 90, y: -90, rotate: -80 } },
  sleepy: { l: { x: 0, y: 25, rotate: 8 }, r: { x: 0, y: 25, rotate: -8 } },
  shy: { l: { x: 175, y: -265, rotate: 20 }, r: { x: -180, y: -250, rotate: -20 } },
  confused: { r: { x: -190, y: -360, rotate: -45 } },
  busy: { l: { x: 70, y: -40, rotate: 15 }, r: { x: -70, y: -40, rotate: -15 } },
  focused: { l: { x: 135, y: -105, rotate: 30 } },
  data: { r: { x: 90, y: -90, rotate: -80 } },
  peek: { l: { x: 175, y: -265, rotate: 20 } },
};
// A short gesture played once when the mood arrives (on top of the resting place above).
const GESTURE = {
  hello: { r: { rotate: [-12, 18, -12, 18, -12], transition: { duration: 1.4, ease: "easeInOut" } } },
  cheer: { l: { y: [-230, -260, -230], transition: { duration: 0.5, repeat: 1 } }, r: { y: [-230, -260, -230], transition: { duration: 0.5, repeat: 1 } } },
  busy: { l: { y: [-40, -55, -40], transition: { duration: 0.35, repeat: Infinity } }, r: { y: [-40, -25, -40], transition: { duration: 0.35, repeat: Infinity } } },
  cheeky: { r: { rotate: [-35, -25, -35, -25, -35], transition: { duration: 0.8 } } },
  confused: { r: { x: [-190, -175, -190, -175, -190], transition: { duration: 0.9 } } },
};
const BLINKS = new Set(["hello", "thinking", "surprised", "pointing", "cheeky", "idle", "confused"]);
// Faces he can glance into for a moment while idle (a wink, a smile), then back.
const GLANCE = { hello: "wink", happy: "wink", idle: "happy", calm: "wink", pointing: "happy" };

let preloaded = false;
function preload() {
  if (preloaded || typeof Image === "undefined") return;
  preloaded = true;
  ["body", "hand-l", "hand-r"].forEach((n) => { new Image().src = `/mascot/${n}.webp`; });
}

/** Where the caret is on screen, near enough: the end of the typed text (or of the last line in a box). */
let measure;
function caretPoint(el) {
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  measure = measure || document.createElement("canvas").getContext("2d");
  measure.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  let pos = el.value.length;
  try { if (typeof el.selectionStart === "number") pos = el.selectionStart; } catch { /* email inputs */ }
  const before = el.value.slice(0, pos);
  const lines = before.split("\n");
  const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.4;
  const x = r.left + parseFloat(cs.paddingLeft) + Math.min(measure.measureText(lines[lines.length - 1]).width, r.width - 20);
  const y = el.tagName === "TEXTAREA" ? Math.min(r.bottom - 8, r.top + parseFloat(cs.paddingTop) + (lines.length - 0.5) * lh) : r.top + r.height / 2;
  return { x, y };
}

/** The eyes. A new face arrives with a quick blink: the old shape closes, the new one opens, so it reads as one face. */
function Face({ face, look = [0, 0], blink }) {
  const draw = FACES[face] || FACES.hello;
  return (
    <g style={{ filter: `drop-shadow(0 0 8px ${GLOW}aa)` }}>
      {EYES.map(([x, y], i) => (
        <motion.g key={i} initial={false} animate={{ x: x + look[0] * LOOK, y: y + look[1] * LOOK }} transition={{ type: "spring", stiffness: 400, damping: 30 }}>
          <motion.g initial={false} animate={{ scaleX: EYE_SCALE, scaleY: blink ? 0.08 : EYE_SCALE }} transition={{ duration: 0.08 }}>
            <AnimatePresence mode="wait" initial={false}>
              <motion.g key={face} initial={{ scaleY: 0.1 }} animate={{ scaleY: 1 }} exit={{ scaleY: 0.1 }} transition={{ duration: 0.09 }}>
                {draw(i === 0 ? -1 : 1)}
              </motion.g>
            </AnimatePresence>
          </motion.g>
        </motion.g>
      ))}
    </g>
  );
}

function Hand({ side, controls }) {
  const h = HAND[side];
  return (
    <motion.g animate={controls} initial={false} style={{ transformBox: "fill-box", transformOrigin: "50% 75%" }}>
      <image href={`/mascot/hand-${side}.webp`} x={h.x} y={h.y} width={h.w} height={h.h} />
    </motion.g>
  );
}

/**
 * <Mascot mood="hello" size={96} />
 *  mood     hello | idle | calm | happy | cheer | thinking | sorry | surprised | wink | cheeky | pointing | sleepy |
 *           confused | busy | focused | data | sit | peek
 *  alive    floats gently and fidgets now and then (default on; still for reduced motion)
 *  size     width in px; changing it makes him grow or shrink, which is how he "turns big or small"
 *  arrive   "hop" jumps in from below and lands with a squash, "pop" scales in
 *  watch    eyes follow the pointer, and your typing anywhere on the page; eyes shut and hands up for passwords
 *  gaze     [x, y] where to look when not watching (about -18..18, -14..14)
 *  say      a short line in a bubble; onTap makes him hop and lets the caller change mood or line
 */
export function Mascot({ mood = "hello", size = 96, arrive = null, watch = false, say = null, sayAlign = "left", onTap, className, label, alive = true, gaze = null }) {
  const reduce = useReducedMotion();
  const [glance, setGlance] = useState(null);
  const ref = useRef(null);
  const body = useAnimationControls();
  const left = useAnimationControls();
  const right = useAnimationControls();
  const [blink, setBlink] = useState(false);
  const [look, setLook] = useState([0, 0]);
  useEffect(preload, []);
  // Where he is looking when he is not following you (for example over at the result beside him).
  const gx = gaze?.[0], gy = gaze?.[1];
  useEffect(() => { if (!watch && gx !== undefined) setLook([gx, gy]); }, [watch, gx, gy]);

  // Blink now and then (every 3-6 s), only for open-eyed moods.
  useEffect(() => {
    if (!BLINKS.has(mood)) return undefined;
    let t;
    const loop = () => { t = setTimeout(() => { setBlink(true); setTimeout(() => setBlink(false), 120); loop(); }, 3000 + Math.random() * 3000); };
    loop();
    return () => clearTimeout(t);
  }, [mood]);

  // Watching with you (owner 2026-11-21): the eyes follow the pointer, and while you type anywhere on the page they
  // follow your words as they appear. While you type a password he shuts his eyes and turns away a little.
  const [typing, setTyping] = useState(null);  // null | "text" | "secret"
  useEffect(() => {
    if (!watch) return undefined;
    const aim = (x, y) => {
      const r = ref.current?.getBoundingClientRect();
      if (!r) return;
      const dx = x - (r.left + r.width / 2), dy = y - (r.top + r.height * 0.33);
      const d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 300);
      setLook([(dx / d) * 18 * k, (dy / d) * 14 * k]);
    };
    const move = (e) => { if (!typingRef.current) aim(e.clientX, e.clientY); };
    const typingRef = { current: null };
    const follow = () => {
      const el = document.activeElement;
      const field = el && (el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && !["checkbox", "radio", "button", "submit", "range", "file"].includes(el.type)));
      if (!field) { typingRef.current = null; setTyping(null); return; }
      const secret = el.type === "password";
      typingRef.current = secret ? "secret" : "text";
      setTyping(typingRef.current);
      if (secret) return;
      const p = caretPoint(el);
      aim(p.x, p.y);
    };
    window.addEventListener("pointermove", move);
    document.addEventListener("focusin", follow);
    const out = () => setTimeout(follow, 0);
    document.addEventListener("focusout", out);
    document.addEventListener("input", follow);
    document.addEventListener("keyup", follow);
    document.addEventListener("click", follow);
    return () => {
      window.removeEventListener("pointermove", move);
      document.removeEventListener("focusin", follow);
      document.removeEventListener("focusout", out);
      document.removeEventListener("input", follow);
      document.removeEventListener("keyup", follow);
      document.removeEventListener("click", follow);
    };
  }, [watch]);
  // What he is showing right now: a password covers his eyes, typing makes him look, otherwise the mood.
  const shown = typing === "secret" ? "shy" : typing ? "hello" : mood;
  const face = glance || FACE_OF[shown] || (FACES[shown] ? shown : "hello");

  // Hands glide to the new gesture, then play its little flourish once.
  useEffect(() => {
    const pose = HANDS[shown] || {};
    const spring = { type: "spring", stiffness: 170, damping: 18 };
    const go = async (ctl, key) => {
      const to = { ...REST, ...(pose[key] || {}) };
      await ctl.start({ ...to, transition: spring });
      const g = GESTURE[shown]?.[key];
      if (g && !reduce) ctl.start(g);
    };
    go(left, "l"); go(right, "r");
  }, [shown, left, right, reduce]);
  useEffect(() => {
    body.start({ rotate: typing === "secret" ? -4 : 0, transition: { type: "spring", stiffness: 200, damping: 16 } });
  }, [typing, body]);

  // Arrival, and a whole-body reaction for the big moods.
  useEffect(() => {
    if (arrive === "hop") body.start({ y: [60, -36, 0, 0], scaleY: [1, 1.04, 0.86, 1], scaleX: [1, 0.97, 1.1, 1], opacity: [0, 1, 1, 1], transition: { duration: 0.75, times: [0, 0.45, 0.75, 1], ease: "easeOut" } });
    else if (arrive === "pop") body.start({ scale: [0.4, 1.08, 1], opacity: [0, 1, 1], transition: { duration: 0.45 } });
  }, [arrive, body]);
  useEffect(() => {
    if (mood === "cheer") body.start({ y: [0, -28, 0, -12, 0], scaleY: [1, 1.03, 0.9, 1, 1], transition: { duration: 0.9 } });
    if (mood === "sorry") body.start({ rotate: [0, -4, 0], y: [0, 4, 0], transition: { duration: 0.8 } });
    if (mood === "surprised") body.start({ y: [0, -10, 0], transition: { duration: 0.35 } });
    if (mood === "thinking" || mood === "confused") body.start({ rotate: [0, 5, 5], transition: { duration: 0.5 } });
    else if (mood !== "sorry") body.start({ rotate: 0, transition: { duration: 0.4 } });
  }, [mood, body]);

  // Alive: every 7-13 s a small fidget (a hop, a head tilt, a glance), never while someone asked for less motion.
  useEffect(() => {
    if (!alive || reduce) return undefined;
    let t, g;
    const next = () => {
      t = setTimeout(() => {
        const r = Math.random();
        if (r < 0.3) body.start({ y: [0, -14, 0], scaleY: [1, 1.03, 0.94, 1], transition: { duration: 0.55 } });
        else if (r < 0.6) body.start({ rotate: [0, -7, 3, 0], transition: { duration: 0.9, ease: "easeInOut" } });
        else if (GLANCE[mood]) { setGlance(GLANCE[mood]); g = setTimeout(() => setGlance(null), 900); }
        else { setBlink(true); setTimeout(() => setBlink(false), 120); }
        next();
      }, 7000 + Math.random() * 6000);
    };
    next();
    return () => { clearTimeout(t); clearTimeout(g); };
  }, [alive, reduce, mood, body]);

  const tap = () => {
    body.start({ y: [0, -30, 0], scaleY: [1, 1.04, 0.9, 1], transition: { duration: 0.5 } });
    onTap?.();
  };

  const Tag = onTap ? motion.button : motion.div;
  return (
    <MotionConfig reducedMotion="user">
      <motion.div initial={false} animate={{ width: size }} transition={{ type: "spring", stiffness: 170, damping: 24 }}
        className={cx("relative inline-block shrink-0 select-none", className)}>
        {say && (
          <motion.p key={say} initial={{ opacity: 0, y: 6, scale: 0.9 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.25, delay: arrive ? 0.6 : 0 }}
            className={cx("absolute bottom-[96%] z-10 w-max max-w-[220px] rounded-xl bg-surface px-3 py-2 text-[13px] leading-snug text-strong shadow-[var(--shadow-lift)] ring-1 ring-line",
              sayAlign === "side" ? "bottom-auto right-full top-[8%] mr-2 rounded-tr-sm" : sayAlign === "left" ? "right-[55%] rounded-br-sm" : "left-[55%] rounded-bl-sm")} role="status">
            {say}
          </motion.p>
        )}
        <motion.div animate={alive ? { y: [0, -5, 0], rotate: [0, 1.2, 0, -1.2, 0], scale: [1, 1.012, 1] } : undefined}
          transition={{ duration: 3.6, repeat: Infinity, ease: "easeInOut" }} style={{ originY: 0.9 }}>
          <Tag ref={ref} type={onTap ? "button" : undefined} onClick={onTap ? tap : undefined} animate={body}
            aria-label={onTap ? (label || "AIMVA") : undefined} aria-hidden={onTap ? undefined : true}
            style={{ originY: 1 }} className={cx("block w-full", onTap && "cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50 rounded-2xl")}>
            <span className="relative block" style={{ aspectRatio: `${BOX.w} / ${BOX.h}` }}>
              <svg viewBox={`0 0 ${W} ${H}`} className="absolute block overflow-visible"
                style={{ left: `${(-BOX.x / BOX.w) * 100}%`, top: `${(-BOX.y / BOX.h) * 100}%`, width: `${(W / BOX.w) * 100}%` }}>
                <image href="/mascot/body.webp" width={W} height={H} />
                <Face face={face} look={typing === "secret" ? [0, 6] : look} blink={blink} />
                <Hand side="l" controls={left} />
                <Hand side="r" controls={right} />
              </svg>
            </span>
          </Tag>
        </motion.div>
      </motion.div>
    </MotionConfig>
  );
}

/** Lines with a bit of cheek, by situation. Never cheeky when someone is waiting, money is involved, or things broke. */
export function homeLine({ waiting = 0, live = 0, leads = 0, hour = new Date().getHours(), taps = 0 }) {
  if (waiting > 0) return { mood: "surprised", say: waiting === 1 ? "Someone's waiting for you. I'd reply first." : `${waiting} people are waiting. I'd reply first.` };
  const lines = [];
  if (!live) lines.push({ mood: "cheeky", say: "Nothing's live yet. I'm getting bored here." }, { mood: "pointing", say: "Type anything in that box. I dare you." });
  else if (leads >= 10) lines.push({ mood: "happy", say: `${leads} leads this week. Show-off.` }, { mood: "wink", say: "Keep this up and I'll need a bigger desk." });
  else if (leads > 0) lines.push({ mood: "happy", say: `${leads} ${leads === 1 ? "lead" : "leads"} this week. I want more.` }, { mood: "cheeky", say: "Not bad. A festival poster would help." });
  else lines.push({ mood: "thinking", say: "Your ad is live. I'm watching it like a hawk." }, { mood: "cheeky", say: "Still waiting on lead number one. Patience is hard." });
  if (hour >= 22 || hour < 5) lines.unshift({ mood: "sleepy", say: "Working late? Me too, sort of." });
  lines.push({ mood: "wink", say: "Stop poking me. Go make something." }, { mood: "cheer", say: "Fine, one jump. Happy now?" });
  return lines[taps % lines.length];
}
