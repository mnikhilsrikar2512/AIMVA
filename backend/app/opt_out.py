"""Leads who say STOP never hear from the business again, on any channel, until they say START.

- Detection: an inbound WhatsApp message that is only an opt-out ("STOP", "please stop messaging me", "unsubscribe",
  "बंद करो", "band karo", "நிறுத்து", "ఆపండి"...) opts that number out. A sentence that merely contains the word
  ("stop by on Saturday", "don't stop the offer") does not: every word must be an opt-out word or a filler word.
- Scope: per business (workspace) and per phone number, so duplicate leads, the raw inbox and the dialer all agree.
  One opt-out blocks WhatsApp (sends, templates, scheduled messages, Concierge follow-ups) and phone calls.
- Back in: the lead replies START (or "subscribe", "resume"). The business can also resume a lead by hand, for when
  the customer asked them in person or on a call; that is recorded on the lead's timeline.
"""
import unicodedata
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .lead_reply import _contacts, wa_number
from .models import Call, FollowUp, Lead, OptOut, WaScheduled, utcnow

BLOCKED = ("This person asked not to be contacted (they replied STOP). AIMVA won't message or call them "
           "unless they reply START, or you resume them on the lead after they asked you to.")

# Words that, alone or with fillers, mean "stop contacting me". Lower-case; Indian scripts as written.
STOP_WORDS = {
    "stop", "stopall", "stopp", "unsubscribe", "unsub", "optout", "opt-out",
    # Hindi / Hinglish / Marathi / Gujarati / Punjabi / Bengali / Odia ("band" = closed / stop)
    "band", "bandh", "बंद", "बन्द", "બંધ", "ਬੰਦ", "বন্ধ", "ବନ୍ଦ",
    # Tamil, Telugu, Kannada, Malayalam
    "நிறுத்து", "நிறுத்துங்கள்", "நிறுத்தவும்", "niruthu", "niruthunga",
    "ఆపు", "ఆపండి", "aapu", "aapandi", "apandi",
    "ನಿಲ್ಲಿಸಿ", "ನಿಲ್ಲಿಸು", "nillisi",
    "നിർത്തുക", "നിർത്തൂ", "നിര്‍ത്തുക", "nirthu", "nirthuka",
    # Arabic
    "توقف", "إيقاف", "ايقاف",
}
STOP_PHRASES = {  # multi-word opt-outs whose words are too common to be STOP_WORDS on their own
    "opt out", "do not message", "dont message", "don't message", "do not contact", "dont contact", "don't contact",
    "no more messages", "remove me", "mat bhejo", "message mat bhejo", "msg mat bhejo", "message mat karo", "msg mat karo",
    "मैसेज मत भेजो", "मैसेज मत भेजिए", "मत भेजो", "संदेश मत भेजो", "إلغاء الاشتراك", "الغاء الاشتراك",
}
START_WORDS = {"start", "unstop", "subscribe", "resume", "शुरू", "shuru"}
FILLER = {
    "please", "pls", "plz", "pl", "now", "it", "all", "me", "my", "number", "this", "here", "thanks", "thank", "you",
    "msg", "msgs", "message", "messages", "messaging", "texting", "texts", "sending", "calls", "calling", "whatsapp",
    "promotions", "promotion", "promo", "promos", "offers", "updates", "marketing", "ads",
    "kindly", "sir", "madam", "ji", "bhai", "to", "from", "list", "the", "again", "anymore", "more",
    # Hinglish / Hindi fillers around "band"
    "karo", "kar", "kardo", "karde", "karein", "karen", "kijiye", "karna", "do", "dijiye", "ye", "yeh", "mujhe",
    "mera", "message", "करो", "करें", "करे", "कीजिए", "करिए", "कर", "दो", "दीजिए", "मैसेज", "प्लीज़", "प्लीज", "कृपया",
    "ये", "यह", "मुझे", "अब", "abhi", "ab",
    # other scripts' "please / do it" endings
    "করুন", "করো", "કરો", "ਕਰੋ", "କରନ୍ତୁ", "करा", "pannunga", "cheyyandi", "maadi", "cheyyu",
    "من", "فضلك", "رجاء",
}


def _words(text: str) -> list:
    """Lower-case words with punctuation, symbols and emoji removed. Combining marks of Indian scripts are kept, and
    zero-width joiners (Malayalam chillu, Devanagari half forms) are dropped so both spellings match."""
    out = []
    for ch in unicodedata.normalize("NFC", (text or "").lower().replace("’", "'")):
        cat = unicodedata.category(ch)
        out.append("" if cat == "Cf" else ch if ch in "-'" or cat[0] not in "PSZC" else " ")
    return [w.strip("-'") for w in "".join(out).split() if w.strip("-'")]


