"""Lead Concierge: no lead waits. A WhatsApp welcome within seconds, then day-2 and day-7 follow-ups that stop
as soon as the lead replies, books or is closed. Without a connected WhatsApp number nothing is faked: the
message is drafted on the lead so the business can send it with one tap."""
from datetime import timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import record, setting
from .. import opt_out
from ..models import FollowUp, Lead, User, WaMessage, utcnow
from ..quality import match_playbook
from ..services import get_integration

ACT_ON = {"website", "meta", "google", "linkedin", "manual"}  # leads who filled a form; WhatsApp/voice leads are already talking
CLOSED = {"qualified", "won", "lost"}
DEFAULTS = {
    "welcome": "Hi {name}, thanks for your enquiry with {business}! {next} Reply here any time with questions.",
    "day2": "Hi {name}, just following up on your enquiry with {business}. Do you have any questions I can help with?",
    "day7": "Hi {name}, we're still happy to help with {business}. Should we keep you posted, or is now not the right time? Reply STOP and we won't message again.",
}
NEXT = {  # the welcome's suggested next step, by industry
    "real_estate": "Would you like to visit the site? Reply with a day and time that suits you (e.g. Sat 11am).",
    "healthcare": "Would you like us to book you an appointment? Reply with a day that suits you.",
    "education": "Would you like to book a free demo class? Reply with a day that suits you.",
    "restaurant": "Would you like to reserve a table? Reply with the day, time and number of guests.",
}
SCHEDULE = (("day2", timedelta(days=2)), ("day7", timedelta(days=7)))


def message(db: Session, user: User, lead: Lead, step: str) -> str:
    """The step's message in the lead's language. The business's own wording is sent as they wrote it."""
    from .. import lead_reply
    cfg = setting(db, user.id, "concierge").config or {}
    custom = (cfg.get("messages") or {}).get(step)
    if cfg.get("brief") and not custom:
        # The owner told AIMVA how to reply (the WhatsApp module's prompt): write this step with it, in the lead's
        # language. Without an AI writer this falls through to the standard wording below.
        d = lead_reply.draft(db, user, lead, "welcome" if step == "welcome" else "follow_up")
        if d["by"] == "ai":
            return d["text"] + ("\n\nReply STOP and we won't message again." if step == "day7" else "")
    english = _english(db, user, lead, step, custom)
    language = lead_reply.language_of(db, lead)
    if custom or language == "en":
        return english
    translated = lead_reply.translate(db, user, english, language)
    if translated:
        return translated
    text = lead_reply.ready_made(language, "welcome" if step == "welcome" else "follow_up", lead, user.company or "")
    return text + ("\n\nReply STOP and we won't message again." if step == "day7" else "")


def _english(db: Session, user: User, lead: Lead, step: str, custom: Optional[str]) -> str:
    text = custom or DEFAULTS[step]
    first = (lead.name or "").split(" ")[0] or "there"
    nxt = NEXT.get(match_playbook("", user.industry), "When would be a good time for a quick call?")
    if "brochure" in (lead.message or "").lower() or "price sheet" in (lead.message or "").lower():
        nxt = "We're sending you the details now. " + nxt
    return text.replace("{name}", first).replace("{business}", user.company or "us").replace("{next}", nxt).strip()


def _deliver(db: Session, user: User, lead: Lead, step: str) -> tuple:
    """Send on WhatsApp if a number is connected; otherwise draft it on the lead. Returns (what happened, why).

    WhatsApp only takes free text within 24 hours of the lead's last message. A form or ad lead has never messaged,
    so the first message goes out as the business's approved template, or is drafted when they have none yet."""
    from .. import lead_reply
    from ..routers.leads import add_event
    from ..routers.whatsapp import send_whatsapp
    text = message(db, user, lead, step)
    label = {"welcome": "Welcome message", "day2": "Day-2 follow-up", "day7": "Day-7 follow-up"}[step]
    integ = get_integration(db, user.id, "whatsapp")
    if integ:
        tpl = None
        if not lead_reply.window_open(db, user.id, lead.phone):
            tpl = lead_reply.template_for(integ, "first" if step == "welcome" else "follow_up", lead_reply.language_of(db, lead))
            if not tpl:
                add_event(db, lead, "note", f"{label} ready to send",
                          text + "\n\nWhatsApp only lets a business start a chat with an approved template. Add yours in "
                                 "WhatsApp settings and AIMVA will send it within seconds.", agent="concierge", draft=True)
                db.commit()
                return "drafted", "No approved WhatsApp template yet"
        try:
            if tpl:
                send_whatsapp(db, user.id, lead.phone, "", lead.name, tpl["name"], tpl["lang"],
                              [lead_reply.first_name(lead)] if tpl["with_name"] else None)
            else:
                send_whatsapp(db, user.id, lead.phone, text, lead.name)
        except HTTPException as e:
            add_event(db, lead, "note", f"{label} not sent", f"{e.detail}\n\n{text}", agent="concierge")
            db.commit()
            return "failed", str(e.detail)
        return "sent", ""  # the message itself shows on the lead's timeline from the WhatsApp inbox
    add_event(db, lead, "note", f"{label} ready to send", text + "\n\nConnect WhatsApp in Settings and AIMVA will send these for you.",
              agent="concierge", draft=True)
    db.commit()
    return "drafted", "WhatsApp isn't connected"


