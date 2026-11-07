"""First-time-right quality layer: playbooks, brief review, import, page audit, ad sets, feedback, owner metrics."""
import io
import json
import socket

import pytest
from PIL import Image

from app.config import settings
from app.quality import audit_page, match_playbook, readiness, review_brief


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    def getaddrinfo(host, port, *a, **k):
        ip = {"localhost": "127.0.0.1", "intranet.example": "10.0.0.8"}.get(host, "93.184.216.34")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 443))]
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


def png(size=(640, 480), color=(40, 120, 200)):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "PNG")
    return b.getvalue()


# ---- playbooks & brief review ------------------------------------------------------------------------
@pytest.mark.parametrize("text,key", [("Real estate developer", "real_estate"), ("Dental clinic", "healthcare"),
                                      ("IIT-JEE coaching", "education"), ("B2B SaaS CRM", "saas"),
                                      ("Bakery & cafe", "restaurant"), ("", "other")])
def test_match_playbook(text, key):
    assert match_playbook(text) == key


def test_onboarding_industry_is_the_fallback():
    assert match_playbook("", "healthcare") == "healthcare"
    assert match_playbook("something unusual", "retail") == "retail"


def test_review_asks_the_questions_that_matter():
    thin = review_brief({"business": "Skyline Homes", "industry": "real estate"})
    assert thin["level"] == "thin" and thin["playbook"]["key"] == "real_estate"
    fields = [m["field"] for m in thin["missing"]]
    assert fields[:2] == ["offer", "address"] and "phone" not in fields  # voice agent calls back: no number needed
    own = review_brief({"business": "Skyline Homes", "industry": "real estate", "contact_mode": "own_phone"})
    assert [m["field"] for m in own["missing"]][:3] == ["offer", "phone", "address"]  # high-importance first
    full = review_brief({"business": "Skyline Homes", "industry": "real estate", "offer": "Free site visit",
                         "audience": "families", "phone": "+91 98765 43210", "features": ["Metro 5 min", "Clubhouse"],
                         "about": "Built by...", "hero_image": "ref:1", "address": "Whitefield, Bengaluru",
                         "pricing": [{"name": "2 BHK", "price": "₹45 L"}]})
    assert full["score"] >= 90 and full["level"] == "ready"


def test_review_endpoint_and_playbooks(auth_client):
    r = auth_client.post("/api/sites/review-brief", json={"business": "Smile Dental", "industry": "dental clinic"})
    assert r.status_code == 200 and r.json()["playbook"]["cta"] == "Book an appointment"
    pbs = auth_client.get("/api/sites/playbooks").json()
    assert {p["key"] for p in pbs} >= {"real_estate", "healthcare", "other"}


def test_template_never_invents_claims(auth_client):
    site = auth_client.post("/api/sites", json={"business": "Skyline Homes", "industry": "real estate", "use_ai": False,
                                                "offer": "Free site visit", "audience": "young families"}).json()
    assert "Trusted by" not in site["html"] and "Expert team" not in site["html"]
    assert "Site visits on your schedule" in site["html"]  # claim-free playbook fallback
    checks = {c["key"]: c for c in auth_client.get(f"/api/sites/{site['id']}/checks").json()}
    assert all(c["ok"] for c in checks.values() if c["level"] == "blocker")
    assert checks["claims"]["ok"] and checks["mobile"]["ok"]


def test_ai_gets_playbook_rules(auth_client, mock_http):
    auth_client.post("/api/providers", json={"preset": "openai", "api_key": "k", "verify": False})
    page = ('<html><head><meta name="viewport" content="width=device-width"></head><body><h1>Hi</h1>'
            '<form data-aimva-lead><input name="phone"></form></body></html>')
    route = mock_http.post("https://api.openai.com/v1/chat/completions").respond(json={"choices": [{"message": {"content": page}}]})
    auth_client.post("/api/sites", json={"business": "Smile", "industry": "dental clinic", "offer": "First check-up"})
    prompt = json.loads(route.calls.last.request.content)["messages"][-1]["content"]
    assert "Clinic / healthcare" in prompt and "placeholder" in prompt


