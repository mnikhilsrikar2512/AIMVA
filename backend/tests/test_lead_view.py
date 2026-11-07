"""Single lead view: cross-channel timeline, notes, stage history, calling a lead."""
from .helpers import connect

GRAPH = "https://graph.facebook.com/v21.0"
PHONE = "+919876543210"


def lead_view(c, lead_id):
    r = c.get(f"/api/leads/{lead_id}")
    assert r.status_code == 200, r.text
    return r.json()


def kinds(view):
    return [i["kind"] for i in view["timeline"]]


def test_manual_lead_has_created_event(auth_client):
    lead = auth_client.post("/api/leads", json={"name": "Asha", "email": "a@x.com"}).json()
    v = lead_view(auth_client, lead["id"])
    assert v["name"] == "Asha" and kinds(v) == ["created"]
    assert v["timeline"][0]["title"] == "Lead created from manual entry"


def test_timeline_merges_every_channel(auth_client, client, db, mock_http):
    # 1. Landing page form
    site = auth_client.post("/api/sites", json={"business": "Skyline Homes", "use_ai": False}).json()
    auth_client.post(f"/api/sites/{site['id']}/deploy", json={"target": "aimva"})
    client.post(f"/api/public/sites/{site['slug']}/lead", data={"name": "Ravi", "phone": PHONE, "message": "Need a 2BHK"})
    lead_id = auth_client.get("/api/leads").json()[0]["id"]

    # 2. WhatsApp both ways (sandbox)
    auth_client.post("/api/whatsapp/simulate-inbound", json={"from": "919876543210", "body": "Is Saturday ok?", "name": "Ravi"})
    auth_client.post("/api/whatsapp/send", json={"to": PHONE, "body": "Yes, 11am works"})

    # 3. Meta lead form for the same person (dedupes into the same lead)
    connect(db, "owner@example.com", "meta", {"access_token": "EAA"}, {"ad_account_id": "act_1"})
    camp = auth_client.post("/api/campaigns", json={"platform": "meta", "name": "Diwali", "lead_form": {"form_id": "F1"}}).json()
    mock_http.post(f"{GRAPH}/act_1/campaigns").respond(json={"id": "C1"})
    mock_http.get(f"{GRAPH}/C1/insights").respond(json={"data": []})
    mock_http.get(f"{GRAPH}/F1/leads").respond(json={"data": [{"id": "L1", "field_data": [
        {"name": "full_name", "values": ["Ravi"]}, {"name": "phone_number", "values": [PHONE]}]}]})
    auth_client.post(f"/api/campaigns/{camp['id']}/publish")
    auth_client.post(f"/api/campaigns/{camp['id']}/sync")

    # 4. Stage change + note
    auth_client.patch(f"/api/leads/{lead_id}", json={"stage": "qualified", "value": 4500000})
    auth_client.post(f"/api/leads/{lead_id}/notes", json={"body": "Prefers east-facing units"})

    assert len(auth_client.get("/api/leads").json()) == 1
    v = lead_view(auth_client, lead_id)
    k = kinds(v)
    for expected in ("created", "form", "whatsapp", "ad", "stage", "value", "note"):
        assert expected in k, (expected, k)
    assert k.count("whatsapp") == 2
    titles = [i["title"] for i in v["timeline"]]
    assert "Submitted the form on Skyline Homes" in titles
    assert "Lead form · Diwali" in titles
    assert "Stage: new → qualified" in titles
    form = next(i for i in v["timeline"] if i["kind"] == "form")
    assert form["body"] == "Need a 2BHK"
    wa = [i for i in v["timeline"] if i["kind"] == "whatsapp"]
    assert {i["meta"]["direction"] for i in wa} == {"in", "out"}
    # Newest first.
    assert [i["at"] for i in v["timeline"]] == sorted((i["at"] for i in v["timeline"]), reverse=True)


