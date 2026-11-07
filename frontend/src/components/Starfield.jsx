import { useEffect, useRef } from "react";

// Lightweight canvas starfield with faint connecting lines (replaces the 6.5k-particle three.js scene).
export default function Starfield({ density = 0.00012 }) {
  const ref = useRef(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas.getContext("2d");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w, h, stars, raf;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.min(220, Math.floor(w * h * density));
      stars = Array.from({ length: n }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        r: Math.random() * 1.3 + 0.2,
        vx: (Math.random() - 0.5) * 0.12,
        vy: (Math.random() - 0.5) * 0.12,
        hue: [190, 250, 280][Math.floor(Math.random() * 3)],
      }));
    };

    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      for (let i = 0; i < stars.length; i++) {
        const s = stars[i];
        if (!reduce) {
          s.x = (s.x + s.vx + w) % w;
          s.y = (s.y + s.vy + h) % h;
        }
        for (let j = i + 1; j < stars.length; j++) {
          const t = stars[j];
          const d = (s.x - t.x) ** 2 + (s.y - t.y) ** 2;
          if (d < 9000) {
            ctx.strokeStyle = `rgba(125,140,255,${0.08 * (1 - d / 9000)})`;
            ctx.beginPath();
            ctx.moveTo(s.x, s.y);
            ctx.lineTo(t.x, t.y);
            ctx.stroke();
          }
        }
        ctx.fillStyle = `hsla(${s.hue},90%,75%,0.8)`;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();
      }
      if (!reduce) raf = requestAnimationFrame(draw);
    };

    resize();
    draw();
    window.addEventListener("resize", resize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, [density]);

  return <canvas ref={ref} aria-hidden className="pointer-events-none fixed inset-0 -z-10 h-full w-full" />;
}
