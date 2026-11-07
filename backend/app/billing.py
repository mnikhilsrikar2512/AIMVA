"""Plans, usage limits, trial and payments.

Built but not switched on (owner's call, 2026-11-06):
- BILLING_ENFORCE=false (default): usage is counted and shown, nothing is blocked.
- Razorpay: checkout and webhooks are implemented but stay off until RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET,
  RAZORPAY_WEBHOOK_SECRET and a plan id per paid plan (RAZORPAY_PLAN_STARTER...) are set.
- Modules don't call charge() yet. To meter one, call `billing.charge(db, user, "images")` before the paid work;
  it records the usage and, once enforcement is on, answers 402 with an upgrade message when the plan is used up.

Plan names, prices and limits below are a starting point: change them here (one place) before launch.
"""
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import get_db
from .models import CreditGrant, Subscription, UsageEvent, User, utcnow
from .routers.feedback import require_admin
from .security import current_user

log = logging.getLogger("aimva.billing")
router = APIRouter(tags=["billing"])

TRIAL_DAYS = 14
PERIOD = timedelta(days=30)
GRACE = timedelta(days=3)  # a failed renewal keeps working this long before limits fall back to the free allowance
METERS = {
    "images": "AI images and image edits",
    "videos": "AI videos",
    "voice_minutes": "AI voice call minutes",
    "sites": "Published websites",
    "ai_actions": "AI writing and agent runs",
}
# price_inr is per month. None = unlimited.
PLANS = {
    "trial":   {"name": "Free trial", "price_inr": 0, "public": False,
                "limits": {"images": 30, "videos": 2, "voice_minutes": 15, "sites": 1, "ai_actions": 100}},
    "starter": {"name": "Starter", "price_inr": 1999, "public": True,
                "limits": {"images": 200, "videos": 10, "voice_minutes": 100, "sites": 3, "ai_actions": 1000}},
    "growth":  {"name": "Growth", "price_inr": 4999, "public": True,
                "limits": {"images": 1000, "videos": 50, "voice_minutes": 500, "sites": 10, "ai_actions": 5000}},
    "agency":  {"name": "Agency", "price_inr": 12999, "public": True,
                "limits": {"images": 5000, "videos": 200, "voice_minutes": 2000, "sites": 50, "ai_actions": None}},
    "expired": {"name": "No active plan", "price_inr": 0, "public": False,
                "limits": {"images": 0, "videos": 0, "voice_minutes": 0, "sites": 1, "ai_actions": 20}},
}


def enforce() -> bool:
    return os.getenv("BILLING_ENFORCE", "false").strip().lower() == "true"


# ---- Subscription state ------------------------------------------------------------------------------------
def subscription(db: Session, user_id: int, now: Optional[datetime] = None) -> Subscription:
    """The user's subscription, created as a trial on first use, rolled to the next period when one ends."""
    now = now or utcnow()
    s = db.scalar(select(Subscription).where(Subscription.user_id == user_id))
    if not s:
        s = Subscription(user_id=user_id, plan="trial", status="trialing", period_start=now,
                         period_end=now + timedelta(days=TRIAL_DAYS))
        db.add(s)
        try:
            db.commit()
        except IntegrityError:  # created by a parallel request
            db.rollback()
            s = db.scalar(select(Subscription).where(Subscription.user_id == user_id))
    changed = False
    if s.status == "trialing" and now >= s.period_end:
        s.plan, s.status, s.period_start, s.period_end = "expired", "expired", s.period_end, s.period_end + PERIOD
        changed = True
    if s.status == "active" and s.processor == "manual":
        while now >= s.period_end:  # invoiced customers: the period rolls on until an admin changes the plan
            s.period_start, s.period_end = s.period_end, s.period_end + PERIOD
            changed = True
    if s.status == "active" and s.processor == "razorpay" and now >= s.period_end + GRACE:
        s.status = "past_due"  # the renewal webhook didn't come
        changed = True
    if s.status == "expired":
        while now >= s.period_end:
            s.period_start, s.period_end = s.period_end, s.period_end + PERIOD
            changed = True
    if changed:
        db.commit()
    return s


def effective_plan(s: Subscription) -> str:
    """The plan whose limits apply now: the paid or trial plan while it's in good standing, else the free allowance."""
    return s.plan if s.status in ("trialing", "active") else "expired"


