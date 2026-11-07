"""Scheduled WhatsApp messages: schedule, list, cancel, send once when due, and the 24-hour rule."""
import json
from datetime import datetime, timedelta

import httpx

from app.agents import scheduler
from app.models import WaMessage, WaScheduled, utcnow
from app.routers.whatsapp import send_due

from .helpers import connect

SEND_URL = "https://graph.facebook.com/v21.0/123/messages"


def later(minutes=60):
    return (utcnow() + timedelta(minutes=minutes)).isoformat() + "Z"


def test_schedule_list_cancel(auth_client, other_client):
    s = auth_client.post("/api/whatsapp/scheduled", json={"to": "+91 98765-43210", "body": "Reminder: visit at 5", "name": "Ravi",
                                                          "send_at": later()}).json()
    assert s["status"] == "scheduled" and s["to"] == "919876543210"
    assert [x["id"] for x in auth_client.get("/api/whatsapp/scheduled").json()] == [s["id"]]
    assert other_client.get("/api/whatsapp/scheduled").json() == []
    assert other_client.delete(f"/api/whatsapp/scheduled/{s['id']}").status_code == 404
    assert auth_client.delete(f"/api/whatsapp/scheduled/{s['id']}").json()["status"] == "cancelled"
    assert auth_client.delete(f"/api/whatsapp/scheduled/{s['id']}").status_code == 409


def test_time_rules(auth_client):
    past = (utcnow() - timedelta(minutes=5)).isoformat() + "Z"
    assert auth_client.post("/api/whatsapp/scheduled", json={"to": "919876543210", "body": "x", "send_at": past}).status_code == 400
    far = (utcnow() + timedelta(days=120)).isoformat() + "Z"
    assert auth_client.post("/api/whatsapp/scheduled", json={"to": "919876543210", "body": "x", "send_at": far}).status_code == 400
    assert auth_client.post("/api/whatsapp/scheduled", json={"to": "919876543210", "body": " ", "send_at": later()}).status_code == 400
    assert auth_client.post("/api/whatsapp/scheduled", json={"to": "919876543210", "template": "Bad Name!", "send_at": later()}).status_code == 422


def test_time_without_zone_is_business_time(auth_client, db):
    local = (utcnow() + timedelta(minutes=330 + 60)).replace(microsecond=0)  # an hour from now, in IST
    s = auth_client.post("/api/whatsapp/scheduled", json={"to": "919876543210", "body": "x", "send_at": local.isoformat()}).json()
    sent_at = datetime.fromisoformat(s["send_at"].rstrip("Z"))
    assert abs((sent_at - (local - timedelta(minutes=330))).total_seconds()) < 1


def test_due_messages_are_sent_once(auth_client, db, mock_http):
    connect(db, "owner@example.com", "whatsapp", {"access_token": "t"}, {"phone_number_id": "123"})
    auth_client.post("/api/whatsapp/simulate-inbound", json={"from": "919876543210", "body": "Hi", "name": "Ravi"})
    route = mock_http.post(SEND_URL).mock(return_value=httpx.Response(200, json={"messages": [{"id": "wamid.1"}]}))
    s = auth_client.post("/api/whatsapp/scheduled", json={"to": "919876543210", "body": "See you at 5", "send_at": later(5)}).json()
    assert "warning" not in s
    assert send_due(db) == 0  # not due yet
    now = utcnow() + timedelta(minutes=6)
    assert send_due(db, now) == 1 and send_due(db, now) == 0
    assert route.call_count == 1 and json.loads(route.calls[0].request.content)["text"]["body"] == "See you at 5"
    row = auth_client.get("/api/whatsapp/scheduled").json()[0]
    assert row["status"] == "sent" and row["sent_at"]
    assert auth_client.get("/api/whatsapp/messages/919876543210").json()[-1]["body"] == "See you at 5"


def test_outside_24h_needs_a_template(auth_client, db, mock_http):
    connect(db, "owner@example.com", "whatsapp", {"access_token": "t"}, {"phone_number_id": "123"})
    route = mock_http.post(SEND_URL).mock(return_value=httpx.Response(200, json={"messages": [{"id": "wamid.2"}]}))
    plain = auth_client.post("/api/whatsapp/scheduled", json={"to": "919876543210", "body": "Hi again", "send_at": later(5)}).json()
    assert "24 hours" in plain["warning"]
    tpl = auth_client.post("/api/whatsapp/scheduled", json={"to": "919876543210", "template": "visit_reminder",
                                                            "template_lang": "en_US", "send_at": later(5)}).json()
    assert "warning" not in tpl
    assert send_due(db, utcnow() + timedelta(minutes=6)) == 1
    rows = {r["id"]: r for r in auth_client.get("/api/whatsapp/scheduled").json()}
    assert rows[plain["id"]]["status"] == "failed" and "24 hours" in rows[plain["id"]]["error"]
    assert rows[tpl["id"]]["status"] == "sent"
    sent = json.loads(route.calls[0].request.content)
    assert sent["type"] == "template" and sent["template"] == {"name": "visit_reminder", "language": {"code": "en_US"}}


def test_whatsapp_refusal_is_recorded(auth_client, db, mock_http):
    connect(db, "owner@example.com", "whatsapp", {"access_token": "t"}, {"phone_number_id": "123"})
    mock_http.post(SEND_URL).mock(return_value=httpx.Response(400, json={"error": {"message": "Template not approved"}}))
    auth_client.post("/api/whatsapp/scheduled", json={"to": "919876543210", "template": "promo", "send_at": later(5)})
    assert send_due(db, utcnow() + timedelta(minutes=6)) == 0
    row = auth_client.get("/api/whatsapp/scheduled").json()[0]
    assert row["status"] == "failed" and "Template not approved" in row["error"]


def test_interrupted_send_is_not_retried(auth_client, db):
    s = auth_client.post("/api/whatsapp/scheduled", json={"to": "919876543210", "body": "x", "send_at": later(5)}).json()
    row = db.get(WaScheduled, s["id"])
    row.status = "sending"
    db.commit()
    send_due(db, utcnow() + timedelta(minutes=30))
    db.refresh(row)
    assert row.status == "failed" and "interrupted" in row.error


def test_scheduler_tick_sends_them(auth_client, db):
    auth_client.post("/api/whatsapp/scheduled", json={"to": "919876543210", "body": "Simulated", "send_at": later(5)})
    out = scheduler.tick(utcnow() + timedelta(minutes=6))
    assert out["whatsapp"] == 1
    assert db.query(WaMessage).filter_by(body="Simulated", status="simulated").count() == 1
