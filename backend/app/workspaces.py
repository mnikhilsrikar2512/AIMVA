"""Agency workspaces: one login, many client businesses, each with its own data.

A workspace is a User row with kind="workspace" and no password. Every module already scopes its data to
`current_user`; that dependency now returns the workspace the person switched to (security.current_user), so leads,
sites, campaigns, brand kits and agents stay separate per client without touching each module.

Roles: owner and admin manage the workspace and its people; editor does the work; client sees everything read-only,
except approvals, which only they (or an owner/admin on their behalf) decide.
"""
import hashlib
import json
import uuid
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import live
from .config import settings
from .db import get_db
from .models import Approval, Campaign, Invite, Lead, Membership, Site, Asset, User, utcnow
from .security import WORKSPACE_COOKIE, current_person, current_user

router = APIRouter(tags=["workspaces"])
WORKSPACE_DOMAIN = "workspaces.aimva.invalid"  # workspaces never receive email directly: see member_emails()
INVITE_DAYS = 14
MAX_WORKSPACES = 200
ROLES = ("owner", "admin", "editor", "client")
MANAGERS = ("owner", "admin")


def role_in(db: Session, person: User, workspace_id: int) -> Optional[str]:
    if workspace_id == person.id:
        return "owner"
    return db.scalar(select(Membership.role).where(Membership.workspace_id == workspace_id, Membership.member_id == person.id))


def _need(db: Session, person: User, workspace_id: int, roles=MANAGERS) -> User:
    role = role_in(db, person, workspace_id)
    ws = db.get(User, workspace_id) if role else None
    if not ws:
        raise HTTPException(404, "Workspace not found.")
    if role not in roles:
        raise HTTPException(403, "Only the workspace's owner or an admin can do that.")
    return ws


def member_emails(db: Session, workspace: User, roles=("owner", "admin", "client")) -> list:
    """Who should get a workspace's emails (weekly report, approvals): its people, never the placeholder address."""
    if workspace.kind != "workspace":
        return [workspace.email]
    rows = db.execute(select(User.email).join(Membership, Membership.member_id == User.id)
                      .where(Membership.workspace_id == workspace.id, Membership.role.in_(roles))).scalars()
    return sorted(set(rows))


def accept_invites(db: Session, person: User) -> int:
    """Pending invites for this person's (verified) email become memberships."""
    n = 0
    for inv in db.scalars(select(Invite).where(func.lower(Invite.email) == person.email.lower(), Invite.accepted_at.is_(None),
                                               Invite.expires_at > utcnow())):
        if not role_in(db, person, inv.workspace_id):
            db.add(Membership(workspace_id=inv.workspace_id, member_id=person.id, role=inv.role))
        inv.accepted_at = utcnow()
        n += 1
    if n:
        db.commit()
    return n


def landing_workspace(db: Session, person: User) -> Optional[User]:
    """Where to start a fresh sign-in: someone who only works in one client's workspace (as admin, editor or client)
    and has nothing in their own account lands in that workspace, not in an empty one."""
    accept_invites(db, person)  # invites become memberships lazily; do it now so a first sign-in counts them
    rows = db.execute(select(Membership.workspace_id, Membership.role).where(Membership.member_id == person.id)).all()
    if len(rows) != 1 or rows[0].role == "owner":
        return None
    if any(db.scalar(select(func.count()).select_from(M).where(M.user_id == person.id)) for M in (Lead, Site, Campaign)):
        return None
    return db.get(User, rows[0].workspace_id)


def ws_out(ws: User, role: str, person: User, active_id: int) -> dict:
    return {"id": ws.id, "name": ws.company or ws.name, "role": role, "own": ws.id == person.id,
            "active": ws.id == active_id, "require_approval": ws.require_approval and settings.agency_features}


