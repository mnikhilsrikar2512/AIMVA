// A quiet grid of dots for the sign-in side panel (the one place outside marketing that may move, design.md v3).
// Dots near the pointer drift away from it and brighten; they settle back when the pointer leaves.
// Still for people who ask for reduced motion, and nothing runs while the pointer is away.
import { useEffect, useRef } from "react";

const GAP = 26;       // px between dots
const REACH = 140;    // how far the pointer's pull is felt
const PUSH = 18;      // max px a dot moves

export function DotField({ className }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, dpr = 1, dots = [], raf = 0;
    const pointer = { x: -1e4, y: -1e4, in: false };

    const layout = () => {
      const r = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = r.width; h = r.height;
      canvas.width = w * dpr; canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      dots = [];
      for (let y = GAP / 2; y < h; y += GAP) for (let x = GAP / 2; x < w; x += GAP) dots.push({ x, y, ox: 0, oy: 0 });
      draw();
    };
    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      let moving = false;
      for (const d of dots) {
        let tx = 0, ty = 0, glow = 0;
        if (pointer.in && !still) {
          const dx = d.x - pointer.x, dy = d.y - pointer.y, dist = Math.hypot(dx, dy);
          if (dist < REACH && dist > 0.01) {
            const f = (1 - dist / REACH) ** 2;
            tx = (dx / dist) * PUSH * f; ty = (dy / dist) * PUSH * f; glow = f;
          }
        }
        d.ox += (tx - d.ox) * 0.15; d.oy += (ty - d.oy) * 0.15;
        if (Math.abs(tx - d.ox) > 0.05 || Math.abs(ty - d.oy) > 0.05) moving = true;
        // Fainter over the dark top, a touch stronger lower down where the gradient turns cyan.
        const base = 0.14 + 0.12 * (d.y / h);
        ctx.fillStyle = `rgba(255,255,255,${Math.min(0.9, base + glow * 0.6)})`;
        ctx.beginPath();
        ctx.arc(d.x + d.ox, d.y + d.oy, 1.2 + glow * 1.3, 0, Math.PI * 2);
        ctx.fill();
      }
      raf = moving || pointer.in ? requestAnimationFrame(draw) : 0;
    };
    const kick = () => { if (!raf && !still) raf = requestAnimationFrame(draw); };
    const host = canvas.parentElement;
    const move = (e) => { const r = canvas.getBoundingClientRect(); pointer.x = e.clientX - r.left; pointer.y = e.clientY - r.top; pointer.in = true; kick(); };
    const leave = () => { pointer.in = false; kick(); };
    const ro = new ResizeObserver(layout);
    ro.observe(canvas);
    host.addEventListener("pointermove", move);
    host.addEventListener("pointerleave", leave);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); host.removeEventListener("pointermove", move); host.removeEventListener("pointerleave", leave); };
  }, []);
  return <canvas ref={ref} aria-hidden className={className} />;
}
