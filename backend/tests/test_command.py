"""Command center: products, attribution, period maths, next steps and decisions."""
from datetime import timedelta

from app.db import SessionLocal
from app.models import CampaignStat, Lead, User, utcnow


def _uid(email="owner@example.com"):
    db = SessionLocal()
    uid = db.query(User).filter_by(email=email).one().id
    db.close()
    return uid


def _leads(uid, n, campaign_id=None, product_id=None, stage="new", score=40, value=0, days_ago=1, phone=""):
    db = SessionLocal()
    for i in range(n):
        db.add(Lead(user_id=uid, name=f"L{i}", email=f"l{campaign_id}-{i}-{stage}@x.com", phone=phone, campaign_id=campaign_id,
                    product_id=product_id, stage=stage, score=score, value=value, source="meta",
                    created_at=utcnow() - timedelta(days=days_ago, hours=i)))
    db.commit()
    db.close()


def _setup(c):
    # Budget is large on purpose: 11,000 spent "today" projects to over 300,000 on the 1st of a month, and an over-pace
    # product never gets "scale" advice, so a small budget made these tests depend on the calendar date.
    p = c.post("/api/products", json={"name": "2BHK Skyline", "price": 4500000, "target_cpl": 500, "monthly_budget": 400000}).json()
    good = c.post("/api/campaigns", json={"platform": "meta", "name": "Good", "daily_budget": 1000, "product_id": p["id"]}).json()
    bad = c.post("/api/campaigns", json={"platform": "google", "name": "Bad", "daily_budget": 1000, "product_id": p["id"]}).json()
    for x in (good, bad):
        c.patch(f"/api/campaigns/{x['id']}", json={"status": "active"})
    c.post(f"/api/campaigns/{good['id']}/results", json={"spend": 3000, "impressions": 20000, "clicks": 400})
    c.post(f"/api/campaigns/{bad['id']}/results", json={"spend": 8000, "impressions": 30000, "clicks": 150})
    uid = _uid()
    _leads(uid, 10, good["id"], p["id"])
    _leads(uid, 2, bad["id"], p["id"])
    return p, good, bad


def test_products_crud_and_isolation(auth_client, other_client):
    p = auth_client.post("/api/products", json={"name": "Dental implants", "kind": "service", "price": 40000}).json()
    assert auth_client.get("/api/products").json()[0]["name"] == "Dental implants"
    assert other_client.get("/api/products").json() == []
    assert other_client.put(f"/api/products/{p['id']}", json={"name": "Hacked"}).status_code == 404
    c = auth_client.post("/api/campaigns", json={"platform": "other", "name": "Radio", "product_id": p["id"]}).json()
    assert other_client.post("/api/campaigns", json={"platform": "meta", "name": "XY", "product_id": p["id"]}).status_code == 404
    assert auth_client.delete(f"/api/products/{p['id']}").json()["ok"]
    assert auth_client.get("/api/campaigns").json()[0]["product_id"] is None and c["product_id"] == p["id"]  # kept, unlinked


def test_overview_rolls_up_and_scores_campaigns(auth_client):
    p, good, bad = _setup(auth_client)
    o = auth_client.get("/api/command/overview?days=30").json()
    prod = o["products"][0]
    assert prod["spend"] == 11000 and prod["leads"] == 12 and prod["cpl"] == round(11000 / 12, 2)
    by = {c["name"]: c for c in prod["campaigns"]}
    assert by["Good"]["cpl"] == 300 and by["Good"]["health"] == "great"
    assert by["Bad"]["cpl"] == 4000 and by["Bad"]["health"] == "attention"
    assert by["Good"]["ctr"] == 2.0 and o["kpis"]["active_campaigns"] == 2
    keys = {r["key"].split(":")[0] for r in o["recommendations"]}
    assert {"fix", "scale"} <= keys
    fix = next(r for r in o["recommendations"] if r["key"].startswith("fix"))
    assert fix["alt"]["type"] == "move_budget" and "Good" in fix["alt"]["label"]  # cheaper option inside the same product
    assert sum(1 for r in o["recommendations"] if r["campaign_id"] == bad["id"]) == 1  # one card per campaign
    assert o["plan"]["leads_next_7"] == round(12 / 30 * 7, 1) and "12 leads" in o["summary"]


