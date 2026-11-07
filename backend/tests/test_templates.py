"""Templates for every module, usage learning, and the template review agent (user + platform)."""
import json

import pytest

from app.config import settings
from app.templates_catalog import CATALOG, MODULES, validate_payload
from .conftest import make_client, signup_and_verify


def profile(c, company="Skyline Homes", industry="real_estate"):
    assert c.post("/api/onboarding/profile", json={"company": company, "industry": industry, "goal": "more_leads"}).status_code == 200


def use(c, ref, module, applied, final):
    r = c.post("/api/templates/use", json={"ref": ref, "module": module, "applied": applied, "final": final})
    assert r.status_code == 200, r.text
    return r.json()


def test_catalogue_covers_every_module_and_validates():
    assert {t["module"] for t in CATALOG} == set(MODULES)
    for t in CATALOG:
        assert validate_payload(t["module"], t["payload"]) == t["payload"]


@pytest.mark.parametrize("module", MODULES)
def test_every_module_lists_templates(auth_client, module):
    r = auth_client.get(f"/api/templates?module={module}").json()
    assert r["module"] == module and len(r["templates"]) >= 6
    assert all(t["source"] == "builtin" and t["ref"].startswith("b:") for t in r["templates"])


def test_templates_are_personalised_and_ranked(auth_client):
    profile(auth_client)
    ts = auth_client.get("/api/templates?module=ads").json()["templates"]
    assert ts[0]["recommended"] and "real_estate" in ts[0]["industries"]
    assert any("Skyline Homes" in t["payload"]["creative"]["text"] for t in ts)  # {business} filled in
    wa = auth_client.get("/api/templates?module=whatsapp").json()["templates"]
    assert all("{name}" in t["payload"]["body"] for t in wa if "{name}" in json.dumps(t["payload"]))  # recipient placeholder kept


def test_save_edit_delete_own_template(auth_client, other_client):
    t = auth_client.post("/api/templates", json={"module": "image", "name": "My hero", "payload": {"prompt": "sunlit villa with pool", "size": "16:9"}}).json()
    assert t["source"] == "mine" and t["payload"]["style"] == ""
    assert any(x["ref"] == t["ref"] for x in auth_client.get("/api/templates?module=image").json()["templates"])
    assert not any(x["ref"] == t["ref"] for x in other_client.get("/api/templates?module=image").json()["templates"])
    assert other_client.patch(f"/api/templates/{t['id']}", json={"name": "Hacked"}).status_code == 404
    assert auth_client.patch(f"/api/templates/{t['id']}", json={"payload": {"prompt": "dusk villa", "size": "4:5"}}).json()["payload"]["size"] == "4:5"
    assert auth_client.delete(f"/api/templates/{t['id']}").json()["ok"]


@pytest.mark.parametrize("module,payload,msg", [
    ("website", {"cta": "Go", "form_fields": ["name", "city"]}, "phone or email"),
    ("voice", {"greeting": "Hello there", "questions": ["Only one?"]}, "two questions"),
    ("image", {"prompt": "x", "size": "3:2"}, ""),
    ("ads", {"creative": {"cta": "x" * 40}}, ""),
])
def test_invalid_templates_are_refused(auth_client, module, payload, msg):
    r = auth_client.post("/api/templates", json={"module": module, "name": "Bad", "payload": payload})
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_use_records_what_was_changed(auth_client, other_client):
    applied = auth_client.get("/api/templates?module=ads").json()["templates"][0]
    final = json.loads(json.dumps(applied["payload"]))
    final["creative"]["cta"] = "Call me"
    final["daily_budget"] = 999
    out = use(auth_client, applied["ref"], "ads", applied["payload"], final)
    assert out["changed"] == ["creative.cta", "daily_budget"]
    mine = auth_client.post("/api/templates", json={"module": "image", "name": "Private", "payload": {"prompt": "secret prompt"}}).json()
    r = other_client.post("/api/templates/use", json={"ref": mine["ref"], "module": "image"})
    assert r.status_code == 404  # can't log use of someone else's template


def test_agent_learns_habitual_edits(auth_client):
    profile(auth_client)
    t = next(x for x in auth_client.get("/api/templates?module=website").json()["templates"] if x["ref"] == "b:web-site-visit")
    for _ in range(3):
        use(auth_client, t["ref"], "website", t["payload"], {**t["payload"], "cta": "Schedule my visit"})
    r = auth_client.post("/api/templates/suggest", json={"module": "website"}).json()
    s = next(x for x in r["new"] if "your version" in x["name"])
    assert s["payload"]["cta"] == "Schedule my visit" and "3 of 3" in s["reason"] and s["source"] == "suggested"
    # accepting makes it the user's own; dismissed suggestions never come back
    acc = auth_client.post(f"/api/templates/{s['id']}/accept").json()
    assert acc["source"] == "mine"
    assert not any("your version" in x["name"] for x in auth_client.post("/api/templates/suggest", json={"module": "website"}).json()["new"])