# ---- audit -----------------------------------------------------------------------------------------
GOOD_HEAD = '<head><title>T</title><meta name="description" content="d"><meta name="viewport" content="width=device-width"></head>'


def test_audit_blocks_placeholders_and_flags_invented_numbers():
    html = (f"<html>{GOOD_HEAD}<body><h1>Welcome to [Your Company]</h1><p>500+ happy clients since 1998. Rated 4.9 stars.</p>"
            "<p>Best in the city, guaranteed results!</p><blockquote>Great!</blockquote>"
            '<form data-aimva-lead><input name="phone"></form><a href="#">x</a><img src="a.jpg"></body></html>')
    c = {x["key"]: x for x in audit_page(html, {"business": "Acme", "offer": "Free trial"})}
    assert not c["placeholders"]["ok"] and c["placeholders"]["level"] == "blocker" and "[Your Company]" in c["placeholders"]["detail"]
    assert not c["claims"]["ok"] and "500+" in c["claims"]["detail"]
    assert not c["risky"]["ok"] and not c["testimonials"]["ok"]
    assert not c["links"]["ok"] and not c["alt"]["ok"]
    assert readiness(list(c.values()))["status"] == "blocked"


def test_audit_accepts_numbers_the_user_gave():
    html = (f"<html>{GOOD_HEAD}<body><h1>Acme</h1><p>Serving 500+ families since 1998.</p>"
            '<form data-aimva-lead><input name="phone"></form><p>+91 98765 43210</p></body></html>')
    c = {x["key"]: x for x in audit_page(html, {"business": "Acme", "about": "500+ families since 1998", "phone": "+91 98765 43210"})}
    assert c["claims"]["ok"] and c["phone"]["ok"]
    assert readiness(list(c.values()))["status"] == "ready"


def test_publish_blocked_by_placeholders(auth_client):
    s = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False}).json()
    html = s["html"].replace("<h1>", "<h1>Call 555-1234 ")
    auth_client.patch(f"/api/sites/{s['id']}", json={"html": html})
    r = auth_client.post(f"/api/sites/{s['id']}/publish", json={"name": "Acme", "slug": "acme-x"})
    assert r.status_code == 400 and "555-1234" in r.json()["detail"]
    a = auth_client.get(f"/api/sites/{s['id']}/audit").json()
    assert a["readiness"]["status"] == "blocked" and a["readiness"]["blockers"] == 1


def test_publish_records_time(auth_client):
    s = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False}).json()
    out = auth_client.post(f"/api/sites/{s['id']}/publish", json={"name": "Acme", "slug": "acme-t"}).json()
    assert out["published_at"]


# ---- import ------------------------------------------------------------------------------------------
SITE = """<html><head><title>Skyline Homes | Luxury flats in Whitefield</title>
<meta name="description" content="2 and 3 BHK homes near the metro.">
<meta property="og:image" content="/img/hero.jpg"><meta name="theme-color" content="#0F766E">
<script type="application/ld+json">{"@type":"RealEstateAgent","telephone":"+91 80 1234 5678",
"address":{"streetAddress":"12 ITPL Road","addressLocality":"Bengaluru"}}</script></head>
<body><h1>Homes you'll love</h1><a href="tel:+91 98765 43210">Call</a><a href="https://wa.me/919876543210">WA</a>
<a href="mailto:hello@skyline.example">Mail</a></body></html>"""


def test_import_reads_business_details(auth_client, mock_http):
    mock_http.get("https://skyline.example/").respond(200, text=SITE)
    r = auth_client.post("/api/sites/import", json={"url": "skyline.example/"})
    assert r.status_code == 200, r.text
    b = r.json()["brief"]
    assert b["business"] == "Skyline Homes" and b["phone"] == "+91 98765 43210" and b["whatsapp"] == "+919876543210"
    assert b["contact_email"] == "hello@skyline.example" and b["primary"] == "#0f766e"
    assert b["hero_image"] == "https://skyline.example/img/hero.jpg" and b["address"] == "12 ITPL Road, Bengaluru"
    assert b["headline"] == "Homes you'll love" and r.json()["source"] == "basic"


