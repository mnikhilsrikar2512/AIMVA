"""AI engine: every AI task in the app runs through here, so it works without anyone's API key.

Each task tries, in order:
  1. yours     your own provider (the one chosen for the task, or your default text provider, or your Gemini key)
  2. platform  the owner's shared key (GEMINI_API_KEY in backend/.env), if set
  3. free      AIMVA free AI: keyless text from Pollinations (open source). Shared by the whole server and limited
               (about 1 reply every 30 s without POLLINATIONS_TOKEN), so it's skipped rather than waited for
  4. rules     the agent's built-in, instant fallback in each module (templates, playbooks, scripted questions)
Answers are remembered for 7 days per user ("memory"), so asking the same thing twice never calls an API again.
A user can set any agent to "rules" (never calls an API) or pin it to one of their providers.
"""
import hashlib
import logging
import threading
import time
from datetime import timedelta
from typing import Callable, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import providers as P
from .config import settings
from .db import SessionLocal
from .models import AgentMemory, AgentPref, AgentRun, ProviderConnection, utcnow
from .security import decrypt_json
from .services import integration_secret, llm

log = logging.getLogger("aimva.ai")

TASKS = {
    "page_writer": {"name": "Page Writer", "does": "Writes your landing pages from the brief.", "module": "Website builder",
                    "rules": "Built-in page layouts and industry playbooks", "free": True, "memory": True},
    "site_reader": {"name": "Website Reader", "does": "Reads your existing website and fills in the brief.", "module": "Website builder",
                    "rules": "Reads contact details, colours and photos directly from the page", "free": True, "memory": True},
    "copywriter": {"name": "Ad Copywriter", "does": "Writes ad headlines and text in your brand voice.", "module": "Ads",
                   "rules": "Proven ad formulas filled with your details", "free": True, "memory": True},
    "prompt_artist": {"name": "Prompt Artist", "does": "Turns short ideas into detailed image and video prompts.", "module": "Images & videos",
                      "rules": "Industry style hints and composition rules", "free": True, "memory": True},
    "call_assistant": {"name": "Call Assistant", "does": "Talks to callers during voice-agent calls.", "module": "Voice agent",
                       "rules": "Your scripted questions, asked in order", "free": False, "memory": False},  # live calls can't wait for a slow free reply
    "analyst": {"name": "Growth Analyst", "does": "Explains your results and writes the weekly brief.", "module": "Analytics & Command Center",
                "rules": "Rule-based insights from your numbers", "free": True, "memory": True},
    "template_curator": {"name": "Template Curator", "does": "Drafts new templates that fit your business.", "module": "Templates",
                         "rules": "Learns from your edits, best campaigns and pages", "free": True, "memory": True},
}
ENGINE_LABELS = {"yours": "Your AI provider", "platform": "AIMVA shared key", "free": "AIMVA free AI", "memory": "Remembered answer",
                 "rules": "Built-in rules"}
MEMORY_DAYS = 7
FREE_URL = "https://text.pollinations.ai/openai"


# ---- the free engine -----------------------------------------------------------------------------------
class _FreeGate:
    """The keyless tier allows ~1 reply per 30 s per server. Never queue users behind it: skip when it's busy."""
    def __init__(self):
        self.lock = threading.Lock()
        self.next_ok = 0.0

    def take(self) -> bool:
        with self.lock:
            now = time.monotonic()
            if now < self.next_ok:
                return False
            self.next_ok = now + (3 if settings.pollinations_token else 31)
            return True

    def busy_for(self, seconds: float) -> None:
        with self.lock:
            self.next_ok = max(self.next_ok, time.monotonic() + seconds)


free_gate = _FreeGate()


def free_available() -> bool:
    return settings.free_ai


def free_chat(prompt: str, system: str = "", max_tokens: int = 2048) -> Optional[str]:
    if not settings.free_ai or not free_gate.take():
        return None
    headers = {"Authorization": f"Bearer {settings.pollinations_token}"} if settings.pollinations_token else {}
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    try:
        r = httpx.post(FREE_URL, json={"model": "openai", "messages": msgs, "max_tokens": max_tokens}, headers=headers, timeout=90)
    except httpx.HTTPError as e:
        log.info("Free AI unreachable: %s", e)
        return None
    if r.status_code in (402, 429):
        wait = r.headers.get("retry-after", "")
        free_gate.busy_for(float(wait) if wait.replace(".", "", 1).isdigit() else 30)
        return None
    if r.status_code >= 400:
        return None
    try:
        text = r.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return text.strip() or None


# ---- engines available to a user ------------------------------------------------------------------------
def _conn_dict(c: ProviderConnection) -> dict:
    return {"adapter": c.adapter, "base_url": c.base_url, "name": c.name, "model": c.model,
            "api_key": decrypt_json(c.secret).get("api_key", "") if c.secret else "", "extra": c.extra or {}}


