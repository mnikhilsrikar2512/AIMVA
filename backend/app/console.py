"""The AIMVA team console API: customer lookup, support actions, the staff log and the team list.

Every route needs a staff role (see app/staff.py). Every change needs a typed reason and is logged.
Support sees a customer's account (plan, usage, members, how much they use each module), never the
contents of their leads, messages or calls, and never a stored token or key.
"""
from collections import defaultdict
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import billing, staff
from .config import settings
from .db import get_db
from .models import (Asset, Call, Campaign, CreditGrant, Integration, Invite, Lead, Membership, Site, StaffAction,
                     StaffMember, Subscription, User, WaMessage, utcnow)
from .routers.integrations import PLATFORM
from .security import rate_limit
from .staff import need, require_staff

router = APIRouter(tags=["console"])

VIEW_LOG_EVERY = timedelta(hours=1)  # one "viewed" line per person per customer per hour is enough


class ReasonIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class CreditsIn(ReasonIn):
    meter: str
    quantity: int = Field(gt=0, le=100_000)
    days: int = Field(30, gt=0, le=365)


class PlanIn(ReasonIn):
    plan: str


class TeamIn(BaseModel):
    email: EmailStr
    role: Literal["manager", "developer", "support"] = "support"


class RoleIn(BaseModel):
    role: Literal["manager", "developer", "support"]


def _iso(d):
    return d.isoformat() + "Z" if d else None


def _target(db: Session, person: User, cid: int, acting: bool = False) -> User:
    u = db.get(User, cid)
    if not u:
        raise HTTPException(404, "No customer with that id.")
    # Only owners act on teammates (a teammate's login can't sign an owner out or hand itself credits).
    if acting and person.staff_role != "owner" and (u.id == person.id or staff.staff_role(db, u)):
        raise HTTPException(403, "Only an owner can do that to someone on the AIMVA team.")
    return u


@router.get("/api/console/me")
def console_me(person: User = Depends(require_staff)):
    role = person.staff_role
    return {"role": role, "role_label": staff.ROLE_LABEL[role], "permissions": sorted(staff.PERMISSIONS[role]),
            "support_credit_limit": staff.SUPPORT_CREDIT_LIMIT, "support_credit_days": staff.SUPPORT_CREDIT_DAYS,
            "plans": [{"id": k, "name": v["name"], "price_inr": v["price_inr"]} for k, v in billing.PLANS.items() if k != "expired"],
            "meters": [{"id": k, "label": v} for k, v in billing.METERS.items() if k != "sites"]}


# ---- customers -------------------------------------------------------------------------------------------------
@router.get("/api/console/customers")
def customers(q: str = "", kind: Literal["all", "person", "workspace"] = "all",
              status: Literal["all", "trialing", "active", "past_due", "expired", "cancelled", "new"] = "all",
              limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
              person: User = Depends(require_staff), db: Session = Depends(get_db)):
    need(person, "customers.view")
    stmt = select(User, Subscription).outerjoin(Subscription, Subscription.user_id == User.id)
    if kind != "all":
        stmt = stmt.where(User.kind == kind)
    q = q.strip()
    if q:
        like = f"%{q.lower()}%"
        cond = [func.lower(User.email).like(like), func.lower(User.name).like(like), func.lower(User.company).like(like)]
        if q.isdigit():
            cond.append(User.id == int(q))
        stmt = stmt.where(or_(*cond))
    if status == "new":
        stmt = stmt.where(Subscription.id.is_(None))
    elif status != "all":
        stmt = stmt.where(Subscription.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(User.created_at.desc(), User.id.desc()).limit(limit).offset(offset)).all()
    ids = [u.id for u, _ in rows]

    leads, last = {}, defaultdict(lambda: None)
    if ids:
        leads = dict(db.execute(select(Lead.user_id, func.count()).where(Lead.user_id.in_(ids)).group_by(Lead.user_id)).all())
        for M in (Lead, Asset, Site, Campaign):
            for uid, at in db.execute(select(M.user_id, func.max(M.created_at)).where(M.user_id.in_(ids)).group_by(M.user_id)):
                if at and (last[uid] is None or at > last[uid]):
                    last[uid] = at
    agencies = {}
    ws_ids = [u.id for u, _ in rows if u.kind == "workspace"]
    if ws_ids:  # who runs each client workspace
        for wid, email in db.execute(select(Membership.workspace_id, User.email).join(User, User.id == Membership.member_id)
                                     .where(Membership.workspace_id.in_(ws_ids), Membership.role == "owner")):
            agencies.setdefault(wid, email)
    return {"total": total, "items": [{
        "id": u.id, "kind": u.kind, "name": u.name, "email": u.email if u.kind == "person" else None,
        "company": u.company, "verified": u.is_verified, "created_at": _iso(u.created_at),
        "plan": s.plan if s else None, "plan_name": billing.PLANS[s.plan]["name"] if s else "Not started",
        "status": s.status if s else "new", "leads": leads.get(u.id, 0), "last_activity": _iso(last[u.id]),
        "agency": agencies.get(u.id), "staff_role": staff.staff_role(db, u),
    } for u, s in rows]}


