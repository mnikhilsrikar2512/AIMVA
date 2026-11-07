"""Campaigns, WhatsApp, voice agent and analytics."""
import hashlib
import hmac
import json

from sqlalchemy import select

from app.models import Campaign

from .helpers import connect

GRAPH = "https://graph.facebook.com/v21.0"
META_SECRET = "test-meta-app-secret"  # set in conftest


def wa_post(client, payload, secret=META_SECRET, signature=None):
    """POST to the WhatsApp webhook the way Meta does: raw JSON body signed with the app secret."""
    raw = json.dumps(payload).encode()
    sig = signature if signature is not None else "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/api/public/whatsapp/webhook", content=raw,
                       headers={"content-type": "application/json", "x-hub-signature-256": sig})


# ---- campaigns -------------------------------------------------------------
def new_campaign(c, platform="meta", **over):
    r = c.post("/api/campaigns", json={"platform": platform, "name": "Diwali leads", "daily_budget": 25, **over})
    assert r.status_code == 200, r.text
    return r.json()


def test_campaign_crud_and_validation(auth_client):
    assert auth_client.post("/api/campaigns", json={"platform": "tiktok", "name": "xx"}).status_code == 400
    assert auth_client.post("/api/campaigns", json={"platform": "meta", "name": "x", "daily_budget": -5}).status_code == 422
    c = new_campaign(auth_client, creative={"headline": "Hi"})
    assert c["status"] == "draft" and c["ctr"] == 0
    new_campaign(auth_client, platform="google")
    assert [x["platform"] for x in auth_client.get("/api/campaigns?platform=google").json()] == ["google"]
    r = auth_client.patch(f"/api/campaigns/{c['id']}", json={"daily_budget": 40})
    assert r.json()["daily_budget"] == 40
    auth_client.delete(f"/api/campaigns/{c['id']}")
    assert len(auth_client.get("/api/campaigns").json()) == 1


def test_invalid_campaign_status_rejected(auth_client):
    c = new_campaign(auth_client)
    assert auth_client.patch(f"/api/campaigns/{c['id']}", json={"status": "deleted"}).status_code == 422


def test_google_and_linkedin_publish_messages(auth_client, db):
    g = new_campaign(auth_client, platform="google")
    r = auth_client.post(f"/api/campaigns/{g['id']}/publish")
    assert r.status_code == 400 and "Connect" in r.json()["detail"]
    connect(db, "owner@example.com", "google", {"access_token": "t"})
    r = auth_client.post(f"/api/campaigns/{g['id']}/publish")
    assert r.status_code == 400 and "developer token" in r.json()["detail"]  # full flow: tests/test_ad_platforms.py


def test_meta_publish_requires_ad_account(auth_client, db):
    c = new_campaign(auth_client)
    assert auth_client.post(f"/api/campaigns/{c['id']}/publish").status_code == 400
    connect(db, "owner@example.com", "meta", {"access_token": "EAA"})
    assert auth_client.post(f"/api/campaigns/{c['id']}/publish").status_code == 400


def test_meta_publish_pause_and_sync(auth_client, db, mock_http):
    connect(db, "owner@example.com", "meta", {"access_token": "EAA"}, {"ad_account_id": "act_1"})
    c = new_campaign(auth_client, lead_form={"form_id": "F1"})
    create = mock_http.post(f"{GRAPH}/act_1/campaigns").respond(json={"id": "C123"})
    p = auth_client.post(f"/api/campaigns/{c['id']}/publish").json()
    assert p["external_id"] == "C123" and p["status"] == "paused"
    assert b"OUTCOME_LEADS" in create.calls[0].request.content

    status = mock_http.post(f"{GRAPH}/C123").respond(json={"success": True})
    auth_client.patch(f"/api/campaigns/{c['id']}", json={"status": "active"})
    assert b"status=ACTIVE" in status.calls[0].request.content

    mock_http.get(f"{GRAPH}/C123/insights").respond(json={"data": [{"spend": "12.5", "impressions": "1000", "clicks": "40"}]})
    mock_http.get(f"{GRAPH}/F1/leads").respond(json={"data": [{"id": "L1", "field_data": [
        {"name": "full_name", "values": ["Meera"]}, {"name": "email", "values": ["meera@x.com"]},
        {"name": "phone_number", "values": ["+919000000002"]}]}]})
    s = auth_client.post(f"/api/campaigns/{c['id']}/sync").json()
    assert (s["spend"], s["impressions"], s["clicks"], s["ctr"], s["new_leads"]) == (12.5, 1000, 40, 4.0, 1)
    lead = auth_client.get("/api/leads").json()[0]
    assert lead["name"] == "Meera" and lead["source"] == "meta"
    # Syncing again doesn't duplicate the lead.
    auth_client.post(f"/api/campaigns/{c['id']}/sync")
    assert len(auth_client.get("/api/leads").json()) == 1


