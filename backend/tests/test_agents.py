"""Work agents: Launch Agent, Lead Concierge, Campaign Autopilot, Weekly Report, Page Fixer and the scheduler."""
import json
import socket
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.agents import concierge, scheduler
from app.models import AgentSetting, FollowUp, Lead, User, WaMessage

from .helpers import connect


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    def getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 443))]
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


def profile(c, company="Skyline Homes", industry="real_estate"):
    assert c.post("/api/onboarding/profile", json={"company": company, "industry": industry, "goal": "more_leads"}).status_code == 200


def lead_form(client, slug, **data):
    return client.post(f"/api/public/sites/{slug}/lead", data={"name": "Ravi Kumar", "phone": "+919812345678", **data}).json()


def publish(c, **brief):
    s = c.post("/api/sites", json={"business": "Skyline Homes", "offer": "2 & 3 BHK near the metro", "use_ai": False, **brief}).json()
    c.post(f"/api/sites/{s['id']}/deploy", json={"target": "aimva"})
    return s


# ---- Launch Agent -----------------------------------------------------------------------------------------
def test_launch_from_one_line_builds_everything_as_drafts(auth_client):
    profile(auth_client)
    j = auth_client.post("/api/agents/launch", json={"description": "3 BHK flats in Kokapet from ₹1.2 Cr, ready by 2027",
                                                     "monthly_budget": 60000, "platforms": ["meta", "google"]}).json()
    job = auth_client.get(f"/api/agents/jobs/{j['id']}").json()  # background task already ran in the test client
    assert job["status"] == "done", job
    r = job["result"]
    site = auth_client.get(f"/api/sites/{r['site_id']}").json()
    assert not site["published"] and "Kokapet" in site["html"]
    camps = auth_client.get("/api/campaigns").json()
    assert {c["platform"] for c in camps} == {"meta", "google"} and all(c["status"] == "draft" for c in camps)
    assert all(c["creative"]["link"].endswith(f"?aimva_c={c['id']}") and c["daily_budget"] == 1000 for c in camps)
    prods = auth_client.get("/api/products").json()
    assert prods[0]["monthly_budget"] == 60000 and all(c["product_id"] == prods[0]["id"] for c in camps)
    assert auth_client.get("/api/voice/agents").json()[0]["name"] == "Skyline Homes assistant"
    labels = [s["label"] for s in job["steps"]]
    assert "Created the product in Command Center" in labels and "Lead Concierge is on" in labels
    assert any(n["title"] == "Publish the page" for n in r["next"]) and any(n["title"] == "Connect WhatsApp" for n in r["next"])


def test_launch_reads_the_website(auth_client, mock_http):
    profile(auth_client)
    page = ("<html><head><title>Green Acres Villas</title><meta name='description' content='Luxury villas in Shamshabad'></head>"
            "<body><h1>Green Acres Villas</h1><p>Call +91 90000 11111</p></body></html>")
    mock_http.get("https://greenacres.example/").respond(200, html=page)
    j = auth_client.post("/api/agents/launch", json={"url": "greenacres.example", "platforms": []}).json()
    job = auth_client.get(f"/api/agents/jobs/{j['id']}").json()
    assert job["status"] == "done" and job["steps"][0]["label"] == "Read your website"
    site = auth_client.get(f"/api/sites/{job['result']['site_id']}").json()
    assert site["brief"]["business"] == "Green Acres Villas" and auth_client.get("/api/campaigns").json() == []


def test_launch_needs_something_and_your_own_brochure(auth_client, other_client):
    assert auth_client.post("/api/agents/launch", json={}).status_code == 400
    ref = other_client.post("/api/references", files={"file": ("b.txt", b"Their brochure text, plenty of words here.", "text/plain")}).json()
    assert auth_client.post("/api/agents/launch", json={"reference_id": ref["id"]}).status_code == 404
    assert other_client.get("/api/agents/jobs").json() == []


def test_launch_explains_when_it_cannot_find_the_offer(auth_client, mock_http):
    profile(auth_client)
    mock_http.get("https://empty.example/").respond(200, html="<html><body><p>Welcome</p></body></html>")
    j = auth_client.post("/api/agents/launch", json={"url": "https://empty.example/"}).json()
    job = auth_client.get(f"/api/agents/jobs/{j['id']}").json()
    assert job["status"] == "failed" and "what you're selling" in job["error"]


# ---- Lead Concierge ---------------------------------------------------------------------------------------
def test_new_lead_gets_a_drafted_welcome_and_follow_ups(auth_client, client):
    profile(auth_client)
    s = publish(auth_client)
    assert lead_form(client, s["slug"]) == {"ok": True}
    lead = auth_client.get("/api/leads").json()[0]
    timeline = auth_client.get(f"/api/leads/{lead['id']}").json()["timeline"]
    welcome = next(t for t in timeline if t["title"] == "Welcome message ready to send")
    assert "Hi Ravi, thanks for your enquiry with Skyline Homes" in welcome["body"] and "visit the site" in welcome["body"]
    fu = auth_client.get(f"/api/agents/leads/{lead['id']}/follow-ups").json()
    assert [f["step"] for f in fu] == ["day2", "day7"] and all(f["status"] == "pending" for f in fu)
    feed = auth_client.get("/api/agents/jobs?kind=concierge").json()
    assert feed[0]["title"] == "Drafted a welcome for Ravi Kumar"


