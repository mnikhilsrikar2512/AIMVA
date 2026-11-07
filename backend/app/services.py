"""Shared helpers: LLM text generation, lead scoring, sentiment, integration lookup."""
import re
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .config import settings
from .models import Integration, Lead
from .security import decrypt_json

_sentiment = SentimentIntensityAnalyzer()


def sentiment(text: str) -> float:
    """Compound sentiment in [-1, 1] using VADER (github.com/cjhutto/vaderSentiment)."""
    return round(_sentiment.polarity_scores(text or "")["compound"], 3)


GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_FALLBACK_MODEL = "gemini-flash-latest"  # Google's alias for the current Flash model


def gemini_key(db: Session, user_id: Optional[int]) -> str:
    """The user's own Gemini key (Settings → Integrations) if connected, else the server-wide key from .env."""
    if user_id is not None:
        own = integration_secret(db, user_id, "gemini").get("api_key")
        if own:
            return own
    return settings.gemini_api_key


def llm(prompt: str, system: str = "", max_tokens: int = 2048, key: Optional[str] = None) -> Optional[str]:
    """Generate text with Gemini, or return None so callers fall back to templates.

    Pass `key=gemini_key(db, user.id)` to use the signed-in user's key; without it the server key is used.
    """
    key = key if key is not None else settings.gemini_api_key
    if not key:
        return None
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    for model in dict.fromkeys([settings.gemini_model, GEMINI_FALLBACK_MODEL]):
        try:
            r = httpx.post(f"{GEMINI_API}/models/{model}:generateContent", params={"key": key}, json=body, timeout=60)
            if r.status_code == 404:  # model retired or renamed: try the "latest Flash" alias
                continue
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip() or None
        except Exception:
            return None
    return None


def score_lead(lead: Lead) -> int:
    """Rule-based predictive score 0-100 from completeness, intent words and source quality."""
    s = 10
    if lead.email and re.match(r"[^@]+@[^@]+\.[^@]+", lead.email):
        s += 15
        if not re.search(r"@(gmail|yahoo|hotmail|outlook)\.", lead.email):
            s += 10  # business domain
    if lead.phone and len(re.sub(r"\D", "", lead.phone)) >= 10:
        s += 20
    msg = (lead.message or "").lower()
    if len(msg) > 30:
        s += 10
    if re.search(r"\b(price|pricing|quote|buy|book|demo|visit|budget|asap|urgent|today|interested)\b", msg):
        s += 20
    s += {"voice": 10, "whatsapp": 8, "website": 6, "google": 6, "meta": 4, "linkedin": 8}.get(lead.source, 0)
    s += int(sentiment(msg) * 5)
    return max(0, min(100, s))


def get_integration(db: Session, user_id: int, provider: str) -> Optional[Integration]:
    return db.scalar(select(Integration).where(Integration.user_id == user_id, Integration.provider == provider))


def integration_secret(db: Session, user_id: int, provider: str) -> dict:
    integ = get_integration(db, user_id, provider)
    return decrypt_json(integ.secret) if integ else {}
