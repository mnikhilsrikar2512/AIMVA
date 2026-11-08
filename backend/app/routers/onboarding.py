"""First-run onboarding: business profile, industry starter templates and a setup checklist.

Checklist progress is derived from real data (sites, calls, leads, integrations), so it can never
drift out of sync with what the user has actually done.
"""
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AgentSetting, Call, Integration, Lead, Site, User, VoiceAgent
from ..security import current_user

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

Industry = Literal["real_estate", "healthcare", "education", "saas", "retail", "services", "other"]
Goal = Literal["more_leads", "book_visits", "sell_online", "support"]

TEMPLATES = {
    "real_estate": {
        "label": "Real estate",
        "site": {"offer": "Free site visit this weekend", "cta": "Book a site visit",
                 "features": ["RERA approved projects", "Close to metro & schools", "Easy home-loan help"]},
        "agent": {"greeting": "Hi! Thanks for your interest in our homes. I'll ask a few quick questions to find the right property for you.",
                  "questions": ["May I have your full name?", "What's the best phone number or email to reach you?",
                                "Which area and what size home are you looking for?", "What's your budget range?",
                                "When would you like to visit the site?"]},
    },
    "healthcare": {
        "label": "Clinic / healthcare",
        "site": {"offer": "Book your first consultation", "cta": "Book an appointment",
                 "features": ["Experienced doctors", "Same-week appointments", "Insurance accepted"]},
        "agent": {"greeting": "Hello! Thanks for contacting our clinic. I can help you book an appointment.",
                  "questions": ["May I have the patient's full name?", "What's the best phone number to reach you?",
                                "What would you like to see the doctor about?", "Which day and time suit you best?"]},
    },
    "education": {
        "label": "Education / coaching",
        "site": {"offer": "Free demo class", "cta": "Book a free demo",
                 "features": ["Expert faculty", "Small batches", "Proven results"]},
        "agent": {"greeting": "Hi! Thanks for your interest in our courses. Let me ask a few quick questions.",
                  "questions": ["May I have the student's name?", "What's the best phone number or email for you?",
                                "Which course or exam are you preparing for?", "When would you like to attend a demo class?"]},
    },
    "saas": {
        "label": "SaaS / software",
        "site": {"offer": "Start your free trial", "cta": "Get a demo",
                 "features": ["Set up in minutes", "Integrates with your tools", "24/7 support"]},
        "agent": {"greeting": "Hi! Thanks for checking us out. I'll ask a couple of questions so we can tailor a demo.",
                  "questions": ["May I have your name and company?", "What's your work email?",
                                "What problem are you hoping to solve?", "How big is your team?",
                                "When would be a good time for a demo?"]},
    },
    "retail": {
        "label": "Retail / e-commerce",
        "site": {"offer": "10% off your first order", "cta": "Claim my offer",
                 "features": ["Free delivery", "Easy returns", "Secure payments"]},
        "agent": {"greeting": "Hi! Thanks for reaching out. I can help you find the right product.",
                  "questions": ["May I have your name?", "What's the best phone number or email for you?",
                                "What are you looking for today?", "What's your budget?"]},
    },
    "services": {
        "label": "Local services",
        "site": {"offer": "Free quote in 24 hours", "cta": "Get a free quote",
                 "features": ["Licensed professionals", "Transparent pricing", "Satisfaction guaranteed"]},
        "agent": {"greeting": "Hi! Thanks for calling. I'll take a few details so we can send you a quote.",
                  "questions": ["May I have your name?", "What's the best phone number or email to reach you?",
                                "What service do you need, and where?", "When would you like it done?"]},
    },
    "other": {
        "label": "Something else",
        "site": {"offer": "Get in touch today", "cta": "Contact us", "features": ["Fast response", "Expert team", "Fair pricing"]},
        "agent": {"greeting": "Hi! Thanks for your interest. I'll ask a few quick questions so we can help you better.",
                  "questions": ["May I have your full name?", "What's the best phone number or email to reach you?",
                                "What are you looking for?", "When is a good time for us to follow up?"]},
    },
}


def _count(db: Session, model, user_id: int, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(model.user_id == user_id, *where)) or 0


def _alerts_ready(db: Session, user_id: int) -> bool:
    """A phone that gets lead alerts, or a WhatsApp number that welcomes leads by itself."""
    alerts = db.scalar(select(AgentSetting).where(AgentSetting.user_id == user_id, AgentSetting.kind == "lead_alerts"))
    if alerts and alerts.enabled and (alerts.config or {}).get("push"):
        return True
    return _count(db, Integration, user_id, Integration.provider == "whatsapp") > 0