def test_connected_whatsapp_sends_the_welcome(auth_client, client, db, mock_http):
    profile(auth_client)
    connect(db, "owner@example.com", "whatsapp", {"access_token": "t"}, {"phone_number_id": "123"})
    route = mock_http.post("https://graph.facebook.com/v21.0/123/messages").respond(json={"messages": [{"id": "wamid.1"}]})
    s = publish(auth_client)
    lead_form(client, s["slug"])
    body = json.loads(route.calls.last.request.content)
    assert body["to"] == "919812345678" and body["text"]["body"].startswith("Hi Ravi")
    assert auth_client.get("/api/agents/jobs?kind=concierge").json()[0]["title"] == "Welcomed Ravi Kumar on WhatsApp"


def test_follow_ups_stop_when_the_lead_replies_or_closes(auth_client, client, db):
    profile(auth_client)
    s = publish(auth_client)
    lead_form(client, s["slug"])
    lead_form(client, s["slug"], name="Asha", phone="+919800000002")
    leads = {l["name"]: l for l in auth_client.get("/api/leads").json()}
    uid = db.scalar(select(User.id).where(User.email == "owner@example.com"))
    db.add(WaMessage(user_id=uid, contact="919812345678", direction="in", body="Saturday 11am works", status="received"))
    db.commit()
    auth_client.patch(f"/api/leads/{leads['Asha']['id']}", json={"stage": "won"})
    assert concierge.run_due(db, datetime.utcnow() + timedelta(days=3)) == 0
    notes = {f.lead_id: f.note for f in db.scalars(select(FollowUp).where(FollowUp.step == "day2"))}
    assert notes[leads["Ravi Kumar"]["id"]] == "The lead replied" and notes[leads["Asha"]["id"]] == "Lead is won"


def test_due_follow_up_is_drafted_and_turning_off_stops_it(auth_client, client, db):
    profile(auth_client)
    s = publish(auth_client)
    lead_form(client, s["slug"])
    assert concierge.run_due(db, datetime.utcnow() + timedelta(days=2, minutes=1)) == 1
    lead = auth_client.get("/api/leads").json()[0]
    assert any(t["title"] == "Day-2 follow-up ready to send" for t in auth_client.get(f"/api/leads/{lead['id']}").json()["timeline"])
    auth_client.put("/api/agents/concierge", json={"enabled": False})
    assert concierge.run_due(db, datetime.utcnow() + timedelta(days=8)) == 0
    lead_form(client, s["slug"], name="New", phone="+919800000009")
    assert db.scalar(select(FollowUp).where(FollowUp.note == "Concierge was turned off")) is not None
    assert len(auth_client.get("/api/agents/jobs?kind=concierge").json()) == 2  # nothing new for the second lead


def test_custom_messages_are_used(auth_client, client):
    profile(auth_client)
    r = auth_client.put("/api/agents/concierge", json={"config": {"messages": {"welcome": "Namaste {name}! {business} here.", "evil": "x"}}}).json()
    assert r["config"]["messages"] == {"welcome": "Namaste {name}! {business} here."}
    s = publish(auth_client)
    lead_form(client, s["slug"])
    lead = auth_client.get("/api/leads").json()[0]
    assert any(t["body"].startswith("Namaste Ravi! Skyline Homes here.") for t in auth_client.get(f"/api/leads/{lead['id']}").json()["timeline"])


# ---- Campaign Autopilot -----------------------------------------------------------------------------------
def leaky(c):
    camp = c.post("/api/campaigns", json={"platform": "linkedin", "name": "Leaky", "daily_budget": 500}).json()
    c.patch(f"/api/campaigns/{camp['id']}", json={"status": "active"})
    c.post(f"/api/campaigns/{camp['id']}/results", json={"spend": 4000, "impressions": 9000, "clicks": 60})
    return camp


def test_autopilot_suggests_by_default_and_changes_nothing(auth_client):
    camp = leaky(auth_client)
    out = auth_client.post("/api/agents/autopilot/run").json()
    assert out["result"]["done"] == [] and any(w["key"] == f"pause:{camp['id']}" for w in out["result"]["waiting"])
    assert auth_client.get("/api/campaigns").json()[0]["status"] == "active"


def test_autopilot_in_auto_mode_pauses_and_logs_the_decision(auth_client):
    camp = leaky(auth_client)
    auth_client.put("/api/agents/autopilot", json={"mode": "auto"})
    out = auth_client.post("/api/agents/autopilot/run").json()
    assert out["result"]["done"][0]["title"].startswith("Pause “Leaky”") and out["job"]["title"] == "Autopilot made 1 change"
    assert auth_client.get("/api/campaigns").json()[0]["status"] == "paused"
    log = auth_client.get("/api/command/overview").json()["decisions"]
    assert log[0]["note"] == "Done by Autopilot"
    assert f"pause:{camp['id']}" not in [w["key"] for w in auth_client.post("/api/agents/autopilot/run").json()["result"]["waiting"]]


