"""Replying to leads in their own language, who is waiting, and WhatsApp's 24-hour rule."""
import json
from datetime import timedelta

from sqlalchemy import select

from app import lead_reply
from app.models import User, WaMessage, utcnow

from .helpers import connect

GRAPH = "https://graph.facebook.com/v21.0"


def add(c, **kw):
    r = c.post("/api/leads", json={"name": "Ravi Kumar", "phone": "+919876543210", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def wrote(db, contact="919876543210", body="Hello?", ago=timedelta(minutes=5)):
    uid = db.scalar(select(User.id).where(User.email == "owner@example.com"))
    db.add(WaMessage(user_id=uid, contact=contact, direction="in", body=body, status="received", created_at=utcnow() - ago))
    db.commit()


def test_language_detection():
    assert lead_reply.detect("मुझे फ्लैट की कीमत जाननी है") == "hi-IN"
    assert lead_reply.detect("मला फ्लॅटची किंमत हवी आहे") == "mr-IN"
    assert lead_reply.detect("Bhai 2bhk ka price kitna hai?") == "hi-Latn"
    assert lead_reply.detect("எனக்கு விலை தெரிய வேண்டும்") == "ta-IN"
    assert lead_reply.detect("Please call me in Telugu") == "te-IN"
    assert lead_reply.detect("What is the price?") is None


def test_local_numbers_get_the_country_code():
    assert lead_reply.wa_number("98765 43210") == "919876543210"
    assert lead_reply.wa_number("098765 43210") == "919876543210"
    assert lead_reply.wa_number("+91 98765-43210") == "919876543210"
    assert lead_reply.wa_number("+1 415 555 0100") == "14155550100"


def test_leads_waiting_on_you_come_first(auth_client, db):
    old = add(auth_client, name="Old", phone="+919800000001")
    replied = add(auth_client, name="Done", phone="+919800000002")
    auth_client.post(f"/api/leads/{replied['id']}/reply", json={"text": "Hi!"})
    hot = add(auth_client, name="Hot", phone="+919800000003", message="Ready to buy this week, budget 80 lakh, call me")
    rows = auth_client.get("/api/leads").json()
    assert [r["name"] for r in rows][:2] == ["Hot", "Old"] and rows[-1]["name"] == "Done"
    assert rows[0]["needs_reply"] and rows[0]["waiting_since"] and not rows[-1]["needs_reply"]
    assert rows[-1]["stage"] == "contacted" and rows[-1]["last_out_at"]
    # The lead writes back: they're waiting on you again.
    wrote(db, "919800000002", "Is Saturday ok?", ago=timedelta(seconds=-1))
    done = next(r for r in auth_client.get("/api/leads").json() if r["name"] == "Done")
    assert done["needs_reply"] and done["waiting_since"] == done["last_in_at"]
    assert [r["name"] for r in auth_client.get("/api/leads?sort=newest").json()] == ["Hot", "Done", "Old"]
    assert old["id"]


def test_closed_leads_never_wait(auth_client):
    lead = add(auth_client)
    auth_client.patch(f"/api/leads/{lead['id']}", json={"stage": "lost"})
    assert auth_client.get("/api/leads").json()[0]["needs_reply"] is False


def test_draft_follows_the_language_without_ai(auth_client, db):
    lead = add(auth_client, message="எனக்கு 2BHK விலை தெரிய வேண்டும்")
    assert lead["language"] == "ta-IN"
    d = auth_client.post(f"/api/leads/{lead['id']}/reply-draft", json={}).json()
    assert d["language_name"] == "Tamil" and d["intent"] == "welcome" and d["text"].startswith("வணக்கம் Ravi")
    assert d["by"] == "ready_made" and d["connected"] is False and d["needs_template"] is False
    visit = auth_client.post(f"/api/leads/{lead['id']}/reply-draft", json={"intent": "visit"}).json()
    assert visit["text"] != d["text"] and visit["intent"] == "visit"


def test_ai_draft_is_used_only_in_the_right_language(auth_client, monkeypatch):
    lead = add(auth_client, message="Bhai 2bhk ka price kitna hai?")
    prompts = []

    def fake(db, user, prompt, system):
        prompts.append(system + prompt)
        return "Namaste Ravi! 2BHK ke prices aapke budget ke hisaab se bhej dete hain, kab baat karein?"
    monkeypatch.setattr(lead_reply, "_write", fake)
    d = auth_client.post(f"/api/leads/{lead['id']}/reply-draft", json={}).json()
    assert d["by"] == "ai" and d["language"] == "hi-Latn" and d["text"].startswith("Namaste Ravi!")
    assert "Hinglish" in prompts[0] and "kitna hai" in prompts[0]
    # An answer in the wrong language falls back to the ready-made reply.
    auth_client.patch(f"/api/leads/{lead['id']}", json={"language": "te-IN"})
    d = auth_client.post(f"/api/leads/{lead['id']}/reply-draft", json={}).json()
    assert d["by"] == "ready_made" and d["text"].startswith("నమస్కారం Ravi")


def test_language_can_be_corrected_and_follows_new_messages(auth_client, db):
    lead = add(auth_client)
    assert lead["language"] == ""
    assert auth_client.patch(f"/api/leads/{lead['id']}", json={"language": "klingon"}).status_code == 400
    assert auth_client.patch(f"/api/leads/{lead['id']}", json={"language": "bn-IN"}).json()["language_name"] == "Bengali"
    auth_client.post("/api/whatsapp/simulate-inbound", json={"from": "919876543210", "body": "మీ ధర ఎంత? వివరాలు పంపండి", "name": "Ravi"})
    assert auth_client.get(f"/api/leads/{lead['id']}").json()["language"] == "te-IN"
    langs = {l["code"] for l in auth_client.get("/api/leads/meta/languages").json()}
    assert {"en", "hi-IN", "hi-Latn", "ta-IN"} <= langs


def test_connected_reply_inside_the_window_sends_text(auth_client, db, mock_http):
    connect(db, "owner@example.com", "whatsapp", {"access_token": "t"}, {"phone_number_id": "123"})
    route = mock_http.post(f"{GRAPH}/123/messages").respond(json={"messages": [{"id": "wamid.1"}]})
    lead = add(auth_client, phone="98765 43210")
    wrote(db)
    d = auth_client.post(f"/api/leads/{lead['id']}/reply-draft", json={}).json()
    assert d["window_open"] and not d["needs_template"] and d["intent"] == "reply"
    v = auth_client.post(f"/api/leads/{lead['id']}/reply", json={"text": "Yes, Saturday 11am works"}).json()
    body = json.loads(route.calls.last.request.content)
    assert body["to"] == "919876543210" and body["text"]["body"] == "Yes, Saturday 11am works"
    assert v["stage"] == "contacted" and not v["needs_reply"]
    assert [i["body"] for i in v["timeline"] if i["kind"] == "whatsapp"][0] == "Yes, Saturday 11am works"


def test_closed_window_needs_the_approved_template(auth_client, db, mock_http):
    connect(db, "owner@example.com", "whatsapp", {"access_token": "t"}, {"phone_number_id": "123"})
    route = mock_http.post(f"{GRAPH}/123/messages").respond(json={"messages": [{"id": "wamid.1"}]})
    lead = add(auth_client, message="मुझे कीमत बताइए, कब मिल सकते हैं")
    wrote(db, body="old message", ago=timedelta(days=2))
    d = auth_client.post(f"/api/leads/{lead['id']}/reply-draft", json={}).json()
    assert d["needs_template"] and d["template"] == "" and "approved template" in d["note"]
    assert auth_client.post(f"/api/leads/{lead['id']}/reply", json={"text": "Hi"}).status_code == 409
    assert auth_client.post(f"/api/leads/{lead['id']}/reply", json={"template": True}).status_code == 400
    assert not route.called
    auth_client.patch("/api/integrations/whatsapp/meta", json={"meta": {"first_message_template": "lead_hello",
                                                                       "template_languages": ["en", "hi"]}})
    d = auth_client.post(f"/api/leads/{lead['id']}/reply-draft", json={}).json()
    assert d["template"] == "lead_hello"
    v = auth_client.post(f"/api/leads/{lead['id']}/reply", json={"template": True}).json()
    sent = json.loads(route.calls.last.request.content)
    assert sent["template"]["name"] == "lead_hello" and sent["template"]["language"]["code"] == "hi"
    assert v["stage"] == "contacted"


def test_reply_is_private_and_needs_a_phone(auth_client, other_client):
    lead = add(auth_client)
    assert other_client.post(f"/api/leads/{lead['id']}/reply-draft", json={}).status_code == 404
    assert other_client.post(f"/api/leads/{lead['id']}/reply", json={"text": "x"}).status_code == 404
    no_phone = auth_client.post("/api/leads", json={"name": "Mail only", "email": "m@x.com"}).json()
    assert auth_client.post(f"/api/leads/{no_phone['id']}/reply-draft", json={}).status_code == 400
    assert auth_client.post(f"/api/leads/{lead['id']}/reply", json={"text": "  "}).status_code == 400


def test_sending_from_your_own_whatsapp_is_recorded_without_the_api(auth_client, db, mock_http):
    # Outside the 24-hour window with no template: the owner sends the draft from their own phone via a wa.me link.
    connect(db, "owner@example.com", "whatsapp", {"access_token": "t"}, {"phone_number_id": "123"})
    route = mock_http.post(f"{GRAPH}/123/messages").respond(json={"messages": [{"id": "wamid.1"}]})
    lead = add(auth_client, phone="98765 43210")
    d = auth_client.post(f"/api/leads/{lead['id']}/reply-draft", json={}).json()
    assert d["needs_template"] and d["wa_number"] == "919876543210" and "your own WhatsApp" in d["note"]
    assert auth_client.post(f"/api/leads/{lead['id']}/reply", json={"own_app": True, "text": " "}).status_code == 400
    v = auth_client.post(f"/api/leads/{lead['id']}/reply", json={"own_app": True, "text": d["text"]}).json()
    assert not route.called and v["stage"] == "contacted" and not v["needs_reply"]
    sent = next(i for i in v["timeline"] if i["kind"] == "whatsapp")
    assert sent["title"] == "Sent from your WhatsApp" and sent["meta"]["status"] == "own_app"