@router.get("/api/workspaces")
def list_workspaces(request: Request, person: User = Depends(current_person), db: Session = Depends(get_db)):
    accept_invites(db, person)
    raw = request.cookies.get(WORKSPACE_COOKIE, "")
    active = int(raw) if raw.isdigit() else person.id
    out = [ws_out(person, "owner", person, active)]
    for ws, role in db.execute(select(User, Membership.role).join(Membership, Membership.workspace_id == User.id)
                               .where(Membership.member_id == person.id).order_by(func.lower(User.company))):
        out.append(ws_out(ws, role, person, active))
    return out


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    industry: str = Field("", max_length=40)


@router.post("/api/workspaces")
def create_workspace(body: WorkspaceIn, person: User = Depends(current_person), db: Session = Depends(get_db)):
    owned = db.scalar(select(func.count()).select_from(Membership).where(Membership.member_id == person.id,
                                                                          Membership.role == "owner")) or 0
    if owned >= MAX_WORKSPACES:
        raise HTTPException(400, f"You can run up to {MAX_WORKSPACES} client workspaces.")
    ws = User(name=body.name.strip(), company=body.name.strip(), industry=body.industry, kind="workspace",
              email=f"ws-{uuid.uuid4().hex}@{WORKSPACE_DOMAIN}", password_hash="!", is_verified=True)
    db.add(ws)
    db.flush()
    db.add(Membership(workspace_id=ws.id, member_id=person.id, role="owner"))
    db.commit()
    return ws_out(ws, "owner", person, ws.id)


@router.post("/api/workspaces/{wid}/switch")
def switch(wid: int, response: Response, person: User = Depends(current_person), db: Session = Depends(get_db)):
    role = role_in(db, person, wid)
    if not role:
        raise HTTPException(404, "Workspace not found.")
    response.set_cookie(WORKSPACE_COOKIE, str(wid), httponly=True, secure=settings.cookie_secure, samesite="lax",
                        max_age=settings.session_days * 86400, path="/")
    return ws_out(db.get(User, wid), role, person, wid)


class WorkspacePatch(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=160)
    require_approval: Optional[bool] = None


@router.patch("/api/workspaces/{wid}")
def update_workspace(wid: int, body: WorkspacePatch, person: User = Depends(current_person), db: Session = Depends(get_db)):
    ws = _need(db, person, wid)
    if body.name is not None:
        ws.company = body.name.strip()
        if ws.kind == "workspace":
            ws.name = body.name.strip()
    if body.require_approval is not None:
        if body.require_approval and not settings.agency_features:
            raise HTTPException(400, "Client approvals aren't available.")
        ws.require_approval = body.require_approval
    db.commit()
    return ws_out(ws, role_in(db, person, wid), person, wid)


class DeleteIn(BaseModel):
    confirm_name: str


@router.delete("/api/workspaces/{wid}")
def delete_workspace(wid: int, body: DeleteIn, response: Response, person: User = Depends(current_person),
                     db: Session = Depends(get_db)):
    """Deletes a client workspace and everything in it (sites, leads, campaigns...). Owners only; type its name."""
    ws = _need(db, person, wid, roles=("owner",))
    if ws.kind != "workspace":
        raise HTTPException(400, "This is your own account, not a client workspace.")
    if body.confirm_name.strip().lower() != (ws.company or ws.name).strip().lower():
        raise HTTPException(400, "Type the workspace's name exactly to delete it.")
    # Same path as deleting a project: pause its ads and take its pages down first, never just drop the rows.
    from .projects import delete_project_data
    out = delete_project_data(db, person, ws)
    response.delete_cookie(WORKSPACE_COOKIE, path="/")
    return {"ok": True, **out}


# ---- People -----------------------------------------------------------------------------------------------
class InviteIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "editor", "client"]


def _agency_only() -> None:
    """Client approvals and the client role are agency features, off for release 1 (settings.agency_features)."""
    if not settings.agency_features:
        raise HTTPException(404, "Not found.")