def used(db: Session, user_id: int, meter: str, since: datetime) -> int:
    if meter == "sites":  # a standing count, not a monthly one
        from .models import Site
        return db.scalar(select(func.count()).select_from(Site).where(Site.user_id == user_id, Site.published.is_(True))) or 0
    return db.scalar(select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
        UsageEvent.user_id == user_id, UsageEvent.meter == meter, UsageEvent.created_at >= since)) or 0


def extra(db: Session, user_id: int, meter: str, now: datetime) -> int:
    return db.scalar(select(func.coalesce(func.sum(CreditGrant.quantity), 0)).where(
        CreditGrant.user_id == user_id, CreditGrant.meter == meter, CreditGrant.expires_at > now)) or 0


def allowance(db: Session, user_id: int, meter: str, now: Optional[datetime] = None) -> dict:
    now = now or utcnow()
    s = subscription(db, user_id, now)
    limit = PLANS[effective_plan(s)]["limits"].get(meter)
    u = used(db, user_id, meter, s.period_start)
    if limit is None:
        return {"meter": meter, "label": METERS[meter], "limit": None, "used": u, "remaining": None}
    total = limit + extra(db, user_id, meter, now)
    return {"meter": meter, "label": METERS[meter], "limit": total, "used": u, "remaining": max(total - u, 0)}


def charge(db: Session, user: User, meter: str, quantity: int = 1, ref: str = "") -> None:
    """Record metered work. With BILLING_ENFORCE=true, refuse (402) when the plan has no room left."""
    if meter not in METERS:
        raise ValueError(f"unknown meter {meter}")
    a = allowance(db, user.id, meter)
    if enforce() and a["remaining"] is not None and a["remaining"] < quantity:
        raise HTTPException(402, f"You've used all {a['limit']} {a['label'].lower()} in your plan this month. "
                                 "Upgrade or add credits in Settings → Plan.")
    if meter != "sites":
        db.add(UsageEvent(user_id=user.id, meter=meter, quantity=quantity, ref=ref[:120]))
        db.commit()


def billing_out(db: Session, user: User) -> dict:
    s = subscription(db, user.id)
    plan = effective_plan(s)
    return {"plan": s.plan, "plan_name": PLANS[s.plan]["name"], "status": s.status, "effective_plan": plan,
            "period_start": s.period_start.isoformat() + "Z", "period_end": s.period_end.isoformat() + "Z",
            "trial_days_left": max((s.period_end - utcnow()).days, 0) if s.status == "trialing" else None,
            "processor": s.processor, "enforced": enforce(), "payments_enabled": razorpay_ready(),
            "usage": [allowance(db, user.id, m) for m in METERS]}


# ---- Razorpay -------------------------------------------------------------------------------------------------
RAZORPAY = "https://api.razorpay.com/v1"


def _rz(name: str) -> str:
    return os.getenv(name, "").strip()


def razorpay_ready() -> bool:
    return bool(_rz("RAZORPAY_KEY_ID") and _rz("RAZORPAY_KEY_SECRET") and _rz("RAZORPAY_WEBHOOK_SECRET"))


def _razorpay_plan(plan: str) -> str:
    return _rz(f"RAZORPAY_PLAN_{plan.upper()}")


def apply_razorpay_event(db: Session, event: dict) -> Optional[Subscription]:
    """Move a subscription along from a verified Razorpay webhook. Unknown or unrelated events are ignored."""
    kind = event.get("event", "")
    ent = ((event.get("payload") or {}).get("subscription") or {}).get("entity") or {}
    sub_id = ent.get("id", "")
    if not sub_id or not kind.startswith("subscription."):
        return None
    s = db.scalar(select(Subscription).where(Subscription.processor_subscription_id == sub_id))
    if not s:
        log.warning("Razorpay event %s for unknown subscription %s", kind, sub_id)
        return None
    plan = (ent.get("notes") or {}).get("aimva_plan") or s.plan
    if kind in ("subscription.activated", "subscription.charged", "subscription.resumed"):
        s.plan, s.status, s.processor = plan if plan in PLANS else s.plan, "active", "razorpay"
        if ent.get("current_start") and ent.get("current_end"):
            s.period_start = datetime.fromtimestamp(int(ent["current_start"]), timezone.utc).replace(tzinfo=None)
            s.period_end = datetime.fromtimestamp(int(ent["current_end"]), timezone.utc).replace(tzinfo=None)
    elif kind in ("subscription.halted", "subscription.pending"):
        s.status = "past_due"
    elif kind in ("subscription.cancelled", "subscription.completed"):
        s.status = "cancelled"
    db.commit()
    return s


