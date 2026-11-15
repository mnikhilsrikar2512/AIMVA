// Download as one icon. Several formats → a small menu (Excel, PDF, CSV). One format → the icon downloads directly.
// Excel is a real .xlsx; PDF is a real .pdf file (built in the browser, never the print dialog).
import { useState } from "react";
import { Download, FileSpreadsheet, FileText, Sheet } from "lucide-react";
import { toast } from "sonner";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "./shadcn/dropdown-menu";
import { Tooltip, TooltipProvider } from "./shadcn/tooltip";
import { downloadBlob, stamp, toXlsx } from "../lib/exporters";
import { cx, Spinner } from "./ui";

export function DownloadMenu({ name, excel, pdf, csvHref, disabled, reason }) {
  const [busy, setBusy] = useState(false);
  const safe = (fn) => async () => {
    setBusy(true);
    try { await fn(); } catch (e) { toast.error(`Couldn't make the file: ${e.message}`); } finally { setBusy(false); }
  };
  const formats = [
    excel && { key: "xlsx", label: "Excel (.xlsx)", icon: FileSpreadsheet, run: safe(() => { downloadBlob(toXlsx(excel()), `AIMVA ${name} ${stamp()}.xlsx`); toast.success("Excel file downloaded."); }) },
    pdf && { key: "pdf", label: "PDF", icon: FileText, run: safe(async () => { await pdf(`AIMVA ${name} ${stamp()}.pdf`); toast.success("PDF downloaded."); }) },
    csvHref && { key: "csv", label: "CSV", icon: Sheet, href: csvHref },
  ].filter(Boolean);
  if (!formats.length) return null;
  const tip = disabled ? (reason || "Nothing to download yet") : formats.length === 1 ? `Download ${formats[0].label}` : "Download";
  const cls = cx("btn-subtle w-9 px-0", (disabled || busy) && "pointer-events-none");
  const icon = busy ? <Spinner className="size-4" /> : <Download className="size-4" />;

  // Nothing to export (no rows, or still loading): a muted, disabled icon whose tooltip says why. Never hidden.
  if (disabled) {
    return <TooltipProvider><Tooltip content={tip}><button type="button" aria-label={`Download ${name.toLowerCase()}: ${tip}`} disabled className={cx(cls, "opacity-40")}>{icon}</button></Tooltip></TooltipProvider>;
  }
  let trigger;
  if (formats.length === 1) {
    const f = formats[0];
    trigger = f.href
      ? <a href={disabled ? undefined : f.href} aria-label={tip} aria-disabled={disabled || undefined} className={cls}>{icon}</a>
      : <button type="button" aria-label={tip} disabled={disabled} className={cls} onClick={f.run}>{icon}</button>;
    return <TooltipProvider><Tooltip content={tip}>{trigger}</Tooltip></TooltipProvider>;
  }
  return (
    <TooltipProvider>
      <DropdownMenu>
        <Tooltip content={tip}>
          <DropdownMenuTrigger asChild>
            <button type="button" aria-label={`Download ${name.toLowerCase()}`} aria-busy={busy || undefined} disabled={disabled || busy} className={cls}>{icon}</button>
          </DropdownMenuTrigger>
        </Tooltip>
        <DropdownMenuContent className="w-52">
          <DropdownMenuLabel>Download {name.toLowerCase()}</DropdownMenuLabel>
          {formats.map((f) => f.href
            ? <DropdownMenuItem key={f.key} asChild><a href={f.href}><f.icon /> {f.label}</a></DropdownMenuItem>
            : <DropdownMenuItem key={f.key} onSelect={f.run}><f.icon /> {f.label}</DropdownMenuItem>)}
        </DropdownMenuContent>
      </DropdownMenu>
    </TooltipProvider>
  );
}
