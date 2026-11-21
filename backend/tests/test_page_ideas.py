"""Ideas to make a page better are written for this business and this page, never one list for everyone."""
import httpx

from app import page_ideas
from app.config import settings

GEMINI = "https://generativelanguage.googleapis.com/v1beta"
DENTAL = {"business": "Smile Studio", "industry": "dental clinic", "offer": "Free check-up this Saturday", "use_ai": False,
          "phone": "+91 9876543210"}
HOMES = {"business": "Skyline Homes", "industry": "real estate", "offer": "2 and 3 BHK near the metro", "use_ai": False,
         "phone": "+91 9876543210"}


def test_ideas_differ_by_business(auth_client):
    a = auth_client.post("/api/sites", json=DENTAL).json()
    b = auth_client.post("/api/sites", json=HOMES).json()
    ia = [i["text"] for i in auth_client.get(f"/api/sites/{a['id']}/ideas").json()["ideas"]]
    ib = [i["text"] for i in auth_client.get(f"/api/sites/{b['id']}/ideas").json()["ideas"]]
    assert ia and ib and set(ia) != set(ib)
    assert any("Smile Studio" in t or "patients" in t or "clinic" in t for t in ia), ia
    assert any("2 and 3 BHK" in t or "site visit" in t or "buyers" in t for t in ib), ib


def test_fixes_use_the_page_own_button_and_come_first():
    page = "<html><body><h1>Hello</h1><form data-aimva-lead></form></body></html>"
    todo = [{"key": "cta_twice"}, {"key": "offer_top"}]
    r = page_ideas.ideas(page, {"business": "Acme Gym", "offer": "First week free", "cta": "Book a free trial"}, {}, todo)
    assert r["ideas"][0]["raises_score"] and "Book a free trial" in r["ideas"][0]["text"]
    assert any("First week free" in i["text"] for i in r["ideas"])


def test_skips_what_the_page_already_has_and_never_asks_for_reviews():
    f = page_ideas.facts({"business": "Acme", "offer": "Plumbing repairs"}, {"area": "Baner"})
    has = "<html><body><h2>How it works</h2><p>Step 1</p><a href='https://wa.me/1'>WhatsApp</a></body></html>"
    out = page_ideas.rule_ideas(has, f, "plumbing services")
    assert not any("how it works" in i.lower() for i in out) and not any("WhatsApp" in i for i in out)
    assert any("Baner" in i for i in out)
    assert not any(page_ideas.BANNED.search(i) for i in out)


def test_writer_ideas_are_used_and_filtered(auth_client, mock_http):
    auth_client.post("/api/integrations/gemini/key", json={"values": {"api_key": "AIza-k"}})
    s = auth_client.post("/api/sites", json=DENTAL).json()
    text = '["Add a short section on what a Saturday check-up includes", "Add 500+ happy patients badge", "Add 5-star reviews"]'
    mock_http.post(url__startswith=f"{GEMINI}/models/{settings.gemini_model}:generateContent").mock(
        return_value=httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]}))
    r = auth_client.get(f"/api/sites/{s['id']}/ideas").json()
    texts = [i["text"] for i in r["ideas"]]
    assert r["source"] == "ai" and "Add a short section on what a Saturday check-up includes" in texts
    assert not any("5-star" in t or "happy patients" in t for t in texts), texts


def test_quick_ideas_never_call_the_writer(auth_client, mock_http):
    auth_client.post("/api/integrations/gemini/key", json={"values": {"api_key": "AIza-k"}})
    s = auth_client.post("/api/sites", json=HOMES).json()
    route = mock_http.post(url__startswith=f"{GEMINI}/models/{settings.gemini_model}:generateContent")
    r = auth_client.get(f"/api/sites/{s['id']}/ideas?quick=true").json()
    assert r["source"] == "rules" and r["ideas"] and route.call_count == 0


def test_writer_cannot_invent_offers():
    def write(prompt, max_tokens=0):
        return '["Add a strict zero-joining-fee limited offer banner", "Add 20% off for new members", "Add a weekly class timetable"]'
    out = page_ideas.ai_ideas(write, "<p>Acme Gym</p>", page_ideas.facts({"business": "Acme Gym"}, {}), [])
    assert out == ["Add a weekly class timetable"]