def _counts(db: Session, uid: int) -> dict:
    since = utcnow() - timedelta(days=30)

    def n(M, *where):
        return db.scalar(select(func.count()).select_from(M).where(M.user_id == uid, *where)) or 0
    return {
        "leads": {"total": n(Lead), "last_30d": n(Lead, Lead.created_at >= since), "opted_out": n(Lead, Lead.opted_out_at.is_not(None))},
        "calls": {"total": n(Call), "last_30d": n(Call, Call.created_at >= since), "failed_30d": n(Call, Call.created_at >= since, Call.status == "failed")},
        "whatsapp": {"last_30d": n(WaMessage, WaMessage.created_at >= since),
                     "failed_30d": n(WaMessage, WaMessage.created_at >= since, WaMessage.status == "failed")},
        "pages": {"total": n(Site), "published": n(Site, Site.published.is_(True))},
        "campaigns": {"total": n(Campaign), "active": n(Campaign, Campaign.status == "active")},
        "pictures_videos": {"last_30d": n(Asset, Asset.created_at >= since),
                            "failed_30d": n(Asset, Asset.created_at >= since, Asset.status == "failed")},
    }


def _detail(db: Session, u: User, role: str) -> dict:
    now = utcnow()
    if u.kind == "workspace":
        members = [{"email": e, "name": nm, "role": r} for e, nm, r in db.execute(
            select(User.email, User.name, Membership.role).join(User, User.id == Membership.member_id)
            .where(Membership.workspace_id == u.id).order_by(Membership.created_at))]
        invites = [{"email": i.email, "role": i.role, "expires_at": _iso(i.expires_at)} for i in db.scalars(
            select(Invite).where(Invite.workspace_id == u.id, Invite.accepted_at.is_(None), Invite.expires_at > now))]
        workspaces = []
    else:
        members, invites = [], []
        workspaces = [{"id": w.id, "name": w.name, "role": r} for w, r in db.execute(
            select(User, Membership.role).join(Membership, Membership.workspace_id == User.id)
            .where(Membership.member_id == u.id, User.id != u.id).order_by(User.name))]
    grants = [{"meter": g.meter, "quantity": g.quantity, "expires_at": _iso(g.expires_at), "note": g.note} for g in db.scalars(
        select(CreditGrant).where(CreditGrant.user_id == u.id, CreditGrant.expires_at > now).order_by(CreditGrant.created_at.desc()))]
    history = [staff.action_out(a) for a in db.scalars(
        select(StaffAction).where(StaffAction.target_id == u.id).order_by(StaffAction.id.desc()).limit(20))]
    return {
        "profile": {"id": u.id, "kind": u.kind, "name": u.name, "email": u.email if u.kind == "person" else None,
                    "company": u.company, "industry": u.industry, "goal": u.goal, "verified": u.is_verified,
                    "created_at": _iso(u.created_at), "locked": bool(u.locked_until and u.locked_until > now),
                    "locked_until": _iso(u.locked_until), "failed_logins": u.failed_logins,
                    "require_approval": u.require_approval, "staff_role": staff.staff_role(db, u)},
        "billing": billing.billing_out(db, u),
        "credits": grants,
        "members": members, "invites": invites, "workspaces": workspaces,
        # Names of what they connected, never the tokens. AI engine keys are an owner matter.
        "connected": sorted({p for p in db.scalars(select(Integration.provider).where(Integration.user_id == u.id))
                             if role == "owner" or p not in PLATFORM}),
        "usage": _counts(db, u.id),
        "history": history,
    }