def test_voice_call_appears_on_lead(auth_client):
    agent = auth_client.post("/api/voice/agents", json={"name": "Sales", "questions": ["Name?", "Email or phone?"]}).json()
    cid = auth_client.post(f"/api/voice/agents/{agent['id']}/calls").json()["call"]["id"]
    auth_client.post(f"/api/voice/calls/{cid}/turn", json={"text": "I'm Meera"})
    out = auth_client.post(f"/api/voice/calls/{cid}/turn", json={"text": "meera@x.com, thanks so much"}).json()
    v = lead_view(auth_client, out["call"]["lead_id"])
    call = next(i for i in v["timeline"] if i["kind"] == "call")
    assert call["meta"]["status"] == "completed" and call["meta"]["sentiment"] > 0
    assert "meera@x.com" in call["body"] and call["meta"]["turns"] == 5


def test_unchanged_stage_records_nothing(auth_client):
    lead = auth_client.post("/api/leads", json={"email": "a@x.com"}).json()
    auth_client.patch(f"/api/leads/{lead['id']}", json={"stage": "new", "value": 0})
    assert kinds(lead_view(auth_client, lead["id"])) == ["created"]


def test_note_validation(auth_client):
    lead = auth_client.post("/api/leads", json={"email": "a@x.com"}).json()
    assert auth_client.post(f"/api/leads/{lead['id']}/notes", json={"body": ""}).status_code == 422
    v = auth_client.post(f"/api/leads/{lead['id']}/notes", json={"body": "  Call after 6pm  "}).json()
    assert v["timeline"][0]["kind"] == "note" and v["timeline"][0]["body"] == "Call after 6pm"


def test_call_lead_requirements_and_success(auth_client, mock_http):
    no_phone = auth_client.post("/api/leads", json={"email": "a@x.com"}).json()
    assert auth_client.post(f"/api/leads/{no_phone['id']}/call", json={}).status_code == 400
    lead = auth_client.post("/api/leads", json={"name": "Ravi", "phone": PHONE}).json()
    r = auth_client.post(f"/api/leads/{lead['id']}/call", json={})
    assert r.status_code == 400 and "voice agent" in r.json()["detail"]
    auth_client.post("/api/voice/agents", json={"name": "Sales"})
    r = auth_client.post(f"/api/leads/{lead['id']}/call", json={})
    assert r.status_code == 400 and "Twilio" in r.json()["detail"]

    auth_client.post("/api/integrations/twilio/key", json={"values": {"account_sid": "AC1", "auth_token": "t", "from_number": "+15550001"}})
    route = mock_http.post("https://api.twilio.com/2010-04-01/Accounts/AC1/Calls.json").respond(201, json={"sid": "CA1"})
    v = auth_client.post(f"/api/leads/{lead['id']}/call", json={}).json()
    assert "To=%2B919876543210" in route.calls[0].request.content.decode()
    call = next(i for i in v["timeline"] if i["kind"] == "call")
    assert call["title"].startswith("Phone call")


def test_call_lead_rejects_someone_elses_agent(auth_client, other_client):
    theirs = other_client.post("/api/voice/agents", json={"name": "Theirs"}).json()
    lead = auth_client.post("/api/leads", json={"phone": PHONE}).json()
    r = auth_client.post(f"/api/leads/{lead['id']}/call", json={"agent_id": theirs["id"]})
    assert r.status_code == 400


def test_lead_view_is_private(auth_client, other_client):
    lead = auth_client.post("/api/leads", json={"phone": PHONE}).json()
    assert other_client.get(f"/api/leads/{lead['id']}").status_code == 404
    assert other_client.post(f"/api/leads/{lead['id']}/notes", json={"body": "x"}).status_code == 404
    assert other_client.post(f"/api/leads/{lead['id']}/call", json={}).status_code == 404
    # Another tenant's WhatsApp messages to the same number never leak into this lead.
    other_client.post("/api/whatsapp/send", json={"to": PHONE, "body": "from another company"})
    assert "whatsapp" not in kinds(lead_view(auth_client, lead["id"]))


def test_deleting_lead_removes_its_events(auth_client, db):
    from sqlalchemy import func, select
    from app.models import LeadEvent
    lead = auth_client.post("/api/leads", json={"email": "a@x.com"}).json()
    auth_client.post(f"/api/leads/{lead['id']}/notes", json={"body": "x"})
    auth_client.delete(f"/api/leads/{lead['id']}")
    assert auth_client.get(f"/api/leads/{lead['id']}").status_code == 404
    assert db.scalar(select(func.count()).select_from(LeadEvent)) == 0