def test_period_maths_uses_snapshots(auth_client):
    c = auth_client.post("/api/campaigns", json={"platform": "other", "name": "Flyers"}).json()
    old = (utcnow() - timedelta(days=40)).date().isoformat()
    auth_client.post(f"/api/campaigns/{c['id']}/results", json={"spend": 5000, "impressions": 100, "clicks": 10, "day": old, "mode": "total"})
    auth_client.post(f"/api/campaigns/{c['id']}/results", json={"spend": 1200, "impressions": 50, "clicks": 5})
    row = auth_client.get("/api/command/overview?days=30").json()["unassigned"]["campaigns"][0]
    # 1,200 was added between a sample 40 days ago and today; spread evenly, ~30/40 of it falls in this window.
    assert row["spend"] == 6200 and 850 <= row["period_spend"] <= 960
    bad = auth_client.post(f"/api/campaigns/{c['id']}/results", json={"spend": 10, "impressions": 1, "clicks": 1, "mode": "total"})
    assert bad.status_code == 400
    future = (utcnow() + timedelta(days=3)).date().isoformat()
    assert auth_client.post(f"/api/campaigns/{c['id']}/results", json={"spend": 1, "day": future}).status_code == 400


def test_accepting_runs_safe_actions_and_logs(auth_client):
    p, good, bad = _setup(auth_client)
    recs = auth_client.get("/api/command/overview").json()["recommendations"]
    fix = next(r for r in recs if r["key"] == f"fix:{bad['id']}")
    out = auth_client.post(f"/api/command/recommendations/{fix['key']}/decide", json={"decision": "accepted"}).json()
    assert "Paused" in out["result"]
    camps = {c["id"]: c for c in auth_client.get("/api/campaigns").json()}
    assert camps[bad["id"]]["status"] == "paused"
    scale = f"scale:{good['id']}"
    auth_client.post(f"/api/command/recommendations/{scale}/decide", json={"decision": "accepted"})
    assert {c["id"]: c for c in auth_client.get("/api/campaigns").json()}[good["id"]]["daily_budget"] == 1200
    o = auth_client.get("/api/command/overview").json()
    assert not any(r["key"] in (fix["key"], scale) for r in o["recommendations"])  # hidden after acting
    assert [d["decision"] for d in o["decisions"]] == ["accepted", "accepted"]
    assert auth_client.post(f"/api/command/recommendations/{fix['key']}/decide", json={"decision": "accepted"}).status_code == 404


def test_snooze_and_dismiss_hide_suggestions(auth_client, other_client):
    auth_client.post("/api/products", json={"name": "Teeth whitening"})
    keys = [r["key"] for r in auth_client.get("/api/command/overview").json()["recommendations"]]
    assert any(k.startswith("advertise:") for k in keys) and any(k.startswith("landing:") for k in keys)
    adv = next(k for k in keys if k.startswith("advertise:"))
    assert other_client.post(f"/api/command/recommendations/{adv}/decide", json={"decision": "dismissed"}).status_code == 404
    auth_client.post(f"/api/command/recommendations/{adv}/decide", json={"decision": "snoozed", "note": "after Diwali"})
    keys2 = [r["key"] for r in auth_client.get("/api/command/overview").json()["recommendations"]]
    assert adv not in keys2


def test_pause_when_spending_without_leads(auth_client):
    c = auth_client.post("/api/campaigns", json={"platform": "linkedin", "name": "Leaky", "daily_budget": 500}).json()
    auth_client.patch(f"/api/campaigns/{c['id']}", json={"status": "active"})
    auth_client.post(f"/api/campaigns/{c['id']}/results", json={"spend": 4000, "impressions": 9000, "clicks": 60})
    r = next(r for r in auth_client.get("/api/command/overview").json()["recommendations"] if r["key"] == f"pause:{c['id']}")
    assert r["priority"] == "high" and "no leads" in r["title"]