@router.get("/api/console/customers/{cid}")
def customer(cid: int, person: User = Depends(require_staff), db: Session = Depends(get_db)):
    need(person, "customers.view")
    u = _target(db, person, cid)
    recent = db.scalar(select(StaffAction.id).where(StaffAction.actor_id == person.id, StaffAction.target_id == u.id,
                                                    StaffAction.action == "customer.view",
                                                    StaffAction.created_at > utcnow() - VIEW_LOG_EVERY).limit(1))
    if not recent:  # who looked at whose account is part of the record (DPDP accountability)
        staff.record(db, person, "customer.view", u)
    out = _detail(db, u, person.staff_role)  # billing_out may roll a lapsed period forward; commit that with the log line
    db.commit()
    return out


@router.post("/api/console/customers/{cid}/credits")
def credits(cid: int, body: CreditsIn, person: User = Depends(require_staff), db: Session = Depends(get_db)):
    need(person, "credits.grant")
    _target(db, person, cid, acting=True)
    if not staff.can(person.staff_role, "credits.grant_any") and (
            body.quantity > staff.SUPPORT_CREDIT_LIMIT or body.days > staff.SUPPORT_CREDIT_DAYS):
        raise HTTPException(403, f"Support can grant up to {staff.SUPPORT_CREDIT_LIMIT} at a time, for up to "
                                 f"{staff.SUPPORT_CREDIT_DAYS} days. Ask an owner for more.")
    rate_limit(f"console-credits:{person.id}", 30, 3600)
    billing.grant_credits(db, person, cid, body.meter, body.quantity, body.days, body.reason)
    return _detail(db, db.get(User, cid), person.staff_role)


@router.post("/api/console/customers/{cid}/plan")
def plan(cid: int, body: PlanIn, person: User = Depends(require_staff), db: Session = Depends(get_db)):
    need(person, "plan.change")
    _target(db, person, cid, acting=True)
    billing.set_plan(db, person, cid, body.plan, body.reason)
    return _detail(db, db.get(User, cid), person.staff_role)


@router.post("/api/console/customers/{cid}/unlock")
def unlock(cid: int, body: ReasonIn, person: User = Depends(require_staff), db: Session = Depends(get_db)):
    """After too many wrong passwords sign-in locks for a while; this lets the person try again now."""
    need(person, "signin.unlock")
    u = _target(db, person, cid, acting=True)
    if u.kind != "person":
        raise HTTPException(400, "A client workspace has no sign-in of its own.")
    staff.record(db, person, "signin.unlock", u, body.reason, {"failed_logins": u.failed_logins})
    u.failed_logins, u.locked_until = 0, None
    db.commit()
    return _detail(db, u, person.staff_role)


