import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge class names; later Tailwind classes win over earlier ones (shadcn convention). */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
