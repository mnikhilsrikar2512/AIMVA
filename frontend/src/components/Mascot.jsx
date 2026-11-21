// AIMVA's mascot (owner 2026-11-21: "add this, I like it" + "it should show emotions" + "it can turn small, big, jump on
// boxes and grids; mischievous, taunting, but friendly"). One body picture, the face drawn on top so each mood is a few
// lines of SVG instead of another image. Rules kept from the plan: small and calm by default, motion only to say
// something (arrive, react, celebrate), still for people who ask their phone for less motion, never cheeky about money,
// errors or customers waiting.
import { MotionConfig, motion, useAnimationControls } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import cx from "clsx";

const W = 760, H = 649;                 // body.png's drawing space
const EYES = [[303, 217], [459, 219]];  // visor eye centres in that space
const GLOW = "#8BF6F1";
const EYE_SCALE = 1.6;                  // owner 2026-11-21: "make the eyes big"

// One eye per mood, drawn around (0,0). `side` is -1 for the left eye, 1 for the right, so shapes can mirror.
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
};
// Real poses (owner's Gemini art, cut out 2026-11-21), used up to 200px wide where the art stays sharp. Above that, and
// for moods without a pose, he is the front body with eyes drawn on the visor (which can also follow the pointer).
const POSES = { hello: "wave", happy: "happy", cheer: "cheer", thinking: "thinking", sorry: "sorry", surprised: "surprised",
  wink: "wink", cheeky: "giggle", pointing: "point", confused: "confused", sit: "sit", peek: "peek" };
const BLINKS = new Set(["hello", "thinking", "surprised", "pointing", "cheeky"]);

/** The face on its own, for places too small for the body (a 24px badge, a toast). */
function Face({ mood, look = [0, 0], blink }) {
  const draw = FACES[mood] || FACES.hello;
  return (
    <g style={{ filter: `drop-shadow(0 0 10px ${GLOW}aa)` }}>
      {EYES.map(([x, y], i) => (
        <motion.g key={i} initial={false} animate={{ x: x + look[0], y: y + look[1], scaleX: EYE_SCALE, scaleY: blink ? 0.15 : EYE_SCALE }}
          transition={{ type: "spring", stiffness: 400, damping: 30, scaleY: { duration: 0.08 } }}>
          {draw(i === 0 ? -1 : 1)}
        </motion.g>
      ))}
    </g>
  );
}

/**
 * <Mascot mood="hello" size={96} />
 *  mood     hello | happy | cheer | thinking | sorry | surprised | wink | cheeky | pointing | sleepy | confused | sit | peek
 *  face     true = always the drawn face (the landing hero, where he is too big for the pose art)
 *  size     width in px; changing it makes him grow or shrink (spring), which is how he "turns big or small"
 *  arrive   "hop" jumps in from below and lands with a squash (use when he lands on a card), "pop" scales in
 *  watch    eyes follow the pointer around the page (Home only; it's the mischievous bit)
 *  say      a short line in a bubble; onTap makes him hop and lets the caller change mood or line
 */
export function Mascot({ mood = "hello", size = 96, arrive = null, watch = false, say = null, sayAlign = "left", onTap, className, label, face = false }) {
  const pose = !face && size <= 200 ? POSES[mood] : null;
  const ref = useRef(null);
  const body = useAnimationControls();
  const [blink, setBlink] = useState(false);
  const [look, setLook] = useState([0, 0]);

  // Blink now and then (every 3-6 s), only for open-eyed moods.
  useEffect(() => {
    if (!BLINKS.has(mood)) return undefined;
    let t;
    const loop = () => { t = setTimeout(() => { setBlink(true); setTimeout(() => setBlink(false), 120); loop(); }, 3000 + Math.random() * 3000); };
    loop();
    return () => clearTimeout(t);
  }, [mood]);

  // Eyes follow the pointer, a few pixels at most.
  useEffect(() => {
    if (!watch) return undefined;
    const move = (e) => {
      const r = ref.current?.getBoundingClientRect();
      if (!r) return;
      const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height * 0.33);
      const d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 400);
      setLook([(dx / d) * 16 * k, (dy / d) * 12 * k]);
    };
    window.addEventListener("pointermove", move);
    return () => window.removeEventListener("pointermove", move);
  }, [watch]);

  // Arrival, and a celebration bounce whenever the mood turns to cheer.
  useEffect(() => {
    if (arrive === "hop") body.start({ y: [60, -36, 0, 0], scaleY: [1, 1.04, 0.86, 1], scaleX: [1, 0.97, 1.1, 1], opacity: [0, 1, 1, 1], transition: { duration: 0.75, times: [0, 0.45, 0.75, 1], ease: "easeOut" } });
    else if (arrive === "pop") body.start({ scale: [0.4, 1.08, 1], opacity: [0, 1, 1], transition: { duration: 0.45 } });
  }, [arrive, body]);
  useEffect(() => {
    if (mood === "cheer") body.start({ y: [0, -28, 0, -12, 0], scaleY: [1, 1.03, 0.9, 1, 1], transition: { duration: 0.9 } });
    if (mood === "sorry") body.start({ rotate: [0, -4, 0], y: [0, 4, 0], transition: { duration: 0.8 } });
    if (mood === "surprised") body.start({ y: [0, -10, 0], transition: { duration: 0.35 } });
  }, [mood, body]);

  const tap = () => {
    body.start({ y: [0, -30, 0], scaleY: [1, 1.04, 0.9, 1], transition: { duration: 0.5 } });
    onTap?.();
  };

  const Tag = onTap ? motion.button : motion.div;
  return (
    <MotionConfig reducedMotion="user">
      <motion.div initial={false} animate={{ width: size }} transition={{ type: "spring", stiffness: 260, damping: 18 }}
        className={cx("relative inline-block shrink-0 select-none", className)}>
        {say && (
          <motion.p key={say} initial={{ opacity: 0, y: 6, scale: 0.9 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.25, delay: arrive ? 0.6 : 0 }}
            className={cx("absolute bottom-[96%] z-10 w-max max-w-[220px] rounded-xl bg-surface px-3 py-2 text-[13px] leading-snug text-strong shadow-[var(--shadow-lift)] ring-1 ring-line",
              sayAlign === "side" ? "bottom-auto right-full top-[8%] mr-2 rounded-tr-sm" : sayAlign === "left" ? "right-[55%] rounded-br-sm" : "left-[55%] rounded-bl-sm")} role="status">
            {say}
          </motion.p>
        )}
        <Tag ref={ref} type={onTap ? "button" : undefined} onClick={onTap ? tap : undefined} animate={body}
          aria-label={onTap ? (label || "AIMVA") : undefined} aria-hidden={onTap ? undefined : true}
          style={{ originY: 1 }} className={cx("block w-full", onTap && "cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50 rounded-2xl")}>
          {pose ? (
            <img src={`/mascot/poses/${pose}.webp`} alt="" draggable={false} className="block h-auto w-full" />
          ) : (
            <svg viewBox={`0 0 ${W} ${H}`} className="block w-full overflow-visible">
              <image href="/mascot/body.webp" width={W} height={H} />
              <Face mood={FACES[mood] ? mood : "hello"} look={look} blink={blink} />
            </svg>
          )}
        </Tag>
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