def test_autopilot_settings_are_bounded(auth_client):
    r = auth_client.put("/api/agents/autopilot", json={"config": {"max_actions": 999, "max_scale_pct": 400, "allow_scale": 1, "spend_all": True}}).json()
    assert r["config"]["max_actions"] == 10 and r["config"]["max_scale_pct"] == 50 and r["config"]["allow_scale"] is True
    assert "spend_all" not in r["config"]
    assert auth_client.put("/api/agents/autopilot", json={"mode": "yolo"}).status_code == 422


# ---- Weekly Report, Page Fixer ----------------------------------------------------------------------------
def test_weekly_report(auth_client, client):
    profile(auth_client)
    s = publish(auth_client)
    lead_form(client, s["slug"])
    out = auth_client.post("/api/agents/weekly_report/run").json()
    assert out["result"]["leads"] == 1 and out["job"]["status"] == "done"
    assert any(st["label"].startswith("Not emailed") for st in out["job"]["steps"])  # no SMTP in tests


def test_page_fixer_runs_on_new_pages_and_on_demand(auth_client):
    s = auth_client.post("/api/sites", json={"business": "Acme", "offer": "Fast repairs", "use_ai": False, "layout": "split"}).json()
    broken = s["html"].replace('<meta name="viewport" content="width=device-width,initial-scale=1">', "") \
        .replace("</body>", '<img src="https://x.example/a.png"><a href="">x</a></body>')
    assert auth_client.patch(f"/api/sites/{s['id']}", json={"html": broken, "note": "Edited HTML"}).status_code == 200
    out = auth_client.post("/api/agents/page_fixer/run", json={"site_id": s["id"]}).json()
    fixed = out["result"]["fixed"]
    assert any("viewport" in f for f in fixed) and any("alt text" in f for f in fixed) and any("empty link" in f for f in fixed)
    html = auth_client.get(f"/api/sites/{s['id']}").json()["html"]
    assert 'name="viewport"' in html and 'alt="Acme"' in html and 'href="#contact"' in html
    assert auth_client.get(f"/api/sites/{s['id']}/versions").json()[0]["note"].startswith("Page Fixer:")
    assert auth_client.post("/api/agents/page_fixer/run", json={"site_id": 99999}).status_code == 404


def test_agents_list_and_privacy(auth_client, other_client):
    kinds = [a["kind"] for a in auth_client.get("/api/agents").json()]
    assert kinds == ["launch", "concierge", "autopilot", "weekly_report", "page_fixer"]
    s = auth_client.post("/api/sites", json={"business": "Acme", "offer": "x offer", "use_ai": False}).json()
    assert other_client.post("/api/agents/page_fixer/run", json={"site_id": s["id"]}).status_code == 404
    job = auth_client.post("/api/agents/autopilot/run").json()["job"]
    assert other_client.get(f"/api/agents/jobs/{job['id']}").status_code == 404


# ---- scheduler --------------------------------------------------------------------------------------------
def test_scheduler_runs_daily_and_weekly_agents_once(auth_client, db):
    auth_client.get("/api/agents")  # creates the settings rows
    monday_10_ist = datetime(2026, 10, 26, 4, 30)  # 10:00 in India
    first = scheduler.tick(monday_10_ist)
    assert first["autopilot"] == 1 and first["reports"] == 1
    again = scheduler.tick(monday_10_ist + timedelta(hours=2))
    assert again["autopilot"] == 0 and again["reports"] == 0
    tuesday = scheduler.tick(monday_10_ist + timedelta(days=1))
    assert tuesday["autopilot"] == 1 and tuesday["reports"] == 0
    early = db.scalar(select(AgentSetting).where(AgentSetting.kind == "autopilot"))
    assert not scheduler.due_daily(early, datetime(2026, 10, 28, 2, 0))  # 7:30 am: too early


# ---- running safely with several server processes ------------------------------------------------
def test_only_one_process_holds_the_scheduler_lease():
    from datetime import timedelta
    from app.agents.scheduler import LEASE_S, take_lease
    from app.models import utcnow
    now = utcnow()
    assert take_lease("worker-a", now) is True
    assert take_lease("worker-b", now) is False  # a live lease belongs to worker-a
    assert take_lease("worker-a", now + timedelta(seconds=30)) is True  # the holder renews
    later = now + timedelta(seconds=30 + LEASE_S + 1)
    assert take_lease("worker-b", later) is True  # worker-a stopped renewing, so worker-b takes over
    assert take_lease("worker-a", later) is False


def test_rate_limits_are_shared_across_processes():
    """The count lives in the database, so a second worker (simulated by clearing process memory) sees it."""
    import pytest
    from fastapi import HTTPException
    from app import security
    for _ in range(3):
        security.rate_limit("t:shared", 3, 60)
    security._last_prune = 0.0
    with pytest.raises(HTTPException) as e:
        security.rate_limit("t:shared", 3, 60)
    assert e.value.status_code == 429
    security.rate_limit("t:other", 3, 60)  # other keys are unaffected
