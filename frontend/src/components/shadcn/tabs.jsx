// shadcn/ui-style Tabs on Radix: roving focus with arrow keys, correct tab roles.
import { Tabs as T } from "radix-ui";
import { cn } from "@/lib/utils";

export const Tabs = T.Root;
export const TabsContent = T.Content;
export function TabsList({ className, ...props }) {
  return <T.List className={cn("inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-lg bg-surface-2 p-0.5 [scrollbar-width:none]", className)} {...props} />;
}
export function TabsTrigger({ className, ...props }) {
  return (
    <T.Trigger
      className={cn("h-7 shrink-0 cursor-pointer whitespace-nowrap rounded-md px-3 text-sm font-medium text-muted transition-colors hover:text-strong",
        "data-[state=active]:bg-surface data-[state=active]:text-strong data-[state=active]:shadow-[var(--shadow-soft)]", className)}
      {...props} />
  );
}
