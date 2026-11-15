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
# Tried in order after GEMINI_MODEL when it is retired, overloaded, rate-limited or slow. New keys can't use 2.5 Flash
# (404 since late 2026) and the "latest" alias was seen hanging for minutes, so a pinned Flash comes first.
GEMINI_FALLBACK_MODELS = ("gemini-3.5-flash", "gemini-flash-lite-latest")
GEMINI_TIMEOUT = 30  # seconds per model; an owner waiting longer than this is better served by the ready-made text


def gemini_key(db: Session, user_id: Optional[int]) -> str:
    """The platform's writing key (app/ai_registry.py). A user's own key only when ALLOW_USER_AI_KEYS is on."""
    from . import ai_registry
    if user_id is not None and ai_registry.user_keys_allowed():
        own = integration_secret(db, user_id, "gemini").get("api_key")
        if own:
            return own
    return ai_registry.key_for("text", "gemini")


def llm(prompt: str, system: str = "", max_tokens: int = 2048, key: Optional[str] = None) -> Optional[str]:
    """Generate text with Gemini, or return None so callers fall back to templates.

    Pass `key=gemini_key(db, user.id)` to use the signed-in user's key; without it the server key is used.
    """
    if key is None:
        from . import ai_registry
        key = ai_registry.key_for("text", "gemini")
    if not key:
        return None
    for model in dict.fromkeys([settings.gemini_model, *GEMINI_FALLBACK_MODELS]):
        out = _gemini_once(model, prompt, system, max_tokens, key)
        if out is not None:
            return out or None
    return None


def _gemini_once(model: str, prompt: str, system: str, max_tokens: int, key: str) -> Optional[str]:
    """One model's answer; "" means it answered nothing, None means try the next model.

    Newer Flash models think before answering and the thinking counts against maxOutputTokens, so a short answer
    (a 12-token label) came back empty. Thinking is turned down to "minimal"; models that refuse that level are
    asked again with their default thinking and room for it on top of the answer."""
    gen = {"maxOutputTokens": max_tokens, "temperature": 0.7, "thinkingConfig": {"thinkingLevel": "minimal"}}
    for attempt in (0, 1):
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": gen}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        try:
            r = httpx.post(f"{GEMINI_API}/models/{model}:generateContent", params={"key": key}, json=body,
                           timeout=GEMINI_TIMEOUT)
        except Exception:
            return None
        if r.status_code == 400 and attempt == 0 and "thinking" in r.text.lower():
            gen = {"maxOutputTokens": max_tokens + 2048, "temperature": 0.7}
            continue
        if r.status_code != 200:
            return None
        try:
            parts = r.json()["candidates"][0]["content"].get("parts", [])
        except Exception:
            return None
        return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
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
