import csv
import io
import logging
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .. import call_hours, lead_reply, live, opt_out
from ..db import SessionLocal, get_db
from ..models import Lead, LeadEvent, User, WaMessage, utcnow
from ..security import current_user
from ..services import get_integration, score_lead
from .integrations import oauth_access_token

router = APIRouter(prefix="/api/leads", tags=["leads"])
COLUMNS = ["id", "created_at", "name", "email", "phone", "source", "stage", "score", "value", "message"]


def lead_out(l: Lead) -> dict:
    return {"id": l.id, "name": l.name, "email": l.email, "phone": l.phone, "message": l.message,
            "source": l.source, "source_ref": l.source_ref, "score": l.score, "stage": l.stage,
            "value": l.value, "synced": l.synced or {}, "language": l.language or "",
            "language_name": lead_reply.LANGUAGES.get(l.language or "", ""), "created_at": l.created_at.isoformat(),
            "opted_out": l.opted_out_at is not None,
            "opted_out_at": l.opted_out_at.isoformat() if l.opted_out_at else None}


def _cell(v) -> str:
    """Stop spreadsheet apps from executing lead-supplied text as a formula."""
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _row(l: Lead) -> list:
    d = lead_out(l)
    return [_cell(d[c]) for c in COLUMNS]


SOURCE_LABEL = {"website": "landing page", "meta": "Meta ads", "google": "Google ads", "linkedin": "LinkedIn ads",
                "whatsapp": "WhatsApp", "voice": "voice call", "manual": "manual entry"}
AD_SOURCES = ("meta", "google", "linkedin")


def add_event(db: Session, lead: Lead, kind: str, title: str, body: str = "", **meta) -> LeadEvent:
    ev = LeadEvent(user_id=lead.user_id, lead_id=lead.id, kind=kind, title=title[:200], body=body or "", meta=meta)
    db.add(ev)
    return ev


def create_lead(db: Session, user_id: int, bg: Optional[BackgroundTasks] = None, event: Optional[dict] = None,
                **fields) -> Lead:
    """Create (or merge into an existing duplicate by email/phone) and score a lead.

    `event` optionally overrides the timeline entry, e.g. {"title": "Lead form · Diwali campaign"}.
    """
    email = (fields.get("email") or "").strip().lower()
    phone = (fields.get("phone") or "").strip()
    conds = [c for c in [Lead.email == email if email else None, Lead.phone == phone if phone else None] if c is not None]
    lead = db.scalar(select(Lead).where(Lead.user_id == user_id, or_(*conds))) if conds else None
    if lead:  # dedupe: enrich the existing record instead of inserting a copy
        for k in ("name", "email", "phone", "product_id", "campaign_id"):
            if not getattr(lead, k) and fields.get(k):
                setattr(lead, k, fields[k])
        if fields.get("message"):
            lead.message = (lead.message + "\n" + fields["message"]).strip()
    else:
        lead = Lead(user_id=user_id, **{k: v for k, v in fields.items() if v is not None})
        lead.email = email
        db.add(lead)
    lead_reply.remember_language(lead, " ".join(filter(None, [fields.get("message"), fields.get("name")])))
    opt_out.mark_new_lead(db, lead)
    is_new = lead.id is None
    lead.score = score_lead(lead)
    db.flush()
    source = fields.get("source", "manual")
    if is_new:
        add_event(db, lead, "created", f"Lead created from {SOURCE_LABEL.get(source, source)}", source=source)
    # Form fills and ad lead forms only live here; WhatsApp messages and calls come from their own tables.
    if source == "website" or source in AD_SOURCES:
        kind = "form" if source == "website" else "ad"
        title = (event or {}).get("title") or ("Submitted a landing page form" if kind == "form" else f"Lead form on {SOURCE_LABEL[source]}")
        add_event(db, lead, kind, title, fields.get("message") or "", source=source, ref=fields.get("source_ref", ""))
    elif source == "manual" and fields.get("message") and not is_new:
        add_event(db, lead, "note", "Note added", fields["message"])
    db.commit()
    live.publish(user_id, "lead", {"type": "created" if is_new else "activity", "source": source,
                                   "lead": lead_out(lead), "unseen": unseen_count(db, user_id)})
    if bg:
        bg.add_task(auto_sync, user_id, lead.id)
        if is_new:
            bg.add_task(_concierge, lead.id)
    return lead