def status(db: Session, user: User) -> dict:
    sites = _count(db, Site, user.id)
    steps = [
        {"key": "verify", "title": "Verify your email", "desc": "Done when you signed up.", "done": True, "to": None},
        {"key": "profile", "title": "Tell us about your business", "desc": "We'll tailor templates to your industry.",
         "done": bool(user.industry), "to": None},
        {"key": "site", "title": "Create a landing page", "desc": "Generate a page with a built-in lead form.",
         "done": sites > 0, "to": "/app/websites"},
        {"key": "publish", "title": "Publish your page", "desc": "Go live with one click on AIMVA hosting.",
         "done": _count(db, Site, user.id, Site.published.is_(True)) > 0, "to": "/app/websites"},
        {"key": "voice", "title": "Test your AI voice agent", "desc": "Have a 1-minute practice call in your browser.",
         "done": _count(db, Call, user.id) > 0, "to": "/app/voice"},
        {"key": "alerts", "title": "Hear about every lead", "desc": "Alerts on your phone, or WhatsApp connected so welcomes go out.",
         "done": _alerts_ready(db, user.id), "to": "/app/settings"},
        {"key": "lead", "title": "Capture your first lead", "desc": "From your page, a test call or WhatsApp.",
         "done": _count(db, Lead, user.id) > 0, "to": "/app/leads"},
        {"key": "connect", "title": "Connect an account", "desc": "Facebook, Google, WhatsApp or hosting.",
         "done": _count(db, Integration, user.id) > 0, "to": "/app/settings?tab=integrations"},
    ]
    done = sum(s["done"] for s in steps)
    return {
        "steps": steps, "completed": done, "total": len(steps), "all_done": done == len(steps),
        "dismissed": user.onboarding_dismissed, "answers": user.onboarding_answers or {}, "needs_profile": not user.industry,
        "industry": user.industry, "goal": user.goal,
        "template": TEMPLATES.get(user.industry or "other"),
        "industries": [{"value": k, "label": v["label"]} for k, v in TEMPLATES.items()],
    }


@router.get("")
def get_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return status(db, user)


class ProfileIn(BaseModel):
    company: str = Field(min_length=1, max_length=160)
    industry: Industry
    goal: Goal = "more_leads"


@router.post("/profile")
def save_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.company, user.industry, user.goal = body.company.strip(), body.industry, body.goal
    # Give new users a ready-to-test voice agent written for their industry.
    if not _count(db, VoiceAgent, user.id):
        t = TEMPLATES[body.industry]["agent"]
        db.add(VoiceAgent(user_id=user.id, name=f"{body.company.strip()} assistant", language="en-IN",
                          greeting=t["greeting"], questions=t["questions"],
                          instructions="You are a friendly, concise assistant. Keep replies under 2 sentences."))
    db.commit()
    return status(db, user)


Short = Field(None, max_length=300)


class AnswersIn(BaseModel):
    """Sign-up questions. Every field is optional and is merged into what's saved, so the app can save step by step."""
    model_config = {"extra": "forbid"}
    for_whom: Optional[Literal["own", "personal", "clients", "employer"]] = None
    website: Optional[str] = Short
    has_website: Optional[bool] = None
    presence: Optional[List[Literal["instagram", "facebook", "google_business", "linkedin", "whatsapp", "youtube", "none"]]] = None
    handles: Optional[Dict[Literal["instagram", "facebook", "google_business", "linkedin", "whatsapp", "youtube"],
                           str]] = None
    acquisition: Optional[Literal["agency", "ads_self", "word_of_mouth", "none"]] = None
    agency_name: Optional[str] = Short
    monthly_budget: Optional[Literal["none", "lt25k", "25k_1l", "gt1l"]] = None
    team_size: Optional[Literal["solo", "small", "large"]] = None


class AnswersBody(BaseModel):
    answers: AnswersIn


@router.post("/answers")
def save_answers(body: AnswersBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    new = body.answers.model_dump(exclude_none=True)
    if "handles" in new:
        new["handles"] = {k: v.strip()[:300] for k, v in new["handles"].items() if v.strip()}
    for k in ("website", "agency_name"):
        if k in new:
            new[k] = new[k].strip()
    if "presence" in new:
        new["presence"] = sorted(set(new["presence"]))
    user.onboarding_answers = {**(user.onboarding_answers or {}), **new}  # a new dict, so the JSON column is saved
    db.commit()
    return status(db, user)


class DismissIn(BaseModel):
    dismissed: bool = True


@router.post("/dismiss")
def dismiss(body: DismissIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.onboarding_dismissed = body.dismissed
    db.commit()
    return status(db, user)
