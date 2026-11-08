// "Made with AIMVA": the sample pages as phones on a rail. The centred phone scrolls through its whole page so people
// see what the builder actually makes, top to bottom. On capable devices the side phones turn away in 3D as they leave
// the centre (one transform per card per frame, written directly, no React re-render).
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ArrowUpRight } from "lucide-react";
import { SAMPLES, sampleImg, sampleUrl } from "./samples";
import { prefersReducedMotion, richMotion } from "./device";
import { cx } from "./Site";

const SCREEN = 19 / 9; // phone screen height / width

export default function SampleGallery() {
  const rail = useRef(null);
  const [active, setActive] = useState(0);
  const [rich] = useState(richMotion);
  const [still] = useState(prefersReducedMotion);
  const [seen, setSeen] = useState(false);

  useEffect(() => {
    const el = rail.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setSeen(e.isIntersecting), { threshold: 0.35 });
    io.observe(el);
    let raf = 0;
    const paint = () => {
      raf = 0;
      const box = el.getBoundingClientRect();
      const mid = box.left + box.width / 2;
      let best = 0, bestD = Infinity;
      [...el.children].forEach((card, n) => {
        const r = card.getBoundingClientRect();
        const d = (r.left + r.width / 2 - mid) / r.width;
        if (Math.abs(d) < bestD) { bestD = Math.abs(d); best = n; }
        if (rich) {
          const c = Math.max(-1.6, Math.min(1.6, d));
          card.style.transform = `perspective(1100px) rotateY(${-c * 22}deg) translateZ(${-Math.abs(c) * 70}px)`;
          card.style.opacity = String(1 - Math.min(0.45, Math.abs(c) * 0.3));
        }
      });
      setActive(best);
    };
    const on = () => { if (!raf) raf = requestAnimationFrame(paint); };
    paint();
    el.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => { io.disconnect(); el.removeEventListener("scroll", on); window.removeEventListener("resize", on); cancelAnimationFrame(raf); };
  }, [rich]);

  const go = (n) => {
    const el = rail.current, card = el?.children[Math.max(0, Math.min(SAMPLES.length - 1, n))];
    card?.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "nearest", inline: "center" });
  };

  return (
    <div className="mt-8 sm:mt-12">
      <div ref={rail} tabIndex={0} aria-label="Sample pages. Use the arrow keys to move between them." role="region"
        onKeyDown={(e) => { if (e.key === "ArrowRight") { e.preventDefault(); go(active + 1); } if (e.key === "ArrowLeft") { e.preventDefault(); go(active - 1); } }}
        className="mk-rail flex gap-4 overflow-x-auto py-6 [padding-inline:calc(50%-110px)] focus-visible:outline-offset-[-2px] sm:gap-8 sm:[padding-inline:calc(50%-125px)]">
        {SAMPLES.map((s, n) => {
          const on = n === active;
          const shift = `${(1 - SCREEN / s.tall) * -100}%`;
          return (
            <figure key={s.key} className="group w-[220px] shrink-0 transition-[opacity] duration-300 will-change-transform sm:w-[250px]">
              <button type="button" onClick={() => (on ? window.open(sampleUrl(s.key), "_blank", "noopener") : go(n))}
                aria-label={on ? `Open the ${s.kind.toLowerCase()} sample page in a new tab` : `Show the ${s.kind.toLowerCase()} sample`}
                className="mk-phone block aspect-[9/19] w-full cursor-pointer">
                <span className="mk-screen block">
                  <img src={sampleImg(s.key, "full")} alt="" width="480" height={Math.round(480 * s.tall)} loading="lazy" decoding="async"
                    className="absolute inset-x-0 top-0 w-full ease-in-out"
                    style={{
                      transform: on && seen && !still ? `translateY(${shift})` : "translateY(0)",
                      transition: still ? "none" : `transform ${on && seen ? Math.round(s.tall * 2.2) : 0.8}s cubic-bezier(0.45,0,0.25,1) ${on && seen ? "0.8s" : "0s"}`,
                    }} />
                </span>
              </button>
              <figcaption className={cx("mt-4 text-center transition-opacity duration-300", on ? "opacity-100" : "opacity-60")}>
                <span className="block text-sm font-semibold text-strong">{s.kind}</span>
                <span className="block text-xs text-muted">{s.layout} · {s.place}</span>
              </figcaption>
            </figure>
          );
        })}
      </div>
      <div className="mt-2 flex items-center justify-center gap-2">
        <button type="button" className="btn-subtle size-10 rounded-full p-0" onClick={() => go(active - 1)} disabled={active === 0} aria-label="Previous sample"><ArrowLeft className="size-4" /></button>
        <div className="flex gap-1.5" aria-hidden>
          {SAMPLES.map((s, n) => <span key={s.key} className={cx("h-1.5 rounded-full transition-all duration-300", n === active ? "w-6 bg-peach" : "w-1.5 bg-line-strong")} />)}
        </div>
        <button type="button" className="btn-subtle size-10 rounded-full p-0" onClick={() => go(active + 1)} disabled={active === SAMPLES.length - 1} aria-label="Next sample"><ArrowRight className="size-4" /></button>
        <a href={sampleUrl(SAMPLES[active].key)} target="_blank" rel="noopener" className="mk-go ml-2 inline-flex h-10 items-center gap-1 rounded-full px-3 text-sm font-semibold text-brand hover:bg-lavender/60">
          Open it <ArrowUpRight className="size-4" />
        </a>
      </div>
    </div>
  );
}