def test_import_uses_ai_but_keeps_exact_contacts(auth_client, mock_http):
    auth_client.post("/api/providers", json={"preset": "openai", "api_key": "k", "verify": False})
    mock_http.get("https://skyline.example/").respond(200, text=SITE)
    ai = {"offer": "Free site visit", "features": ["Near metro", "Clubhouse"], "phone": "000", "faqs": [{"q": "Possession?", "a": "Dec 2027"}]}
    mock_http.post("https://api.openai.com/v1/chat/completions").respond(json={"choices": [{"message": {"content": json.dumps(ai)}}]})
    b = auth_client.post("/api/sites/import", json={"url": "https://skyline.example/"}).json()["brief"]
    assert b["offer"] == "Free site visit" and b["features"] == ["Near metro", "Clubhouse"] and b["phone"] == "+91 98765 43210"
    assert b["faqs"][0]["a"] == "Dec 2027"


def test_import_rejects_internal_and_non_html(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "allow_private_providers", False)
    assert auth_client.post("/api/sites/import", json={"url": "https://intranet.example/"}).status_code == 400
    mock_http.get("https://files.example/x").respond(200, text="just text")
    r = auth_client.post("/api/sites/import", json={"url": "https://files.example/x"})
    assert r.status_code == 400 and "web page" in r.json()["detail"]


# ---- images ------------------------------------------------------------------------------------------
def _image(auth_client):
    ref = auth_client.post("/api/references", files={"file": ("p.png", png(), "image/png")}).json()
    from app.db import SessionLocal
    from app.models import Asset, User
    db = SessionLocal()
    u = db.query(User).filter_by(email="owner@example.com").one()
    a = Asset(user_id=u.id, kind="image", prompt="flat", model="m", url=ref["url"], params={})
    db.add(a)
    db.commit()
    aid = a.id
    db.close()
    return aid


def test_enhance_prompt_without_ai(auth_client):
    r = auth_client.post("/api/content/enhance", json={"prompt": "skincare bottle on stone", "kind": "image"}).json()
    assert r["source"] == "rules" and r["prompt"].startswith("skincare bottle on stone") and "no text" in r["prompt"]
    assert "watermark" in r["negative_prompt"]
    v = auth_client.post("/api/content/enhance", json={"prompt": "drone over villas", "kind": "video"}).json()
    assert "camera" in v["prompt"]


def test_enhance_prompt_with_ai(auth_client, mock_http):
    auth_client.post("/api/providers", json={"preset": "openai", "api_key": "k", "verify": False})
    mock_http.post("https://api.openai.com/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": '"A frosted glass serum bottle on wet grey stone, soft window light"'}}]})
    r = auth_client.post("/api/content/enhance", json={"prompt": "skincare bottle on stone"}).json()
    assert r["source"] == "ai" and r["prompt"].startswith("A frosted glass")


def test_adset_makes_every_size_with_real_text(auth_client, other_client):
    aid = _image(auth_client)
    r = auth_client.post(f"/api/content/image/{aid}/adset", json={"sizes": ["1:1", "9:16", "1.91:1"], "headline": "From ₹45 L",
                                                                   "cta": "Book a visit"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert [(a["params"]["width"], a["params"]["height"]) for a in out] == [(1080, 1080), (1080, 1920), (1200, 628)]
    assert all(a["params"]["parent"] == aid for a in out)
    img = Image.open(io.BytesIO(auth_client.get(out[1]["url"]).content))
    assert img.size == (1080, 1920)
    assert other_client.post(f"/api/content/image/{aid}/adset", json={"sizes": ["1:1"]}).status_code == 404
    assert auth_client.post(f"/api/content/image/{aid}/adset", json={"sizes": []}).status_code == 422


# ---- feedback & owner metrics ------------------------------------------------------------------------
def test_feedback_upserts_and_is_private(auth_client, other_client):
    s = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False}).json()
    assert auth_client.post("/api/feedback", json={"kind": "site", "id": s["id"], "rating": -1, "reason": "too_generic"}).status_code == 200
    auth_client.post("/api/feedback", json={"kind": "site", "id": s["id"], "rating": 1, "reason": "too_generic"})
    assert auth_client.get("/api/feedback?kind=site").json() == {str(s["id"]): {"rating": 1, "reason": ""}}
    assert other_client.post("/api/feedback", json={"kind": "site", "id": s["id"], "rating": 1}).status_code == 404


