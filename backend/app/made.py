"""One prompt, then changes, for Calls and Campaigns (design.md v3 7.3, release 2).

Pictures and videos already keep every version as an asset. A call script and a campaign draft are one row each,
so their versions live here, with the owner's (or a teammate's) own words and who asked.

  POST  /api/calls/script                the call assistant's script, written from one sentence
  POST  /api/calls/script/change         a change to the script, in the owner's words
  PATCH /api/voice/agents/{id}/enabled   call-backs on or off
  POST  /api/campaigns/draft             a draft campaign (nothing is spent) from one sentence
  POST  /api/campaigns/{id}/change       a change to the draft, in the owner's words
  GET   /api/versions/{kind}/{ref_id}    the changes panel: newest first, the words, who asked, which is showing
  GET   /api/versions/{id}               one version's content (for Compare)
  POST  /api/versions/{id}/restore       put an older version back; saved as a new version, nothing is lost

No response explains how a prompt was read, and none names an AI provider (project rules).
"""
import json
import re
from typing import Callable, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ai_registry
from .db import get_db
from .models import Asset, Campaign, MadeVersion, Site, User, VoiceAgent
from .security import current_user, rate_limit

router = APIRouter(tags=["made"])
Kind = Literal["call_script", "campaign"]
SCRIPT_KEYS = ("name", "language", "greeting", "instructions", "questions", "handoff_number")
CAMPAIGN_KEYS = ("name", "objective", "daily_budget", "creative", "targeting", "lead_form")

# Language names an owner may write, in English or romanised, to the voice codes the call assistant speaks.
LANG_WORDS = {
    "te-IN": r"telugu", "hi-IN": r"hindi|hinglish", "ta-IN": r"tamil", "kn-IN": r"kannada", "ml-IN": r"malayalam",
    "mr-IN": r"marathi", "bn-IN": r"bengali|bangla", "gu-IN": r"gujarati", "pa-IN": r"punjabi", "od-IN": r"odia|oriya",
    "en-IN": r"english",
}
LANG_NAMES = {"te-IN": "Telugu", "hi-IN": "Hindi", "ta-IN": "Tamil", "kn-IN": "Kannada", "ml-IN": "Malayalam",
              "mr-IN": "Marathi", "bn-IN": "Bengali", "gu-IN": "Gujarati", "pa-IN": "Punjabi", "od-IN": "Odia", "en-IN": "English"}
PROFILE_LANG = {"te-Latn": "te-IN", "ta-Latn": "ta-IN", "hi-Latn": "hi-IN", "en": "en-IN"}
GOALS = [  # first match wins: what the call should end with
    ("site visit", r"site visit"), ("visit", r"\bvisit\b"), ("appointment", r"appointment|consultation|check-?up"),
    ("demo", r"\bdemo\b"), ("table booking", r"\btable\b"), ("trial class", r"trial|demo class"),
    ("call with our team", r"call with|talk to (?:the|our) team"),
]


# ---- versions ---------------------------------------------------------------------------------------------
def _person(req: Request) -> Optional[int]:
    p = getattr(req.state, "person", None)
    return p.id if p else None


def snapshot(kind: str, obj) -> dict:
    keys = SCRIPT_KEYS if kind == "call_script" else CAMPAIGN_KEYS
    return {k: getattr(obj, k) for k in keys}


def record(db: Session, kind: str, obj, by_id: Optional[int], request: str = "", note: str = "") -> MadeVersion:
    """Save what obj looks like now as its next version. Nothing is ever overwritten."""
    n = db.scalar(select(func.max(MadeVersion.number)).where(MadeVersion.kind == kind, MadeVersion.ref_id == obj.id)) or 0
    v = MadeVersion(user_id=obj.user_id, kind=kind, ref_id=obj.id, number=n + 1, request=request.strip()[:300],
                    note=note[:120], data=json.loads(json.dumps(snapshot(kind, obj), default=str)), by_id=by_id)
    db.add(v)
    db.flush()  # so the next version in the same request counts this one
    return v


