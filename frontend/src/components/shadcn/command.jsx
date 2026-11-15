// shadcn/ui-style Command palette on cmdk (Ctrl/Cmd+K): search, arrow keys, groups.
import { Command as C } from "cmdk";
import { Search } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "./dialog";
import { cn } from "@/lib/utils";

// Match word starts, then plain substrings. No loose fuzzy matches: cmdk 1.1 does not reorder groups, so a fuzzy
// hit like "dASHboard" for "asha" would sit above the lead Asha Nair and win Enter.
const esc = (w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
function filter(value, search, keywords) {
  const words = search.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const text = `${value} ${(keywords || []).join(" ")}`.toLowerCase();
  if (!words.length) return 1;
  if (words.every((w) => new RegExp(`(^|[\\s@.+-])${esc(w)}`).test(text))) return 1;
  return words.every((w) => text.includes(w)) ? 0.5 : 0;
}

export function CommandDialog({ open, onOpenChange, placeholder = "Search or jump to…", search, onSearch, children }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent hideClose className="sm:top-[18%] sm:translate-y-0 sm:max-w-xl" aria-describedby={undefined}>
        <DialogTitle className="sr-only">Search</DialogTitle>
        <C className="flex flex-col" loop filter={filter}>
          <div className="flex items-center gap-2 border-b border-line px-3">
            <Search className="size-4 text-muted" />
            <C.Input value={search} onValueChange={onSearch} placeholder={placeholder} className="h-11 flex-1 bg-transparent text-sm text-strong outline-none placeholder:text-faint" />
          </div>
          <C.List className="max-h-80 overflow-y-auto p-1">
            <C.Empty className="px-3 py-6 text-center text-sm text-muted">Nothing found.</C.Empty>
            {children}
          </C.List>
        </C>
      </DialogContent>
    </Dialog>
  );
}
export const CommandGroup = ({ className, ...p }) => <C.Group className={cn("[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted", className)} {...p} />;
export const CommandItem = ({ className, ...p }) => <C.Item className={cn("flex h-9 cursor-pointer items-center gap-2 rounded-lg px-2.5 text-sm text-ink data-[selected=true]:bg-surface-2 [&_svg]:size-4 [&_svg]:text-muted", className)} {...p} />;
