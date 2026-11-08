"""Outbound calls only 9 am to 9 pm in the lead's time (TRAI). Outside that they wait, they are never dropped."""
from datetime import datetime

import pytest

from app import call_hours

PHONE = "+919876543210"
TWILIO = {"values": {"account_sid": "AC1", "auth_token": "tok", "from_number": "+15550001"}}
URL = "https://api.twilio.com/2010-04-01/Accounts/AC1/Calls.json"


@pytest.fixture
def clock(monkeypatch):
    state = {"now": datetime(2026, 11, 8, 17, 0)}  # 22:30 IST: closed
    monkeypatch.setattr(call_hours, "now", lambda: state["now"])
    return state


def test_window_follows_the_leads_country():
    # 03:29 UTC = 08:59 IST (closed), 03:30 UTC = 09:00 IST (open), 15:30 UTC = 21:00 IST (closed)
    assert not call_hours.is_open(PHONE, datetime(2026, 11, 8, 3, 29))
    assert call_hours.is_open(PHONE, datetime(2026, 11, 8, 3, 30))
    assert call_hours.is_open(PHONE, datetime(2026, 11, 8, 15, 29))
    assert not call_hours.is_open(PHONE, datetime(2026, 11, 8, 15, 30))
    # Dubai is UTC+4: 05:00 UTC is 9 am there, 10:30 am in India
    assert call_hours.offset_minutes("+971501234567") == 240
    assert call_hours.is_open("+971501234567", datetime(2026, 11, 8, 5, 0))
    assert not call_hours.is_open("+971501234567", datetime(2026, 11, 8, 4, 59))
    # Unknown / local numbers use the business time zone (IST by default)
    assert call_hours.offset_minutes("+14155550100") == 330
    assert call_hours.offset_minutes("09876543210") == 330


def test_next_open_is_the_coming_9am():
    late = datetime(2026, 11, 8, 17, 0)  # 22:30 IST -> 09:00 IST next day = 03:30 UTC
    assert call_hours.next_open(PHONE, late) == datetime(2026, 11, 9, 3, 30)
    early = datetime(2026, 11, 8, 0, 0)  # 05:30 IST -> 09:00 IST same day
    assert call_hours.next_open(PHONE, early) == datetime(2026, 11, 8, 3, 30)
    day = datetime(2026, 11, 8, 6, 0)
    assert call_hours.next_open(PHONE, day) == day


def test_night_call_waits_and_goes_out_at_9am(auth_client, mock_http, clock, db):
    from app.routers.voice import place_due_calls
    auth_client.post("/api/integrations/twilio/key", json=TWILIO)
    auth_client.post("/api/voice/agents", json={"name": "Sales"})
    lead = auth_client.post("/api/leads", json={"name": "Ravi", "phone": PHONE}).json()
    route = mock_http.post(URL).respond(201, json={"sid": "CA1"})

    v = auth_client.post(f"/api/leads/{lead['id']}/call", json={}).json()
    assert not route.called  # 10:30 pm their time: nothing dialled
    assert v["call_scheduled_for"] == "2026-11-09T03:30:00" and "9:00 am tomorrow" in v["call_note"]
    call = next(i for i in v["timeline"] if i["kind"] == "call")
    assert call["meta"]["status"] == "scheduled" and "9:00 am" in call["title"]
    # Pressing it again doesn't queue a second call
    auth_client.post(f"/api/leads/{lead['id']}/call", json={})
    assert len([c for c in auth_client.get("/api/voice/calls").json() if c["status"] == "scheduled"]) == 1

    clock["now"] = datetime(2026, 11, 9, 3, 29)  # 8:59 am: still waiting
    assert place_due_calls(db, clock["now"]) == 0 and not route.called
    clock["now"] = datetime(2026, 11, 9, 3, 30)  # 9:00 am
    assert place_due_calls(db, clock["now"]) == 1
    assert "To=%2B919876543210" in route.calls[0].request.content.decode()
    c = auth_client.get("/api/voice/calls").json()[0]
    assert c["status"] == "active" and c["scheduled_for"] is None
    assert auth_client.get(f"/api/leads/{lead['id']}").json()["stage"] == "contacted"
    assert place_due_calls(db, clock["now"]) == 0  # placed once only


def test_daytime_call_goes_straight_out(auth_client, mock_http, clock):
    clock["now"] = datetime(2026, 11, 8, 6, 0)  # 11:30 am IST
    auth_client.post("/api/integrations/twilio/key", json=TWILIO)
    a = auth_client.post("/api/voice/agents", json={"name": "Sales"}).json()
    route = mock_http.post(URL).respond(201, json={"sid": "CA1"})
    c = auth_client.post(f"/api/voice/agents/{a['id']}/dial", json={"to": PHONE}).json()
    assert route.called and c["status"] == "active" and c["scheduled_for"] is None


def test_waiting_call_can_be_cancelled_and_old_ones_expire(auth_client, mock_http, clock, db):
    from app.routers.voice import place_due_calls
    auth_client.post("/api/integrations/twilio/key", json=TWILIO)
    a = auth_client.post("/api/voice/agents", json={"name": "Sales"}).json()
    route = mock_http.post(URL).respond(201, json={"sid": "CA1"})
    c = auth_client.post(f"/api/voice/agents/{a['id']}/dial", json={"to": PHONE}).json()
    assert c["status"] == "scheduled"
    assert auth_client.post(f"/api/voice/calls/{c['id']}/end").json()["status"] == "cancelled"
    auth_client.post(f"/api/voice/agents/{a['id']}/dial", json={"to": "+919876500000"})
    clock["now"] = datetime(2026, 11, 11, 6, 0)  # three days later: too late to call out of the blue
    assert place_due_calls(db, clock["now"]) == 0 and not route.called
    assert {x["status"] for x in auth_client.get("/api/voice/calls").json()} == {"cancelled"}


def test_twilio_missing_is_still_said_at_night(auth_client, clock):
    a = auth_client.post("/api/voice/agents", json={"name": "Sales"}).json()
    r = auth_client.post(f"/api/voice/agents/{a['id']}/dial", json={"to": PHONE})
    assert r.status_code == 400 and "Twilio" in r.json()["detail"]
