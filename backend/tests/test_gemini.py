"""Per-user Google Gemini key: verification on connect, used by every AI feature, server key fallback."""
import json

import httpx
import pytest

from app.config import settings

GEMINI = "https://generativelanguage.googleapis.com/v1beta"


def gemini_reply(mock_http, text, model=None):
    url = f"{GEMINI}/models/{model or settings.gemini_model}:generateContent"
    return mock_http.post(url__startswith=url).respond(json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def connect(c, key="AIza-user-key"):
    r = c.post("/api/integrations/gemini/key", json={"values": {"api_key": key}})
    assert r.status_code == 200, r.text


@pytest.mark.real_verify
def test_gemini_key_verified_before_saving(auth_client, mock_http):
    mock_http.get(url__startswith=f"{GEMINI}/models").mock(side_effect=[
        httpx.Response(400, json={"error": {"message": "API key not valid"}}),
        httpx.Response(200, json={"models": [{"name": "models/gemini-2.5-flash"}]}),
    ])
    bad = auth_client.post("/api/integrations/gemini/key", json={"values": {"api_key": "nope"}})
    assert bad.status_code == 400 and "Gemini key" in bad.json()["detail"]
    connect(auth_client)
    row = next(i for i in auth_client.get("/api/integrations").json() if i["provider"] == "gemini")
    assert row["connected"] and "aistudio" in row["hints"]["api_key"]


def test_ai_status_reports_key_source(auth_client, monkeypatch):
    assert auth_client.get("/api/integrations/ai/status").json() == {"ai": False, "full": False, "free": False}
    monkeypatch.setattr(settings, "gemini_api_key", "server-key")
    assert auth_client.get("/api/integrations/ai/status").json() == {"ai": True, "full": True, "free": False}  # no supplier, model or key source
    connect(auth_client)
    assert auth_client.get("/api/integrations/ai/status").json()["full"] is True


def test_ad_copy_uses_the_users_own_key(auth_client, mock_http):
    route = gemini_reply(mock_http, "Headline: Live by the sea\nText: Book a visit today.\n\nHeadline: Sunset homes\nText: Ready to move in.")
    connect(auth_client)
    r = auth_client.post("/api/content/ad-copy", json={"product": "Skyline Homes"}).json()
    assert r["source"] == "ai" and r["variants"][0]["headline"] == "Live by the sea"
    assert route.calls[0].request.url.params["key"] == "AIza-user-key"


def test_server_key_used_when_user_has_none(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "server-key")
    route = gemini_reply(mock_http, "1. Do more\n2. Spend less\n3. Call hot leads")
    r = auth_client.get("/api/analytics/insights").json()
    assert r["source"] == "ai" and route.calls[0].request.url.params["key"] == "server-key"


def test_no_key_means_templates_and_no_network(auth_client, mock_http):
    route = mock_http.post(url__startswith=GEMINI).respond(json={})
    site = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": True, "offer": "Free trial"}).json()
    assert site["generator"] == "template" and not route.called


def test_ai_landing_page_with_user_key(auth_client, mock_http):
    html = '<!doctype html><html><body><h1>Acme by AI</h1><form data-aimva-lead><input name="phone"></form></body></html>'
    route = gemini_reply(mock_http, f"```html\n{html}\n```")
    connect(auth_client)
    site = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": True, "offer": "Free trial"}).json()
    assert site["generator"] == "ai" and "Acme by AI" in site["html"]
    assert f"/api/public/sites/{site['slug']}/lead" in site["html"]  # lead capture script still injected
    assert "```" not in site["html"]
    assert json.loads(route.calls[0].request.content)["generationConfig"]["maxOutputTokens"] == 8000


def test_voice_agent_uses_owner_key(auth_client, mock_http):
    route = gemini_reply(mock_http, "Lovely to meet you, Priya! What's the best number to reach you?")
    connect(auth_client)
    agent = auth_client.post("/api/voice/agents", json={"name": "Sales"}).json()
    cid = auth_client.post(f"/api/voice/agents/{agent['id']}/calls").json()["call"]["id"]
    r = auth_client.post(f"/api/voice/calls/{cid}/turn", json={"text": "I'm Priya"}).json()
    assert r["reply"].startswith("Lovely to meet you") and route.calls[0].request.url.params["key"] == "AIza-user-key"


def test_keys_are_per_user(auth_client, other_client, mock_http):
    route = gemini_reply(mock_http, "Headline: A\nText: B")
    connect(auth_client)
    r = other_client.post("/api/content/ad-copy", json={"product": "Other Co"}).json()
    assert r["source"] == "template" and not route.called  # the other user never borrows this key


def test_retired_model_falls_back_to_latest_alias(auth_client, mock_http):
    mock_http.post(url__startswith=f"{GEMINI}/models/{settings.gemini_model}:").respond(404, json={"error": "not found"})
    fallback = gemini_reply(mock_http, "Headline: Fresh\nText: Still works.", model="gemini-flash-latest")
    connect(auth_client)
    r = auth_client.post("/api/content/ad-copy", json={"product": "Acme"}).json()
    assert r["source"] == "ai" and fallback.called


def test_gemini_failure_falls_back_to_template(auth_client, mock_http):
    mock_http.post(url__startswith=GEMINI).mock(side_effect=httpx.ConnectError("down"))
    connect(auth_client)
    assert auth_client.post("/api/content/ad-copy", json={"product": "Acme"}).json()["source"] == "template"
