"""Projects and the idea-first setup (PRD "Requirements: projects", "Backend and API requirements"; design.md 3.5, 11).

A project is one business or idea. Underneath it is a workspace: the owner's own account is their first project, and
every other project is a User row with kind="workspace" (see workspaces.py). Every module already scopes its data to
the workspace a request works in, so projects stay closed worlds without a project_id on every table.

  GET    /api/projects                     every project the person works on, newest activity first
  POST   /api/projects                     a new project (a workspace), ready for /start
  PATCH  /api/projects/{id}                rename, archive or restore
  DELETE /api/projects/{id}                pause its ads, take its pages down, then delete it (never the owner's account)
  POST   /api/start                        idea in -> profile, gaps, modules out; the first module starts by itself
  GET    /api/modules/{key}/prompt         the pre-written prompt for a module, from the profile
  GET    /api/projects/{id}/modules        revealed modules (the rail order)
  PUT    /api/projects/{id}/modules
  POST   /api/route                        a sentence typed on Home -> the module it belongs to, the prompt, and
                                           whether anything in it pointed there (sure); never why

No response explains how an idea or prompt was read, and none names an AI provider (project rules).
"""
import logging
import re
import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import idea_sense
from .db import get_db
from .models import AgentJob, Asset, BrandKit, Campaign, Lead, Membership, ReferenceFile, Site, User, utcnow
from .security import WORKSPACE_COOKIE, current_person, current_user, rate_limit
from .workspaces import MAX_WORKSPACES, WORKSPACE_DOMAIN, role_in

log = logging.getLogger("aimva.projects")
router = APIRouter(tags=["projects"])
WRITERS = ("owner", "admin", "editor")
ModuleKey = Literal["page", "whatsapp", "calls", "pictures", "campaigns", "videos"]


# ---- helpers ----------------------------------------------------------------------------------------------
def projects_of(db: Session, person: User) -> list:
    """[(workspace, role)] for every project this person can open: their own account first."""
    rows = [(person, "owner")]
    rows += list(db.execute(select(User, Membership.role).join(Membership, Membership.workspace_id == User.id)
                            .where(Membership.member_id == person.id)).all())
    return rows


def _project(db: Session, person: User, pid: int, roles=WRITERS) -> tuple:
    role = role_in(db, person, pid)
    ws = db.get(User, pid) if role else None
    if not ws:
        raise HTTPException(404, "Project not found.")
    if role not in roles:
        raise HTTPException(403, "Only the project's owner can do that." if roles == ("owner",)
                            else "Only the project's owner or an admin can do that." if roles == ("owner", "admin")
                            else "You can view this project but not change it.")
    return ws, role


def _profile(ws: User) -> dict:
    return dict((ws.onboarding_answers or {}).get("profile") or {})


def project_name(ws: User) -> str:
    """The business's name; before it has one, a few words of its idea ("Dental clinic"), never the person's name."""
    answers = ws.onboarding_answers or {}
    if ws.company:
        return ws.company
    if (answers.get("profile") or {}).get("name"):
        return answers["profile"]["name"]
    if answers.get("idea"):
        head = re.split(r"[,.;:!?\n]| in | at | for | near | from ", answers["idea"].strip(), maxsplit=1)[0].strip()
        head = re.sub(r"^(?:i|we)\s+(?:want to|am|are|run|have)\s+(?:start\s+|open\s+)?(?:an?\s+)?", "", head, flags=re.I)
        if head:
            return (head[:1].upper() + head[1:])[:60]
    return ws.name


def _waiting(db: Session, ws: User) -> int:
    from . import lead_reply
    leads = list(db.scalars(select(Lead).where(Lead.user_id == ws.id, Lead.stage.notin_(("won", "lost")))
                            .order_by(Lead.id.desc()).limit(300)))
    if not leads:
        return 0
    act = lead_reply.activity(db, ws.id, leads)
    return sum(1 for l in leads if act[l.id]["needs_reply"])


def _last_activity(db: Session, ws: User):
    times = [ws.created_at]
    for col in (Lead.created_at, Site.updated_at, Asset.created_at, Campaign.created_at):
        t = db.scalar(select(func.max(col)).where(col.class_.user_id == ws.id))
        if t:
            times.append(t)
    return max(times)


