// Client sign-off. When a workspace asks for approval, Publish / Deploy / Launch turn into "Send for approval"
// until the client says yes (ApprovalGate), and the client decides from their bell (ApprovalInbox).
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, Clock, ExternalLink, MessageSquare, Send } from "lucide-react";
import { Button, Modal, Spinner } from "./ui";
import { post } from "../lib/api";
import { timeAgo, useApi } from "../lib/hooks";
import { useIsClient } from "../lib/auth";

const KIND_LABEL = { site: "page", campaign: "campaign", asset: "picture" };

/** Reload when an approval is requested or decided anywhere in this workspace (live events, or this tab). */
export function useApprovalEvents(handler) {
  useEffect(() => {
    window.addEventListener("aimva:approval", handler);
    return () => window.removeEventListener("aimva:approval", handler);
  }, [handler]);
}
const announce = (detail) => window.dispatchEvent(new CustomEvent("aimva:approval", { detail }));

/**
 * Wraps a Publish / Deploy / Launch control. With approval off, or once the client approved this exact version,
 * it shows `children` unchanged. Otherwise it shows where things stand and a "Send for approval" button.
 * `beforeSend` runs first (e.g. save the editor) so the client sees the latest version.
 */
export function ApprovalGate({ kind, refId, children, beforeSend }) {
  const isClient = useIsClient();  // clients decide from their bell; they never send
  const { data, error, reload } = useApi(refId && !isClient ? `/api/approvals/status?kind=${kind}&ref_id=${refId}` : null);
  const [open, setOpen] = useState(false);
  useApprovalEvents(reload);
  // Not loaded or not needed: show the normal button. If approval is needed after all, the server says so on click.
  if (!refId || isClient || error || (data && (!data.required || data.state === "approved"))) return children;
  if (!data) return <Button size="sm" variant="ghost" disabled aria-label="Checking approval"><Spinner /></Button>;
  const a = data.approval;
  if (data.state === "pending") {
    return (
      <>
        <button type="button" className="btn-ghost btn-sm whitespace-nowrap" onClick={() => setOpen(true)}
          title={`Sent to your client${a ? ` ${timeAgo(a.created_at)}` : ""}. Click to send it again.`}>
          <Clock className="size-3.5 text-amber-600" /> Waiting for client
        </button>
        <SendDialog open={open} onClose={() => setOpen(false)} kind={kind} refId={refId} beforeSend={beforeSend} state={data.state} approval={a} onSent={reload} />
      </>
    );
  }
  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}
        title={data.state === "edited" ? "Changed since the client approved it, so it needs their OK again" : undefined}>
        <Send className="size-3.5" /> {data.state === "none" ? "Send for approval" : "Send for approval again"}
      </Button>
      <SendDialog open={open} onClose={() => setOpen(false)} kind={kind} refId={refId} beforeSend={beforeSend} state={data.state} approval={a} onSent={reload} />
    </>
  );
}

function SendDialog({ open, onClose, kind, refId, beforeSend, state, approval, onSent }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await beforeSend?.();
      const a = await post("/api/approvals", { kind, ref_id: refId, note: note.trim() });
      toast.success("Sent to your client. You can publish once they approve.");
      setNote("");
      onClose();
      onSent?.();
      announce({ type: "requested", approval: a });
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Send for approval">
      <form onSubmit={send} className="space-y-4">
        {state === "changes" && approval?.comment && (
          <div className="rounded-xl bg-surface-2 px-4 py-3 text-sm">
            <p className="text-xs font-medium text-muted">Your client asked for changes {approval.decided_at ? timeAgo(approval.decided_at) : ""}</p>
            <p className="mt-1 whitespace-pre-line text-ink">“{approval.comment}”</p>
          </div>
        )}
        {state === "edited" && <p className="text-sm text-muted">This {KIND_LABEL[kind]} changed after your client approved it, so it needs their OK again.</p>}
        {state === "pending" && <p className="text-sm text-muted">Your client hasn't answered yet. Sending again replaces the earlier request and emails them again.</p>}
        <p className="text-sm text-muted">Your client gets an email and finds it in their bell. Publishing unlocks as soon as they approve.</p>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-strong">Note for your client <span className="font-normal text-muted">(optional)</span></span>
          <textarea className="input" rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)}
            placeholder={state === "changes" ? "Swapped in your clinic photo." : "Anything they should look at first."} />
        </label>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" busy={busy}><Send className="size-4" /> Send</Button>
        </div>
      </form>
    </Modal>
  );
}

