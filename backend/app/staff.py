"""Who is on the AIMVA team, what each role may do, and the log of what they did.

Four roles:
- owner: everything. Owners are the emails in ADMIN_EMAILS, set on the server. Nobody can make someone an
  owner from the app, so a stolen teammate login can never promote itself.
- manager (management team): runs the business side. Customers, plan changes, credits of any size, the
  quality and usage numbers, the whole staff log. Can't manage the team or touch AI engines and keys.
- developer (development team): looks into problems. Customers (read-only), the quality and usage numbers,
  the whole staff log, and can sign a customer out everywhere (a leaked session). No money actions.
- support: looks up customers, grants small goodwill credits, unlocks a locked sign-in, signs a customer out
  everywhere. Can't change plans, see AI engines or keys, or manage the team.

Every change a staff member makes is written to staff_actions with the reason they typed.
"""
from typing import Optional

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from .config import settings
from .db import get_db
from .models import StaffAction, StaffMember, User
from .security import current_person

ROLES = ("owner", "manager", "developer", "support")
TEAM_ROLES = ROLES[1:]  # what an owner can give from the app
ROLE_LABEL = {"owner": "Owner", "manager": "Management", "developer": "Development", "support": "Support"}
# What each role may do. The frontend reads this from /api/console/me to decide what to show;
# the endpoints below check it again, so hiding a button is never the only guard.
PERMISSIONS = {
    "owner": {"customers.view", "credits.grant", "credits.grant_any", "plan.change", "signin.unlock", "signin.revoke",
              "activity.view_all", "team.manage", "quality.view"},
    "manager": {"customers.view", "credits.grant", "credits.grant_any", "plan.change", "signin.unlock", "signin.revoke",
                "activity.view_all", "quality.view"},
    "developer": {"customers.view", "signin.revoke", "activity.view_all", "quality.view"},
    "support": {"customers.view", "credits.grant", "signin.unlock", "signin.revoke"},
}
SUPPORT_CREDIT_LIMIT = 50   # most units support can grant in one go
SUPPORT_CREDIT_DAYS = 30    # and for how long


def staff_role(db: Optional[Session], user: Optional[User]) -> Optional[str]:
    """owner, manager, developer, support or None. Workspaces (no login of their own) and unverified emails are never staff."""
    if not user or getattr(user, "kind", "person") != "person":
        return None
    email = (user.email or "").lower()
    if email in settings.admin_emails:
        return "owner"
    db = db or object_session(user)
    if not db or not user.is_verified:
        return None
    m = db.scalar(select(StaffMember).where(StaffMember.email == email))
    return m.role if m and m.role in ROLES else None


def can(role: Optional[str], permission: str) -> bool:
    return bool(role) and permission in PERMISSIONS.get(role, set())


def require_staff(person: User = Depends(current_person), db: Session = Depends(get_db)) -> User:
    role = staff_role(db, person)
    if not role:
        raise HTTPException(403, "Only the AIMVA team can see this page.")
    person.staff_role = role  # plain attribute for the request, not a column
    return person


def need(person: User, permission: str) -> None:
    if not can(getattr(person, "staff_role", None), permission):
        raise HTTPException(403, "Your role on the AIMVA team can't do that. Ask an owner.")


def record(db: Session, actor: User, action: str, target: Optional[User] = None, reason: str = "",
           detail: Optional[dict] = None, role: Optional[str] = None) -> StaffAction:
    """Add one line to the staff log. The caller commits (so the log and the change land together)."""
    a = StaffAction(actor_id=actor.id, actor_email=actor.email, actor_role=role or getattr(actor, "staff_role", None) or staff_role(db, actor) or "",
                    action=action, target_id=target.id if target else None,
                    target_label=(target.email if target and target.kind == "person" else (target.name if target else ""))[:255],
                    reason=(reason or "").strip()[:500], detail=detail or {})
    db.add(a)
    return a


def action_out(a: StaffAction) -> dict:
    return {"id": a.id, "at": a.created_at.isoformat() + "Z", "actor": a.actor_email, "actor_role": a.actor_role,
            "action": a.action, "target_id": a.target_id, "target": a.target_label, "reason": a.reason, "detail": a.detail or {}}


def require(permission: str):
    """A dependency: a staff member whose role has this permission."""
    def dep(person: User = Depends(require_staff)) -> User:
        need(person, permission)
        return person
    return dep
