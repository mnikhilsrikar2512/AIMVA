"""Work agents: they do the busy work for the user instead of asking them to do it.

  launch         one link, brochure or sentence → product, Showcase page, ad drafts, voice assistant, follow-ups
  concierge      every new lead gets an instant WhatsApp welcome and day-2 / day-7 follow-ups until they reply
  autopilot      checks campaigns daily; fixes the safe things itself (auto) or lines them up for one click (suggest)
  weekly_report  Monday summary of leads, spend and what to do next, by email and on the dashboard
  page_fixer     fixes safe launch issues on every new page (alt text, mobile tag, title, description, dead links)

Each run is recorded as an AgentJob with its steps, so the user can see exactly what was done for them.
(AI writing itself goes through app/ai_engine.py, which picks the user's AI, the shared key, free AI or rules.)
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import live
from ..models import AgentJob, AgentSetting, utcnow

log = logging.getLogger("aimva.agents")

KINDS = {
    "launch": {"label": "Launch Agent", "mode": "auto", "config": {}},
    "concierge": {"label": "Lead Concierge", "mode": "auto", "config": {"messages": {}}},
    "autopilot": {"label": "Campaign Autopilot", "mode": "suggest",
                  "config": {"max_actions": 3, "allow_scale": False, "max_scale_pct": 20}},
    "weekly_report": {"label": "Weekly Report", "mode": "auto", "config": {"email": True}},
    "page_fixer": {"label": "Page Fixer", "mode": "auto", "config": {}},
    "lead_alerts": {"label": "Lead alerts", "mode": "auto", "config": {"email": True}},  # app/alerts.py
}


def setting(db: Session, user_id: int, kind: str) -> AgentSetting:
    s = db.scalar(select(AgentSetting).where(AgentSetting.user_id == user_id, AgentSetting.kind == kind))
    if not s:
        d = KINDS[kind]
        s = AgentSetting(user_id=user_id, kind=kind, enabled=True, mode=d["mode"], config=dict(d["config"]))
        db.add(s)
        db.flush()
    return s


def enabled(db: Session, user_id: int, kind: str) -> bool:
    return setting(db, user_id, kind).enabled


def job_out(j: AgentJob) -> dict:
    return {"id": j.id, "kind": j.kind, "agent": KINDS[j.kind]["label"], "title": j.title, "status": j.status, "steps": j.steps,
            "result": j.result, "error": j.error, "created_at": j.created_at.isoformat(),
            "finished_at": j.finished_at.isoformat() if j.finished_at else None}


class Job:
    """Records an agent's work step by step and tells the user's open tabs as it goes."""

    def __init__(self, db: Session, user_id: int, kind: str, title: str, input: Optional[dict] = None, job: Optional[AgentJob] = None):
        self.db = db
        self.row = job or AgentJob(user_id=user_id, kind=kind, title=title[:200], input=input or {})
        if not job:
            db.add(self.row)
        self.row.status = "running"
        db.commit()

    def step(self, label: str, status: str = "done", detail: str = "") -> None:
        self.row.steps = [*self.row.steps, {"label": label[:160], "status": status, "detail": detail[:400]}]
        self.db.commit()
        live.publish(self.row.user_id, "agent", {"type": "progress", "job": job_out(self.row)})

    def finish(self, result: Optional[dict] = None, title: str = "", status: str = "done", error: str = "") -> AgentJob:
        if title:
            self.row.title = title[:200]
        self.row.result, self.row.status, self.row.error, self.row.finished_at = result or {}, status, error[:500], utcnow()
        self.db.commit()
        live.publish(self.row.user_id, "agent", {"type": "finished", "job": job_out(self.row)})
        return self.row


def record(db: Session, user_id: int, kind: str, title: str, result: Optional[dict] = None, steps: Optional[list] = None) -> AgentJob:
    """A one-line agent action for the activity feed (e.g. the concierge welcoming a lead)."""
    j = AgentJob(user_id=user_id, kind=kind, title=title[:200], status="done", steps=steps or [], result=result or {}, finished_at=utcnow())
    db.add(j)
    db.commit()
    live.publish(user_id, "agent", {"type": "finished", "job": job_out(j)})
    return j