def test_meta_ad_accounts(auth_client, db, mock_http):
    assert auth_client.get("/api/campaigns/meta/ad-accounts").status_code == 400
    connect(db, "owner@example.com", "meta", {"access_token": "EAA"})
    mock_http.get(f"{GRAPH}/me/adaccounts").respond(json={"data": [{"id": "act_1", "name": "Main"}]})
    assert auth_client.get("/api/campaigns/meta/ad-accounts").json() == [{"id": "act_1", "name": "Main"}]


def test_campaigns_are_private(auth_client, other_client):
    c = new_campaign(auth_client)
    assert other_client.get("/api/campaigns").json() == []
    assert other_client.patch(f"/api/campaigns/{c['id']}", json={"name": "x"}).status_code == 404
    assert other_client.post(f"/api/campaigns/{c['id']}/publish").status_code == 404


# ---- WhatsApp -----------------------------------------------------------------
def test_sandbox_send_and_conversations(auth_client):
    m = auth_client.post("/api/whatsapp/send", json={"to": "+91 98765-43210", "body": "Hello", "name": "Ravi"}).json()
    assert m["contact"] == "919876543210" and m["status"] == "simulated"
    auth_client.post("/api/whatsapp/send", json={"to": "919876543210", "body": "Second"})
    auth_client.post("/api/whatsapp/send", json={"to": "911111111111", "body": "Other"})
    convos = auth_client.get("/api/whatsapp/conversations").json()
    assert [c["body"] for c in convos] == ["Other", "Second"]
    assert [m["body"] for m in auth_client.get("/api/whatsapp/messages/919876543210").json()] == ["Hello", "Second"]


def test_simulated_inbound_creates_lead(auth_client):
    auth_client.post("/api/whatsapp/simulate-inbound", json={"from": "919876543210", "body": "Price please", "name": "Ravi"})
    lead = auth_client.get("/api/leads").json()[0]
    assert lead["source"] == "whatsapp" and lead["phone"] == "+919876543210"


def test_real_send_via_cloud_api(auth_client, mock_http):
    auth_client.post("/api/integrations/whatsapp/key", json={"values": {"access_token": "EAAG", "phone_number_id": "PN1"}})
    route = mock_http.post(f"{GRAPH}/PN1/messages").respond(json={"messages": [{"id": "wamid.1"}]})
    m = auth_client.post("/api/whatsapp/send", json={"to": "919876543210", "body": "Hi"}).json()
    assert m["status"] == "sent" and route.calls[0].request.headers["authorization"] == "Bearer EAAG"


def test_failed_send_is_recorded(auth_client, mock_http):
    auth_client.post("/api/integrations/whatsapp/key", json={"values": {"access_token": "EAAG", "phone_number_id": "PN1"}})
    mock_http.post(f"{GRAPH}/PN1/messages").respond(400, json={"error": "bad"})
    assert auth_client.post("/api/whatsapp/send", json={"to": "919876543210", "body": "Hi"}).status_code == 502
    assert auth_client.get("/api/whatsapp/messages/919876543210").json()[0]["status"] == "failed"