class CheckoutIn(BaseModel):
    plan: str


@router.get("/api/billing/plans")
def plans():
    return [{"id": k, "name": p["name"], "price_inr": p["price_inr"], "limits": p["limits"]}
            for k, p in PLANS.items() if p["public"]]


@router.get("/api/billing")
def my_billing(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return billing_out(db, user)


@router.post("/api/billing/checkout")
def checkout(body: CheckoutIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Start a Razorpay subscription; the frontend opens the returned short_url (or Razorpay Checkout with its id)."""
    if body.plan not in PLANS or not PLANS[body.plan]["public"]:
        raise HTTPException(400, "Pick one of the plans.")
    if not razorpay_ready() or not _razorpay_plan(body.plan):
        raise HTTPException(503, "Online payments aren't switched on yet. Contact us to upgrade.")
    r = httpx.post(f"{RAZORPAY}/subscriptions", auth=(_rz("RAZORPAY_KEY_ID"), _rz("RAZORPAY_KEY_SECRET")), timeout=30,
                   json={"plan_id": _razorpay_plan(body.plan), "total_count": 120, "customer_notify": 1,
                         "notes": {"aimva_user_id": str(user.id), "aimva_plan": body.plan}})
    if r.status_code >= 400:
        raise HTTPException(502, "The payment provider didn't accept the request. Please try again.")
    data = r.json()
    s = subscription(db, user.id)
    s.processor_subscription_id = data["id"]
    db.commit()
    return {"subscription_id": data["id"], "short_url": data.get("short_url"), "key_id": _rz("RAZORPAY_KEY_ID")}


@router.post("/api/public/billing/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    secret = _rz("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(403, "Payments aren't switched on.")
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("x-razorpay-signature", "")):
        raise HTTPException(403, "Invalid webhook signature.")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Invalid JSON.")
    apply_razorpay_event(db, event if isinstance(event, dict) else {})
    return {"ok": True}


# ---- Admin: invoiced customers and goodwill credits --------------------------------------------------------
class AdminPlanIn(BaseModel):
    plan: str
    note: str = Field("", max_length=300)


class GrantIn(BaseModel):
    meter: str
    quantity: int = Field(gt=0, le=100_000)
    days: int = Field(30, gt=0, le=365)
    note: str = Field("", max_length=300)


@router.post("/api/admin/billing/{user_id}/plan")
def admin_set_plan(user_id: int, body: AdminPlanIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Put a customer on a plan you invoice yourself (no card needed)."""
    if body.plan not in PLANS or body.plan in ("expired",):
        raise HTTPException(400, "Unknown plan.")
    if not db.get(User, user_id):
        raise HTTPException(404, "User not found.")
    s = subscription(db, user_id)
    now = utcnow()
    if body.plan == "trial":
        s.plan, s.status, s.period_start, s.period_end = "trial", "trialing", now, now + timedelta(days=TRIAL_DAYS)
    else:
        s.plan, s.status, s.processor, s.period_start, s.period_end = body.plan, "active", "manual", now, now + PERIOD
    s.note = body.note or f"Set by {admin.email}"
    db.commit()
    return billing_out(db, db.get(User, user_id))


@router.post("/api/admin/billing/{user_id}/credits")
def admin_grant(user_id: int, body: GrantIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.meter not in METERS or body.meter == "sites":
        raise HTTPException(400, "Unknown meter.")
    if not db.get(User, user_id):
        raise HTTPException(404, "User not found.")
    db.add(CreditGrant(user_id=user_id, meter=body.meter, quantity=body.quantity,
                       expires_at=utcnow() + timedelta(days=body.days), note=body.note or f"Granted by {admin.email}"))
    db.commit()
    return billing_out(db, db.get(User, user_id))