def project_out(db: Session, ws: User, role: str, person: User, active_id: int, full: bool = True) -> dict:
    answers = ws.onboarding_answers or {}
    out = {"id": ws.id, "name": project_name(ws), "role": role, "own": ws.id == person.id, "active": ws.id == active_id,
           "idea": (answers.get("idea") or "")[:200], "archived": bool(answers.get("archived")),
           "modules": answers.get("modules") or [], "set_up": bool(answers.get("profile"))}
    if full:
        thumb = db.scalar(select(Asset.url).where(Asset.user_id == ws.id, Asset.kind == "image").order_by(Asset.id.desc()).limit(1))
        out.update({"thumbnail": thumb, "waiting": _waiting(db, ws), "last_activity": _last_activity(db, ws).isoformat() + "Z"})
    return out


def _active(request: Request, person: User) -> int:
    raw = request.headers.get("x-aimva-workspace") or request.cookies.get(WORKSPACE_COOKIE, "")
    return int(raw) if raw.isdigit() else person.id


# ---- the Projects window ----------------------------------------------------------------------------------
@router.get("/api/projects")
def list_projects(request: Request, archived: bool = False, person: User = Depends(current_person),
                  db: Session = Depends(get_db)):
    from .workspaces import accept_invites
    accept_invites(db, person)
    active = _active(request, person)
    out = [project_out(db, ws, role, person, active) for ws, role in projects_of(db, person)]
    out = [p for p in out if p["archived"] == archived]
    out.sort(key=lambda p: p["last_activity"], reverse=True)
    return out


def landing(db: Session, person: User) -> str:
    """Where a sign-in lands (PRD P-5): "projects" when the person has two or more open projects, else "home"."""
    open_ = [ws for ws, _ in projects_of(db, person) if not (ws.onboarding_answers or {}).get("archived")]
    if person in open_ and not _has_anything(db, person):
        open_.remove(person)  # someone invited into one project with an empty account of their own lands inside it
    return "projects" if len(open_) >= 2 else "home"


def _has_anything(db: Session, ws: User) -> bool:
    if (ws.onboarding_answers or {}).get("profile") or ws.industry:
        return True
    return any(db.scalar(select(func.count()).select_from(M).where(M.user_id == ws.id)) for M in (Lead, Site, Campaign))


class ProjectIn(BaseModel):
    name: str = Field("", max_length=160)  # optional: /start can name it from the idea


@router.post("/api/projects")
def create_project(body: ProjectIn, request: Request, response: Response, person: User = Depends(current_person),
                   db: Session = Depends(get_db)):
    """A new project, opened straight away so /start fills it. Starts with the current project's brand kit (P-6)."""
    owned = db.scalar(select(func.count()).select_from(Membership).where(Membership.member_id == person.id,
                                                                          Membership.role == "owner")) or 0
    if owned >= MAX_WORKSPACES:
        raise HTTPException(400, f"You can run up to {MAX_WORKSPACES} projects.")
    rate_limit(f"new-project:{person.id}", 20, 3600)
    name = body.name.strip() or "New project"
    ws = User(name=name, company=name if body.name.strip() else "", kind="workspace", is_verified=True, password_hash="!",
              email=f"ws-{uuid.uuid4().hex}@{WORKSPACE_DOMAIN}", onboarding_answers={})
    db.add(ws)
    db.flush()
    db.add(Membership(workspace_id=ws.id, member_id=person.id, role="owner"))
    source_id = _active(request, person)
    if not role_in(db, person, source_id):
        source_id = person.id
    kit = db.scalar(select(BrandKit).where(BrandKit.user_id == source_id))
    if kit:
        db.add(BrandKit(user_id=ws.id, name="", tagline="", colors=list(kit.colors or []), voice=kit.voice,
                        voice_notes=kit.voice_notes, style=list(kit.style or []), audience="", avoid=kit.avoid))
    db.commit()
    from .config import settings
    response.set_cookie(WORKSPACE_COOKIE, str(ws.id), httponly=True, secure=settings.cookie_secure, samesite="lax",
                        max_age=settings.session_days * 86400, path="/")
    return project_out(db, ws, "owner", person, ws.id)


class ProjectPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=160)
    archived: Optional[bool] = None


@router.patch("/api/projects/{pid}")
def update_project(pid: int, body: ProjectPatch, request: Request, person: User = Depends(current_person),
                   db: Session = Depends(get_db)):
    ws, role = _project(db, person, pid, roles=("owner", "admin"))
    if body.name is not None:
        ws.company = body.name.strip()
        if ws.kind == "workspace":
            ws.name = body.name.strip()
    if body.archived is not None:
        if ws.id == person.id:
            raise HTTPException(400, "Your first project can't be archived.")
        ws.onboarding_answers = {**(ws.onboarding_answers or {}), "archived": body.archived}
    db.commit()
    return project_out(db, ws, role, person, _active(request, person))


class DeleteIn(BaseModel):
    confirm_name: str


def delete_project_data(db: Session, person: User, ws: User) -> dict:
    """Pause ads, take pages down, revoke what only this project uses, remove files, then delete the workspace.
    A connected account another of the person's projects also uses is NOT revoked: revoking a Meta or Google grant
    drops it for every project that shares the same login."""
    from .account import erase_account
    from .models import Integration
    from . import teardown
    stopped = teardown.stop_everything(db, ws)
    others = [w.id for w, _ in projects_of(db, person) if w.id != ws.id]
    shared = set(db.scalars(select(Integration.provider).where(Integration.user_id.in_(others)))) if others else set()
    result = erase_account(db, ws, keep_grants=shared)
    db.commit()
    log.info("project %s deleted by %s (%d ads not paused, %d pages still online)", ws.id, person.id,
             len(stopped["campaigns_not_paused"]), len(stopped["pages_still_online"]))
    return {**stopped, "revoked": result["revoked"]}


@router.delete("/api/projects/{pid}")
def delete_project(pid: int, body: DeleteIn, request: Request, response: Response, person: User = Depends(current_person),
                   db: Session = Depends(get_db)):
    """Delete one project. The owner's own account is never deleted here; that is account deletion in Settings."""
    ws, _ = _project(db, person, pid, roles=("owner",))
    if ws.id == person.id or ws.kind != "workspace":
        raise HTTPException(400, "This is your first project. To remove it, delete your account in Settings.")
    typed = body.confirm_name.strip().lower()
    names = {n.strip().lower() for n in (project_name(ws), ws.company, ws.name) if n and n.strip()}  # the card shows project_name
    if typed not in names:
        raise HTTPException(400, "Type the project's name exactly to delete it.")
    was_active = _active(request, person) == ws.id
    out = delete_project_data(db, person, ws)
    if was_active:  # deleting another project from the Projects window must not switch the person out of this one
        response.delete_cookie(WORKSPACE_COOKIE, path="/")
    return {"ok": True, **out}


# ---- inviting one person to the projects the owner picks -------------------------------------------------
class ProjectInviteIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "editor"] = "editor"
    project_ids: List[int] = Field(min_length=1, max_length=MAX_WORKSPACES)


