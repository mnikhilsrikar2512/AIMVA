"""Tell the owner the moment a new lead arrives, so the fast reply that wins the sale doesn't wait for them to
happen to open AIMVA. Email today (with a one-tap WhatsApp reply link); phone push once the app is installed.

At most ALERTS_PER_HOUR emails an hour per account: a burst of leads from one ad shouldn't flood an inbox, and the
rest are still waiting at the top of Leads.
"""
import logging
import re
from html import escape
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .agents import setting
from .config import settings
from .mailer import send_email
from .models import Lead, User
from .security import rate_limit

log = logging.getLogger("aimva.alerts")
ALERTS_PER_HOUR = 10
SOURCE = {"website": "your page", "meta": "your Meta ad", "google": "your Google ad", "linkedin": "your LinkedIn ad",
          "whatsapp": "WhatsApp", "voice": "a call", "manual": "a manual entry"}


def wa_link(phone: str, text: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:  # Indian mobile typed without the country code
        digits = "91" + digits
    return f"https://wa.me/{digits}?text={quote(text)}" if len(digits) >= 11 else ""


def on_new_lead(db: Session, lead_id: int) -> bool:
    """Email the owner about one new lead. True when an email went out."""
    lead = db.get(Lead, lead_id)
    if not lead or lead.source == "manual":  # they typed it in themselves
        return False
    owner = db.get(User, lead.user_id)
    s = setting(db, lead.user_id, "lead_alerts")
    db.commit()
    if not owner or not s.enabled or not (s.config or {}).get("email", True):
        return False
    try:
        rate_limit(f"lead-alert:{owner.id}", ALERTS_PER_HOUR, 3600)
    except HTTPException:
        return False
    who = lead.name or lead.phone or lead.email or "Someone"
    first = (lead.name or "").split(" ")[0] or "there"
    business = owner.company or owner.name or "us"
    open_url = f"{settings.frontend_url}/app/leads?lead={lead.id}&reply=1"
    wa = wa_link(lead.phone, f"Hi {first}, thanks for contacting {business}! ")
    src = SOURCE.get(lead.source, lead.source)
    lines = [f"{who} just asked through {src}.", ""]
    if lead.message:
        lines += [f"“{lead.message[:400]}”", ""]
    lines += [x for x in (f"Phone: {lead.phone}" if lead.phone else "", f"Email: {lead.email}" if lead.email else "") if x]
    lines += ["", f"Reply on WhatsApp: {wa}" if wa else "", f"Open in AIMVA: {open_url}", "",
              "Leads answered in the first 5 minutes are far more likely to buy.",
              "Turn these emails off in AIMVA under Settings, Lead alerts."]
    btn = "display:inline-block;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:600;margin-right:8px"
    html = (f"<p style='font-size:16px'><b>{escape(who)}</b> just asked through {escape(src)}.</p>"
            + (f"<blockquote style='margin:0 0 12px;padding:8px 12px;border-left:3px solid #a34d22;color:#333'>{escape(lead.message[:400])}</blockquote>" if lead.message else "")
            + (f"<p style='color:#555'>{escape(lead.phone)}{' · ' + escape(lead.email) if lead.email else ''}</p>" if lead.phone else
               f"<p style='color:#555'>{escape(lead.email)}</p>" if lead.email else "")
            + (f"<a href='{escape(wa)}' style='{btn};background:#1f7a4d;color:#fff'>Reply on WhatsApp</a>" if wa else "")
            + f"<a href='{escape(open_url)}' style='{btn};background:#1c1917;color:#fff'>Open in AIMVA</a>"
            + "<p style='color:#777;font-size:12px;margin-top:16px'>Leads answered in the first 5 minutes are far more likely to buy. "
              "Turn these emails off in AIMVA under Settings, Lead alerts.</p>")
    sent = send_email(owner.email, f"New lead: {who}" + (f" ({src})" if src else ""), "\n".join(l for l in lines if l is not None), html)
    log.info("Lead alert for lead %s: %s", lead.id, "sent" if sent else "not sent (no mail server)")
    return sent
