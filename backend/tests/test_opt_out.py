"""Leads who reply STOP get no more WhatsApp messages or calls, on any path, until they reply START."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app import opt_out
from app.agents import concierge
from app.models import FollowUp, OptOut, WaScheduled, utcnow
from app.routers.whatsapp import send_due

from .helpers import connect
from .test_agents import fake_dns, lead_form, profile, publish  # noqa: F401  (fake_dns is a fixture)
from .test_engage import wa_post

GRAPH = "https://graph.facebook.com/v21.0"
PHONE = "+919876543210"
CONTACT = "919876543210"


@pytest.mark.parametrize("text", [
    "STOP", "stop", "Stop.", " STOP!!! ", "STOP🛑", "Please stop", "stop messaging me", "Stop sending messages please", "Stop promotions",
    "STOP ALL", "stopall", "Unsubscribe", "unsubscribe me", "opt out", "Opt-out", "Do not message me",
    "please don't contact me again", "remove me from the list", "no more messages",
    "बंद", "बंद करो", "कृपया मैसेज बंद करें", "मैसेज मत भेजो", "band karo", "Band kar do please", "msg mat bhejo",
    "message band karo bhai", "நிறுத்து", "நிறுத்துங்கள்", "ఆపండి", "aapu", "ನಿಲ್ಲಿಸಿ", "നിർത്തുക", "നിര്‍ത്തുക",
    "বন্ধ করুন", "બંધ કરો", "ਬੰਦ ਕਰੋ", "ବନ୍ଦ", "توقف", "إلغاء الاشتراك",
])
def test_opt_out_words(text):
    assert opt_out.wants_out(text), text


@pytest.mark.parametrize("text", [
    "Can you stop by on Saturday?", "Don't stop the offer, I want it", "What time does the bus stop?",
    "Stop. Call me tomorrow at 5", "Is the price final or will it go down?", "Band baja baraat booking for December",
    "I want to unsubscribe from my old plan and take the new one", "", "Hi", "start", "Please send the brochure",
    "do not call after 9pm", "stop calling after 9pm",
])
def test_ordinary_messages_do_not_opt_out(text):
    assert not opt_out.wants_out(text), text


def test_start_words():
    assert opt_out.wants_back_in("START") and opt_out.wants_back_in("start please") and opt_out.wants_back_in("Unstop")
    assert not opt_out.wants_back_in("When can we start the course?") and not opt_out.wants_back_in("stop")


def _wa(auth_client, db):
    connect(db, "owner@example.com", "whatsapp", {"access_token": "t"}, {"phone_number_id": "123"})


def _inbound(auth_client, body, frm=CONTACT, name="Ravi"):
    r = auth_client.post("/api/whatsapp/simulate-inbound", json={"from": frm, "body": body, "name": name})
    assert r.status_code == 200, r.text


def test_stop_on_whatsapp_blocks_every_send(auth_client, db, mock_http):
    lead = auth_client.post("/api/leads", json={"name": "Ravi", "phone": "98765 43210"}).json()  # stored without +91
    _wa(auth_client, db)
    route = mock_http.post(f"{GRAPH}/123/messages").respond(json={"messages": [{"id": "wamid.1"}]})
    _inbound(auth_client, "Hi, price?")
    assert auth_client.post("/api/whatsapp/send", json={"to": CONTACT, "body": "It's 80L"}).status_code == 200
    queued = auth_client.post("/api/whatsapp/scheduled", json={"to": CONTACT, "body": "Reminder",
                                                               "send_at": (utcnow() + timedelta(hours=1)).isoformat() + "Z"}).json()
    _inbound(auth_client, "STOP")
    sent_before = route.call_count

    row = auth_client.get(f"/api/leads/{lead['id']}").json()
    assert row["opted_out"] and row["opted_out_at"] and not row["needs_reply"]  # a STOP isn't waiting for an answer
    assert any(t["kind"] == "opt_out" and "STOP" in t["body"] for t in row["timeline"])
    assert auth_client.get("/api/whatsapp/conversations").json()[0]["opted_out"] is True

    for path, body in [("/api/whatsapp/send", {"to": CONTACT, "body": "Are you sure?"}),
                       ("/api/whatsapp/send", {"to": "+91 98765-43210", "body": "Other spelling"}),
                       (f"/api/leads/{lead['id']}/reply", {"text": "Sorry to see you go"}),
                       (f"/api/leads/{lead['id']}/reply", {"text": "From my phone", "own_app": True}),
                       (f"/api/leads/{lead['id']}/reply", {"template": True}),
                       (f"/api/leads/{lead['id']}/reply-draft", {}),
                       ("/api/whatsapp/scheduled", {"to": CONTACT, "body": "Later", "send_at": (utcnow() + timedelta(hours=2)).isoformat() + "Z"})]:
        r = auth_client.post(path, json=body)
        assert r.status_code == 409 and "STOP" in r.json()["detail"], (path, r.text)
    # What was already queued is cancelled, and nothing went out.
    assert db.get(WaScheduled, queued["id"]).status == "cancelled"
    assert send_due(db, utcnow() + timedelta(hours=3)) == 0
    assert route.call_count == sent_before


def test_stop_cancels_concierge_follow_ups_and_blocks_new_ones(auth_client, client, db):
    profile(auth_client)
    s = publish(auth_client)
    lead_form(client, s["slug"])  # Ravi, +919812345678: welcome drafted, day 2 + day 7 queued
    lead = auth_client.get("/api/leads").json()[0]
    _inbound(auth_client, "please stop", frm="919812345678")
    notes = [f.note for f in db.scalars(select(FollowUp).where(FollowUp.lead_id == lead["id"]))]
    assert notes == ["The lead opted out", "The lead opted out"]
    assert concierge.run_due(db, datetime.utcnow() + timedelta(days=8)) == 0
    # The same person fills the form again: a new lead row, but no welcome and no follow-ups.
    lead_form(client, s["slug"], name="Ravi K", email="ravi@x.com")
    rows = auth_client.get("/api/leads").json()
    assert all(r["opted_out"] for r in rows if r["phone"].endswith("9812345678"))
    assert db.scalar(select(FollowUp).where(FollowUp.status == "pending")) is None


def test_no_calls_after_stop(auth_client, client, db, mock_http):
    lead = auth_client.post("/api/leads", json={"name": "Ravi", "phone": PHONE}).json()
    agent = auth_client.post("/api/voice/agents", json={"name": "Sales"}).json()
    auth_client.post("/api/integrations/twilio/key", json={"values": {"account_sid": "AC1", "auth_token": "t", "from_number": "+15550001"}})
    route = mock_http.post("https://api.twilio.com/2010-04-01/Accounts/AC1/Calls.json").respond(201, json={"sid": "CA1"})
    _inbound(auth_client, "बंद करो")
    r = auth_client.post(f"/api/leads/{lead['id']}/call", json={})
    assert r.status_code == 409 and "STOP" in r.json()["detail"]
    assert auth_client.post(f"/api/voice/agents/{agent['id']}/dial", json={"to": PHONE}).status_code == 409
    assert not route.called


def test_start_opts_back_in(auth_client, db):
    lead = auth_client.post("/api/leads", json={"name": "Ravi", "phone": PHONE}).json()
    _inbound(auth_client, "unsubscribe")
    assert auth_client.get(f"/api/leads/{lead['id']}").json()["opted_out"]
    _inbound(auth_client, "START")
    row = auth_client.get(f"/api/leads/{lead['id']}").json()
    assert not row["opted_out"] and any(t["kind"] == "opt_in" for t in row["timeline"])
    assert db.scalar(select(OptOut)) is None
    assert auth_client.post("/api/whatsapp/send", json={"to": CONTACT, "body": "Welcome back"}).status_code == 200


def test_business_can_mark_and_resume_by_hand(auth_client, other_client):
    lead = auth_client.post("/api/leads", json={"name": "Ravi", "phone": PHONE}).json()
    assert other_client.post(f"/api/leads/{lead['id']}/opt-out", json={}).status_code == 404
    v = auth_client.post(f"/api/leads/{lead['id']}/opt-out", json={"note": "Asked on the phone"}).json()
    assert v["opted_out"] and v["timeline"][0]["title"].startswith("Opted out")
    assert auth_client.post("/api/whatsapp/send", json={"to": PHONE, "body": "x"}).status_code == 409
    # Another business is not affected by this one's opt-out list.
    assert other_client.post("/api/whatsapp/send", json={"to": PHONE, "body": "x"}).status_code == 200
    v = auth_client.delete(f"/api/leads/{lead['id']}/opt-out").json()
    assert not v["opted_out"] and v["timeline"][0]["title"] == "Messages resumed"
    assert auth_client.post("/api/whatsapp/send", json={"to": PHONE, "body": "x"}).status_code == 200


def test_stop_from_the_real_webhook_and_a_template_button(auth_client, client, db):
    auth_client.post("/api/integrations/whatsapp/key", json={"values": {"access_token": "EAAG", "phone_number_id": "PN1"}})
    payload = lambda msg: {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "PN1"},
                                                            "contacts": [{"wa_id": CONTACT, "profile": {"name": "Ravi"}}],
                                                            "messages": [msg]}}]}]}
    assert wa_post(client, payload({"from": CONTACT, "id": "w1", "type": "text", "text": {"body": "Hi"}})).status_code == 200
    assert not auth_client.get("/api/leads").json()[0]["opted_out"]
    # Meta's own marketing-template button.
    assert wa_post(client, payload({"from": CONTACT, "id": "w2", "type": "button",
                                    "button": {"text": "Stop promotions", "payload": "Stop promotions"}})).status_code == 200
    assert auth_client.get("/api/leads").json()[0]["opted_out"]
    assert wa_post(client, payload({"from": CONTACT, "id": "w3", "type": "interactive",
                                    "interactive": {"button_reply": {"id": "b", "title": "Start"}}})).status_code == 200
    assert not auth_client.get("/api/leads").json()[0]["opted_out"]


def test_call_waiting_for_9am_is_not_placed_after_stop(auth_client, mock_http, db, monkeypatch):
    from app import call_hours
    from app.models import Call
    from app.routers.voice import place_due_calls
    state = {"now": datetime(2026, 11, 8, 17, 0)}  # 22:30 IST: calls wait for 9 am
    monkeypatch.setattr(call_hours, "now", lambda: state["now"])
    monkeypatch.setattr(call_hours, "START_HOUR", 9)  # conftest opens calling hours all day; use the real window
    monkeypatch.setattr(call_hours, "END_HOUR", 21)
    auth_client.post("/api/integrations/twilio/key", json={"values": {"account_sid": "AC1", "auth_token": "t", "from_number": "+15550001"}})
    auth_client.post("/api/voice/agents", json={"name": "Sales"})
    route = mock_http.post("https://api.twilio.com/2010-04-01/Accounts/AC1/Calls.json").respond(201, json={"sid": "CA1"})
    a = auth_client.post("/api/leads", json={"name": "Ravi", "phone": PHONE}).json()
    b = auth_client.post("/api/leads", json={"name": "Asha", "phone": "+919800000002"}).json()
    assert auth_client.post(f"/api/leads/{a['id']}/call", json={}).json()["call_scheduled_for"]
    assert auth_client.post(f"/api/leads/{b['id']}/call", json={}).json()["call_scheduled_for"]
    _inbound(auth_client, "STOP")  # Ravi texts STOP overnight
    assert db.scalar(select(Call).where(Call.lead_id == a["id"])).status == "cancelled"
    # Even a waiting call the opt-out didn't catch (number stored another way) is checked when it's due.
    other = db.scalar(select(Call).where(Call.lead_id == b["id"]))
    opt_out.opt_out(db, other.user_id, "919800000002", "manual")
    other.status = "scheduled"
    db.commit()
    state["now"] = datetime(2026, 11, 9, 3, 30)  # 9:00 am IST
    assert place_due_calls(db) == 0 and not route.called
    db.refresh(other)
    assert other.status == "cancelled"
