// shadcn/ui-style DropdownMenu on Radix: arrow keys, typeahead, Escape, correct menu roles.
import { DropdownMenu as M } from "radix-ui";
import { cn } from "@/lib/utils";

export const DropdownMenu = M.Root;
export const DropdownMenuTrigger = M.Trigger;
export const DropdownMenuGroup = M.Group;
export function DropdownMenuContent({ className, sideOffset = 6, align = "end", ...props }) {
  return (
    <M.Portal>
      <M.Content sideOffset={sideOffset} align={align}
        className={cn("z-50 min-w-44 rounded-xl bg-surface p-1 text-sm shadow-[var(--shadow-lift)] outline-none data-[state=open]:animate-[appfade_.12s_ease-out]", className)}
        {...props} />
    </M.Portal>
  );
}
export function DropdownMenuItem({ className, danger, ...props }) {
  return (
    <M.Item
      className={cn("flex h-8 cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 text-ink outline-none data-[highlighted]:bg-surface-2 data-[disabled]:opacity-50 [&_svg]:size-4 [&_svg]:text-muted",
        danger && "text-danger data-[highlighted]:bg-danger/10 [&_svg]:text-danger", className)}
      {...props} />
  );
}
export const DropdownMenuSeparator = ({ className, ...p }) => <M.Separator className={cn("my-1 h-px bg-line", className)} {...p} />;
export const DropdownMenuLabel = ({ className, ...p }) => <M.Label className={cn("px-2.5 py-1.5 text-xs font-medium text-muted", className)} {...p} />;
