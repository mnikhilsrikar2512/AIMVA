"""WhatsApp Business (Cloud API).

Without a connected number, messages are stored as "simulated" so the inbox can be tried end to end.
Webhook: GET/POST /api/public/whatsapp/webhook (set it in the Meta app dashboard).
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Integration, User, WaMessage, WaScheduled, utcnow
from ..security import current_user, decrypt_json
from ..services import get_integration
from ..webhooks import check_meta_signature
from .leads import create_lead

router = APIRouter(tags=["whatsapp"])
GRAPH = "https://graph.facebook.com/v21.0"


def msg_out(m: WaMessage) -> dict:
    return {"id": m.id, "contact": m.contact, "contact_name": m.contact_name, "direction": m.direction,
            "body": m.body, "status": m.status, "created_at": m.created_at.isoformat()}


@router.get("/api/whatsapp/conversations")
def conversations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    last = (select(WaMessage.contact, func.max(WaMessage.id).label("mid"))
            .where(WaMessage.user_id == user.id).group_by(WaMessage.contact).subquery())
    rows = list(db.scalars(select(WaMessage).join(last, WaMessage.id == last.c.mid).order_by(WaMessage.id.desc())))
    # The newest message may be ours (no name), so use the contact's most recent known name.
    names = dict(db.execute(select(WaMessage.contact, WaMessage.contact_name)
                            .where(WaMessage.user_id == user.id, WaMessage.contact_name != "").order_by(WaMessage.id)).all())
    return [{**msg_out(m), "contact_name": m.contact_name or names.get(m.contact, "")} for m in rows]


@router.get("/api/whatsapp/messages/{contact}")
def messages(contact: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(WaMessage).where(WaMessage.user_id == user.id, WaMessage.contact == contact).order_by(WaMessage.id)
    return [msg_out(m) for m in db.scalars(q)]


class SendIn(BaseModel):
    to: str = Field(min_length=6, max_length=20)
    body: str = Field(min_length=1, max_length=4096)
    name: str = ""


def send_whatsapp(db: Session, user_id: int, to: str, text: str, name: str = "", template: str = "",
                  template_lang: str = "en") -> WaMessage:
    """Send (or, without a connected number, simulate) a WhatsApp text, or an approved template when `template` is set.
    Raises HTTPException(502) if WhatsApp refuses it."""
    to = "".join(ch for ch in to if ch.isdigit())
    integ = get_integration(db, user_id, "whatsapp")
    m = WaMessage(user_id=user_id, contact=to, contact_name=name, direction="out", body=text or f"[template: {template}]")
    if integ:
        token = decrypt_json(integ.secret).get("access_token")
        payload = ({"type": "template", "template": {"name": template, "language": {"code": template_lang}}} if template
                   else {"type": "text", "text": {"body": text}})
        r = httpx.post(f"{GRAPH}/{integ.meta.get('phone_number_id')}/messages",
                       headers={"Authorization": f"Bearer {token}"}, timeout=30,
                       json={"messaging_product": "whatsapp", "to": to, **payload})
        if r.status_code >= 400:
            m.status = "failed"
            db.add(m)
            db.commit()
            raise HTTPException(502, f"WhatsApp error: {r.text[:300]}")
        m.wa_id = (r.json().get("messages") or [{}])[0].get("id", "")
    else:
        m.status = "simulated"
    db.add(m)
    db.commit()
    return m


@router.post("/api/whatsapp/send")
def send(body: SendIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return msg_out(send_whatsapp(db, user.id, body.to, body.body, body.name))


# ---- Scheduled messages -------------------------------------------------------------------------------
WINDOW = timedelta(hours=24)  # WhatsApp only allows free-form messages within 24 h of the customer's last message
MAX_AHEAD = timedelta(days=90)
STUCK = timedelta(minutes=10)


class ScheduleIn(BaseModel):
    to: str = Field(min_length=6, max_length=20)
    body: str = Field("", max_length=4096)
    name: str = Field("", max_length=160)
    send_at: datetime  # with a time zone, or without one = the business time zone (TZ_OFFSET_MINUTES)
    template: str = Field("", max_length=120, pattern=r"^[a-z0-9_]*$")
    template_lang: str = Field("en", max_length=12)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt - timedelta(minutes=settings.tz_offset_minutes)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _last_inbound(db: Session, user_id: int, contact: str) -> Optional[datetime]:
    return db.scalar(select(func.max(WaMessage.created_at)).where(
        WaMessage.user_id == user_id, WaMessage.contact == contact, WaMessage.direction == "in"))


def scheduled_out(s: WaScheduled, db: Optional[Session] = None) -> dict:
    out = {"id": s.id, "to": s.contact, "name": s.contact_name, "body": s.body, "template": s.template,
           "template_lang": s.template_lang, "send_at": s.send_at.isoformat() + "Z", "status": s.status, "error": s.error,
           "sent_at": s.sent_at.isoformat() + "Z" if s.sent_at else None, "created_at": s.created_at.isoformat() + "Z"}
    if db is not None and s.status == "scheduled" and not s.template:
        last = _last_inbound(db, s.user_id, s.contact)
        if not last or last + WINDOW < s.send_at:
            out["warning"] = ("This customer won't have messaged you in the last 24 hours when it sends, so WhatsApp "
                              "will only deliver an approved template. Pick a template, or it will fail.")
    return out


@router.post("/api/whatsapp/scheduled")
def schedule(body: ScheduleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.body.strip() and not body.template:
        raise HTTPException(400, "Write a message or pick an approved template.")
    send_at = _to_utc(body.send_at)
    now = utcnow()
    if send_at < now + timedelta(minutes=1):
        raise HTTPException(400, "Pick a time at least a minute from now.")
    if send_at > now + MAX_AHEAD:
        raise HTTPException(400, "You can schedule up to 90 days ahead.")
    contact = "".join(ch for ch in body.to if ch.isdigit())
    if db.scalar(select(func.count()).select_from(WaScheduled).where(WaScheduled.user_id == user.id,
                                                                      WaScheduled.status == "scheduled")) >= 500:
        raise HTTPException(400, "You have 500 messages waiting already. Cancel some first.")
    s = WaScheduled(user_id=user.id, contact=contact, contact_name=body.name, body=body.body.strip(), template=body.template,
                    template_lang=body.template_lang, send_at=send_at)
    db.add(s)
    db.commit()
    return scheduled_out(s, db)


@router.get("/api/whatsapp/scheduled")
def list_scheduled(status: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(WaScheduled).where(WaScheduled.user_id == user.id)
    if status:
        q = q.where(WaScheduled.status == status)
    return [scheduled_out(s, db) for s in db.scalars(q.order_by(WaScheduled.send_at.desc()).limit(500))]


@router.delete("/api/whatsapp/scheduled/{sid}")
def cancel_scheduled(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.execute(update(WaScheduled).where(WaScheduled.id == sid, WaScheduled.user_id == user.id,
                                             WaScheduled.status == "scheduled").values(status="cancelled"))
    db.commit()
    s = db.get(WaScheduled, sid)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Scheduled message not found.")
    if not r.rowcount:
        raise HTTPException(409, f"This message is already {s.status}.")
    return scheduled_out(s)


def send_due(db: Session, now: Optional[datetime] = None) -> int:
    """Send scheduled messages that are due. Each row is claimed with a conditional update first, so it goes out once."""
    now = now or utcnow()
    db.execute(update(WaScheduled).where(WaScheduled.status == "sending", WaScheduled.send_at < now - STUCK)
               .values(status="failed", error="Sending was interrupted; check the chat before sending it again."))
    db.commit()
    sent = 0
    for s in list(db.scalars(select(WaScheduled).where(WaScheduled.status == "scheduled", WaScheduled.send_at <= now)
                             .order_by(WaScheduled.send_at).limit(100))):
        claimed = db.execute(update(WaScheduled).where(WaScheduled.id == s.id, WaScheduled.status == "scheduled")
                             .values(status="sending")).rowcount
        db.commit()
        if not claimed:
            continue
        db.refresh(s)
        connected = get_integration(db, s.user_id, "whatsapp") is not None
        last = _last_inbound(db, s.user_id, s.contact)
        if connected and not s.template and (not last or last + WINDOW < now):
            s.status, s.error = "failed", ("Not sent: the customer hasn't messaged you in the last 24 hours, so WhatsApp "
                                           "only allows an approved template.")
            db.commit()
            continue
        try:
            m = send_whatsapp(db, s.user_id, s.contact, s.body, s.contact_name, s.template, s.template_lang)
            s.status, s.sent_at, s.message_id = "sent", utcnow(), m.id
            sent += 1
        except HTTPException as e:
            s.status, s.error = "failed", str(e.detail)
        except Exception as e:  # network trouble: don't retry blindly, the message may have gone out
            s.status, s.error = "failed", f"Couldn't reach WhatsApp: {type(e).__name__}"
        db.commit()
    return sent


class SimIn(BaseModel):
    from_: str = Field(alias="from", min_length=6)
    body: str
    name: str = ""


@router.post("/api/whatsapp/simulate-inbound")
def simulate_inbound(body: SimIn, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Test the inbox without a real number: pretend a customer messaged you."""
    contact = "".join(ch for ch in body.from_ if ch.isdigit())
    m = WaMessage(user_id=user.id, contact=contact, contact_name=body.name, direction="in", body=body.body, status="received")
    db.add(m)
    db.commit()
    create_lead(db, user.id, bg, name=body.name, phone="+" + contact, message=body.body, source="whatsapp")
    return msg_out(m)