def test_agent_turns_best_campaign_into_a_template(auth_client):
    from app.db import SessionLocal
    from app.models import Lead, User
    profile(auth_client)
    c = auth_client.post("/api/campaigns", json={"platform": "meta", "name": "Reels winter", "daily_budget": 900,
                                                "creative": {"headline": "Homes near the metro", "text": "Skyline Homes, 2 & 3 BHK", "cta": "Book now"},
                                                "lead_form": {"fields": ["full_name", "phone_number"]}}).json()
    auth_client.post(f"/api/campaigns/{c['id']}/results", json={"spend": 3000, "impressions": 9000, "clicks": 300})
    db = SessionLocal()
    uid = db.query(User).filter_by(email="owner@example.com").one().id
    for i in range(4):
        db.add(Lead(user_id=uid, name=f"L{i}", email=f"l{i}@x.com", campaign_id=c["id"], source="meta"))
    db.commit()
    db.close()
    new = auth_client.post("/api/templates/suggest", json={"module": "ads"}).json()["new"]
    best = next(x for x in new if x["name"].startswith("Best performer"))
    assert "₹750 per lead from 4 leads" in best["reason"] and best["payload"]["creative"]["headline"] == "Homes near the metro"


def test_ai_drafts_are_validated(auth_client, mock_http):
    profile(auth_client)
    auth_client.post("/api/providers", json={"preset": "openai", "api_key": "k", "verify": False})
    drafts = [{"name": "Rooftop dusk", "description": "d", "reason": "new angle", "payload": {"prompt": "Rooftop terrace at dusk with city lights", "size": "4:5"}},
              {"name": "Broken", "payload": {"prompt": "x", "size": "7:7"}}]
    mock_http.post("https://api.openai.com/v1/chat/completions").respond(json={"choices": [{"message": {"content": json.dumps(drafts)}}]})
    new = auth_client.post("/api/templates/suggest", json={"module": "image"}).json()["new"]
    names = [x["name"] for x in new]
    assert "Rooftop dusk" in names and "Broken" not in names
    assert next(x for x in new if x["name"] == "Rooftop dusk")["reason"].startswith("AI idea")


def test_platform_review_publishes_for_everyone(auth_client, other_client, monkeypatch):
    third = make_client()
    signup_and_verify(third, email="third@example.com", name="Third")
    clients = [auth_client, other_client, third]
    for i, c in enumerate(clients):
        profile(c, company=f"Biz {i}")
    base = next(x for x in CATALOG if x["key"] == "wa-follow-up")
    for c in clients:
        use(c, "b:wa-follow-up", "whatsapp", base["payload"], {"body": "Hi {name}, any questions about your enquiry? Reply here and we'll call you."})
    assert auth_client.get("/api/admin/templates").status_code == 403
    monkeypatch.setattr(settings, "admin_emails", {"owner@example.com"})
    insights = auth_client.get("/api/admin/templates").json()
    row = next(u for u in insights["usage"] if u["ref"] == "b:wa-follow-up")
    assert row["uses"] == 3 and row["users"] == 3 and row["most_edited"][0] == {"field": "body", "label": "message", "rate": 100}
    r = auth_client.post("/api/admin/templates/review").json()
    revised = next(p for p in r["pending"] if p["based_on"] == "b:wa-follow-up")
    assert "3 of 3 uses change the message" in revised["reason"]
    assert auth_client.post(f"/api/admin/templates/{revised['id']}/publish").json()["ok"]
    seen = other_client.get("/api/templates?module=whatsapp").json()["templates"]
    assert any(t["source"] == "platform" and t["name"].endswith("(revised)") for t in seen)
    assert other_client.post(f"/api/admin/templates/{revised['id']}/dismiss").status_code == 403


def test_shared_custom_templates_are_anonymised(auth_client, other_client, monkeypatch):
    profile(auth_client, company="Alpha Dental")
    profile(other_client, company="Beta Dental")
    for c, name in ((auth_client, "Alpha Dental"), (other_client, "Beta Dental")):
        c.post("/api/templates", json={"module": "whatsapp", "name": "Cleaning reminder",
                                       "payload": {"body": f"Hi {{name}}, it's time for your cleaning at {name}. Reply to book."}})
    monkeypatch.setattr(settings, "admin_emails", {"owner@example.com"})
    pending = auth_client.post("/api/admin/templates/review").json()["pending"]
    shared = next(p for p in pending if p["name"] == "Cleaning reminder")
    assert "{business}" in shared["payload"]["body"] and "Dental" not in shared["payload"]["body"]
    assert "2 businesses" in shared["reason"]
