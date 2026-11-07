// shadcn/ui-style Popover on Radix: positioned, collision-aware, closes on Escape / outside click.
import { Popover as P } from "radix-ui";
import { cn } from "@/lib/utils";

export const Popover = P.Root;
export const PopoverTrigger = P.Trigger;
export const PopoverAnchor = P.Anchor;
export function PopoverContent({ className, align = "start", sideOffset = 6, ...props }) {
  return (
    <P.Portal>
      <P.Content align={align} sideOffset={sideOffset}
        className={cn("z-50 w-72 rounded-xl bg-surface p-3 text-sm text-ink shadow-[var(--shadow-lift)] outline-none data-[state=open]:animate-[fade_.12s_ease]", className)}
        {...props} />
    </P.Portal>
  );
}