def _concierge(lead_id: int) -> None:
    """New lead → the Lead Concierge agent welcomes them and schedules follow-ups (see app/agents/concierge.py)."""
    from ..agents.concierge import on_new_lead
    db = SessionLocal()
    try:
        on_new_lead(db, lead_id)
    except Exception:
        logging.getLogger("aimva.agents").exception("Lead concierge failed for lead %s", lead_id)
    finally:
        db.close()


def unseen_count(db: Session, user_id: int) -> int:
    user = db.get(User, user_id)
    q = select(func.count()).select_from(Lead).where(Lead.user_id == user_id)
    if user and user.leads_seen_at:
        q = q.where(Lead.created_at > user.leads_seen_at)
    return db.scalar(q) or 0


def _sync_google(db: Session, user_id: int, leads: list) -> str:
    integ = get_integration(db, user_id, "google")
    sheet_id = (integ.meta or {}).get("sheet_id") if integ else None
    if not sheet_id:
        raise HTTPException(400, "Connect Google and set a Sheet ID in Lead Sync settings.")
    token = oauth_access_token(db, user_id, "google")
    r = httpx.post(f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/A1:append",
                   params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
                   headers={"Authorization": f"Bearer {token}"}, json={"values": [_row(l) for l in leads]}, timeout=30)
    if r.status_code >= 400:
        raise HTTPException(502, f"Google Sheets error: {r.text[:200]}")
    return "google_sheets"


def _sync_onedrive(db: Session, user_id: int) -> str:
    token = oauth_access_token(db, user_id, "microsoft")
    if not token:
        raise HTTPException(400, "Connect Microsoft (OneDrive) first.")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    for l in db.scalars(select(Lead).where(Lead.user_id == user_id).order_by(Lead.id)):
        w.writerow(_row(l))
    r = httpx.put("https://graph.microsoft.com/v1.0/me/drive/root:/AIMVA/leads.csv:/content",
                  headers={"Authorization": f"Bearer {token}", "Content-Type": "text/csv"},
                  content=buf.getvalue().encode(), timeout=30)
    if r.status_code >= 400:
        raise HTTPException(502, f"OneDrive error: {r.text[:200]}")
    return "onedrive"


def auto_sync(user_id: int, lead_id: int) -> None:
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        for provider, fn in (("google", lambda: _sync_google(db, user_id, [lead])),
                             ("microsoft", lambda: _sync_onedrive(db, user_id))):
            integ = get_integration(db, user_id, provider)
            if integ and (integ.meta or {}).get("auto_sync"):
                try:
                    target = fn()
                    lead.synced = {**(lead.synced or {}), target: True}
                    db.commit()
                except Exception:
                    pass
    finally:
        db.close()