def on_new_lead(db: Session, lead_id: int) -> None:
    """Called once for each new lead (in the background, after the lead is saved)."""
    lead = db.get(Lead, lead_id)
    if not lead or lead.source not in ACT_ON or not lead.phone or opt_out.is_out(db, lead.user_id, lead.phone):
        return
    user = db.get(User, lead.user_id)
    s = setting(db, user.id, "concierge")
    db.commit()
    if not s.enabled:
        return
    outcome, why = _deliver(db, user, lead, "welcome")
    now = utcnow()
    # The welcome is kept as a finished step so the lead list can say whether it really went out.
    db.add(FollowUp(user_id=user.id, lead_id=lead.id, step="welcome", due_at=now, status=outcome, note=why[:300]))
    for step, delay in SCHEDULE:
        db.add(FollowUp(user_id=user.id, lead_id=lead.id, step=step, due_at=now + delay))
    db.commit()
    who = lead.name or lead.phone
    record(db, user.id, "concierge", {"sent": f"Welcomed {who} on WhatsApp", "drafted": f"Drafted a welcome for {who}",
                                      "failed": f"Couldn't WhatsApp {who}"}[outcome],
           {"lead_id": lead.id, "outcome": outcome, "follow_ups": [s for s, _ in SCHEDULE]})


def _replied(db: Session, lead: Lead) -> bool:
    from ..lead_reply import _contacts
    contacts = _contacts(lead.phone)
    return bool(contacts and db.scalar(select(WaMessage.id).where(WaMessage.user_id == lead.user_id, WaMessage.direction == "in",
                                                                 WaMessage.contact.in_(contacts), WaMessage.created_at > lead.created_at)))


def run_due(db: Session, now=None) -> int:
    """Send follow-ups that are due. Skips leads who replied, were closed, or whose owner turned the concierge off."""
    now = now or utcnow()
    done = 0
    for f in db.scalars(select(FollowUp).where(FollowUp.status == "pending", FollowUp.due_at <= now).limit(200)):
        lead, user = db.get(Lead, f.lead_id), db.get(User, f.user_id)
        if not lead or not user:
            f.status = "skipped"
            continue
        if not setting(db, user.id, "concierge").enabled:
            f.status, f.note = "skipped", "Concierge was turned off"
        elif lead.opted_out_at or opt_out.is_out(db, user.id, lead.phone):
            f.status, f.note = "skipped", "The lead opted out"
        elif lead.stage in CLOSED:
            f.status, f.note = "skipped", f"Lead is {lead.stage}"
        elif _replied(db, lead):
            f.status, f.note = "skipped", "The lead replied"
        else:
            outcome, _ = _deliver(db, user, lead, f.step)
            f.status, f.note = ("sent" if outcome == "sent" else "skipped"), outcome
            record(db, user.id, "concierge", f"{'Followed up with' if outcome == 'sent' else 'Drafted a follow-up for'} {lead.name or lead.phone}"
                   f" ({'day 2' if f.step == 'day2' else 'day 7'})", {"lead_id": lead.id, "outcome": outcome})
            done += 1
        db.commit()
    return done


def pending_for(db: Session, lead_id: int) -> list:
    return [{"step": f.step, "due_at": f.due_at.isoformat(), "status": f.status, "note": f.note}
            for f in db.scalars(select(FollowUp).where(FollowUp.lead_id == lead_id).order_by(FollowUp.due_at))]


def cancel(db: Session, lead_id: int, why: str) -> Optional[int]:
    n = 0
    for f in db.scalars(select(FollowUp).where(FollowUp.lead_id == lead_id, FollowUp.status == "pending")):
        f.status, f.note = "skipped", why
        n += 1
    return n