@router.get("/api/public/whatsapp/webhook")
def verify_webhook(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == settings.whatsapp_verify_token:
        return PlainTextResponse(p.get("hub.challenge", ""))
    raise HTTPException(403, "Verification failed.")


@router.post("/api/public/whatsapp/webhook")
async def receive_webhook(request: Request, bg: BackgroundTasks, db: Session = Depends(get_db)):
    raw = await request.body()
    check_meta_signature(raw, request.headers.get("x-hub-signature-256", ""))
    try:
        data = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Invalid JSON.")
    if not isinstance(data, dict):
        raise HTTPException(400, "Invalid JSON.")
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            v = change.get("value", {})
            pnid = (v.get("metadata") or {}).get("phone_number_id")
            integ = next((i for i in db.scalars(select(Integration).where(Integration.provider == "whatsapp"))
                          if (i.meta or {}).get("phone_number_id") == pnid), None)
            if not integ:
                continue
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in v.get("contacts", [])}
            for msg in v.get("messages", []):
                text = (msg.get("text") or {}).get("body") or f"[{msg.get('type')}]"
                db.add(WaMessage(user_id=integ.user_id, contact=msg["from"], contact_name=names.get(msg["from"], ""),
                                 direction="in", body=text, status="received", wa_id=msg.get("id", "")))
                db.commit()
                create_lead(db, integ.user_id, bg, name=names.get(msg["from"], ""), phone="+" + msg["from"],
                            message=text, source="whatsapp")
            for st in v.get("statuses", []):
                m = db.scalar(select(WaMessage).where(WaMessage.wa_id == st.get("id")))
                if m:
                    m.status = st.get("status", m.status)
                    db.commit()
    return {"ok": True}