def test_owner_metrics(auth_client, other_client, monkeypatch):
    assert auth_client.get("/api/admin/metrics").status_code == 403
    monkeypatch.setattr(settings, "admin_emails", {"owner@example.com"})
    assert auth_client.get("/api/auth/me").json()["user"]["is_admin"] is True
    a = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False}).json()
    auth_client.post(f"/api/sites/{a['id']}/publish", json={"name": "Acme", "slug": "acme-m"})
    b = other_client.post("/api/sites", json={"business": "Beta", "use_ai": False}).json()
    other_client.patch(f"/api/sites/{b['id']}", json={"html": b["html"] + "<!-- edit -->"})
    other_client.post(f"/api/sites/{b['id']}/publish", json={"name": "Beta", "slug": "beta-m"})
    other_client.post("/api/feedback", json={"kind": "site", "id": b["id"], "rating": -1, "reason": "wrong_facts", "note": "price"})
    m = auth_client.get("/api/admin/metrics?days=7").json()
    assert m["users"]["total"] == 2 and m["websites"]["published"] == 2
    assert m["websites"]["first_time_right"] == 50 and m["websites"]["manual_edits"] == 1
    assert m["feedback"]["reasons"] == [{"reason": "Wrong or invented facts", "count": 1}]
    assert other_client.get("/api/admin/metrics").status_code == 403


# ---- layouts, designs, visual edits, call backs ---------------------------------------------------------
BASE = {"business": "Smile Dental", "industry": "dental clinic", "offer": "First check-up", "use_ai": False,
        "features": ["Same-week appointments", "Kids welcome"]}


@pytest.mark.parametrize("layout", ["showcase", "split", "centered", "immersive", "editorial", "bento"])
def test_every_layout_renders_a_working_page(auth_client, layout):
    s = auth_client.post("/api/sites", json={**BASE, "layout": layout}).json()
    assert f'aimva:layout" content="{layout}"' in s["html"] and s["brief"]["layout"] == layout
    c = {x["key"]: x for x in auth_client.get(f"/api/sites/{s['id']}/checks").json()}
    assert all(x["ok"] for x in c.values() if x["level"] == "blocker")


def test_auto_layout_gives_each_new_page_a_different_design(auth_client):
    layouts = [auth_client.post("/api/sites", json=BASE).json()["brief"]["layout"] for _ in range(5)]
    assert len(set(layouts)) == 5  # five pages, five structures
    assert auth_client.post("/api/sites", json=BASE).json()["brief"]["decor"] in ("blobs", "grid", "dots", "plain")


def test_directions_are_three_distinct_designs(auth_client):
    d = auth_client.post("/api/sites/directions", json=BASE).json()
    assert len(d) == 3 and len({x["layout"] for x in d}) == 3 and len({x["decor"] for x in d}) == 3
    assert all("<form data-aimva-lead" in x["html"] for x in d)
    assert auth_client.get("/api/sites").json() == []  # previews aren't saved


def test_ai_follows_the_chosen_layout(auth_client, mock_http):
    auth_client.post("/api/providers", json={"preset": "openai", "api_key": "k", "verify": False})
    page = '<html><body><h1>Hi</h1><form data-aimva-lead><input name="phone"></form></body></html>'
    route = mock_http.post("https://api.openai.com/v1/chat/completions").respond(json={"choices": [{"message": {"content": page}}]})
    auth_client.post("/api/sites", json={**BASE, "use_ai": True, "layout": "editorial"})
    prompt = json.loads(route.calls.last.request.content)["messages"][-1]["content"]
    assert "Magazine style" in prompt and "Do not show any business phone number" in prompt and 'name=\"callback\"' in prompt