def _norm(words: set) -> set:
    return {" ".join(_words(w)) for w in words}


STOP_WORDS, STOP_PHRASES, START_WORDS, FILLER = map(_norm, (STOP_WORDS, STOP_PHRASES, START_WORDS, FILLER))


def _only(words: list, triggers: set) -> bool:
    return bool(words) and len(words) <= 8 and any(w in triggers for w in words) and all(w in triggers or w in FILLER for w in words)


def wants_out(text: str) -> bool:
    words = _words(text)
    if _only(words, STOP_WORDS):
        return True
    joined = " ".join(words)
    for phrase in STOP_PHRASES:
        if phrase in joined:
            rest = joined.replace(phrase, " ").split()
            if all(w in FILLER or w in STOP_WORDS for w in rest):
                return True
    return False


def wants_back_in(text: str) -> bool:
    return _only(_words(text), START_WORDS)


def _row(db: Session, user_id: int, phone: str) -> Optional[OptOut]:
    contacts = _contacts(phone)
    if not contacts:
        return None
    return db.scalar(select(OptOut).where(OptOut.user_id == user_id, OptOut.contact.in_(contacts)))


def is_out(db: Session, user_id: int, phone: str) -> bool:
    return _row(db, user_id, phone) is not None


def guard(db: Session, user_id: int, phone: str) -> None:
    """Call before any message or call to a person. Raises 409 if they opted out."""
    if is_out(db, user_id, phone):
        raise HTTPException(409, BLOCKED)


def _leads(db: Session, user_id: int, phone: str) -> list:
    contacts = _contacts(phone)
    return [l for l in db.scalars(select(Lead).where(Lead.user_id == user_id, Lead.phone != ""))
            if _contacts(l.phone) & contacts]


def opt_out(db: Session, user_id: int, phone: str, source: str, note: str = "") -> bool:
    """Record an opt-out, cancel everything queued for that number, and mark their leads. False if already out."""
    from .routers.leads import add_event
    contact = wa_number(phone)
    if not contact or is_out(db, user_id, phone):
        return False
    now = utcnow()
    db.add(OptOut(user_id=user_id, contact=contact, source=source, note=note[:300]))
    db.execute(update(WaScheduled).where(WaScheduled.user_id == user_id, WaScheduled.contact.in_(_contacts(phone)),
                                         WaScheduled.status == "scheduled")
               .values(status="cancelled", error="Cancelled: they asked not to be contacted."))
    for c in db.scalars(select(Call).where(Call.user_id == user_id, Call.status == "scheduled")):
        if _contacts(c.to_number) & _contacts(phone):  # an AI call waiting for 9 am is called off too
            c.status = "cancelled"
    for lead in _leads(db, user_id, phone):
        lead.opted_out_at = now
        db.execute(update(FollowUp).where(FollowUp.lead_id == lead.id, FollowUp.status == "pending")
                   .values(status="skipped", note="The lead opted out"))
        add_event(db, lead, "opt_out", "Opted out: no more messages or calls",
                  {"whatsapp": f"They replied “{note}” on WhatsApp." if note else "They asked to stop on WhatsApp.",
                   "manual": "You marked them as not to be contacted."}.get(source, ""), source=source)
    db.commit()
    return True


def opt_in(db: Session, user_id: int, phone: str, source: str) -> bool:
    """Undo an opt-out. `source` is "whatsapp" (they replied START) or "manual" (the business resumed them)."""
    from .routers.leads import add_event
    contacts = _contacts(phone)
    rows = list(db.scalars(select(OptOut).where(OptOut.user_id == user_id, OptOut.contact.in_(contacts)))) if contacts else []
    if not rows:
        return False
    for r in rows:
        db.delete(r)
    for lead in _leads(db, user_id, phone):
        lead.opted_out_at = None
        add_event(db, lead, "opt_in", "Messages resumed",
                  "They replied START on WhatsApp." if source == "whatsapp" else
                  "You resumed messages and calls. Only do this when the customer asked you to.", source=source)
    db.commit()
    return True


def on_inbound(db: Session, user_id: int, contact: str, text: str) -> None:
    """Check every inbound WhatsApp message for STOP / START."""
    if wants_out(text):
        opt_out(db, user_id, contact, "whatsapp", (text or "").strip()[:80])
    elif wants_back_in(text):
        opt_in(db, user_id, contact, "whatsapp")


def mark_new_lead(db: Session, lead: Lead) -> None:
    """A new lead whose number already opted out starts opted out."""
    if lead.phone and not lead.opted_out_at:
        row = _row(db, lead.user_id, lead.phone)
        if row:
            lead.opted_out_at = row.created_at
