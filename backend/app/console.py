"""The AIMVA team console API: customer lookup, support actions, the staff log and the team list.

Every route needs a staff role (see app/staff.py). Every change needs a typed reason and is logged.
Support sees a customer's account (plan, usage, members, how much they use each module), never the
contents of their leads, messages or calls, and never a stored token or key.
"""
from collections import defaultdict
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import billing, staff
from .config import settings
from .db import get_db
from .models import (Asset, Call, Campaign, CreditGrant, Integration, Invite, Lead, Membership, Site, StaffAction,
                     StaffMember, StaffTask, Subscription, User, WaMessage, utcnow)
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
    role: Literal["manager", "developer", "support", "accountant"] = "support"


class RoleIn(BaseModel):
    role: Literal["manager", "developer", "support", "accountant"]


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
def console_me(person: User = Depends(require_staff), db: Session = Depends(get_db)):
    role = person.staff_role
    team = []
    if staff.can(role, "tasks.assign"):  # who a task can go to
        roles = {e: "owner" for e in settings.admin_emails} | {m.email: m.role for m in db.scalars(select(StaffMember))}
        names = _names(db, roles)
        team = sorted(({"email": e, "name": names.get(e, ""), "role": r} for e, r in roles.items()), key=lambda x: (x["name"] or x["email"]).lower())
    return {"email": person.email.lower(), "team": team, "role": role, "role_label": staff.ROLE_LABEL[role], "permissions": sorted(staff.PERMISSIONS[role]),
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
        select(StaffAction).where(StaffAction.target_id == u.id, StaffAction.action != "customer.view").order_by(StaffAction.id.desc()).limit(20))]
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
        "history": history,  # changes only; who opened the account is in the Activity log
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


# ---- tasks ------------------------------------------------------------------------------------------------------
TASK_STATUSES = ("open", "doing", "done", "cancelled")


class TaskIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    note: str = Field("", max_length=4000)
    assignee: EmailStr
    customer_id: Optional[int] = None
    priority: Literal["normal", "high"] = "normal"
    due_on: Optional[date] = None


class TaskPatch(BaseModel):
    status: Optional[Literal["open", "doing", "done", "cancelled"]] = None
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    note: Optional[str] = Field(None, max_length=4000)
    assignee: Optional[EmailStr] = None
    priority: Optional[Literal["normal", "high"]] = None
    due_on: Optional[date] = None
    clear_due: bool = False


def _staff_emails(db: Session) -> set:
    return set(settings.admin_emails) | {e.lower() for e in db.scalars(select(StaffMember.email))}


def _names(db: Session, emails) -> dict:
    emails = {e for e in emails if e}
    if not emails:
        return {}
    return {e.lower(): n for e, n in db.execute(select(User.email, User.name).where(func.lower(User.email).in_(emails)))}


def _task_out(t: StaffTask, names: dict, today: date) -> dict:
    return {"id": t.id, "title": t.title, "note": t.note, "assignee": t.assignee_email, "assignee_name": names.get(t.assignee_email, ""),
            "created_by": t.created_by_email, "created_by_name": names.get(t.created_by_email.lower(), ""),
            "customer_id": t.customer_id, "customer": t.customer_label, "priority": t.priority, "status": t.status,
            "due_on": t.due_on.isoformat() if t.due_on else None,
            "overdue": bool(t.due_on and t.due_on < today and t.status in ("open", "doing")),
            "done_at": _iso(t.done_at), "created_at": _iso(t.created_at), "updated_at": _iso(t.updated_at)}


def _assignee(db: Session, email: str) -> str:
    email = email.lower()
    if email not in _staff_emails(db):
        raise HTTPException(400, "Tasks go to people on the AIMVA team. Add them on the Team tab first.")
    return email