/** The client's side: everything waiting for their OK, with a look at it and Approve / Ask for changes. */
export function useApprovalInbox(enabled) {
  const inbox = useApi(enabled ? "/api/approvals?status=pending&preview=true" : null, []);
  useApprovalEvents(inbox.reload);
  return inbox;
}

export function ApprovalInbox({ inbox }) {
  const items = Array.isArray(inbox.data) ? inbox.data : [];
  if (inbox.error) return (
    <p className="px-1 py-4 text-center text-sm text-muted">
      Approvals didn't load. <button className="font-medium text-brand hover:underline" onClick={inbox.reload}>Try again</button>
    </p>
  );
  if (!items.length) return null;
  const done = (id) => inbox.setData(items.filter((x) => x.id !== id));
  return (
    <section aria-label="Waiting for your approval" className="mb-3">
      <h3 className="px-1 pb-1 text-xs font-semibold uppercase tracking-wide text-muted">Waiting for your OK</h3>
      <ul className="border-t border-line">
        {items.map((a) => <ApprovalItem key={a.id} a={a} onDone={() => done(a.id)} />)}
      </ul>
    </section>
  );
}

function ApprovalItem({ a, onDone }) {
  const [asking, setAsking] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState("");
  const p = a.preview || {};
  const decide = async (decision) => {
    setBusy(decision);
    try {
      const out = await post(`/api/approvals/${a.id}/decide`, { decision, comment: comment.trim() });
      toast.success(decision === "approved" ? "Approved. Your agency can publish it now." : "Sent. Your agency will make the changes.");
      onDone();
      announce({ type: "decided", approval: out });
    } catch (e) { toast.error(e.message); } finally { setBusy(""); }
  };
  return (
    <li className="border-b border-line py-3">
      <p className="text-sm font-medium text-strong">{a.title}</p>
      <p className="mt-0.5 text-xs text-muted">
        {KIND_LABEL[a.kind] ? KIND_LABEL[a.kind][0].toUpperCase() + KIND_LABEL[a.kind].slice(1) : a.kind}
        {a.requested_by ? ` from ${a.requested_by}` : ""} · {timeAgo(a.created_at)}
      </p>
      {a.note && <p className="mt-1.5 whitespace-pre-line rounded-lg bg-surface-2 px-3 py-2 text-xs text-ink">“{a.note}”</p>}
      {a.kind === "campaign" && (p.headline || p.text || p.image_url) && (
        <div className="mt-2 overflow-hidden rounded-lg border border-line">
          {p.image_url && <img src={p.image_url} alt="" className="max-h-40 w-full object-cover" />}
          <div className="space-y-0.5 px-3 py-2 text-xs">
            {p.headline && <p className="font-semibold text-strong">{p.headline}</p>}
            {p.text && <p className="line-clamp-3 text-ink">{p.text}</p>}
            <p className="pt-1 text-muted">{p.daily_budget ? `₹${Number(p.daily_budget).toLocaleString("en-IN")} a day` : "No budget set"}{p.platform ? ` · ${p.platform === "meta" ? "Facebook & Instagram" : p.platform === "google" ? "Google" : p.platform === "linkedin" ? "LinkedIn" : p.platform}` : ""}</p>
          </div>
        </div>
      )}
      {a.kind === "site" && p.preview_url && (
        <a href={p.preview_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline">
          Open the page <ExternalLink className="size-3.5" />
        </a>
      )}
      {asking ? (
        <form className="mt-2 space-y-2" onSubmit={(e) => { e.preventDefault(); decide("changes"); }}>
          <textarea className="input text-sm" rows={3} maxLength={2000} autoFocus value={comment} onChange={(e) => setComment(e.target.value)}
            placeholder="What should change? For example: use our clinic photo, and the price is ₹2,999." aria-label="What should change" />
          <div className="flex gap-1.5">
            <button type="submit" className="btn-primary btn-sm" disabled={!comment.trim() || !!busy}>{busy === "changes" && <Spinner />}Send to agency</button>
            <button type="button" className="btn-subtle btn-sm" onClick={() => { setAsking(false); setComment(""); }}>Cancel</button>
          </div>
        </form>
      ) : (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button type="button" className="btn-primary btn-sm" disabled={!!busy} onClick={() => decide("approved")}>{busy === "approved" ? <Spinner /> : <Check className="size-3.5" />}Approve</button>
          <button type="button" className="btn-ghost btn-sm" disabled={!!busy} onClick={() => setAsking(true)}><MessageSquare className="size-3.5" />Ask for changes</button>
        </div>
      )}
    </li>
  );
}
