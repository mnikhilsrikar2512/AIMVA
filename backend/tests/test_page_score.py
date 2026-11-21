"""Page score: every new page is marked against one checklist, and low marks get fixed before the owner sees it."""
import json

from app import page_score
from app.config import settings

GEMINI = "https://generativelanguage.googleapis.com/v1beta"
BRIEF = {"business": "Skyline Homes", "offer": "2 and 3 BHK near the metro", "use_ai": False, "phone": "+91 9876543210"}

WEAK = ('<!doctype html><html><head><title>x</title></head><body><h1>Welcome to our wonderful website where everything '
        'is wonderful and good for everyone always</h1><p>Lorem.</p><form data-aimva-lead><input name="phone">'
        '</form></body></html>')
STRONG = ('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Acme</title>'
          '<meta name="description" content="Free trial at Acme"></head><body><h1>Acme: free trial this week</h1>'
          '<a href="#contact" class="btn">Get a free quote</a><p>Acme gyms in Pune.</p>'
          '<form data-aimva-lead id="contact"><label>Phone <input name="phone"></label><button>Get a free quote</button></form>'
          '</body></html>')


def gemini(mock_http, *texts):
    url = f"{GEMINI}/models/{settings.gemini_model}:generateContent"
    return mock_http.post(url__startswith=url).mock(side_effect=[
        __import__("httpx").Response(200, json={"candidates": [{"content": {"parts": [{"text": t}]}}]}) for t in texts])


def connect(c):
    assert c.post("/api/integrations/gemini/key", json={"values": {"api_key": "AIza-k"}}).status_code == 200


def test_template_page_passes_and_reports_six_parts(auth_client):
    s = auth_client.post("/api/sites", json=BRIEF).json()
    ps = s["page_score"]
    assert [p["key"] for p in ps["parts"]] == list(page_score.PARTS)
    assert ps["passes"] and ps["average"] >= 8, ps
    audit = auth_client.get(f"/api/sites/{s['id']}/audit").json()["page_score"]
    assert audit["parts"] and audit["average"] >= 8


def test_brand_book_words_and_name_count(auth_client):
    s = auth_client.post("/api/sites", json=BRIEF).json()
    before = next(p["score"] for p in s["page_score"]["parts"] if p["key"] == "brand")
    auth_client.put("/api/brand/book", json={"never_say": "metro"})
    after = auth_client.get(f"/api/sites/{s['id']}/audit").json()["page_score"]
    brand = next(p["score"] for p in after["parts"] if p["key"] == "brand")
    assert brand < before and any("metro" in t["detail"] for t in after["todo"])


def test_weak_page_scores_low_with_plain_todos():
    r = page_score.score(WEAK, {"business": "Acme", "offer": "Free trial", "cta": "Get a free quote"})
    assert not r["passes"]
    keys = {t["key"] for t in r["todo"]}
    assert {"offer_top", "cta_top", "name"} <= keys
    notes = page_score.notes_for_writer(r)
    assert "Free trial" in notes and "Lorem" not in notes


def test_ai_page_rewritten_once_when_it_scores_low(auth_client, mock_http):
    route = gemini(mock_http, WEAK, STRONG)
    connect(auth_client)
    s = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": True, "offer": "Free trial"}).json()
    assert s["generator"] == "ai" and route.call_count == 2
    assert "Acme: free trial this week" in s["html"] and f"/api/public/sites/{s['slug']}/lead" in s["html"]
    assert "problems" in json.loads(route.calls[1].request.content)["contents"][0]["parts"][0]["text"]
    assert any("Rewrote" in f for f in s["auto_fixed"])


def test_rewrite_that_drops_the_form_or_scores_lower_is_ignored(auth_client, mock_http):
    no_form = STRONG.replace("data-aimva-lead", "")
    route = gemini(mock_http, WEAK, no_form)
    connect(auth_client)
    s = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": True, "offer": "Free trial"}).json()
    assert route.call_count == 2 and "Welcome to our wonderful website" in s["html"]
    assert not any("Rewrote" in f for f in s["auto_fixed"])


def test_no_rewrite_when_page_fixer_is_off(auth_client, mock_http):
    route = gemini(mock_http, WEAK, STRONG)
    connect(auth_client)
    auth_client.put("/api/agents/page_fixer", json={"enabled": False})
    s = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": True, "offer": "Free trial"}).json()
    assert route.call_count == 1 and s["auto_fixed"] == [] and s["page_score"]["passes"] is False


def test_rewrite_rounds_stop_at_three():
    calls = []

    def rewrite(html, notes):
        calls.append(notes)
        return html.replace("<p>", "<p>Acme ", 1)  # a tiny gain every time, never a pass
    page_score.improve(WEAK, {"business": "Acme", "offer": "Free trial"}, rewrite=rewrite)
    assert len(calls) <= page_score.ROUNDS