def test_webhook_verification(client):
    ok = client.get("/api/public/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "aimva-verify", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get("/api/public/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"})
    assert bad.status_code == 403


def test_webhook_inbound_and_status_updates(auth_client, other_client, client, mock_http):
    auth_client.post("/api/integrations/whatsapp/key", json={"values": {"access_token": "EAAG", "phone_number_id": "PN1"}})
    mock_http.post(f"{GRAPH}/PN1/messages").respond(json={"messages": [{"id": "wamid.out"}]})
    auth_client.post("/api/whatsapp/send", json={"to": "919876543210", "body": "Hi"})
    payload = {"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "PN1"},
        "contacts": [{"wa_id": "919876543210", "profile": {"name": "Ravi"}}],
        "messages": [{"from": "919876543210", "id": "wamid.in", "type": "text", "text": {"body": "Book a visit"}}],
        "statuses": [{"id": "wamid.out", "status": "read"}],
    }}]}]}
    assert wa_post(client, payload).json() == {"ok": True}
    msgs = auth_client.get("/api/whatsapp/messages/919876543210").json()
    assert [(m["direction"], m["status"]) for m in msgs] == [("out", "read"), ("in", "received")]
    assert auth_client.get("/api/leads").json()[0]["name"] == "Ravi"
    assert other_client.get("/api/whatsapp/conversations").json() == []


def test_webhook_for_unknown_number_is_ignored(client):
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "UNKNOWN"},
                                                 "messages": [{"from": "1", "id": "x", "text": {"body": "hi"}}]}}]}]}
    assert wa_post(client, payload).json() == {"ok": True}


def test_malformed_webhook_does_not_500(client):
    raw = b"not json"
    sig = "sha256=" + hmac.new(META_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    assert client.post("/api/public/whatsapp/webhook", content=raw,
                       headers={"content-type": "application/json", "x-hub-signature-256": sig}).status_code == 400


def test_forged_whatsapp_webhooks_are_rejected(auth_client, client, monkeypatch):
    auth_client.post("/api/integrations/whatsapp/key", json={"values": {"access_token": "EAAG", "phone_number_id": "PN1"}})
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "PN1"},
                                                 "messages": [{"from": "919999999999", "id": "x", "text": {"body": "fake"}}]}}]}]}
    assert client.post("/api/public/whatsapp/webhook", json=payload).status_code == 403  # unsigned
    assert wa_post(client, payload, secret="wrong-secret").status_code == 403  # signed with the wrong secret
    assert wa_post(client, payload, signature="sha256=deadbeef").status_code == 403
    assert auth_client.get("/api/leads").json() == [] and auth_client.get("/api/whatsapp/conversations").json() == []
    # A public server without META_APP_SECRET refuses every webhook instead of trusting them.
    from app.config import settings
    monkeypatch.setattr(settings, "meta_app_secret", "")
    assert wa_post(client, payload).status_code == 403
    # Local development without the secret still works, so the inbox can be tried end to end.
    monkeypatch.setattr(settings, "public_url", "http://localhost:8000")
    assert wa_post(client, payload).json() == {"ok": True}


# ---- voice agent -----------------------------------------------------------------
def new_agent(c, **over):
    return c.post("/api/voice/agents", json={"name": "Sales", **over}).json()