@router.get("/api/workspaces/{wid}/members")
def members(wid: int, person: User = Depends(current_person), db: Session = Depends(get_db)):
    ws = _need(db, person, wid, roles=("owner", "admin", "editor"))
    rows = [{"id": u.id, "name": u.name, "email": u.email, "role": r}
            for u, r in db.execute(select(User, Membership.role).join(Membership, Membership.member_id == User.id)
                                   .where(Membership.workspace_id == wid).order_by(User.name))]
    if ws.kind == "person":
        rows.insert(0, {"id": ws.id, "name": ws.name, "email": ws.email, "role": "owner"})
    invites = [{"id": i.id, "email": i.email, "role": i.role, "expires_at": i.expires_at.isoformat() + "Z"}
               for i in db.scalars(select(Invite).where(Invite.workspace_id == wid, Invite.accepted_at.is_(None),
                                                        Invite.expires_at > utcnow()))]
    return {"members": rows, "invites": invites}


@router.post("/api/workspaces/{wid}/invites")
def invite(wid: int, body: InviteIn, bg: BackgroundTasks, person: User = Depends(current_person), db: Session = Depends(get_db)):
    from .mailer import send_email
    ws = _need(db, person, wid)
    if body.role == "client" and not settings.agency_features:
        raise HTTPException(400, "Invite people as an admin or an editor.")
    email = body.email.lower()
    existing = db.scalar(select(User).where(func.lower(User.email) == email, User.kind == "person"))
    if existing and role_in(db, existing, wid):
        raise HTTPException(409, "They already have access.")
    name = ws.company or ws.name
    link = f"{settings.public_url}/signup?email={email}"
    if existing and existing.is_verified:
        db.add(Membership(workspace_id=wid, member_id=existing.id, role=body.role))
        db.commit()
        bg.add_task(send_email, email, f"You now have access to {name} on AIMVA",
                    f"{person.name} gave you {body.role} access to {name}. Sign in at {settings.public_url}/login")
        return {"added": True, "email": email, "role": body.role}
    db.execute(delete(Invite).where(Invite.workspace_id == wid, func.lower(Invite.email) == email, Invite.accepted_at.is_(None)))
    db.add(Invite(workspace_id=wid, email=email, role=body.role, invited_by=person.id,
                  expires_at=utcnow() + timedelta(days=INVITE_DAYS)))
    db.commit()
    bg.add_task(send_email, email, f"{person.name} invited you to {name} on AIMVA",
                f"Create your account with this email address to join: {link}\nThe invitation lasts {INVITE_DAYS} days.")
    return {"invited": True, "email": email, "role": body.role}


@router.delete("/api/workspaces/{wid}/members/{member_id}")
def remove_member(wid: int, member_id: int, person: User = Depends(current_person), db: Session = Depends(get_db)):
    _need(db, person, wid)
    m = db.scalar(select(Membership).where(Membership.workspace_id == wid, Membership.member_id == member_id))
    if not m:
        raise HTTPException(404, "Not a member.")
    if m.role == "owner":
        owners = db.scalar(select(func.count()).select_from(Membership).where(Membership.workspace_id == wid,
                                                                              Membership.role == "owner"))
        if owners <= 1:
            raise HTTPException(400, "A workspace needs at least one owner.")
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.delete("/api/workspaces/{wid}/invites/{iid}")
def cancel_invite(wid: int, iid: int, person: User = Depends(current_person), db: Session = Depends(get_db)):
    _need(db, person, wid)
    inv = db.get(Invite, iid)
    if not inv or inv.workspace_id != wid:
        raise HTTPException(404, "Invite not found.")
    db.delete(inv)
    db.commit()
    return {"ok": True}


# ---- Client approvals --------------------------------------------------------------------------------------
KINDS = {"campaign": Campaign, "site": Site, "asset": Asset}


def approval_out(a: Approval) -> dict:
    return {"id": a.id, "kind": a.kind, "ref_id": a.ref_id, "title": a.title, "note": a.note, "status": a.status,
            "comment": a.comment, "created_at": a.created_at.isoformat() + "Z",
            "decided_at": a.decided_at.isoformat() + "Z" if a.decided_at else None}


