from sqlalchemy import create_engine, inspect, text

import app.db as dbmod


def keys_done(status):
    return {s["key"] for s in status["steps"] if s["done"]}


def test_new_user_starts_with_verify_only(auth_client):
    s = auth_client.get("/api/onboarding").json()
    assert keys_done(s) == {"verify"} and s["completed"] == 1 and s["total"] == 8
    assert s["needs_profile"] and not s["dismissed"] and not s["all_done"]
    assert {i["value"] for i in s["industries"]} >= {"real_estate", "healthcare", "saas"}


def test_profile_sets_industry_and_creates_starter_agent(auth_client):
    s = auth_client.post("/api/onboarding/profile", json={"company": "Skyline Homes", "industry": "real_estate",
                                                          "goal": "book_visits"}).json()
    assert "profile" in keys_done(s) and not s["needs_profile"]
    assert s["template"]["site"]["cta"] == "Book a site visit"
    agents = auth_client.get("/api/voice/agents").json()
    assert len(agents) == 1 and agents[0]["name"] == "Skyline Homes assistant"
    assert any("budget" in q for q in agents[0]["questions"])
    me = auth_client.get("/api/auth/me").json()["user"]
    assert (me["company"], me["industry"], me["goal"]) == ("Skyline Homes", "real_estate", "book_visits")
    # Saving again doesn't add a second agent.
    auth_client.post("/api/onboarding/profile", json={"company": "Skyline", "industry": "saas"})
    assert len(auth_client.get("/api/voice/agents").json()) == 1


def test_profile_validation(auth_client):
    assert auth_client.post("/api/onboarding/profile", json={"company": "", "industry": "saas"}).status_code == 422
    assert auth_client.post("/api/onboarding/profile", json={"company": "X", "industry": "mining"}).status_code == 422


def test_checklist_follows_real_activity(auth_client, client):
    auth_client.post("/api/onboarding/profile", json={"company": "Acme", "industry": "services"})
    site = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False}).json()
    assert "site" in keys_done(auth_client.get("/api/onboarding").json())
    auth_client.post(f"/api/sites/{site['id']}/deploy", json={"target": "aimva"})
    client.post(f"/api/public/sites/{site['slug']}/lead", data={"phone": "+919999999999"})
    agent = auth_client.get("/api/voice/agents").json()[0]
    auth_client.post(f"/api/voice/agents/{agent['id']}/calls")
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "k"}})
    s = auth_client.get("/api/onboarding").json()
    assert s["completed"] == 7 and "alerts" not in keys_done(s)
    auth_client.post("/api/alerts/devices", json={"endpoint": "https://fcm.googleapis.com/fcm/send/abc",
                                                  "keys": {"p256dh": "B" + "A" * 86, "auth": "A" * 22}})
    s = auth_client.get("/api/onboarding").json()
    assert s["all_done"] and s["completed"] == 8


def test_dismiss_and_restore(auth_client):
    assert auth_client.post("/api/onboarding/dismiss", json={"dismissed": True}).json()["dismissed"] is True
    assert auth_client.get("/api/onboarding").json()["dismissed"] is True
    assert auth_client.post("/api/onboarding/dismiss", json={"dismissed": False}).json()["dismissed"] is False


def test_onboarding_is_per_user(auth_client, other_client):
    auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False})
    assert "site" not in keys_done(other_client.get("/api/onboarding").json())


def test_add_missing_columns_upgrades_old_database(tmp_path, monkeypatch):
    old = create_engine(f"sqlite:///{tmp_path}/old.db")
    with old.begin() as c:
        c.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR, email VARCHAR, password_hash VARCHAR)"))
        c.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('Old', 'old@example.com', 'x')"))
    monkeypatch.setattr(dbmod, "engine", old)
    dbmod.add_missing_columns()
    cols = {c["name"] for c in inspect(old).get_columns("users")}
    assert {"industry", "goal", "onboarding_dismissed", "company"} <= cols
    with old.begin() as c:
        row = c.execute(text("SELECT industry, onboarding_dismissed FROM users")).one()
    assert row == ("", 0)
    dbmod.add_missing_columns()  # idempotent


def test_signup_answers_are_saved_step_by_step(auth_client):
    r = auth_client.post("/api/onboarding/answers", json={"answers": {"for_whom": "clients", "has_website": True,
                                                                      "website": " https://smilecare.example "}})
    assert r.status_code == 200, r.text
    r = auth_client.post("/api/onboarding/answers", json={"answers": {
        "presence": ["instagram", "whatsapp", "instagram"], "handles": {"instagram": "@smilecare", "youtube": " "},
        "acquisition": "agency", "agency_name": "Pixel Co", "monthly_budget": "25k_1l", "team_size": "small"}})
    a = auth_client.get("/api/onboarding").json()["answers"]
    assert a == {"for_whom": "clients", "has_website": True, "website": "https://smilecare.example",
                 "presence": ["instagram", "whatsapp"], "handles": {"instagram": "@smilecare"}, "acquisition": "agency",
                 "agency_name": "Pixel Co", "monthly_budget": "25k_1l", "team_size": "small"}
    assert auth_client.post("/api/onboarding/answers", json={"answers": {"for_whom": "aliens"}}).status_code == 422
    assert auth_client.post("/api/onboarding/answers", json={"answers": {"for_whom": "personal"}}).json()["answers"]["for_whom"] == "personal"
    assert auth_client.post("/api/onboarding/answers", json={"answers": {"unknown": 1}}).status_code == 422
    assert auth_client.post("/api/onboarding/answers", json={"answers": {"agency_name": "x" * 301}}).status_code == 422


def test_alerts_step_is_done_by_a_phone_or_a_connected_whatsapp(auth_client, db):
    from app.models import AgentSetting, User
    keys = lambda: {s["key"] for s in auth_client.get("/api/onboarding").json()["steps"] if s["done"]}
    assert "alerts" not in keys()
    uid = db.query(User).filter_by(email="owner@example.com").one().id
    db.add(AgentSetting(user_id=uid, kind="lead_alerts", enabled=True, mode="auto", config={"push": [{"endpoint": "https://fcm.googleapis.com/x"}]}))
    db.commit()
    assert "alerts" in keys()