def talk(c, call_id, text):
    r = c.post(f"/api/voice/calls/{call_id}/turn", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_agent_crud(auth_client):
    a = new_agent(auth_client, language="hi-IN")
    assert len(a["questions"]) == 4 and a["language"] == "hi-IN"
    r = auth_client.put(f"/api/voice/agents/{a['id']}", json={**a, "questions": ["Name?", "Phone?"]})
    assert r.json()["questions"] == ["Name?", "Phone?"]
    assert "te-IN" in auth_client.get("/api/voice/languages").json()
    auth_client.delete(f"/api/voice/agents/{a['id']}")
    assert auth_client.get("/api/voice/agents").json() == []


def test_full_qualification_call_creates_lead(auth_client):
    a = new_agent(auth_client)
    start = auth_client.post(f"/api/voice/agents/{a['id']}/calls").json()
    assert a["questions"][0] in start["reply"]
    cid = start["call"]["id"]
    talk(auth_client, cid, "My name is Priya Sharma")
    talk(auth_client, cid, "priya@acme.io or +91 99000 11122")
    talk(auth_client, cid, "A 2BHK, budget 50 lakhs")
    last = talk(auth_client, cid, "Saturday morning works great, thanks!")
    assert last["status"] == "completed" and last["call"]["lead_id"]
    assert last["call"]["sentiment"] > 0
    lead = auth_client.get("/api/leads").json()[0]
    assert lead["name"] == "Priya Sharma" and lead["email"] == "priya@acme.io" and lead["source"] == "voice"
    assert auth_client.post(f"/api/voice/calls/{cid}/turn", json={"text": "hello?"}).status_code == 400


def test_handoff_on_request_or_anger(auth_client):
    a = new_agent(auth_client, handoff_number="+911234567890")
    cid = auth_client.post(f"/api/voice/agents/{a['id']}/calls").json()["call"]["id"]
    r = talk(auth_client, cid, "Can I speak to a real person")
    assert r["status"] == "handoff" and "connect you" in r["reply"]

    cid2 = auth_client.post(f"/api/voice/agents/{a['id']}/calls").json()["call"]["id"]
    r = talk(auth_client, cid2, "This is absolutely horrible, worst service, I hate it")
    assert r["status"] == "handoff" and r["sentiment"] < -0.6


def test_end_call_early(auth_client):
    a = new_agent(auth_client)
    cid = auth_client.post(f"/api/voice/agents/{a['id']}/calls").json()["call"]["id"]
    talk(auth_client, cid, "I'm Arjun, reach me at arjun@x.com")
    c = auth_client.post(f"/api/voice/calls/{cid}/end").json()
    assert c["status"] == "completed"
    assert auth_client.get("/api/voice/calls").json()[0]["id"] == cid


def test_dial_needs_twilio_then_places_call(auth_client, mock_http):
    a = new_agent(auth_client)
    assert auth_client.post(f"/api/voice/agents/{a['id']}/dial", json={"to": "+919876543210"}).status_code == 400
    auth_client.post("/api/integrations/twilio/key", json={"values": {"account_sid": "AC1", "auth_token": "tok", "from_number": "+15550001"}})
    route = mock_http.post("https://api.twilio.com/2010-04-01/Accounts/AC1/Calls.json").respond(201, json={"sid": "CA1"})
    c = auth_client.post(f"/api/voice/agents/{a['id']}/dial", json={"to": "+919876543210"}).json()
    body = route.calls[0].request.content.decode()
    assert "From=%2B15550001" in body and f"twilio%2F{c['id']}%2Fstart" in body
    assert c["channel"] == "phone"


def tw_post(client, path, data=None, token="tok"):
    """POST the way Twilio does: form params signed with the account's auth token over the public URL."""
    from app.webhooks import twilio_signature
    data = data or {}
    sig = twilio_signature(token, "http://testserver" + path, data)
    return client.post(path, data=data, headers={"x-twilio-signature": sig})


def test_twilio_webhooks_drive_the_dialogue(auth_client, client):
    auth_client.post("/api/integrations/twilio/key", json={"values": {"account_sid": "AC1", "auth_token": "tok", "from_number": "+15550001"}})
    a = new_agent(auth_client, questions=["Your name?", "Your email?"], handoff_number="+911234567890")
    cid = auth_client.post(f"/api/voice/agents/{a['id']}/calls").json()["call"]["id"]
    base = f"/api/public/voice/twilio/{cid}"
    r = tw_post(client, f"{base}/start")
    assert r.headers["content-type"].startswith("application/xml") and "<Gather" in r.text
    r = tw_post(client, f"{base}/turn", {"SpeechResult": ""})
    assert "didn't catch" in r.text
    r = tw_post(client, f"{base}/turn", {"SpeechResult": "Kiran & <Co>"})
    assert "Your email?" in r.text and "<Co>" not in r.text  # user speech never breaks the XML
    r = tw_post(client, f"{base}/turn", {"SpeechResult": "I want a human"})
    assert "<Dial>+911234567890</Dial>" in r.text


def test_forged_twilio_webhooks_are_rejected(auth_client, client):
    a = new_agent(auth_client, questions=["Your name?"])
    cid = auth_client.post(f"/api/voice/agents/{a['id']}/calls").json()["call"]["id"]
    base = f"/api/public/voice/twilio/{cid}"
    assert tw_post(client, f"{base}/start").status_code == 403  # no Twilio connected: nothing to verify against
    auth_client.post("/api/integrations/twilio/key", json={"values": {"account_sid": "AC1", "auth_token": "tok", "from_number": "+15550001"}})
    assert client.post(f"{base}/start").status_code == 403  # unsigned
    assert tw_post(client, f"{base}/turn", {"SpeechResult": "Fake Name"}, token="wrong").status_code == 403
    # A valid signature over different params doesn't carry over (the speech text is signed too).
    from app.webhooks import twilio_signature
    sig = twilio_signature("tok", f"http://testserver{base}/turn", {"SpeechResult": "Real"})
    assert client.post(f"{base}/turn", data={"SpeechResult": "Forged"}, headers={"x-twilio-signature": sig}).status_code == 403
    assert tw_post(client, f"{base}/start").status_code == 200


def test_voice_is_private(auth_client, other_client):
    a = new_agent(auth_client)
    cid = auth_client.post(f"/api/voice/agents/{a['id']}/calls").json()["call"]["id"]
    assert other_client.get("/api/voice/agents").json() == []
    assert other_client.post(f"/api/voice/agents/{a['id']}/calls").status_code == 404
    assert other_client.post(f"/api/voice/calls/{cid}/turn", json={"text": "hi"}).status_code == 404
    assert other_client.get("/api/voice/calls").json() == []


# ---- analytics ---------------------------------------------------------------------
def test_empty_analytics(auth_client):
    o = auth_client.get("/api/analytics/overview").json()
    assert o["kpis"]["leads"] == 0 and o["kpis"]["roi"] is None and len(o["series"]) == 30
    assert "No leads yet" in auth_client.get("/api/analytics/insights").json()["items"][0]


def test_analytics_numbers(auth_client, db):
    a = auth_client.post("/api/leads", json={"email": "a@x.com", "source": "website"}).json()
    auth_client.post("/api/leads", json={"email": "b@x.com", "source": "website"})
    auth_client.post("/api/leads", json={"phone": "+919999999999", "source": "voice"})
    auth_client.patch(f"/api/leads/{a['id']}", json={"stage": "won", "value": 300})
    c = new_campaign(auth_client)
    row = db.get(Campaign, c["id"])
    row.spend = 100
    db.commit()
    o = auth_client.get("/api/analytics/overview?days=7").json()
    k = o["kpis"]
    assert k["leads"] == 3 and k["spend"] == 100 and k["cpl"] == 33.33 and k["roi"] == 200 and k["won_value"] == 300
    assert o["by_source"][0] == {"source": "website", "count": 2}
    assert {f["stage"]: f["count"] for f in o["funnel"]}["won"] == 1
    assert len(o["series"]) == 7 and sum(p["leads"] for p in o["series"]) == 3
    assert "'website'" in auth_client.get("/api/analytics/insights").json()["items"][0]


def test_analytics_days_bounded(auth_client):
    assert auth_client.get("/api/analytics/overview?days=0").status_code == 422
    assert auth_client.get("/api/analytics/overview?days=100000").status_code == 422


def test_analytics_are_private(auth_client, other_client):
    auth_client.post("/api/leads", json={"email": "a@x.com"})
    assert other_client.get("/api/analytics/overview").json()["kpis"]["leads"] == 0


def test_conversation_keeps_contact_name_after_our_reply(auth_client):
    auth_client.post("/api/whatsapp/simulate-inbound", json={"from": "919876543210", "body": "Hi", "name": "Ravi"})
    auth_client.post("/api/whatsapp/send", json={"to": "919876543210", "body": "Hello Ravi"})
    [convo] = auth_client.get("/api/whatsapp/conversations").json()
    assert convo["body"] == "Hello Ravi" and convo["contact_name"] == "Ravi"


def test_site_conversion_never_exceeds_100(auth_client, client):
    site = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False}).json()
    auth_client.post(f"/api/sites/{site['id']}/deploy", json={"target": "aimva"})
    for i in range(3):
        client.post(f"/api/public/sites/{site['slug']}/lead", data={"phone": f"+91999999990{i}"})
    assert auth_client.get("/api/analytics/overview").json()["kpis"]["conversion"] == 100.0