def _object(db: Session, ws: User, kind: str, ref_id: int):
    obj = db.get(KINDS[kind], ref_id) if kind in KINDS else None
    if not obj or obj.user_id != ws.id:
        raise HTTPException(404, "Nothing to approve with that id.")
    return obj


def fingerprint(kind: str, obj) -> str:
    """What the client signs off on: the content only. Visits, stats, domain checks and deploy URLs don't count,
    so a page view or a stats sync never undoes an approval."""
    if kind == "site":
        data = [obj.html or "", obj.pages or []]
    elif kind == "campaign":
        data = [obj.name, obj.objective, obj.daily_budget, obj.creative, obj.targeting, obj.lead_form]
    else:
        data = [obj.url, obj.prompt, obj.params]
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _latest(db: Session, ws: User, kind: str, ref_id: int) -> Optional[Approval]:
    return db.scalar(select(Approval).where(Approval.workspace_id == ws.id, Approval.kind == kind, Approval.ref_id == ref_id)
                     .order_by(Approval.id.desc()))


def require_approved(db: Session, ws: User, kind: str, ref_id: int) -> None:
    """When the workspace asks for client sign-off, block publishing until the latest request is approved
    and the content hasn't changed since."""
    if not ws.require_approval or not settings.agency_features:
        return
    a = _latest(db, ws, kind, ref_id)
    obj = db.get(KINDS[kind], ref_id)
    if not a or a.status != "approved" or (obj and a.content_hash and a.content_hash != fingerprint(kind, obj)):
        raise HTTPException(409, "Waiting for the client's approval. Send it for approval, then publish once they say yes.")


def keep_approved(db: Session, ws: User, kind: str, ref_id: int) -> None:
    """Publishing itself rewrites a page (new address in the lead form, SEO tags). Those are part of the approved
    launch, so move the approval's fingerprint along with them. The caller commits."""
    if not ws.require_approval or not settings.agency_features:
        return
    a, obj = _latest(db, ws, kind, ref_id), db.get(KINDS[kind], ref_id)
    if a and obj and a.status == "approved":
        a.content_hash = fingerprint(kind, obj)


def approval_state(db: Session, ws: User, kind: str, ref_id: int) -> dict:
    """Where one page or campaign stands with the client, for the Publish / Launch button.
    state: none (never sent), pending, changes (client asked for changes), approved, edited (approved, then changed)."""
    if not ws.require_approval or not settings.agency_features:
        return {"required": False, "state": "approved", "approval": None}
    a = _latest(db, ws, kind, ref_id)
    if not a or a.status == "withdrawn":
        return {"required": True, "state": "none", "approval": None}
    state = a.status
    obj = db.get(KINDS[kind], ref_id)
    if a.status == "approved" and obj and a.content_hash and a.content_hash != fingerprint(kind, obj):
        state = "edited"
    return {"required": True, "state": state, "approval": approval_out(a)}


def approval_preview(db: Session, ws: User, a: Approval) -> dict:
    """What the client looks at before deciding. Sites open as a draft preview; campaigns show the ad itself,
    because a client can't open the Campaigns pages."""
    obj = db.get(KINDS[a.kind], a.ref_id) if a.kind in KINDS else None
    if not obj or obj.user_id != ws.id:
        return {}
    if a.kind == "site":
        return {"preview_url": f"/api/sites/{obj.id}/preview", "live_url": obj.deploy_url or None}
    if a.kind == "campaign":
        cr = obj.creative or {}
        return {"platform": obj.platform, "objective": obj.objective, "daily_budget": obj.daily_budget,
                "headline": cr.get("headline", ""), "text": cr.get("text", ""), "image_url": cr.get("image_url", ""),
                "cta": cr.get("cta", ""), "locations": (obj.targeting or {}).get("locations", [])}
    return {"image_url": obj.url}


