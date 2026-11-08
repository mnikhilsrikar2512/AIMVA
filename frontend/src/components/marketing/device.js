// Decides how much motion the public site runs. Mid-range phones on mobile data are the common case, so anything
// heavy (pointer tilt, WebGL) only runs when the device can clearly afford it; everyone else gets the same scene, still.

const mq = (q) => typeof window !== "undefined" && window.matchMedia?.(q).matches;

export const prefersReducedMotion = () => !!mq("(prefers-reduced-motion: reduce)");
export const finePointer = () => !!mq("(hover: hover) and (pointer: fine)");

/** Enough memory, cores and bandwidth for continuous motion, and the person hasn't asked for less of it. */
export function richMotion() {
  if (typeof navigator === "undefined" || prefersReducedMotion()) return false;
  const c = navigator.connection;
  if (c?.saveData || /(^|-)2g$/.test(c?.effectiveType || "")) return false;
  if (navigator.deviceMemory && navigator.deviceMemory < 4) return false;
  if (navigator.hardwareConcurrency && navigator.hardwareConcurrency < 4) return false;
  return true;
}

/** WebGL scenes need everything above plus a working GPU context. */
export function canWebGL() {
  if (!richMotion()) return false;
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}
