"""AI voice agent: lead qualification calls with sentiment analysis and human handoff.

- Browser calls: the frontend does speech-to-text / text-to-speech with the Web Speech API and
  sends each utterance to /turn; the agent replies (Gemini when configured, scripted otherwise).
- Phone calls: Twilio places the call and drives the same dialogue through TwiML <Gather> webhooks.
"""
import re
from typing import List, Optional
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import ai_registry, call_hours, speech
from ..config import settings
from ..db import get_db
from ..models import Call, User, VoiceAgent
from ..security import current_user
from ..services import integration_secret, sentiment
from ..webhooks import TwilioRequest, twilio_request
from .providers import writer
from .leads import create_lead

router = APIRouter(tags=["voice"])
HANDOFF_WORDS = re.compile(r"\b(human|real person|agent|representative|manager|talk to someone)\b", re.I)
LANGS = {"en-US": "English", "en-IN": "English (India)", "hi-IN": "Hindi", "te-IN": "Telugu", "ta-IN": "Tamil",
         "es-ES": "Spanish", "fr-FR": "French", "de-DE": "German", "ar-SA": "Arabic"}
DEFAULT_QUESTIONS = ["May I have your full name?", "What's the best phone number or email to reach you?",
                     "What are you looking for, and what's your budget?", "When would be a good time for a visit or demo?"]


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    language: str = "en-US"
    greeting: str = "Hi! Thanks for your interest. I'm here to ask a few quick questions so we can help you better."
    instructions: str = "You are a friendly, concise sales assistant. Keep replies under 2 sentences."
    questions: List[str] = DEFAULT_QUESTIONS
    handoff_number: str = ""


def agent_out(a: VoiceAgent) -> dict:
    return {"id": a.id, "name": a.name, "language": a.language, "greeting": a.greeting,
            "instructions": a.instructions, "questions": a.questions, "handoff_number": a.handoff_number,
            "created_at": a.created_at.isoformat()}


def call_out(c: Call) -> dict:
    return {"id": c.id, "agent_id": c.agent_id, "lead_id": c.lead_id, "channel": c.channel, "to_number": c.to_number,
            "transcript": c.transcript, "sentiment": c.sentiment, "answers": c.answers, "status": c.status,
            "created_at": c.created_at.isoformat(),
            "scheduled_for": (lambda t: t.isoformat() if t else None)(scheduled_for(c))}


def _agent(db: Session, user: User, aid: int) -> VoiceAgent:
    a = db.get(VoiceAgent, aid)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Agent not found.")
    return a


@router.get("/api/voice/languages")
def languages():
    """Codes and names only. The list grows on its own when the multilingual voice engine is switched on."""
    return ai_registry.voice_languages()


def call_lang(agent: VoiceAgent, call: Call) -> str:
    """The language this call speaks: chosen when it started (from the lead), or switched on their first reply."""
    return (call.transcript[0].get("lang") if call.transcript else None) or agent.language


@router.get("/api/voice/agents")
def list_agents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [agent_out(a) for a in db.scalars(select(VoiceAgent).where(VoiceAgent.user_id == user.id).order_by(VoiceAgent.id))]