class ApprovalIn(BaseModel):
    kind: Literal["campaign", "site", "asset"]
    ref_id: int
    note: str = Field("", max_length=2000)


@router.post("/api/approvals")
def request_approval(body: ApprovalIn, request: Request, bg: BackgroundTasks, ws: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    from .mailer import send_email
    _agency_only()
    obj = _object(db, ws, body.kind, body.ref_id)
    if request.state.role == "client":
        raise HTTPException(403, "Only the agency sends things for approval.")
    db.execute(Approval.__table__.update().where(Approval.workspace_id == ws.id, Approval.kind == body.kind,
                                                 Approval.ref_id == body.ref_id, Approval.status == "pending")
               .values(status="withdrawn"))
    title = getattr(obj, "name", None) or getattr(obj, "prompt", "") or body.kind
    a = Approval(workspace_id=ws.id, kind=body.kind, ref_id=body.ref_id, title=str(title)[:200], note=body.note,
                 requested_by=request.state.person.id)
    db.add(a)
    db.commit()
    for to in member_emails(db, ws, roles=("client",)):
        bg.add_task(send_email, to, f"Please review: {a.title}",
                    f"{request.state.person.name} sent you a {body.kind} to approve.\n\n{body.note}\n\n"
                    f"Review it at {settings.public_url}/app")
    live.publish(ws.id, "approval", {"type": "requested", "approval": approval_out(a)})
    return approval_out(a)


@router.get("/api/approvals")
def list_approvals(status: str = "", preview: bool = False, ws: User = Depends(current_user), db: Session = Depends(get_db)):
    _agency_only()
    q = select(Approval).where(Approval.workspace_id == ws.id)
    if status:
        q = q.where(Approval.status == status)
    rows = db.scalars(q.order_by(Approval.id.desc()).limit(200)).all()
    if not preview:
        return [approval_out(a) for a in rows]
    people = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_({a.requested_by for a in rows if a.requested_by})))}
    return [{**approval_out(a), "requested_by": people.get(a.requested_by, ""), "preview": approval_preview(db, ws, a)} for a in rows]


@router.get("/api/approvals/status")
def approval_status(kind: Literal["campaign", "site", "asset"], ref_id: int, ws: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    _object(db, ws, kind, ref_id)
    return approval_state(db, ws, kind, ref_id)  # always answers: off means {"required": false, "state": "approved"}


class DecideIn(BaseModel):
    decision: Literal["approved", "changes"]
    comment: str = Field("", max_length=2000)


@router.post("/api/approvals/{aid}/decide")
def decide(aid: int, body: DecideIn, request: Request, bg: BackgroundTasks, ws: User = Depends(current_user),
           db: Session = Depends(get_db)):
    from .mailer import send_email
    _agency_only()
    if request.state.role == "editor":
        raise HTTPException(403, "The client (or the workspace owner on their behalf) decides approvals.")
    a = db.get(Approval, aid)
    if not a or a.workspace_id != ws.id:
        raise HTTPException(404, "Approval not found.")
    if a.status != "pending":
        raise HTTPException(409, f"This was already {a.status}.")
    if body.decision == "changes" and not body.comment.strip():
        raise HTTPException(400, "Say what should change.")
    a.status, a.comment, a.decided_by, a.decided_at = body.decision, body.comment.strip(), request.state.person.id, utcnow()
    obj = db.get(KINDS[a.kind], a.ref_id)
    a.content_hash = fingerprint(a.kind, obj) if obj and a.status == "approved" else None
    db.commit()
    requester = db.get(User, a.requested_by) if a.requested_by else None
    if requester:
        verdict = "approved" if a.status == "approved" else "asked for changes on"
        bg.add_task(send_email, requester.email, f"{request.state.person.name} {verdict} {a.title}", a.comment or "No comment.")
    live.publish(ws.id, "approval", {"type": "decided", "approval": approval_out(a)})
    return approval_out(a)