def test_overspend_pace_trims_budgets(auth_client):
    p = auth_client.post("/api/products", json={"name": "Course", "monthly_budget": 1000}).json()
    c = auth_client.post("/api/campaigns", json={"platform": "meta", "name": "Ads", "daily_budget": 1000, "product_id": p["id"]}).json()
    auth_client.patch(f"/api/campaigns/{c['id']}", json={"status": "active"})
    auth_client.post(f"/api/campaigns/{c['id']}/results", json={"spend": 5000, "impressions": 100, "clicks": 1})
    r = next(r for r in auth_client.get("/api/command/overview").json()["recommendations"] if r["key"].startswith("pace:"))
    out = auth_client.post(f"/api/command/recommendations/{r['key']}/decide", json={"decision": "accepted"}).json()
    assert "Trimmed 1 daily budget" in out["result"]
    assert auth_client.get("/api/campaigns").json()[0]["daily_budget"] < 1000


def test_hot_leads_need_twilio_and_say_so(auth_client):
    _leads(_uid(), 2, score=85, days_ago=1, phone="+919876543210")
    r = next(r for r in auth_client.get("/api/command/overview").json()["recommendations"] if r["key"].startswith("call_hot"))
    out = auth_client.post(f"/api/command/recommendations/{r['key']}/decide", json={"decision": "accepted"})
    assert out.status_code == 400 and "voice agent" in out.json()["detail"]
    auth_client.post("/api/voice/agents", json={"name": "Asha", "greeting": "Hi", "questions": ["Name?"]})
    out = auth_client.post(f"/api/command/recommendations/{r['key']}/decide", json={"decision": "accepted"})
    assert out.status_code == 400 and "Twilio" in out.json()["detail"]
    assert auth_client.get("/api/command/overview").json()["decisions"] == []  # nothing logged when it didn't run


def test_landing_page_leads_are_attributed_to_campaign(auth_client, client):
    p = auth_client.post("/api/products", json={"name": "Villas"}).json()
    camp = auth_client.post("/api/campaigns", json={"platform": "meta", "name": "Villa ads", "product_id": p["id"]}).json()
    s = auth_client.post("/api/sites", json={"business": "Villas", "use_ai": False}).json()
    auth_client.post("/api/products/link", json={"kind": "site", "id": s["id"], "product_id": p["id"]})
    auth_client.post(f"/api/sites/{s['id']}/publish", json={"name": "Villas", "slug": "villas-x"})
    client.post("/api/public/sites/villas-x/lead", data={"name": "A", "email": "a@b.com", "aimva_c": str(camp["id"]),
                                                         "utm_source": "facebook"})
    o = auth_client.get("/api/command/overview").json()
    assert o["products"][0]["leads"] == 1 and o["products"][0]["campaigns"][0]["leads"] == 1
    assert o["products"][0]["pages"][0]["id"] == s["id"]
    lead = auth_client.get("/api/leads").json()[0]
    assert "utm_source=facebook" in lead["message"]


def test_foreign_campaign_tag_is_ignored(auth_client, other_client, client):
    other = other_client.post("/api/campaigns", json={"platform": "meta", "name": "Theirs"}).json()
    s = auth_client.post("/api/sites", json={"business": "Mine", "use_ai": False}).json()
    auth_client.post(f"/api/sites/{s['id']}/publish", json={"name": "Mine", "slug": "mine-x"})
    client.post("/api/public/sites/mine-x/lead", data={"email": "z@z.com", "aimva_c": str(other["id"])})
    assert other_client.get("/api/command/overview").json()["unassigned"]["campaigns"][0]["leads"] == 0


def test_brief_without_ai_uses_rules(auth_client):
    r = auth_client.get("/api/command/brief").json()
    assert r["source"] == "rules" and "No campaigns" in r["text"]