@router.post("/api/projects/invite")
def invite_to_projects(body: ProjectInviteIn, bg: BackgroundTasks, person: User = Depends(current_person),
                       db: Session = Depends(get_db)):
    """Invite one teammate to the projects the owner ticks (any number, from one to all of them), with one email.
    Every project must be one this person manages; otherwise nothing is changed."""
    from datetime import timedelta
    from sqlalchemy import delete
    from .config import settings
    from .mailer import send_email
    from .models import Invite
    from .workspaces import INVITE_DAYS
    rate_limit(f"invite:{person.id}", 30, 3600)
    targets = [_project(db, person, pid, roles=("owner", "admin"))[0] for pid in dict.fromkeys(body.project_ids)]
    email = body.email.lower()
    existing = db.scalar(select(User).where(func.lower(User.email) == email, User.kind == "person"))
    results = []
    for ws in targets:
        if existing and role_in(db, existing, ws.id):
            result = "already"
        elif existing and existing.is_verified:
            db.add(Membership(workspace_id=ws.id, member_id=existing.id, role=body.role))
            result = "added"
        else:
            db.execute(delete(Invite).where(Invite.workspace_id == ws.id, func.lower(Invite.email) == email,
                                            Invite.accepted_at.is_(None)))
            db.add(Invite(workspace_id=ws.id, email=email, role=body.role, invited_by=person.id,
                          expires_at=utcnow() + timedelta(days=INVITE_DAYS)))
            result = "invited"
        results.append({"id": ws.id, "name": project_name(ws), "result": result})
    db.commit()
    names = ", ".join(r["name"] for r in results if r["result"] != "already")
    if names and existing and existing.is_verified:
        bg.add_task(send_email, email, f"You now have access to {names} on AIMVA",
                    f"{person.name} gave you {body.role} access to {names}. Sign in at {settings.public_url}/login")
    elif names:
        bg.add_task(send_email, email, f"{person.name} invited you to {names} on AIMVA",
                    f"Create your account with this email address to join: {settings.public_url}/signup?email={email}\n"
                    f"The invitation lasts {INVITE_DAYS} days.")
    return {"email": email, "role": body.role, "projects": results}


# ---- revealed modules -------------------------------------------------------------------------------------
def module_out(key: str, i: int, profile: dict) -> dict:
    return {"key": key, "line": outcome_line(key, profile), "auto_start": i == 0}


@router.get("/api/projects/{pid}/modules")
def get_modules(pid: int, person: User = Depends(current_person), db: Session = Depends(get_db)):
    ws, _ = _project(db, person, pid, roles=WRITERS + ("client",))
    p = _profile(ws)
    return {"modules": [module_out(k, i, p) for i, k in enumerate((ws.onboarding_answers or {}).get("modules") or [])]}


class ModulesIn(BaseModel):
    modules: List[ModuleKey] = Field(max_length=6)


@router.put("/api/projects/{pid}/modules")
def put_modules(pid: int, body: ModulesIn, person: User = Depends(current_person), db: Session = Depends(get_db)):
    ws, _ = _project(db, person, pid)
    keys = list(dict.fromkeys(body.modules))
    ws.onboarding_answers = {**(ws.onboarding_answers or {}), "modules": keys}
    db.commit()
    p = _profile(ws)
    return {"modules": [module_out(k, i, p) for i, k in enumerate(keys)]}


# ---- pre-written prompts ----------------------------------------------------------------------------------
def _who(p: dict) -> str:
    name = p.get("name") or "my business"
    where = p.get("area") or p.get("city")
    return f"{name} in {where}" if where else name


def outcome_line(key: str, p: dict) -> str:
    """One line on what a module will make for this business (the reveal rows)."""
    place = p.get("area") or p.get("city") or "your area"
    lines = {
        "page": "A page that turns visitors into enquiries" if p.get("kind") != "idea_only" else "A waitlist page to test the idea",
        "whatsapp": "Every enquiry answered on WhatsApp within a minute, in the customer's language",
        "calls": "A call back to every new lead, in their language",
        "pictures": "Pictures for posts, ads and your page",
        "campaigns": f"Ads that bring enquiries from {place}" if p.get("kind") != "b2b" else "LinkedIn and Google ads aimed at buyers",
        "videos": "Short videos for reels and ads",
    }
    return lines[key]


def module_prompt(key: str, p: dict) -> str:
    """The prompt a module opens with, written from the profile. The owner presses Enter or changes it."""
    who, offer = _who(p), (p.get("offer") or "").strip().rstrip(".")
    place = p.get("area") or p.get("city") or "my area"
    langs = ", ".join(_language_names(p.get("customer_languages") or [])) or "English"
    prompts = {
        "page": (f"A waitlist page for {offer or who}, asking people to sign up for the launch" if p.get("kind") == "idea_only"
                 else f"A page for {who}: {offer}. Main button: enquire on WhatsApp." if offer
                 else f"A page for {who}. Main button: enquire on WhatsApp."),
        "whatsapp": f"Reply to every new enquiry for {who} within a minute, in {langs}, and offer a call back.",
        "calls": f"Call every new lead for {who} back, in {langs}, and book a time to talk.",
        "pictures": f"A picture for {who}" + (f": {offer}" if offer else "") + ", for Instagram and WhatsApp status.",
        "campaigns": (f"Ads for {who} on LinkedIn and Google, aimed at decision makers" if p.get("kind") == "b2b"
                      else f"Ads for {who} reaching people in and around {place}, sending them to WhatsApp."),
        "videos": f"A 20-second reel for {who}" + (f" showing {offer}" if offer else "") + ".",
    }
    return prompts[key]


