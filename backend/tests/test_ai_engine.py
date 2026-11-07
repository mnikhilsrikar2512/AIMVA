"""AI engine: chain (yours → shared → free → rules), memory and the free-tier throttle."""
import pytest

from app import ai_engine as E
from app.config import settings
from app.routers.providers import writer

FREE = E.FREE_URL
OPENAI = "https://api.openai.com/v1/chat/completions"


@pytest.fixture(autouse=True)
def reset_free_gate():
    E.free_gate.next_ok = 0.0
    yield


def reply(text):
    return {"choices": [{"message": {"content": text}}]}


def uid():
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    i = db.query(User).filter_by(email="owner@example.com").one().id
    db.close()
    return i


def w(task, ref="auto"):
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        return writer(db, uid(), ref, agent=task)
    finally:
        db.close()


def runs(task):
    from app.db import SessionLocal
    from app.models import AgentRun
    db = SessionLocal()
    out = [(r.engine, r.ok) for r in db.query(AgentRun).filter_by(agent=task).order_by(AgentRun.id)]
    db.close()
    return out


def test_no_engines_means_rules(auth_client):
    assert w("copywriter") is None  # free AI is off in tests and no key is set


def test_free_ai_works_without_any_key(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "free_ai", True)
    route = mock_http.post(FREE).respond(json=reply("Fresh headline"))
    assert w("copywriter")("Write a headline") == "Fresh headline" and route.call_count == 1
    assert runs("copywriter") == [("free", True)]


def test_answers_are_remembered(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "free_ai", True)
    route = mock_http.post(FREE).respond(json=reply("Same answer"))
    assert w("analyst")("How did we do?") == "Same answer"
    E.free_gate.next_ok = 0.0
    assert w("analyst")("How did we do?") == "Same answer"
    assert route.call_count == 1 and runs("analyst") == [("free", True), ("memory", True)]


def test_free_tier_is_skipped_not_waited_for(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "free_ai", True)
    route = mock_http.post(FREE).respond(json=reply("ok"))
    assert w("prompt_artist")("idea one") == "ok"
    assert w("prompt_artist")("idea two") is None and route.call_count == 1
    E.free_gate.next_ok = 0.0
    mock_http.post(FREE).respond(402, text="Free limit reached", headers={"retry-after": "25"})
    assert w("prompt_artist")("idea three") is None and E.free_gate.next_ok > 0


def test_your_provider_first_then_fallback(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "free_ai", True)
    auth_client.post("/api/providers", json={"preset": "openai", "api_key": "k", "verify": False})
    mock_http.post(OPENAI).respond(json=reply("From your OpenAI"))
    assert w("page_writer")("Write a page") == "From your OpenAI"
    mock_http.post(OPENAI).respond(500, json={"error": {"message": "down"}})
    free = mock_http.post(FREE).respond(json=reply("From free AI"))
    assert w("page_writer")("Another page") == "From free AI" and free.call_count == 1
    assert runs("page_writer") == [("yours", True), ("yours", False), ("free", True)]


def test_shared_key_before_free(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "free_ai", True)
    monkeypatch.setattr(settings, "gemini_api_key", "server-key")
    mock_http.post(url__regex=r"https://generativelanguage\.googleapis\.com/.*").respond(json={"candidates": [{"content": {"parts": [{"text": "Shared"}]}}]})
    assert w("analyst")("Brief me") == "Shared" and runs("analyst") == [("platform", True)]


def test_live_calls_never_wait_on_free_ai(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "free_ai", True)
    assert w("call_assistant") is None


def test_page_builder_uses_free_ai_end_to_end(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "free_ai", True)
    page = '<html><head><meta name="viewport" content="width=device-width"></head><body><h1>Free AI page</h1><form data-aimva-lead><input name="phone"></form></body></html>'
    mock_http.post(FREE).respond(json=reply(page))
    s = auth_client.post("/api/sites", json={"business": "Acme", "offer": "Free trial"}).json()
    assert s["generator"] == "ai" and "Free AI page" in s["html"]
