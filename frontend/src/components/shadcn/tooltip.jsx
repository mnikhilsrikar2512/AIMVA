// shadcn/ui-style Tooltip on Radix. Use for icon-only buttons; never put essential info only here.
import { Tooltip as T } from "radix-ui";
import { cn } from "@/lib/utils";

export const TooltipProvider = ({ delayDuration = 300, ...p }) => <T.Provider delayDuration={delayDuration} {...p} />;
export function Tooltip({ content, children, side = "top" }) {
  // A disabled button gets no pointer or focus events, so its reason would never show. Wrap it in a span that does.
  const off = children?.props?.disabled || children?.props?.["aria-disabled"];
  return (
    <T.Root>
      <T.Trigger asChild>{off ? <span tabIndex={0} className="inline-flex cursor-not-allowed rounded-lg">{children}</span> : children}</T.Trigger>
      <T.Portal>
        <T.Content side={side} sideOffset={6} className={cn("z-50 rounded-md bg-strong px-2 py-1 text-xs text-white shadow-sm")}>{content}</T.Content>
      </T.Portal>
    </T.Root>
  );
}