def _provider_fn(conn: dict) -> Callable:
    def call(prompt, system="", max_tokens=2048):
        try:
            return P.chat(conn, prompt, system, max_tokens) or None
        except P.ProviderError as e:
            log.warning("Text provider %s failed: %s", conn["name"], e.message)
            return None
        except (KeyError, IndexError, ValueError, TypeError):
            return None
    return call


def engines(db: Session, user_id: Optional[int], agent: str, ref: str = "auto") -> list:
    """The chain an agent will try for this user, as (engine, label, callable)."""
    info = TASKS.get(agent, {"free": True})
    pref = db.scalar(select(AgentPref).where(AgentPref.user_id == user_id, AgentPref.agent == agent)) if user_id else None
    choice = ref if ref not in ("", "auto") else (pref.engine if pref else "auto")
    if choice == "rules":
        return []
    chain = []
    conn = None
    if choice.startswith("conn:") and choice[5:].isdigit():
        conn = db.get(ProviderConnection, int(choice[5:]))
        if not conn or conn.user_id != user_id or conn.kind != "text":
            conn = None
    elif choice != "builtin:gemini" and user_id:
        conn = db.scalar(select(ProviderConnection).where(ProviderConnection.user_id == user_id, ProviderConnection.kind == "text",
                                                          ProviderConnection.is_default.is_(True)))
    if conn:
        chain.append(("yours", f"{conn.name}{' · ' + conn.model if conn.model else ''}", _provider_fn(_conn_dict(conn))))
    own_gemini = integration_secret(db, user_id, "gemini").get("api_key") if user_id else ""
    if own_gemini:
        chain.append(("yours", "Your Gemini key", lambda p, s="", m=2048, k=own_gemini: llm(p, s, m, key=k)))
    if settings.gemini_api_key:
        chain.append(("platform", "AIMVA shared key", lambda p, s="", m=2048: llm(p, s, m, key=settings.gemini_api_key)))
    if info.get("free") and free_available():
        chain.append(("free", "AIMVA free AI (shared, limited)", free_chat))
    return chain


# ---- memory and run log ----------------------------------------------------------------------------------
def _key(user_id, agent, prompt, system, max_tokens) -> str:
    return hashlib.sha256(f"{user_id}|{agent}|{max_tokens}|{system}|{prompt}".encode()).hexdigest()


def _log(user_id, agent, engine, ok, ms):
    db = SessionLocal()
    try:
        db.add(AgentRun(user_id=user_id, agent=agent, engine=engine, ok=ok, ms=ms))
        db.commit()
    except Exception:  # logging must never break the work itself
        db.rollback()
    finally:
        db.close()


def recall(user_id, agent, key) -> Optional[str]:
    db = SessionLocal()
    try:
        m = db.get(AgentMemory, key)
        if not m or utcnow() - m.created_at > timedelta(days=MEMORY_DAYS):
            return None
        m.hits += 1
        db.commit()
        return m.answer
    finally:
        db.close()


def remember(user_id, agent, key, answer):
    db = SessionLocal()
    try:
        m = db.get(AgentMemory, key) or AgentMemory(key=key, user_id=user_id, agent=agent, answer="")
        m.answer, m.created_at = answer, utcnow()
        db.merge(m)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def note_rules(user_id: Optional[int], agent: str) -> None:
    """Record that an agent answered from its built-in rules (no AI was available or wanted)."""
    _log(user_id, agent, "rules", True, 0)


def agent_writer(db: Session, user_id: Optional[int], agent: str = "general", ref: str = "auto") -> Optional[Callable[..., Optional[str]]]:
    """A write(prompt, system="", max_tokens=...) for this agent, or None when it should use its built-in rules.
    The callable returns None if every engine is unavailable, and the caller then falls back to its rules."""
    chain = engines(db, user_id, agent, ref)
    if not chain:
        return None
    use_memory = TASKS.get(agent, {}).get("memory", True)

    def write(prompt: str, system: str = "", max_tokens: int = 2048) -> Optional[str]:
        k = _key(user_id, agent, prompt, system, max_tokens)
        if use_memory:
            hit = recall(user_id, agent, k)
            if hit:
                _log(user_id, agent, "memory", True, 0)
                return hit
        for engine, _, fn in chain:
            t = time.monotonic()
            out = fn(prompt, system, max_tokens)
            ms = int((time.monotonic() - t) * 1000)
            if out:
                _log(user_id, agent, engine, True, ms)
                if use_memory:
                    remember(user_id, agent, k, out)
                return out
            _log(user_id, agent, engine, False, ms)
        _log(user_id, agent, "rules", True, 0)
        return None
    return write