class LeadIn(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    message: str = ""
    source: str = "manual"
    value: float = 0


class LeadPatch(BaseModel):
    stage: Optional[Literal["new", "contacted", "qualified", "won", "lost"]] = None
    value: Optional[float] = None
    name: Optional[str] = None
    language: Optional[str] = Field(None, max_length=12)


def with_activity(db: Session, user_id: int, leads: list) -> list:
    act = lead_reply.activity(db, user_id, leads)
    out = []
    for l in leads:
        row = {**lead_out(l), **act[l.id]}
        if not row["language"]:  # leads saved before languages were remembered: read it from their message
            guess = lead_reply.detect(l.message)
            if guess:
                row["language"], row["language_name"] = guess, lead_reply.LANGUAGES[guess]
        out.append(row)
    return out


@router.get("")
def list_leads(q: str = "", source: str = "", stage: str = "", sort: Literal["needs", "newest"] = "needs",
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Everyone who asked. sort=needs (default) puts leads waiting on you first; each row says who is waiting and since when."""
    stmt = select(Lead).where(Lead.user_id == user.id).order_by(Lead.created_at.desc()).limit(500)
    if source:
        stmt = stmt.where(Lead.source == source)
    if stage:
        stmt = stmt.where(Lead.stage == stage)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Lead.name.ilike(like), Lead.email.ilike(like), Lead.phone.ilike(like)))
    leads = list(db.scalars(stmt))
    if sort == "needs":
        leads = lead_reply.needs_first(leads, lead_reply.activity(db, user.id, leads))
    return with_activity(db, user.id, leads)


@router.post("")
def add_lead(body: LeadIn, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not (body.email or body.phone):
        raise HTTPException(400, "A lead needs an email or phone number.")
    return lead_out(create_lead(db, user.id, bg, **body.model_dump()))


@router.patch("/{lead_id}")
def patch_lead(lead_id: int, body: LeadPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if not lead or lead.user_id != user.id:
        raise HTTPException(404, "Not found.")
    changes = body.model_dump(exclude_none=True)
    if "language" in changes and changes["language"] not in lead_reply.LANGUAGES and changes["language"] != "":
        raise HTTPException(400, "Pick one of the listed languages.")
    if "stage" in changes and changes["stage"] != lead.stage:
        add_event(db, lead, "stage", f"Stage: {lead.stage} → {changes['stage']}", previous=lead.stage, stage=changes["stage"])
    if "value" in changes and changes["value"] != lead.value:
        add_event(db, lead, "value", f"Deal value set to {changes['value']:,.0f}", value=changes["value"])
    for k, v in changes.items():
        setattr(lead, k, v)
    db.commit()
    return with_activity(db, user.id, [lead])[0]


@router.delete("/{lead_id}")
def delete_lead(lead_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Deletes the lead with its history: timeline, follow-ups, and the WhatsApp messages and calls with that
    number, so a person who asks to be erased is erased (DPDP). Conversations stay when another lead in this
    account has the same number."""
    from ..models import Call, WaScheduled
    lead = db.get(Lead, lead_id)
    if lead and lead.user_id == user.id:
        contacts = lead_reply._contacts(lead.phone) if lead.phone else set()
        shared = contacts and any(lead_reply._contacts(p) & contacts for p in db.scalars(
            select(Lead.phone).where(Lead.user_id == user.id, Lead.id != lead.id, Lead.phone != "")))
        db.execute(delete(Call).where(Call.user_id == user.id, Call.lead_id == lead.id))
        if contacts and not shared:
            db.execute(delete(WaMessage).where(WaMessage.user_id == user.id, WaMessage.contact.in_(contacts)))
            db.execute(delete(WaScheduled).where(WaScheduled.user_id == user.id, WaScheduled.contact.in_(contacts)))
            digits = "".join(ch for ch in lead.phone if ch.isdigit())
            if len(digits) >= 10:
                db.execute(delete(Call).where(Call.user_id == user.id, Call.to_number.contains(digits[-10:])))
        db.delete(lead)
        db.commit()
    return {"ok": True}


@router.get("/unseen")
def get_unseen(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"unseen": unseen_count(db, user.id)}


@router.post("/seen")
def mark_seen(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.leads_seen_at = utcnow()
    db.commit()
    live.publish(user.id, "seen", {"unseen": 0})  # clear the badge in the user's other tabs
    return {"unseen": 0}


@router.get("/export.csv")
def export_csv(user: User = Depends(current_user), db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    for l in db.scalars(select(Lead).where(Lead.user_id == user.id).order_by(Lead.id)):
        w.writerow(_row(l))
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=aimva-leads.csv"})


@router.post("/sync/{target}")
def sync_now(target: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if target == "google":
        leads = list(db.scalars(select(Lead).where(Lead.user_id == user.id).order_by(Lead.id)))
        if not leads:
            return {"ok": True, "count": 0}
        _sync_google(db, user.id, leads)
        key = "google_sheets"
    elif target == "onedrive":
        _sync_onedrive(db, user.id)
        key, leads = "onedrive", list(db.scalars(select(Lead).where(Lead.user_id == user.id)))
    else:
        raise HTTPException(404, "Unknown sync target.")
    for l in leads:
        l.synced = {**(l.synced or {}), key: True}
    db.commit()
    return {"ok": True, "count": len(leads)}


# ---- single lead view ---------------------------------------------------------
def _digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _own(db: Session, user: User, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead or lead.user_id != user.id:
        raise HTTPException(404, "Lead not found.")
    return lead


def timeline(db: Session, lead: Lead) -> list:
    from ..models import Call, WaMessage
    items = [{"id": f"e{e.id}", "kind": e.kind, "at": e.created_at.isoformat(), "title": e.title, "body": e.body,
              "meta": e.meta or {}} for e in db.scalars(select(LeadEvent).where(LeadEvent.lead_id == lead.id))]
    phone = _digits(lead.phone)
    if phone:
        for m in db.scalars(select(WaMessage).where(WaMessage.user_id == lead.user_id,
                                                    WaMessage.contact.in_(lead_reply._contacts(lead.phone)))):
            items.append({"id": f"w{m.id}", "kind": "whatsapp", "at": m.created_at.isoformat(),
                          "title": "WhatsApp received" if m.direction == "in" else
                          "Sent from your WhatsApp" if m.status == "own_app" else "WhatsApp sent", "body": m.body,
                          "meta": {"direction": m.direction, "status": m.status}})
    conds = [Call.lead_id == lead.id] + ([Call.to_number.contains(phone[-10:])] if len(phone) >= 10 else [])
    for c in db.scalars(select(Call).where(Call.user_id == lead.user_id, or_(*conds))):
        answers = "\n".join(f"{q} {a}" for q, a in (c.answers or {}).items())
        items.append({"id": f"c{c.id}", "kind": "call", "at": c.created_at.isoformat(),
                      "title": f"{'Phone' if c.channel == 'phone' else 'Voice agent'} call · "
                               + (f"set for {call_hours.label(c.to_number, call_hours.next_open(c.to_number, c.created_at))}" if c.status == "scheduled" else c.status),
                      "body": answers, "meta": {"call_id": c.id, "status": c.status, "sentiment": c.sentiment,
                                                "turns": len(c.transcript or []), "transcript": c.transcript or []}})
    return sorted(items, key=lambda i: i["at"], reverse=True)


def lead_view(db: Session, lead: Lead) -> dict:
    return {**with_activity(db, lead.user_id, [lead])[0], "timeline": timeline(db, lead)}


@router.get("/{lead_id}")
def get_lead(lead_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return lead_view(db, _own(db, user, lead_id))


@router.get("/meta/languages")
def languages(user: User = Depends(current_user)):
    return [{"code": k, "name": v} for k, v in lead_reply.LANGUAGES.items()]


class DraftIn(BaseModel):
    intent: Literal["auto", "welcome", "reply", "follow_up", "visit", "pricing"] = "auto"


@router.post("/{lead_id}/reply-draft")
def reply_draft(lead_id: int, body: DraftIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A WhatsApp reply in the lead's language, and whether WhatsApp will take free text or only a template now."""
    lead = _own(db, user, lead_id)
    if not lead.phone:
        raise HTTPException(400, "Add a phone number to message this lead.")
    opt_out.guard(db, user.id, lead.phone)
    return lead_reply.draft(db, user, lead, body.intent)


class ReplyIn(BaseModel):
    text: str = Field("", max_length=4096)
    template: bool = False  # send the approved template (outside WhatsApp's 24-hour window)
    own_app: bool = False  # the business sent `text` from their own WhatsApp (wa.me link): just record it
    intent: Literal["auto", "welcome", "reply", "follow_up", "visit", "pricing"] = "auto"


@router.post("/{lead_id}/reply")
def reply(lead_id: int, body: ReplyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Send a WhatsApp reply to a lead. A new lead moves to "contacted" so it leaves the waiting list."""
    from .whatsapp import CLOSED_WINDOW, send_whatsapp
    lead = _own(db, user, lead_id)
    if not lead.phone:
        raise HTTPException(400, "Add a phone number to message this lead.")
    opt_out.guard(db, user.id, lead.phone)  # also for "sent from my WhatsApp": the business shouldn't message them either
    language = lead_reply.language_of(db, lead)
    state = lead_reply.send_state(db, user, lead, language, body.intent)
    if body.own_app:
        # Sent by a person from their own WhatsApp, so the API's 24-hour rule doesn't apply. We can't see the
        # message leave their phone, so it's recorded as "sent from your WhatsApp", not as delivered.
        if not body.text.strip():
            raise HTTPException(400, "Write a message first.")
        db.add(WaMessage(user_id=user.id, contact=lead_reply.wa_number(lead.phone), contact_name=lead.name,
                         direction="out", body=body.text.strip(), status="own_app"))
    elif body.template:
        if not state["needs_template"]:
            raise HTTPException(400, "You can write to this lead freely right now; send a message instead.")
        integ = get_integration(db, user.id, "whatsapp")
        tpl = lead_reply.template_for(integ, "follow_up" if body.intent == "follow_up" else "first", language)
        if not tpl:
            raise HTTPException(400, "Add your approved WhatsApp template in WhatsApp settings first.")
        send_whatsapp(db, user.id, lead.phone, "", lead.name, tpl["name"], tpl["lang"],
                      [lead_reply.first_name(lead)] if tpl["with_name"] else None)
    else:
        if not body.text.strip():
            raise HTTPException(400, "Write a message first.")
        if state["needs_template"]:
            raise HTTPException(409, CLOSED_WINDOW)
        send_whatsapp(db, user.id, lead.phone, body.text.strip(), lead.name)
    if lead.stage == "new":
        add_event(db, lead, "stage", "Stage: new → contacted", previous="new", stage="contacted")
        lead.stage = "contacted"
    db.commit()
    live.publish(user.id, "lead", {"type": "activity", "source": "whatsapp", "lead": lead_out(lead),
                                   "unseen": unseen_count(db, user.id)})
    return lead_view(db, lead)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@router.post("/{lead_id}/notes")
def add_note(lead_id: int, body: NoteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    lead = _own(db, user, lead_id)
    add_event(db, lead, "note", "Note added", body.body.strip())
    db.commit()
    return lead_view(db, lead)


class CallLeadIn(BaseModel):
    agent_id: Optional[int] = None


@router.post("/{lead_id}/call")
def call_lead(lead_id: int, body: CallLeadIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Have the AI voice agent phone this lead (needs Twilio)."""
    from ..models import VoiceAgent
    from .voice import place_phone_call
    lead = _own(db, user, lead_id)
    if not lead.phone:
        raise HTTPException(400, "This lead has no phone number.")
    agent = db.get(VoiceAgent, body.agent_id) if body.agent_id else \
        db.scalar(select(VoiceAgent).where(VoiceAgent.user_id == user.id).order_by(VoiceAgent.id))
    if not agent or agent.user_id != user.id:
        raise HTTPException(400, "Create a voice agent first.")
    from .voice import scheduled_for
    c = place_phone_call(db, user, agent, lead.phone, lead_id=lead.id)
    when = scheduled_for(c)
    return {**lead_view(db, lead), "call_scheduled_for": when.isoformat() if when else None,
            "call_note": f"Outside calling hours ({call_hours.window_text()}). AI call set for "
                         f"{call_hours.label(c.to_number, when)}." if when else ""}


class OptOutIn(BaseModel):
    note: str = Field("", max_length=300)


@router.post("/{lead_id}/opt-out")
def mark_opted_out(lead_id: int, body: OptOutIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The customer asked the business not to contact them (on a call, in person...): stop all messages and calls."""
    lead = _own(db, user, lead_id)
    if not lead.phone:
        raise HTTPException(400, "This lead has no phone number.")
    opt_out.opt_out(db, user.id, lead.phone, "manual", body.note.strip())
    db.refresh(lead)
    return lead_view(db, lead)


@router.delete("/{lead_id}/opt-out")
def resume(lead_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Allow messages and calls again. Only when the customer asked for it (they can also reply START themselves)."""
    lead = _own(db, user, lead_id)
    if not opt_out.opt_in(db, user.id, lead.phone, "manual"):
        lead.opted_out_at = None  # nothing recorded for the number (e.g. its phone was edited): just clear the flag
        db.commit()
    db.refresh(lead)
    return lead_view(db, lead)
