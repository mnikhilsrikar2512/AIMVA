import { useRef, useState } from "react";
import { FileText, Paperclip, Trash2, UploadCloud } from "lucide-react";
import { toast } from "sonner";
import { Spinner, cx } from "./ui";
import { api, del } from "../lib/api";

export const ACCEPT_IMAGES = "image/png,image/jpeg,image/webp,image/gif";
export const ACCEPT_ALL = `${ACCEPT_IMAGES},application/pdf,.docx,.txt,.md,.csv`;
const MAX_MB = 15;

/** Upload one or more reference files. Calls onUploaded(ref) for each success; shows clear errors otherwise. */
export function useReferenceUpload(onUploaded) {
  const [busy, setBusy] = useState(false);
  const upload = async (files) => {
    setBusy(true);
    for (const file of files) {
      if (file.size > MAX_MB * 1024 * 1024) {
        toast.error(`${file.name}: files must be ${MAX_MB} MB or smaller.`);
        continue;
      }
      const form = new FormData();
      form.append("file", file);
      try {
        const r = await api("/api/references", { method: "POST", form });
        onUploaded?.(r);
        toast.success(`${file.name} added${r.kind === "document" ? ` (${r.chars.toLocaleString()} characters read)` : ""}`);
      } catch (e) {
        toast.error(`${file.name}: ${e.message}`);
      }
    }
    setBusy(false);
  };
  return [busy, upload];
}

export function UploadTile({ accept = ACCEPT_ALL, onUploaded, label = "Upload", className }) {
  const input = useRef(null);
  const [busy, upload] = useReferenceUpload(onUploaded);
  return (
    <button type="button" onClick={() => input.current?.click()} disabled={busy} aria-label={label}
      className={cx("grid shrink-0 place-items-center rounded-xl border-2 border-dashed border-line-strong text-xs font-medium text-muted transition hover:border-brand hover:text-brand", className)}>
      {busy ? <Spinner className="size-4" /> : <span className="flex flex-col items-center gap-0.5"><UploadCloud className="size-4" />{label}</span>}
      <input ref={input} type="file" hidden multiple accept={accept} onChange={(e) => { upload([...e.target.files]); e.target.value = ""; }} />
    </button>
  );
}

export function ReferenceDropzone({ accept = ACCEPT_ALL, onUploaded, hint }) {
  const input = useRef(null);
  const [over, setOver] = useState(false);
  const [busy, upload] = useReferenceUpload(onUploaded);
  return (
    <button type="button" onClick={() => input.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); upload([...e.dataTransfer.files]); }}
      className={cx("flex w-full flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed px-4 py-5 text-center transition",
        over ? "border-brand bg-lavender" : "border-line-strong bg-surface-2/40 hover:border-brand/50")}>
      {busy ? <Spinner className="size-5 text-brand" /> : <Paperclip className="size-5 text-brand" />}
      <span className="text-sm font-semibold text-strong">Drop reference files or click to upload</span>
      <span className="text-xs text-faint">{hint || `Images, PDF, Word (.docx), .txt, .md, .csv · up to ${MAX_MB} MB each`}</span>
      <input ref={input} type="file" hidden multiple accept={accept} onChange={(e) => { upload([...e.target.files]); e.target.value = ""; }} />
    </button>
  );
}

/** Select uploaded documents (PDF/Word/text) to brief the AI writer. value: number[] of reference ids. */
export function DocumentPicker({ docs, value, onChange, onDeleted }) {
  if (!docs.length) return null;
  return (
    <ul className="space-y-1.5">
      {docs.map((d) => {
        const on = value.includes(d.id);
        return (
          <li key={d.id} className={cx("flex items-center gap-3 rounded-xl px-3 py-2 text-sm", on ? "bg-lavender/70" : "bg-surface-2/60")}>
            <input type="checkbox" className="size-4 accent-violet-500" checked={on} aria-label={`Use ${d.filename}`}
              onChange={() => onChange(on ? value.filter((x) => x !== d.id) : value.length < 10 ? [...value, d.id] : value)} />
            <FileText className="size-4 shrink-0 text-faint" />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium text-strong">{d.filename}</span>
              <span className="block truncate text-xs text-muted">{d.excerpt}</span>
            </span>
            <button type="button" className="btn-subtle btn-sm" aria-label={`Delete ${d.filename}`}
              onClick={async () => { await del(`/api/references/${d.id}`); onDeleted(d.id); }}><Trash2 className="size-3.5" /></button>
          </li>
        );
      })}
    </ul>
  );
}
