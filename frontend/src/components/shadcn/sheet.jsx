// shadcn/ui-style Sheet: a Radix Dialog that slides in from the side (side panels, drawers).
import { Dialog as D } from "radix-ui";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export const Sheet = D.Root;
export const SheetTrigger = D.Trigger;
export const SheetClose = D.Close;
export const SheetTitle = ({ className, ...p }) => <D.Title className={cn("text-sm font-semibold text-strong", className)} {...p} />;
export const SheetDescription = ({ className, ...p }) => <D.Description className={cn("text-sm text-muted", className)} {...p} />;

export function SheetContent({ side = "right", className, children, ...props }) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-strong/20 data-[state=open]:animate-[appfade_.12s_ease-out]" />
      <D.Content
        className={cn(
          "fixed inset-y-0 z-50 flex w-full max-w-sm flex-col bg-bg shadow-[var(--shadow-lift)] outline-none data-[state=open]:animate-[appfade_.12s_ease-out]",
          side === "right" ? "right-0 border-l border-line" : "left-0 border-r border-line",
          className,
        )}
        {...props}
      >
        {children}
        <D.Close className="btn-subtle btn-sm absolute right-2 top-2 px-2" aria-label="Close">
          <X className="size-4" />
        </D.Close>
      </D.Content>
    </D.Portal>
  );
}
