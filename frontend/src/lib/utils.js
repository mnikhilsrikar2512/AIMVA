import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge class names; later Tailwind classes win over earlier ones (shadcn convention). */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/**
 * Send a picture or video to WhatsApp (plan S8). Phones: the share sheet with the file itself, so it lands in a chat or
 * status as media. Computers: the file downloads and WhatsApp Web opens, so it can be attached there.
 * Returns "shared" | "downloaded" | "cancelled".
 */
export async function shareToWhatsApp(url, name = "aimva") {
  const res = await fetch(url, { credentials: "include" });
  const blob = await res.blob();
  const ext = (blob.type.split("/")[1] || "png").replace("jpeg", "jpg").split("+")[0];
  const file = new File([blob], `${name}.${ext}`, { type: blob.type });
  if (navigator.canShare?.({ files: [file] })) {
    try { await navigator.share({ files: [file] }); return "shared"; } catch (e) { if (e?.name === "AbortError") return "cancelled"; }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = file.name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  window.open("https://web.whatsapp.com/", "_blank", "noopener");
  return "downloaded";
}