@router.get("/api/console/tasks")
def tasks(scope: Literal["mine", "all"] = "mine", status: Literal["active", "done", "all"] = "active",
          assignee: str = "", customer_id: Optional[int] = None,
          person: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Mine = assigned to me. All = everyone's (owners and managers)."""
    stmt = select(StaffTask)
    if scope == "all":
        need(person, "tasks.assign")
        if assignee:
            stmt = stmt.where(StaffTask.assignee_email == assignee.strip().lower())
    else:
        stmt = stmt.where(StaffTask.assignee_email == person.email.lower())
    if status == "active":
        stmt = stmt.where(StaffTask.status.in_(("open", "doing")))
    elif status == "done":
        stmt = stmt.where(StaffTask.status.in_(("done", "cancelled")))
    if customer_id is not None:
        stmt = stmt.where(StaffTask.customer_id == customer_id)
    # Active: high priority first, then the soonest due date (no date last), then oldest. Done: most recent first.
    if status == "active":
        stmt = stmt.order_by((StaffTask.priority == "high").desc(), StaffTask.due_on.is_(None), StaffTask.due_on, StaffTask.id)
    else:
        stmt = stmt.order_by(StaffTask.updated_at.desc(), StaffTask.id.desc())
    rows = list(db.scalars(stmt.limit(300)))
    names = _names(db, {t.assignee_email for t in rows} | {t.created_by_email.lower() for t in rows})
    today = utcnow().date()
    return {"items": [_task_out(t, names, today) for t in rows],
            "assignees": sorted(_staff_emails(db)) if staff.can(person.staff_role, "tasks.assign") else []}


@router.post("/api/console/tasks")
def create_task(body: TaskIn, person: User = Depends(require_staff), db: Session = Depends(get_db)):
    need(person, "tasks.assign")
    target = None
    if body.customer_id is not None:
        target = db.get(User, body.customer_id)
        if not target:
            raise HTTPException(404, "No customer with that id.")
    t = StaffTask(title=body.title.strip(), note=body.note.strip(), assignee_email=_assignee(db, body.assignee),
                  created_by=person.id, created_by_email=person.email, customer_id=target.id if target else None,
                  customer_label=(target.email if target and target.kind == "person" else target.name if target else "")[:255],
                  priority=body.priority, due_on=body.due_on)
    db.add(t)
    db.flush()
    staff.record(db, person, "task.assign", target, "", {"task_id": t.id, "title": t.title, "to": t.assignee_email})
    db.commit()
    return _task_out(t, _names(db, {t.assignee_email, person.email.lower()}), utcnow().date())


@router.patch("/api/console/tasks/{tid}")
def update_task(tid: int, body: TaskPatch, person: User = Depends(require_staff), db: Session = Depends(get_db)):
    t = db.get(StaffTask, tid)
    manager = staff.can(person.staff_role, "tasks.assign")
    mine = t is not None and t.assignee_email == person.email.lower()
    if not t or not (manager or mine):
        raise HTTPException(404, "Task not found.")
    edits = body.model_dump(exclude_unset=True)
    if not manager and set(edits) - {"status", "note"}:
        raise HTTPException(403, "Only an owner or a manager can change who does a task, or its title, priority or due date.")
    target = db.get(User, t.customer_id) if t.customer_id else None
    if body.status and body.status != t.status:
        staff.record(db, person, "task.status", target, "", {"task_id": t.id, "title": t.title, "from": t.status, "to": body.status})
        t.status = body.status
        t.done_at = utcnow() if body.status in ("done", "cancelled") else None
    if body.assignee and body.assignee.lower() != t.assignee_email:
        new = _assignee(db, body.assignee)
        staff.record(db, person, "task.assign", target, "", {"task_id": t.id, "title": t.title, "to": new, "from": t.assignee_email})
        t.assignee_email = new
    for f in ("title", "note", "priority", "due_on"):
        if f in edits and edits[f] is not None:
            setattr(t, f, edits[f].strip() if isinstance(edits[f], str) else edits[f])
    if body.clear_due and manager:
        t.due_on = None
    db.commit()
    return _task_out(t, _names(db, {t.assignee_email, t.created_by_email.lower()}), utcnow().date())


# ---- overview ---------------------------------------------------------------------------------------------------
@router.get("/api/console/overview")
def overview(days: int = Query(7, ge=1, le=90), person: User = Depends(require_staff), db: Session = Depends(get_db)):
    """How the platform is doing and what each teammate has been doing, for the owner and managers."""
    need(person, "overview.view")
    now = utcnow()
    since = now - timedelta(days=days)
    today = now.date()

    def count(M, *where):
        return db.scalar(select(func.count()).select_from(M).where(*where)) or 0

    active = set()
    for M in (Lead, Asset, Site, Campaign):
        active |= set(db.scalars(select(M.user_id).where(M.created_at >= since).distinct()))
    platform = {
        "customers": count(User, User.kind == "person"), "workspaces": count(User, User.kind == "workspace"),
        "new_customers": count(User, User.kind == "person", User.created_at >= since),
        "active_accounts": len(active),
        "leads": count(Lead, Lead.created_at >= since),
        "trials_ending": count(Subscription, Subscription.status == "trialing", Subscription.period_end <= now + timedelta(days=7)),
        "past_due": count(Subscription, Subscription.status == "past_due"),
        "paying": count(Subscription, Subscription.status == "active", Subscription.plan != "trial"),
        "failed": {"calls": count(Call, Call.created_at >= since, Call.status == "failed"),
                   "whatsapp": count(WaMessage, WaMessage.created_at >= since, WaMessage.status == "failed"),
                   "pictures_videos": count(Asset, Asset.created_at >= since, Asset.status == "failed")},
        "locked_signins": count(User, User.locked_until > now),
    }

    people = [(e, "owner") for e in sorted(settings.admin_emails)] + \
             [(m.email, m.role) for m in db.scalars(select(StaffMember).order_by(StaffMember.created_at))]
    emails = [e for e, _ in people]
    names = _names(db, emails)
    acts = defaultdict(lambda: {"actions": 0, "views": 0, "last": None, "kinds": defaultdict(int)})
    for a in db.scalars(select(StaffAction).where(StaffAction.created_at >= since, func.lower(StaffAction.actor_email).in_(emails))):
        r = acts[a.actor_email.lower()]
        if a.action == "customer.view":
            r["views"] += 1
        else:
            r["actions"] += 1
            r["kinds"][a.action] += 1
        if r["last"] is None or a.created_at > r["last"]:
            r["last"] = a.created_at
    tasks_by = defaultdict(lambda: {"open": 0, "doing": 0, "overdue": 0, "done": 0})
    for t in db.scalars(select(StaffTask).where(StaffTask.assignee_email.in_(emails), or_(
            StaffTask.status.in_(("open", "doing")), StaffTask.done_at >= since))):
        r = tasks_by[t.assignee_email]
        if t.status in ("open", "doing"):
            r[t.status] += 1
            r["overdue"] += bool(t.due_on and t.due_on < today)
        elif t.status == "done":
            r["done"] += 1
    team_rows = [{"email": e, "name": names.get(e, ""), "role": role, "role_label": staff.ROLE_LABEL[role],
                  "actions": acts[e]["actions"], "customers_opened": acts[e]["views"], "last_active": _iso(acts[e]["last"]),
                  "top": sorted(acts[e]["kinds"].items(), key=lambda kv: -kv[1])[:3],
                  "tasks": tasks_by[e]} for e, role in people]
    return {"days": days, "platform": platform, "team": team_rows}


# ---- billing (read-only) ----------------------------------------------------------------------------------------
@router.get("/api/console/billing")
def billing_view(days: int = Query(30, ge=1, le=365), person: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Every account's plan and what it's worth a month, plus the credits the team gave away. Nothing here changes data.
    Prices are the list prices in app/billing.py; payments aren't live yet, so this is what plans say, not cash received."""
    need(person, "billing.view")
    now = utcnow()
    since = now - timedelta(days=days)
    rows = db.execute(select(User, Subscription).join(Subscription, Subscription.user_id == User.id)
                      .order_by(Subscription.status, Subscription.period_end)).all()
    out, mrr, by_status = [], 0, defaultdict(int)
    for u, s in rows:
        price = billing.PLANS.get(s.plan, {}).get("price_inr", 0)
        paying = s.status in ("active", "past_due") and price > 0
        mrr += price if s.status == "active" else 0
        by_status[s.status] += 1
        out.append({"id": u.id, "name": u.name, "email": u.email if u.kind == "person" else None, "kind": u.kind,
                    "plan": s.plan, "plan_name": billing.PLANS.get(s.plan, {}).get("name", s.plan), "price_inr": price if paying else 0,
                    "status": s.status, "processor": s.processor or "", "period_start": _iso(s.period_start), "period_end": _iso(s.period_end),
                    "note": s.note})
    grants = db.execute(select(CreditGrant, User).join(User, User.id == CreditGrant.user_id)
                        .where(CreditGrant.created_at >= since).order_by(CreditGrant.created_at.desc())).all()
    return {
        "days": days, "live_payments": billing.razorpay_ready(), "enforced": billing.enforce(),
        "totals": {"mrr_inr": mrr, "past_due_inr": sum(r["price_inr"] for r in out if r["status"] == "past_due"),
                   "by_status": dict(by_status), "invoiced": sum(1 for r in out if r["processor"] == "manual" and r["status"] == "active")},
        "plans": [{"id": k, "name": v["name"], "price_inr": v["price_inr"]} for k, v in billing.PLANS.items() if v["public"]],
        "subscriptions": out,
        "credits": [{"at": _iso(g.created_at), "customer": u.email if u.kind == "person" else u.name, "customer_id": u.id,
                     "meter": g.meter, "quantity": g.quantity, "expires_at": _iso(g.expires_at), "note": g.note} for g, u in grants],
    }
