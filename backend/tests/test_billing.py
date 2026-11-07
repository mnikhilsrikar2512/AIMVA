"""Plans, trial, usage limits (off by default), admin plans and credits, Razorpay checkout and webhooks."""
import hashlib
import hmac
import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app import billing
from app.models import Subscription, User, utcnow


def me(db, email="owner@example.com"):
    return db.scalar(select(User).where(User.email == email))


@pytest.fixture
def admin(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "admin_emails", {"owner@example.com"})


@pytest.fixture
def razorpay(monkeypatch):
    for k, v in {"RAZORPAY_KEY_ID": "rzp_test_1", "RAZORPAY_KEY_SECRET": "sec", "RAZORPAY_WEBHOOK_SECRET": "whsec",
                 "RAZORPAY_PLAN_GROWTH": "plan_G"}.items():
        monkeypatch.setenv(k, v)


def signed(client, event: dict, secret="whsec"):
    raw = json.dumps(event).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/api/public/billing/razorpay/webhook", content=raw, headers={"X-Razorpay-Signature": sig})


def test_new_users_start_a_14_day_trial(auth_client):
    b = auth_client.get("/api/billing").json()
    assert b["plan"] == "trial" and b["status"] == "trialing" and b["trial_days_left"] in (13, 14)
    assert not b["enforced"] and not b["payments_enabled"]
    images = next(u for u in b["usage"] if u["meter"] == "images")
    assert images == {"meter": "images", "label": "AI images and image edits", "limit": 30, "used": 0, "remaining": 30}
    assert [p["id"] for p in auth_client.get("/api/billing/plans").json()] == ["starter", "growth", "agency"]


def test_usage_is_counted_but_not_blocked_by_default(auth_client, db):
    u = me(db)
    for _ in range(31):
        billing.charge(db, u, "images")
    images = billing.allowance(db, u.id, "images")
    assert images["used"] == 31 and images["remaining"] == 0


def test_limits_block_when_enforced(auth_client, db, monkeypatch):
    monkeypatch.setenv("BILLING_ENFORCE", "true")
    u = me(db)
    billing.charge(db, u, "videos", 2)
    with pytest.raises(Exception) as e:
        billing.charge(db, u, "videos")
    assert e.value.status_code == 402 and "Upgrade" in e.value.detail


def test_trial_ends_into_the_free_allowance(auth_client, db):
    u = me(db)
    billing.subscription(db, u.id)
    later = utcnow() + timedelta(days=15)
    s = billing.subscription(db, u.id, later)
    assert s.status == "expired" and billing.allowance(db, u.id, "images", later)["limit"] == 0


def test_admin_plans_and_credits(auth_client, other_client, db, admin):
    other = me(db, "intruder@example.com")
    assert other_client.post(f"/api/admin/billing/{other.id}/plan", json={"plan": "agency"}).status_code == 403
    b = auth_client.post(f"/api/admin/billing/{other.id}/plan", json={"plan": "growth", "note": "Invoice #12"}).json()
    assert b["plan"] == "growth" and b["status"] == "active" and b["processor"] == "manual"
    b = auth_client.post(f"/api/admin/billing/{other.id}/credits", json={"meter": "videos", "quantity": 25}).json()
    assert next(u for u in b["usage"] if u["meter"] == "videos")["limit"] == 75
    agency = auth_client.post(f"/api/admin/billing/{other.id}/plan", json={"plan": "agency"}).json()
    assert next(u for u in agency["usage"] if u["meter"] == "ai_actions")["limit"] is None
    s = billing.subscription(db, other.id, utcnow() + timedelta(days=65))  # invoiced plans roll on
    assert s.status == "active" and s.period_end > utcnow() + timedelta(days=65)


def test_checkout_is_off_until_razorpay_is_set_up(auth_client):
    r = auth_client.post("/api/billing/checkout", json={"plan": "growth"})
    assert r.status_code == 503 and "aren't switched on" in r.json()["detail"]
    assert auth_client.post("/api/billing/checkout", json={"plan": "trial"}).status_code == 400


def test_razorpay_checkout_and_webhooks(auth_client, client, db, razorpay, mock_http):
    route = mock_http.post("https://api.razorpay.com/v1/subscriptions").respond(
        json={"id": "sub_1", "short_url": "https://rzp.io/i/abc"})
    r = auth_client.post("/api/billing/checkout", json={"plan": "growth"}).json()
    assert r == {"subscription_id": "sub_1", "short_url": "https://rzp.io/i/abc", "key_id": "rzp_test_1"}
    sent = json.loads(route.calls[0].request.content)
    assert sent["plan_id"] == "plan_G" and sent["notes"]["aimva_plan"] == "growth"

    assert signed(client, {"event": "subscription.activated"}, secret="wrong").status_code == 403
    now = int(utcnow().timestamp())
    ev = {"event": "subscription.activated", "payload": {"subscription": {"entity": {
        "id": "sub_1", "status": "active", "current_start": now, "current_end": now + 30 * 86400,
        "notes": {"aimva_plan": "growth"}}}}}
    assert signed(client, ev).status_code == 200
    b = auth_client.get("/api/billing").json()
    assert b["plan"] == "growth" and b["status"] == "active" and b["processor"] == "razorpay"
    assert next(u for u in b["usage"] if u["meter"] == "images")["limit"] == 1000

    signed(client, {"event": "subscription.halted", "payload": {"subscription": {"entity": {"id": "sub_1"}}}})
    b = auth_client.get("/api/billing").json()
    assert b["status"] == "past_due" and b["effective_plan"] == "expired"


def test_missed_renewal_falls_back_after_grace(auth_client, db):
    u = me(db)
    s = billing.subscription(db, u.id)
    s.plan, s.status, s.processor, s.period_end = "starter", "active", "razorpay", utcnow()
    db.commit()
    assert billing.subscription(db, u.id, utcnow() + timedelta(days=1)).status == "active"
    assert billing.subscription(db, u.id, utcnow() + timedelta(days=4)).status == "past_due"
