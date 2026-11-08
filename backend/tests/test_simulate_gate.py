"""'Simulate inbound' is a test tool: open on a laptop, owner-only on a live server, and silent there (no Sheets, no Concierge)."""
from app.config import settings
from app.routers import leads as leads_router

SIM = {"from": "919876543210", "body": "Price please", "name": "Ravi"}


def test_dev_server_allows_everyone(auth_client):
    assert auth_client.get("/api/auth/me").json()["user"]["can_simulate"] is True
    assert auth_client.post("/api/whatsapp/simulate-inbound", json=SIM).status_code == 200


def test_live_server_hides_it_from_customers(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "admin_emails", set())
    assert auth_client.get("/api/auth/me").json()["user"]["can_simulate"] is False
    assert auth_client.post("/api/whatsapp/simulate-inbound", json=SIM).status_code == 404
    assert auth_client.get("/api/leads").json() == []


def test_live_server_owner_can_test_without_side_effects(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "admin_emails", {"owner@example.com"})
    ran = []
    monkeypatch.setattr(leads_router, "auto_sync", lambda *a: ran.append("sync"))
    monkeypatch.setattr(leads_router, "_concierge", lambda *a: ran.append("concierge"))
    assert auth_client.get("/api/auth/me").json()["user"]["can_simulate"] is True
    assert auth_client.post("/api/whatsapp/simulate-inbound", json=SIM).status_code == 200
    assert len(auth_client.get("/api/leads").json()) == 1
    assert ran == []