def _language_names(codes: list) -> list:
    from .lead_reply import LANGUAGES
    return [LANGUAGES.get(c, "") for c in codes if LANGUAGES.get(c)]


@router.get("/api/modules/{key}/prompt")
def get_prompt(key: ModuleKey, user: User = Depends(current_user)):
    p = _profile(user) or {"name": user.company or "", "kind": "unclear"}
    return {"prompt": module_prompt(key, p), "outcome_line": outcome_line(key, p)}


# ---- /start -----------------------------------------------------------------------------------------------
class StartIn(BaseModel):
    idea: str = Field("", max_length=1000)
    link: str = Field("", max_length=500)
    reference_id: Optional[int] = None
    project_id: Optional[int] = None


@router.post("/api/start")
def start(body: StartIn, bg: BackgroundTasks, request: Request, user: User = Depends(current_user),
          db: Session = Depends(get_db)):
    person = request.state.person
    if body.project_id is not None:
        ws, _ = _project(db, person, body.project_id)
    else:
        if request.state.role not in WRITERS:
            raise HTTPException(403, "You can view this project but not change it.")
        ws = user
    idea, link = body.idea.strip(), body.link.strip()
    if not (idea or link or body.reference_id):
        raise HTTPException(400, "Tell us your idea in a sentence, or paste a link.")
    if body.reference_id:
        r = db.get(ReferenceFile, body.reference_id)
        if not r or r.user_id != ws.id or r.kind != "document":
            raise HTTPException(404, "That file wasn't found.")
    rate_limit(f"start:{person.id}", 10, 3600)
    from .ai_engine import agent_writer
    read = idea_sense.read_idea(idea, link, write=agent_writer(db, ws.id, "site_reader"))  # AI first, rules as backup
    profile, modules = read["profile"], read["modules"]
    if not profile["name"]:
        profile["name"] = ws.company if ws.company and ws.company != "New project" else ""
    answers = ws.onboarding_answers or {}
    gaps = [g for g in read["gaps"] if g not in answers]
    if "customer_languages" in answers:
        profile["customer_languages"] = answers["customer_languages"]
    if answers.get("customer_area") and not profile["city"]:
        profile["area"] = answers["customer_area"]
    ws.onboarding_answers = {**answers, "idea": idea, "link": link, "profile": profile, "modules": modules}
    if profile["name"] and (not ws.company or ws.company == "New project"):
        ws.company = profile["name"]
        if ws.kind == "workspace":
            ws.name = profile["name"]
    if not ws.industry:
        ws.industry = profile["industry"]
    from .routers.onboarding import starter_voice_agent
    starter_voice_agent(db, ws)
    job_id = None
    if modules[0] == "page":
        from .agents.launch import LaunchIn
        from .routers.agents import _run_launch
        launch_in = LaunchIn(url=link, business=profile["name"], description=(idea or link)[:1000],
                             reference_id=body.reference_id)
        j = AgentJob(user_id=ws.id, kind="launch", title="Making your page", status="queued", input=launch_in.model_dump())
        db.add(j)
        db.flush()
        job_id = j.id
    db.commit()
    if job_id:
        bg.add_task(_run_launch, job_id)
    return {"project_id": ws.id, "profile": profile, "gaps": gaps,
            "modules": [module_out(k, i, profile) for i, k in enumerate(modules)], "job_id": job_id}


# ---- Home prompt routing ----------------------------------------------------------------------------------
class RouteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/api/route")
def route_prompt(body: RouteIn, user: User = Depends(current_user)):
    revealed = (user.onboarding_answers or {}).get("modules") or ["page"]
    module, sure = idea_sense.route_sure(body.text, fallback=revealed[0])
    return {"module": module, "prompt": body.text.strip(), "sure": sure}
