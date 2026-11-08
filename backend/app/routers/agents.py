"""API for the work agents (app/agents): their on/off switches, launching, manual runs and the activity feed.
There's no separate Agents page: the switches and results show where the work happens (Dashboard, Leads,
Command Center, Websites)."""
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents import KINDS, job_out, setting
from ..agents.launch import LaunchIn
from ..db import SessionLocal, get_db
from ..models import AgentJob, ReferenceFile, Site, User
from ..security import current_user, rate_limit

router = APIRouter(prefix="/api/agents", tags=["agents"])
Kind = Literal["launch", "concierge", "autopilot", "weekly_report", "page_fixer", "lead_alerts"]


def setting_out(s) -> dict:
    cfg = dict(s.config or {})
    if "push" in cfg:  # device addresses stay on the server; the page only needs to know how many
        cfg["push_devices"] = len(cfg.pop("push") or [])
    return {"kind": s.kind, "label": KINDS[s.kind]["label"], "enabled": s.enabled, "mode": s.mode, "config": cfg,
            "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None}


@router.get("")
def list_agents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = [setting_out(setting(db, user.id, k)) for k in KINDS]
    db.commit()
    return out


class SettingIn(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[Literal["suggest", "auto"]] = None
    config: Optional[dict] = None


ALLOWED_CONFIG = {  # what each agent's config may contain, with limits
    "concierge": {"messages"},
    "autopilot": {"max_actions", "allow_scale", "max_scale_pct"},
    "weekly_report": {"email"},
    "lead_alerts": {"email"},
}


def _clean_config(kind: str, cfg: dict) -> dict:
    out = {k: v for k, v in cfg.items() if k in ALLOWED_CONFIG.get(kind, set())}
    if "messages" in out:
        msgs = out["messages"] if isinstance(out["messages"], dict) else {}
        out["messages"] = {k: str(v).strip()[:1000] for k, v in msgs.items() if k in ("welcome", "day2", "day7") and str(v).strip()}
    if "max_actions" in out:
        out["max_actions"] = max(0, min(10, int(out["max_actions"])))
    if "max_scale_pct" in out:
        out["max_scale_pct"] = max(0, min(50, int(out["max_scale_pct"])))
    for k in ("allow_scale", "email"):
        if k in out:
            out[k] = bool(out[k])
    return out


@router.put("/{kind}")
def update_agent(kind: Kind, body: SettingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = setting(db, user.id, kind)
    if body.enabled is not None:
        s.enabled = body.enabled
    if body.mode is not None:
        s.mode = body.mode
    if body.config is not None:
        try:
            s.config = {**(s.config or {}), **_clean_config(kind, body.config)}
        except (TypeError, ValueError):
            raise HTTPException(422, "Those settings aren't valid.")
    db.commit()
    return setting_out(s)


def _run_launch(job_id: int) -> None:
    from ..agents import launch
    db = SessionLocal()
    try:
        launch.run(db, db.get(AgentJob, job_id))
    finally:
        db.close()


@router.post("/launch")
def launch(body: LaunchIn, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Start the Launch Agent. Returns the job straight away; progress arrives as live "agent" events."""
    rate_limit(f"launch:{user.id}", 6, 3600)
    if not (body.url.strip() or body.description.strip() or body.reference_id):
        raise HTTPException(400, "Give the agent your website link, a brochure, or one line about what you sell.")
    if body.reference_id:
        r = db.get(ReferenceFile, body.reference_id)
        if not r or r.user_id != user.id or r.kind != "document":
            raise HTTPException(404, "That brochure wasn't found in your reference files.")
    title = f"Launching {(body.product or body.description or body.url or 'your offer').strip()[:80]}"
    j = AgentJob(user_id=user.id, kind="launch", title=title, status="queued", input=body.model_dump())
    db.add(j)
    db.commit()
    bg.add_task(_run_launch, j.id)
    return job_out(j)


class RunIn(BaseModel):
    site_id: Optional[int] = None  # page_fixer: which page


@router.post("/{kind}/run")
def run_now(kind: Literal["autopilot", "weekly_report", "page_fixer"], body: RunIn = RunIn(), user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    rate_limit(f"agent-run:{user.id}", 20, 600)
    if kind == "autopilot":
        from ..agents import autopilot
        out = autopilot.run(db, user, force=True)
    elif kind == "weekly_report":
        from ..agents import report
        out = report.run(db, user, force=True)
    else:
        out = fix_site(db, user, body.site_id)
    job = db.scalar(select(AgentJob).where(AgentJob.user_id == user.id, AgentJob.kind == kind).order_by(AgentJob.id.desc()))
    return {"result": out, "job": job_out(job) if job else None}


def fix_site(db: Session, user: User, site_id: Optional[int]) -> dict:
    from ..agents import Job
    from ..agents.fixer import fix_html, remaining
    from .sites import add_version
    s = db.get(Site, site_id) if site_id else None
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Site not found.")
    job = Job(db, user.id, "page_fixer", f"Checking “{s.name}”")
    html, fixed = fix_html(s.html, s.brief or {})
    if fixed:
        s.html = html
        add_version(db, s, "Page Fixer: " + "; ".join(fixed)[:150], "fixer")
        db.commit()
        for f in fixed:
            job.step(f)
    left = remaining(s.html, s.brief or {})
    if left:
        job.step(f"{len(left)} thing{'s' if len(left) != 1 else ''} need{'' if len(left) != 1 else 's'} your eye", "skipped", "; ".join(left[:3]))
    job.finish({"site_id": s.id, "fixed": fixed, "remaining": left},
               title=f"Fixed {len(fixed)} issue{'s' if len(fixed) != 1 else ''} on “{s.name}”" if fixed else f"“{s.name}” needed no automatic fixes")
    return {"fixed": fixed, "remaining": left}


@router.get("/jobs")
def jobs(kind: Optional[Kind] = None, limit: int = Query(20, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(AgentJob).where(AgentJob.user_id == user.id)
    if kind:
        q = q.where(AgentJob.kind == kind)
    return [job_out(j) for j in db.scalars(q.order_by(AgentJob.id.desc()).limit(limit))]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = db.get(AgentJob, job_id)
    if not j or j.user_id != user.id:
        raise HTTPException(404, "Not found.")
    return job_out(j)


@router.get("/leads/{lead_id}/follow-ups")
def lead_follow_ups(lead_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..agents.concierge import pending_for
    from ..models import Lead
    lead = db.get(Lead, lead_id)
    if not lead or lead.user_id != user.id:
        raise HTTPException(404, "Lead not found.")
    return pending_for(db, lead_id)