def _target(db: Session, user: User, kind: str, ref_id: int):
    M = VoiceAgent if kind == "call_script" else Campaign
    obj = db.get(M, ref_id)
    if not obj or obj.user_id != user.id:
        raise HTTPException(404, "Not found.")
    return obj


@router.get("/api/versions/{kind}/{ref_id}")
def list_versions(kind: Kind, ref_id: int, req: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """`by` is the teammate who asked, or null when it was the viewer; `request` is their own words."""
    obj = _target(db, user, kind, ref_id)
    rows = list(db.scalars(select(MadeVersion).where(MadeVersion.kind == kind, MadeVersion.ref_id == obj.id)
                           .order_by(MadeVersion.number.desc())))
    me = _person(req)
    ids = {v.by_id for v in rows if v.by_id and v.by_id != me}
    names = dict(db.execute(select(User.id, User.name).where(User.id.in_(ids))).all()) if ids else {}
    now = json.loads(json.dumps(snapshot(kind, obj), default=str))
    current = next((v.id for v in rows if v.data == now), None)
    return [{"id": v.id, "number": v.number, "request": v.request, "note": v.note, "by": names.get(v.by_id) or None,
             "created_at": v.created_at.isoformat(), "current": v.id == current} for v in rows]


def _version(db: Session, user: User, vid: int) -> MadeVersion:
    v = db.get(MadeVersion, vid)
    if not v or v.user_id != user.id:
        raise HTTPException(404, "Version not found.")
    return v


@router.get("/api/versions/{vid}")
def get_version(vid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    v = _version(db, user, vid)
    return {"id": v.id, "number": v.number, "kind": v.kind, "data": v.data}


@router.post("/api/versions/{vid}/restore")
def restore(vid: int, req: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    v = _version(db, user, vid)
    obj = _target(db, user, v.kind, v.ref_id)
    for k, val in v.data.items():
        if k in (SCRIPT_KEYS if v.kind == "call_script" else CAMPAIGN_KEYS):
            setattr(obj, k, val)
    record(db, v.kind, obj, _person(req), note=f"Back to v{v.number}")
    db.commit()
    return _out(v.kind, obj)


def _out(kind: str, obj) -> dict:
    if kind == "call_script":
        from .routers.voice import agent_out
        return agent_out(obj)
    from .routers.campaigns import campaign_out
    return campaign_out(obj)


# ---- shared helpers ---------------------------------------------------------------------------------------
def _writer(db: Session, user: User) -> Optional[Callable]:
    from .ai_engine import agent_writer
    return agent_writer(db, user.id, "copywriter")


def _json(out: Optional[str]) -> dict:
    m = re.search(r"\{.*\}", out or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _profile(user: User) -> dict:
    return dict((user.onboarding_answers or {}).get("profile") or {})


def _business(user: User) -> str:
    return (user.company or _profile(user).get("name") or "").strip() or "our business"


def langs_in(text: str) -> List[str]:
    """Voice codes for the languages a sentence names, in the order it names them."""
    found = [(m.start(), code) for code, pat in LANG_WORDS.items() for m in [re.search(rf"\b(?:{pat})\b", text or "", re.I)] if m]
    return [code for _, code in sorted(found)]


def _speakable(codes: List[str]) -> str:
    """The first named language the call assistant can speak, else Indian English."""
    can = ai_registry.voice_languages()
    return next((c for c in codes if c in can), "en-IN")


def _sentence(text: str) -> str:
    text = " ".join((text or "").split()).strip(" .")
    return (text[:1].upper() + text[1:]) if text else ""


def _question(text: str) -> str:
    q = _sentence(text).rstrip("?")
    return f"{q}?" if q else ""


# ---- Calls ------------------------------------------------------------------------------------------------
class ScriptIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)
    agent_id: Optional[int] = None


class ChangeIn(BaseModel):
    request: str = Field(min_length=2, max_length=300)


def _agent_for(db: Session, user: User, agent_id: Optional[int]) -> VoiceAgent:
    if agent_id is not None:
        return _target(db, user, "call_script", agent_id)
    a = db.scalar(select(VoiceAgent).where(VoiceAgent.user_id == user.id).order_by(VoiceAgent.id))
    if not a:
        a = VoiceAgent(user_id=user.id, name=f"{_business(user)} assistant"[:120], language="en-IN", greeting="",
                       instructions="", questions=[])
        db.add(a)
        db.flush()
    return a


def _template_questions(db: Session, user: User) -> tuple:
    from .quality import match_playbook
    from .template_agent import fill, user_ctx
    from .templates_catalog import CATALOG
    playbook = match_playbook(_profile(user).get("industry", ""), user.industry)
    voice = [t for t in CATALOG if t["module"] == "voice"]
    t = next((t for t in voice if playbook in t["industries"]), None) or next((t for t in voice if not t["industries"]), voice[0])
    p = fill(t["payload"], user_ctx(db, user))
    return p["greeting"], list(p["questions"])


def _goal(text: str) -> Optional[str]:
    return next((g for g, pat in GOALS if re.search(pat, text or "", re.I)), None)


def _instructions(business: str, codes: List[str], goal: Optional[str], brief: str) -> str:
    names = [LANG_NAMES[c] for c in codes if c in LANG_NAMES] or ["English"]
    spoken = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]
    parts = [f"You call back people who asked {business} to call them.",
             f"Speak {spoken}. If the caller answers in another language, switch to theirs.",
             "Be warm and brief: at most two sentences a turn.",
             f"Aim to book a {goal}." if goal else "Aim to agree a next step and a time.",
             "Never promise prices, offers or times you weren't given.",
             f"The owner's brief: {_sentence(brief)}."]
    return " ".join(parts)


def write_script(db: Session, user: User, prompt: str) -> dict:
    """{language, greeting, instructions, questions} for this business from one sentence."""
    profile = _profile(user)
    codes = langs_in(prompt) or [PROFILE_LANG.get(c, c) for c in (profile.get("customer_languages") or [])]
    codes = [c for c in codes if c in LANG_NAMES]
    business = _business(user)
    greeting, questions = _template_questions(db, user)
    goal = _goal(prompt)
    if goal and not any(re.search(goal.split()[0], q, re.I) for q in questions):
        questions = questions[:-1] + [f"When would suit you for a {goal}?"] if len(questions) > 2 else questions + [f"When would suit you for a {goal}?"]
    script = {"language": _speakable(codes), "greeting": greeting, "questions": questions[:8],
              "instructions": _instructions(business, codes, goal, prompt)}
    write = _writer(db, user)
    if write:
        ai = _json(write(
            "Write the script for a phone assistant that calls back new leads, as JSON {\"greeting\": one or two "
            "sentences it says first, \"questions\": 3 to 6 short questions asked in order (always the caller's name and "
            "a good time), \"instructions\": how it should speak and behave, under 600 characters}. Write the greeting "
            "and questions in English; the assistant translates as it speaks. No invented prices, offers or claims.\n"
            f"Business: {business}. What it sells: {profile.get('offer') or ''}. The owner asked for: {prompt}",
            max_tokens=700))
        qs = [_question(q) for q in ai.get("questions", []) if isinstance(q, str) and q.strip()] if isinstance(ai.get("questions"), list) else []
        if isinstance(ai.get("greeting"), str) and ai["greeting"].strip() and 2 <= len(qs) <= 8:
            script.update(greeting=_sentence(ai["greeting"])[:400] + ".", questions=qs)
            if isinstance(ai.get("instructions"), str) and ai["instructions"].strip():
                script["instructions"] = (ai["instructions"].strip()[:700] + " Never promise prices, offers or times you weren't given.")
    return script


def change_script(db: Session, user: User, a: VoiceAgent, request: str) -> None:
    """Apply one change in the owner's words to the script."""
    req = request.strip()
    write = _writer(db, user)
    if write:
        now = {k: getattr(a, k) for k in ("greeting", "instructions", "questions")}
        ai = _json(write("Here is a phone assistant's script as JSON. Apply the owner's change and return the whole "
                         "script as the same JSON, changing nothing else. Keep greeting and questions in English. "
                         f"No invented prices, offers or claims.\nScript: {json.dumps(now, ensure_ascii=False)}\n"
                         f"Change: {req}", max_tokens=900))
        qs = ai.get("questions") if isinstance(ai.get("questions"), list) else None
        if qs and all(isinstance(q, str) for q in qs) and isinstance(ai.get("greeting"), str) and ai["greeting"].strip():
            a.greeting = ai["greeting"].strip()[:400]
            a.questions = [_question(q) for q in qs if q.strip()][:8]
            if isinstance(ai.get("instructions"), str) and ai["instructions"].strip():
                a.instructions = ai["instructions"].strip()[:1500]
            codes = langs_in(req)
            if codes:
                a.language = _speakable(codes)
            return
    done = False
    codes = langs_in(req)
    if codes:
        a.language = _speakable(codes)
        names = [LANG_NAMES[c] for c in codes]
        line = f"Speak {names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' or ' + names[-1]}. If the caller answers in another language, switch to theirs."
        a.instructions, n = re.subn(r"Speak [^.]+\. If the caller answers in another language, switch to theirs\.", line, a.instructions or "")
        if not n:
            a.instructions = f"{line} {a.instructions or ''}".strip()
        done = True
    m = re.search(r"(?:add (?:a |one more )?question|also ask(?: them)?|ask (?:them )?(?:also|too))\s*[:\-]?\s*(.+)", req, re.I)
    if m:
        a.questions = (a.questions or []) + [_question(m.group(1))]
        done = True
    m = re.search(r"(?:don'?t ask|stop asking|remove|drop)(?: the)?(?: question)?(?: about)?\s+(.+?)(?: question)?$", req, re.I)
    if m:
        words = [w for w in re.findall(r"[a-z]{3,}", m.group(1).lower()) if w not in ("the", "question", "about", "their")]
        keep = [q for q in (a.questions or []) if not any(w in q.lower() for w in words)]
        if words and len(keep) < len(a.questions or []):
            a.questions, done = keep, True
    m = re.search(r"(?:greet (?:them )?with|start with|first say|greeting)\s*[:\-]?\s*[\"“']?(.+?)[\"”']?$", req, re.I)
    if m and len(m.group(1)) > 3:
        a.greeting, done = _sentence(m.group(1))[:400] + ".", True
    if re.search(r"\b(shorter|brief|quick|less talk)\b", req, re.I) and not done:
        a.instructions = f"{a.instructions or ''} Keep every turn very short: one sentence where you can.".strip()
        done = True
    goal = _goal(req)
    if goal and not done:
        a.instructions = re.sub(r"Aim to (?:book a [^.]+|agree a next step and a time)\.", f"Aim to book a {goal}.", a.instructions or "")
        done = True
    if not done:  # the assistant reads these on every call, so the words still change what it does
        a.instructions = f"{a.instructions or ''} Also: {_sentence(req)}.".strip()[:1500]


def _script_changed(a: VoiceAgent, script: dict) -> None:
    for k, v in script.items():
        setattr(a, k, v)


@router.post("/api/calls/script")
def make_script(body: ScriptIn, req: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(f"script:{user.id}", 20, 600)
    a = _agent_for(db, user, body.agent_id)
    _script_changed(a, write_script(db, user, body.prompt.strip()))
    record(db, "call_script", a, _person(req), request=body.prompt)
    db.commit()
    from .routers.voice import agent_out
    return agent_out(a)


@router.post("/api/calls/script/change")
def change_script_route(body: ChangeIn, req: Request, agent_id: Optional[int] = None, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    rate_limit(f"script:{user.id}", 20, 600)
    a = _agent_for(db, user, agent_id)
    if not db.scalar(select(MadeVersion.id).where(MadeVersion.kind == "call_script", MadeVersion.ref_id == a.id)):
        record(db, "call_script", a, None, note="Before your changes")  # the script as it was, so it can come back
    change_script(db, user, a, body.request)
    record(db, "call_script", a, _person(req), request=body.request)
    db.commit()
    from .routers.voice import agent_out
    return agent_out(a)


class EnabledIn(BaseModel):
    enabled: bool


@router.patch("/api/voice/agents/{aid}/enabled")
def set_enabled(aid: int, body: EnabledIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _target(db, user, "call_script", aid)
    a.enabled = body.enabled
    db.commit()
    from .routers.voice import agent_out
    return agent_out(a)


# ---- Campaigns --------------------------------------------------------------------------------------------
class DraftIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)
    platform: Literal["meta", "google", "linkedin"] = "meta"
    asset_id: Optional[int] = None  # a picture or video from "Use in a campaign"


_NUM = r"(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?|l)?"
_MONEY = [rf"(?:₹|\brs\.?|\binr|\brupees)\s*{_NUM}", rf"{_NUM}\s*(?:₹|rs\b|rupees|/-)", r"(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?)\b"]
_PER = r"\s*(?:a|per|/|every)?\s*(day|daily|week|weekly|month|monthly|mo)?\b"


def budget_in(text: str) -> Optional[float]:
    """A daily budget in rupees from "₹500 a day", "Rs 15,000 a month", "5k per week"."""
    m = next((m for pat in _MONEY for m in [re.search(pat + _PER, text or "", re.I)] if m), None)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    num *= 100000 if unit.startswith("l") else 1000 if unit in ("k", "thousand") else 1
    per = (m.group(3) or "").lower()
    if per.startswith("week"):
        num /= 7
    elif per.startswith("mo"):
        num /= 30
    elif not per and num >= 5000:  # a bare total that big is a month's budget, not a day's
        num /= 30
    return round(num, 2)


def place_in(text: str) -> dict:
    out = {}
    km = re.search(r"(\d{1,3})\s*(?:km|kms|kilometres|kilometers)\b", text or "", re.I)
    if km:
        out["radius_km"] = int(km.group(1))
    m = re.search(r"(?:\d\s*(?:km|kms|kilometres|kilometers)\s+(?:of|from|around)|\baround|\bnear|\bin and around|\bwithin\s+(?!\d)|\bin)\s+"
                  r"((?-i:[A-Z])[\w'.-]*(?:\s+(?-i:[A-Z])[\w'.-]*){0,3})", text or "", re.I)
    if m and m.group(1).lower() not in ("meta", "google", "linkedin", "instagram", "facebook", "whatsapp", "telugu", "hindi", "english"):
        out["locations"] = m.group(1).strip(" .,")
    ages = re.search(r"\b(\d{2})\s*(?:-|–|to)\s*(\d{2})\b", text or "")
    if ages and 13 <= int(ages.group(1)) < int(ages.group(2)) <= 65:
        out["age_min"], out["age_max"] = int(ages.group(1)), int(ages.group(2))
    who = re.search(r"\bfor\s+((?:young |working |new |local )?(?:families|parents|students|couples|women|men|mothers|professionals|"
                    r"business owners|homebuyers|home buyers|investors|kids|seniors|doctors|founders|retailers)[\w ]{0,30}?)"
                    r"(?=\s+(?:within|in|around|near|aged|age|on|at|,|\.)|$)", text or "", re.I)
    if who:
        out["interests"] = who.group(1).strip()
    return out


def _page_link(db: Session, user: User) -> str:
    q = select(Site).where(Site.user_id == user.id)
    s = db.scalar(q.where(Site.published.is_(True)).order_by(Site.id.desc())) or db.scalar(q.order_by(Site.id.desc()))
    from .config import settings
    return (s.deploy_url or f"{settings.public_url}/s/{s.slug}") if s else ""


def _latest_image(db: Session, user: User) -> str:
    a = db.scalar(select(Asset).where(Asset.user_id == user.id, Asset.kind == "image", Asset.status == "done")
                  .order_by(Asset.id.desc()))
    return a.url if a else ""


def _with_campaign(link: str, cid: int) -> str:
    if not link:
        return ""
    link = re.sub(r"([?&])aimva_c=\d+&?", r"\1", link).rstrip("?&")
    return f"{link}{'&' if '?' in link else '?'}aimva_c={cid}"


_ASK = re.compile(r"^\s*(?:please\s+)?(?:run|make|create|draft|start|launch|set up|give me|i want|i need)?\s*(?:me\s+)?(?:an?\s+|some\s+)?"
                  r"(?:(?:₹|rs\.?\s*)?[\d,]+k?\s+)?(?:(?:meta|facebook|instagram|google|linkedin|whats ?app)\s+)?(?:ads?|campaigns?|promotion)\b\s*(?:for|about|on|of|to promote)?\s*", re.I)
_NOISE = re.compile(r"\b(?:₹|rs\.?|inr)?\s*[\d,]+\s*(?:k)?\s*(?:a|per)?\s*(?:day|daily|budget|rupees)\b|\bthis week\b|\btoday\b|"
                    r"\b(?:within|in|around|near)\s+\d+\s*km\b.*$", re.I)


def offer_in(prompt: str) -> str:
    """What the owner wants advertised, from their own sentence: "Run an ad for our Sankranti offer: 20% off membership"
    -> "Sankranti offer: 20% off membership". Empty when the sentence only asks for an ad ("run ads", "₹500 ad this week")."""
    t = _ASK.sub("", prompt or "", count=1)
    t = _NOISE.sub("", t)
    if re.match(r"\s*(?:that|which|to)\s+(?:brings?|sends?|takes?|gets?)\b", t, re.I):
        return ""  # "an ad that brings people to my page": about where it goes, not what is offered
    if re.match(r"\s*(?:in|at|near|around|within|across)\b", t, re.I):
        return ""  # "ads in Kukatpally": a place, read separately by place_in
    t = re.sub(r"^\s*(?:our|my|the)\s+", "", t, flags=re.I).strip(" .,:;-")
    t = re.sub(r"\s+(?:ads?|campaigns?)\s*$", "", t, flags=re.I)
    words = [w for w in re.findall(r"[^\W\d_]{2,}", t) if w.lower() not in {"run", "make", "an", "ad", "ads", "rupees", "rs", "inr", "please"}]
    return t[:120] if len(words) >= 2 else ""


def draft_campaign(db: Session, user: User, prompt: str, platform: str, asset_id: Optional[int] = None) -> Campaign:
    from .agents.launch import _ad_copy
    from .quality import match_playbook
    profile = _profile(user)
    business = _business(user)
    where = place_in(prompt)
    area = where.get("locations") or profile.get("area") or profile.get("city") or ""
    playbook = match_playbook(profile.get("industry", ""), user.industry)
    # The ad speaks about the business, never repeats the owner's instructions back ("A Meta campaign for...").
    site = db.scalar(select(Site).where(Site.user_id == user.id).order_by(Site.id.desc()))
    # The owner's own words win: "an ad for our Sankranti offer" is about Sankranti, not the offer saved at setup.
    offer = (offer_in(prompt) or profile.get("offer") or ((site.brief or {}).get("offer") if site else "") or "").strip()
    facts = {"business": business, "offer": offer or (f"{business} in {area}" if area else business), "location_line": area,
             "audience": where.get("interests", "")}
    copy = _ad_copy(db, user, facts, playbook)
    whatsapp = bool(re.search(r"whats\s?app", prompt, re.I))
    if whatsapp:
        copy["cta"] = "Send message"
    targeting = {"locations": area, "radius_km": where.get("radius_km", 10 if area else 0),
                 "age_min": where.get("age_min", 18), "age_max": where.get("age_max", 65),
                 "interests": where.get("interests", "")}
    budget = budget_in(prompt)
    media = {"image_url": _latest_image(db, user)}
    if asset_id is not None:
        a = db.get(Asset, asset_id)
        if not a or a.user_id != user.id or a.kind not in ("image", "video") or a.status != "done":
            raise HTTPException(404, "That picture or video isn't in this project.")
        media = {"image_url": a.url} if a.kind == "image" else {**media, "video_url": a.url}
    c = Campaign(user_id=user.id, platform=platform, objective="leads",
                 name=(f"{business} · {area}" if area else business)[:200],
                 daily_budget=budget if budget is not None else 500.0,
                 creative={**copy, **media, "destination": "whatsapp" if whatsapp else "page"},
                 targeting=targeting, lead_form={"fields": ["full_name", "phone_number"]})
    db.add(c)
    db.flush()
    c.creative = {**c.creative, "link": _with_campaign(_page_link(db, user), c.id)}
    return c


def change_campaign(db: Session, user: User, c: Campaign, request: str) -> None:
    from .agents.launch import clip
    req = request.strip()
    creative, targeting = dict(c.creative or {}), dict(c.targeting or {})
    done = False
    budget = budget_in(req)
    if budget is None:
        m = re.search(r"budget\s+(?:to|of|at)?\s*([\d,]+)", req, re.I)
        budget = float(m.group(1).replace(",", "")) if m else None
    if budget is not None:
        c.daily_budget, done = budget, True
    where = place_in(req)
    if where:
        targeting.update(where)
        done = True
    if re.search(r"whats\s?app", req, re.I):
        creative.update(cta="Send message", destination="whatsapp")
        done = True
    elif re.search(r"(?:to|send (?:them|people) to) (?:my|the) (?:page|website|site)", req, re.I):
        creative.update(destination="page", link=_with_campaign(_page_link(db, user), c.id))
        done = True
    if re.search(r"(?:latest|newest|new|last) (?:picture|image|photo)", req, re.I):
        img = _latest_image(db, user)
        if img:
            creative["image_url"], done = img, True
    quoted = re.search(r"[\"“']([^\"”']{3,120})[\"”']", req)
    if quoted and re.search(r"headline|title", req, re.I):
        creative["headline"], done = clip(quoted.group(1), 40), True
    elif quoted and re.search(r"\btext\b|copy|body|description", req, re.I):
        creative["text"], done = quoted.group(1)[:500], True
    if not done:
        write = _writer(db, user)
        ai = _json(write("Here is an ad as JSON {\"headline\": max 40 chars, \"text\": max 300 chars}. Apply the owner's "
                         "change and return the same JSON. No invented numbers, awards or claims; no exclamation marks.\n"
                         f"Ad: {json.dumps({'headline': creative.get('headline', ''), 'text': creative.get('text', '')}, ensure_ascii=False)}\n"
                         f"Change: {req}", max_tokens=400)) if write else {}
        if isinstance(ai.get("headline"), str) and ai["headline"].strip() and isinstance(ai.get("text"), str):
            creative.update(headline=clip(ai["headline"].strip(), 40), text=ai["text"].strip()[:500])
            done = True
        elif re.search(r"\bshort(?:er)?\b", req, re.I):
            if re.search(r"headline|title", req, re.I) or not re.search(r"\btext\b|copy|body", req, re.I):
                creative["headline"] = clip(creative.get("headline", ""), 28)
            if not re.search(r"headline|title", req, re.I):
                creative["text"] = clip(creative.get("text", "").split("\n")[0], 120)
            done = True
    if not done:
        raise HTTPException(422, "That change needs a hand: click the headline, text or budget on the ad to edit it.")
    c.creative, c.targeting = creative, targeting


@router.post("/api/campaigns/draft")
def make_draft(body: DraftIn, req: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(f"draft:{user.id}", 20, 600)
    c = draft_campaign(db, user, body.prompt.strip(), body.platform, body.asset_id)
    record(db, "campaign", c, _person(req), request=body.prompt)
    db.commit()
    from .routers.campaigns import campaign_out
    return campaign_out(c)


@router.post("/api/campaigns/{cid}/change")
def change_campaign_route(cid: int, body: ChangeIn, req: Request, user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    rate_limit(f"draft:{user.id}", 30, 600)
    c = _target(db, user, "campaign", cid)
    if not db.scalar(select(MadeVersion.id).where(MadeVersion.kind == "campaign", MadeVersion.ref_id == c.id)):
        record(db, "campaign", c, None, note="Before your changes")
    change_campaign(db, user, c, body.request)
    record(db, "campaign", c, _person(req), request=body.request)
    db.commit()
    from .routers.campaigns import campaign_out
    return campaign_out(c)