@router.post("/api/voice/agents")
def create_agent(body: AgentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = VoiceAgent(user_id=user.id, **body.model_dump())
    db.add(a)
    db.commit()
    return agent_out(a)


@router.put("/api/voice/agents/{aid}")
def update_agent(aid: int, body: AgentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, aid)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    db.commit()
    return agent_out(a)


@router.delete("/api/voice/agents/{aid}")
def delete_agent(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_agent(db, user, aid))
    db.commit()
    return {"ok": True}


# ---- dialogue engine --------------------------------------------------------
def _next_reply(agent: VoiceAgent, call: Call, user_text: str, write=None) -> str:
    asked = [t for t in call.transcript if t["role"] == "agent"]
    q_idx = len(call.answers)
    if q_idx < len(agent.questions) and asked:
        call.answers = {**call.answers, agent.questions[q_idx]: user_text}
        q_idx += 1
    remaining = agent.questions[q_idx:]
    history = "\n".join(f"{t['role']}: {t['text']}" for t in call.transcript[-12:])
    ai = write and write(f"Conversation so far:\n{history}\nuser: {user_text}\n\n"
             f"Questions still to ask, in order: {remaining or 'none - wrap up, confirm next steps and say goodbye'}.\n"
             f"Reply in {ai_registry.voice_languages().get(call_lang(agent, call), LANGS.get(agent.language, 'English'))} as the agent. Acknowledge briefly, then ask the next question.",
             system=agent.instructions, max_tokens=200)
    if ai:
        return ai
    if remaining:
        return ("Thanks! " if asked else "") + remaining[0]
    return "Thank you, that's everything I need. Our team will confirm your visit shortly. Have a great day!"


def _extract_contact(answers: dict) -> dict:
    blob = " ".join(answers.values())
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", blob)
    phone = re.search(r"\+?\d[\d\s-]{8,}\d", blob)
    name = next(iter(answers.values()), "") if answers else ""
    name = re.sub(r"^(my name is|i am|i'm|this is)\s+", "", name, flags=re.I).strip()[:80]
    return {"name": name, "email": email.group(0) if email else "", "phone": phone.group(0) if phone else ""}


def _process_turn(db: Session, agent: VoiceAgent, call: Call, text: str) -> dict:
    s = sentiment(text)
    call.transcript = call.transcript + [{"role": "user", "text": text, "sentiment": s}]
    user_turns = [t["sentiment"] for t in call.transcript if t["role"] == "user"]
    call.sentiment = round(sum(user_turns) / len(user_turns), 3)
    if HANDOFF_WORDS.search(text) or s <= -0.6:
        reply = ("I understand. Let me connect you with a member of our team right away."
                 if agent.handoff_number else "I understand. A member of our team will call you back shortly.")
        call.status = "handoff"
    else:
        reply = _next_reply(agent, call, text, writer(db, agent.user_id, agent="call_assistant"))
        if len(call.answers) >= len(agent.questions):
            call.status = "completed"
    call.transcript = call.transcript + [{"role": "agent", "text": reply}]
    db.commit()
    return {"reply": reply, "sentiment": s, "status": call.status, "call": call_out(call)}


def _finish(db: Session, user_id: int, call: Call, bg: Optional[BackgroundTasks]) -> None:
    if call.lead_id or not call.answers:
        return
    c = _extract_contact(call.answers)
    if c["email"] or c["phone"]:
        summary = " | ".join(f"{q} {a}" for q, a in call.answers.items())
        lead = create_lead(db, user_id, bg, name=c["name"], email=c["email"], phone=c["phone"] or call.to_number,
                           message=f"Voice call (sentiment {call.sentiment:+.2f}): {summary}", source="voice",
                           source_ref=str(call.id))
        call.lead_id = lead.id
        db.commit()


# ---- browser calls ------------------------------------------------------------
@router.post("/api/voice/agents/{aid}/calls")
def start_call(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _agent(db, user, aid)
    first = a.questions[0] if a.questions else "How can I help you today?"
    greeting = f"{a.greeting} {first}".strip()
    c = Call(user_id=user.id, agent_id=a.id, channel="browser", transcript=[{"role": "agent", "text": greeting}])
    db.add(c)
    db.commit()
    return {"reply": greeting, "call": call_out(c)}


class TurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/api/voice/calls/{cid}/turn")
def turn(cid: int, body: TurnIn, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Call, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Call not found.")
    if c.status != "active":
        raise HTTPException(400, "This call has ended.")
    out = _process_turn(db, db.get(VoiceAgent, c.agent_id), c, body.text)
    if c.status != "active":
        _finish(db, user.id, c, bg)
        out["call"] = call_out(c)
    return out


@router.post("/api/voice/calls/{cid}/end")
def end_call(cid: int, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Call, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Call not found.")
    if c.status == "scheduled":  # a call waiting for calling hours: ending it cancels it
        c.status = "cancelled"
        db.commit()
        return call_out(c)
    if c.status == "active":
        c.status = "completed"
    db.commit()
    _finish(db, user.id, c, bg)
    return call_out(c)


@router.get("/api/voice/calls")
def list_calls(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Call).where(Call.user_id == user.id).order_by(Call.id.desc()).limit(100)
    return [call_out(c) for c in db.scalars(q)]


# ---- phone calls via Twilio ----------------------------------------------------
class DialIn(BaseModel):
    to: str = Field(min_length=8, max_length=20)


def _twilio(db: Session, user_id: int):
    from ..services import get_integration
    tw = integration_secret(db, user_id, "twilio")
    integ = get_integration(db, user_id, "twilio")
    sid = tw.get("account_sid") or settings.twilio_account_sid
    tok = tw.get("auth_token") or settings.twilio_auth_token
    frm = (integ.meta or {}).get("from_number") if integ else settings.twilio_from_number
    if not (sid and tok and frm):
        raise HTTPException(400, "Connect Twilio in Settings → Integrations to place real phone calls.")
    return sid, tok, frm


def _dial(db: Session, c: Call) -> None:
    sid, tok, frm = _twilio(db, c.user_id)
    c.status = "active"  # before dialling: Twilio's /start webhook only answers active calls
    db.commit()
    r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json", auth=(sid, tok), timeout=30,
                   data={"To": c.to_number, "From": frm, "Url": f"{settings.public_url}/api/public/voice/twilio/{c.id}/start"})
    if r.status_code >= 400:
        c.status = "failed"
        db.commit()
        raise HTTPException(502, f"Twilio error: {r.text[:300]}")


def place_phone_call(db: Session, user: User, agent: VoiceAgent, to: str, lead_id: Optional[int] = None) -> Call:
    """Phone `to` with this agent now, or, outside 9 am to 9 pm in the lead's time, save it as "scheduled"
    so the scheduler places it when their calling hours open (call_hours.py). Never dropped."""
    from .. import opt_out
    opt_out.guard(db, user.id, to)  # they replied STOP: no calls either
    _twilio(db, user.id)  # say "connect Twilio" now, not hours later
    if not call_hours.is_open(to):
        waiting = db.scalar(select(Call).where(Call.user_id == user.id, Call.status == "scheduled", Call.to_number == to))
        if waiting:  # pressing "AI call" twice at night still makes one call in the morning
            return waiting
    first = agent.questions[0] if agent.questions else ""
    from ..models import Lead
    lead = db.get(Lead, lead_id) if lead_id else None
    lang = speech.call_language(agent.language, (lead.message if lead and lead.user_id == user.id else "") or "", written=True)
    c = Call(user_id=user.id, agent_id=agent.id, channel="phone", to_number=to, lead_id=lead_id,
             status="active" if call_hours.is_open(to) else "scheduled", created_at=call_hours.now(),
             transcript=[{"role": "agent", "text": f"{agent.greeting} {first}".strip(), "lang": lang}])
    db.add(c)
    db.commit()
    if c.status == "active":
        _dial(db, c)
    return c


def scheduled_for(c: Call):
    """When a deferred call will be placed (naive UTC), or None if it isn't waiting."""
    return call_hours.next_open(c.to_number, c.created_at) if c.status == "scheduled" else None


def place_due_calls(db: Session, at=None) -> int:
    """Scheduler tick: place deferred calls whose lead's calling hours have opened. Stale ones are cancelled, and so
    are calls to anyone who replied STOP while the call was waiting."""
    from .. import opt_out
    from ..models import Lead
    from .leads import add_event
    at = at or call_hours.now()
    placed = 0
    for c in list(db.scalars(select(Call).where(Call.status == "scheduled", Call.channel == "phone").order_by(Call.id))):
        if at - c.created_at > call_hours.STALE_AFTER:
            c.status = "cancelled"
            db.commit()
            continue
        if opt_out.is_out(db, c.user_id, c.to_number):
            c.status = "cancelled"
            db.commit()
            continue
        if not call_hours.is_open(c.to_number, at):
            continue
        lead = db.get(Lead, c.lead_id) if c.lead_id else None
        try:
            _dial(db, c)
            placed += 1
            if lead and lead.stage == "new":
                lead.stage = "contacted"
                db.commit()
        except HTTPException as e:
            c.status = "failed"
            if lead:
                add_event(db, lead, "call", "Scheduled call failed", str(e.detail))
            db.commit()
    return placed


@router.post("/api/voice/agents/{aid}/dial")
def dial(aid: int, body: DialIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return call_out(place_phone_call(db, user, _agent(db, user, aid), body.to))


def _twiml(agent: VoiceAgent, call: Call, say: str, gather: bool) -> Response:
    code = call_lang(agent, call)
    lang = escape(code)
    url = speech.audio_url(say, code) if speech.speaks(code) else None  # natural multilingual voice when switched on
    body = f"<Play>{escape(url)}</Play>" if url else f'<Say language="{lang}">{escape(say)}</Say>'
    if call.status == "handoff" and agent.handoff_number:
        body += f"<Dial>{escape(agent.handoff_number)}</Dial>"
    elif gather:
        body = (f'<Gather input="speech" language="{lang}" speechTimeout="auto" '
                f'action="{settings.public_url}/api/public/voice/twilio/{call.id}/turn">{body}</Gather>'
                f'<Redirect>{settings.public_url}/api/public/voice/twilio/{call.id}/turn</Redirect>')
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>', media_type="application/xml")


def _twilio_token(db: Session, user_id: int) -> str:
    return integration_secret(db, user_id, "twilio").get("auth_token") or settings.twilio_auth_token


@router.get("/api/public/voice/audio/{token}")
def voice_audio(token: str):
    """Short-lived, signed audio for the phone network to <Play>. Nothing else is reachable here."""
    path = speech.audio_file(token)
    if not path:
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=900"})


@router.post("/api/public/voice/twilio/{cid}/start")
def twilio_start(cid: int, tw: TwilioRequest = Depends(twilio_request), db: Session = Depends(get_db)):
    c = db.get(Call, cid)
    if not c:
        raise HTTPException(404)
    tw.verify(_twilio_token(db, c.user_id))
    return _twiml(db.get(VoiceAgent, c.agent_id), c, c.transcript[0]["text"], True)


@router.post("/api/public/voice/twilio/{cid}/turn")
def twilio_turn(cid: int, bg: BackgroundTasks, SpeechResult: str = Form(""), tw: TwilioRequest = Depends(twilio_request),
                db: Session = Depends(get_db)):
    c = db.get(Call, cid)
    if not c or c.status != "active":
        raise HTTPException(404)
    tw.verify(_twilio_token(db, c.user_id))
    agent = db.get(VoiceAgent, c.agent_id)
    if not SpeechResult:
        return _twiml(agent, c, "Sorry, I didn't catch that. Could you repeat?", True)
    # First reply in another language the call can speak? Carry on in theirs.
    if c.transcript and len([t for t in c.transcript if t["role"] == "user"]) == 0:
        switched = speech.call_language(call_lang(agent, c), SpeechResult)
        if switched != call_lang(agent, c):
            c.transcript = [{**c.transcript[0], "lang": switched}] + c.transcript[1:]
    out = _process_turn(db, agent, c, SpeechResult)
    if c.status != "active":
        _finish(db, c.user_id, c, bg)
    return _twiml(agent, c, out["reply"], c.status == "active")