@router.post("/api/console/customers/{cid}/sign-out")
def sign_out_everywhere(cid: int, body: ReasonIn, person: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Ends every session the person has (lost phone, shared password). They sign in again with their password."""
    need(person, "signin.revoke")
    u = _target(db, person, cid, acting=True)
    if u.kind != "person":
        raise HTTPException(400, "A client workspace has no sign-in of its own.")
    u.token_version += 1
    staff.record(db, person, "signin.revoke", u, body.reason)
    db.commit()
    return _detail(db, u, person.staff_role)


# ---- the staff log ---------------------------------------------------------------------------------------------
@router.get("/api/console/activity")
def activity(target_id: Optional[int] = None, actor: str = "", action: str = "", before: Optional[int] = None,
             limit: int = Query(50, ge=1, le=200), person: User = Depends(require_staff), db: Session = Depends(get_db)):
    stmt = select(StaffAction)
    if not staff.can(person.staff_role, "activity.view_all"):
        # Support sees what happened to customers (for hand-offs), not team or template changes.
        stmt = stmt.where(StaffAction.target_id.is_not(None))
    if target_id is not None:
        stmt = stmt.where(StaffAction.target_id == target_id)
    if actor:
        stmt = stmt.where(func.lower(StaffAction.actor_email) == actor.strip().lower())
    if action:
        stmt = stmt.where(StaffAction.action == action)
    if before:
        stmt = stmt.where(StaffAction.id < before)
    rows = list(db.scalars(stmt.order_by(StaffAction.id.desc()).limit(limit + 1)))
    return {"items": [staff.action_out(a) for a in rows[:limit]], "more": len(rows) > limit,
            "next": rows[limit - 1].id if len(rows) > limit else None}


# ---- the team ---------------------------------------------------------------------------------------------------
def _team(db: Session) -> dict:
    people = {u.email.lower(): u for u in db.scalars(select(User).where(User.kind == "person", or_(
        func.lower(User.email).in_(settings.admin_emails),
        func.lower(User.email).in_(select(StaffMember.email)))))}

    def state(email):
        u = people.get(email)
        return "active" if u and u.is_verified else ("not verified" if u else "hasn't signed up")
    return {
        # Owners come from ADMIN_EMAILS on the server; the app can't add or remove them.
        "owners": [{"email": e, "name": people[e].name if e in people else "", "state": state(e)} for e in sorted(settings.admin_emails)],
        "members": [{"id": m.id, "email": m.email, "name": people[m.email].name if m.email in people else "", "role": m.role,
                     "state": state(m.email), "added_at": _iso(m.created_at)}
                    for m in db.scalars(select(StaffMember).order_by(StaffMember.created_at))],
        "roles": [{"id": r, "label": staff.ROLE_LABEL[r], "can": sorted(staff.PERMISSIONS[r]), "assignable": r in staff.TEAM_ROLES}
                  for r in staff.ROLES],
    }


@router.get("/api/console/team")
def team(person: User = Depends(require_staff), db: Session = Depends(get_db)):
    need(person, "team.manage")
    return _team(db)


@router.post("/api/console/team")
def add_member(body: TeamIn, person: User = Depends(require_staff), db: Session = Depends(get_db)):
    need(person, "team.manage")
    email = body.email.lower()
    if email in settings.admin_emails:
        raise HTTPException(400, "That person is already an owner.")
    if db.scalar(select(StaffMember).where(StaffMember.email == email)):
        raise HTTPException(400, "That person is already on the team.")
    db.add(StaffMember(email=email, role=body.role, added_by=person.id))
    staff.record(db, person, "team.add", None, "", {"email": email, "role": body.role})
    db.commit()
    return _team(db)


@router.post("/api/console/team/{mid}/role")
def change_role(mid: int, body: RoleIn, person: User = Depends(require_staff), db: Session = Depends(get_db)):
    need(person, "team.manage")
    m = db.get(StaffMember, mid)
    if not m:
        raise HTTPException(404, "Not on the team.")
    if m.role != body.role:
        staff.record(db, person, "team.role", None, "", {"email": m.email, "from": m.role, "to": body.role})
        m.role = body.role
        db.commit()
    return _team(db)


@router.post("/api/console/team/{mid}/remove")
def remove_member(mid: int, person: User = Depends(require_staff), db: Session = Depends(get_db)):
    need(person, "team.manage")
    m = db.get(StaffMember, mid)
    if not m:
        raise HTTPException(404, "Not on the team.")
    staff.record(db, person, "team.remove", None, "", {"email": m.email, "role": m.role})
    db.delete(m)
    db.commit()
    return _team(db)