def test_visual_edit_and_embed(auth_client, other_client):
    s = auth_client.post("/api/sites", json=BASE).json()
    out = auth_client.patch(f"/api/sites/{s['id']}", json={"html": s["html"].replace("First check-up", "Free first check-up"),
                                                           "note": "Edited visually"}).json()
    assert "Free first check-up" in out["html"]
    assert auth_client.get(f"/api/sites/{s['id']}/versions").json()[0]["note"] == "Edited visually"
    assert auth_client.patch(f"/api/sites/{s['id']}", json={"html": "x", "note": "Hacked"}).status_code == 422
    ref = auth_client.post("/api/references", files={"file": ("p.png", png(), "image/png")}).json()
    src = auth_client.post("/api/sites/embed-image", json={"ref": ref["ref"]}).json()["src"]
    assert src.startswith("data:image/")
    assert other_client.post("/api/sites/embed-image", json={"ref": ref["ref"]}).status_code == 404
    assert auth_client.post("/api/sites/embed-image", json={"ref": "javascript:alert(1)"}).status_code == 422


def test_voice_agent_mode_hides_business_number(auth_client):
    s = auth_client.post("/api/sites", json={**BASE, "phone": "+91 80 1111 2222", "form_fields": ["name", "email"]}).json()
    assert "80 1111 2222" not in s["html"] and "Request a call back" in s["html"] and 'name="callback"' in s["html"]
    assert 'name="phone"' in s["html"]  # visitor's number is added so the agent can call
    own = auth_client.post("/api/sites", json={**BASE, "contact_mode": "own_phone", "phone": "+91 80 1111 2222"}).json()
    assert "tel:+91 80 1111 2222" in own["html"] and 'name="callback"' not in own["html"]
    r = auth_client.post("/api/sites", json={**BASE, "contact_mode": "own_phone"})
    assert r.status_code == 422 and "voice agent" in r.text


def test_call_back_request_logs_and_dials(auth_client, client, mock_http, monkeypatch):
    from app.routers import sites as S
    calls = []
    monkeypatch.setattr(S, "_dial_back", lambda *a: calls.append(a))
    s = auth_client.post("/api/sites", json=BASE).json()
    auth_client.post(f"/api/sites/{s['id']}/publish", json={"name": "Smile", "slug": "smile-cb"})
    r = client.post("/api/public/sites/smile-cb/lead", data={"name": "Asha", "phone": "098765 43210", "callback": "yes"})
    assert r.json()["ok"] and calls and calls[0][2] == "+919876543210"
    client.post("/api/public/sites/smile-cb/lead", data={"name": "Asha", "phone": "098765 43210", "callback": "yes"})
    assert len(calls) == 1  # one call per number per 15 minutes
    lead = auth_client.get("/api/leads").json()[0]
    titles = [x.get("title") for x in auth_client.get(f"/api/leads/{lead['id']}").json()["timeline"]]
    assert "Asked for a call back" in titles


def test_dial_back_without_twilio_leaves_a_clear_note(auth_client, client):
    from app.routers import sites as S
    from app.db import SessionLocal
    from app.models import Lead, LeadEvent, User
    s = auth_client.post("/api/sites", json=BASE).json()
    auth_client.post(f"/api/sites/{s['id']}/publish", json={"name": "Smile", "slug": "smile-nt"})
    db = SessionLocal()
    u = db.query(User).filter_by(email="owner@example.com").one()
    lead = Lead(user_id=u.id, name="Ravi", phone="+919876543210", email="")
    db.add(lead)
    db.commit()
    S._dial_back(u.id, lead.id, "+919876543210", None)
    notes = [e.body for e in db.query(LeadEvent).filter_by(lead_id=lead.id)]
    db.close()
    assert any("Twilio" in n or "voice agent" in n for n in notes)