def test_offline_campaigns_get_tracking_advice_not_pause(auth_client):
    c = auth_client.post("/api/campaigns", json={"platform": "other", "name": "Radio spots"}).json()
    auth_client.patch(f"/api/campaigns/{c['id']}", json={"status": "active"})
    auth_client.post(f"/api/campaigns/{c['id']}/results", json={"spend": 12000})
    keys = [r["key"] for r in auth_client.get("/api/command/overview").json()["recommendations"]]
    assert f"track:{c['id']}" in keys and f"pause:{c['id']}" not in keys
    out = auth_client.post(f"/api/command/recommendations/track:{c['id']}/decide", json={"decision": "accepted"}).json()
    assert out["result"] == "Noted."


def test_lifetime_totals_are_spread_over_the_running_period(auth_client):
    c = auth_client.post("/api/campaigns", json={"platform": "meta", "name": "Old campaign"}).json()
    since = (utcnow() - timedelta(days=60)).date().isoformat()
    auth_client.post(f"/api/campaigns/{c['id']}/results", json={"spend": 60000, "impressions": 600000, "clicks": 6000,
                                                                "mode": "total", "since": since})
    week = auth_client.get("/api/command/overview?days=7").json()["unassigned"]["campaigns"][0]
    assert 6500 <= week["period_spend"] <= 7500  # ~7 of 60 days, not the whole 60,000


def test_budget_moves_stay_within_a_product(auth_client):
    a = auth_client.post("/api/products", json={"name": "Plots", "target_cpl": 900}).json()
    b = auth_client.post("/api/products", json={"name": "Loans", "target_cpl": 250}).json()
    uid = _uid()
    for pid, name, spend, n in ((a["id"], "Plots ads", 20000, 10), (b["id"], "Loan ads", 2000, 10)):
        c = auth_client.post("/api/campaigns", json={"platform": "meta", "name": name, "daily_budget": 1000, "product_id": pid}).json()
        auth_client.patch(f"/api/campaigns/{c['id']}", json={"status": "active"})
        auth_client.post(f"/api/campaigns/{c['id']}/results", json={"spend": spend, "impressions": 50000, "clicks": 900})
        _leads(uid, n, c["id"], pid)
    recs = auth_client.get("/api/command/overview").json()["recommendations"]
    assert not any(r["key"].startswith("move") or (r.get("alt") or {}).get("type") == "move_budget" for r in recs)


def test_no_scaling_while_product_is_over_pace(auth_client):
    p = auth_client.post("/api/products", json={"name": "Towers", "target_cpl": 600, "monthly_budget": 1000}).json()
    c = auth_client.post("/api/campaigns", json={"platform": "meta", "name": "Cheap reels", "daily_budget": 1000, "product_id": p["id"]}).json()
    auth_client.patch(f"/api/campaigns/{c['id']}", json={"status": "active"})
    auth_client.post(f"/api/campaigns/{c['id']}/results", json={"spend": 3000, "impressions": 20000, "clicks": 400})
    _leads(_uid(), 12, c["id"], p["id"])
    keys = [r["key"] for r in auth_client.get("/api/command/overview").json()["recommendations"]]
    assert any(k.startswith("pace:") for k in keys) and f"scale:{c['id']}" not in keys


def test_accepting_the_alternative_moves_budget(auth_client):
    p, good, bad = _setup(auth_client)
    fix = next(r for r in auth_client.get("/api/command/overview").json()["recommendations"] if r["key"] == f"fix:{bad['id']}")
    out = auth_client.post(f"/api/command/recommendations/{fix['key']}/decide", json={"decision": "accepted", "alt": True}).json()
    assert out["result"].startswith("Moved")
    camps = {c["id"]: c for c in auth_client.get("/api/campaigns").json()}
    assert camps[bad["id"]]["status"] == "active" and camps[bad["id"]]["daily_budget"] == 700 and camps[good["id"]]["daily_budget"] == 1300


def test_hot_leads_card_promises_what_it_does(auth_client):
    _leads(_uid(), 9, score=90, days_ago=1, phone="+919876543210")
    r = next(r for r in auth_client.get("/api/command/overview").json()["recommendations"] if r["key"].startswith("call_hot"))
    assert r["title"] == "Call your 5 hottest leads now" and "9 leads" in r["why"] and r["group"] == "leads"
