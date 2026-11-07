// shadcn/ui-style Dialog on Radix: focus trap, focus return, Escape and outside click, screen-reader title.
import { Dialog as D } from "radix-ui";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({ className, children, hideClose, ...props }) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-strong/25 backdrop-blur-[2px] data-[state=open]:animate-[fade_.15s_ease]" />
      <D.Content
        className={cn(
          "fixed inset-x-0 bottom-0 z-50 max-h-[92dvh] w-full overflow-y-auto bg-surface pb-[env(safe-area-inset-bottom)] shadow-[var(--shadow-lift)] outline-none sm:pb-0",
          "rounded-t-2xl sm:inset-auto sm:left-1/2 sm:top-1/2 sm:max-w-lg sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl",
          "data-[state=open]:animate-[rise_.18s_ease]",
          className,
        )}
        {...props}
      >
        {children}
        {!hideClose && (
          <D.Close className="btn-subtle btn-sm absolute right-3 top-3 px-2" aria-label="Close">
            <X className="size-4" />
          </D.Close>
        )}
      </D.Content>
    </D.Portal>
  );
}
export function DialogHeader({ className, ...props }) {
  return <div className={cn("px-5 pb-1 pt-4 pr-12", className)} {...props} />;
}
export function DialogTitle({ className, ...props }) {
  return <D.Title className={cn("text-base font-semibold text-strong", className)} {...props} />;
}
export function DialogDescription({ className, ...props }) {
  return <D.Description className={cn("mt-1 text-sm text-muted", className)} {...props} />;
}
