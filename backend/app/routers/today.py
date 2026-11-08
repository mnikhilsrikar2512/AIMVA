"""Home is about today: what came in since the owner last looked, who is waiting on them, and what AIMVA will do
by itself before the day ends. The 30-day numbers live on Results; this only answers "what do I do now?".

`since` is the owner's last visit, kept by the browser (no column needed); without it, the last 24 hours.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import lead_reply
from ..db import get_db
from ..models import Call, FollowUp, Lead, LeadEvent, User, utcnow
from ..security import current_user
from .leads import welcomes

router = APIRouter(prefix="/api/today", tags=["today"])


def _since(raw: Optional[str], now: datetime) -> datetime:
    try:
        t = datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
        if t.tzinfo:  # the database keeps naive UTC
            t = t.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return now - timedelta(hours=24)
    return max(now - timedelta(days=30), min(t, now))


def _brief(l: Lead, act: dict) -> dict:
    a = act.get(l.id, {})
    return {"id": l.id, "name": l.name or l.phone or l.email or "Someone", "source": l.source, "phone": l.phone,
            "message": (l.message or "")[:140], "waiting_since": a.get("waiting_since"), "score": l.score,
            "language_name": lead_reply.LANGUAGES.get(l.language or "", "") if l.language not in ("", "en") else ""}


@router.get("")
def today(since: Optional[str] = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    uid, now = user.id, utcnow()
    t0 = _since(since, now)
    open_leads = list(db.scalars(select(Lead).where(Lead.user_id == uid, Lead.stage.notin_(("won", "lost")),
                                                    Lead.opted_out_at.is_(None))
                                 .order_by(Lead.created_at.desc()).limit(300)))
    act = lead_reply.activity(db, uid, open_leads)
    waiting = [l for l in lead_reply.needs_first(open_leads, act) if act[l.id]["needs_reply"]]

    new = list(db.scalars(select(Lead).where(Lead.user_id == uid, Lead.created_at >= t0).order_by(Lead.created_at.desc())))
    wel = welcomes(db, uid, new)
    unsent = [l for l in new if (wel.get(l.id) or {}).get("status") in ("drafted", "failed")]
    won_ids = set(db.scalars(select(LeadEvent.lead_id).where(LeadEvent.user_id == uid, LeadEvent.kind == "stage",
                                                              LeadEvent.created_at >= t0, LeadEvent.title.like("%→ won"))))
    won = [l for l in db.scalars(select(Lead).where(Lead.id.in_(won_ids))) if l.stage == "won"] if won_ids else []
    calls = db.scalar(select(func.count(Call.id)).where(Call.user_id == uid, Call.created_at >= t0,
                                                        Call.status.in_(("completed", "handoff")))) or 0

    end_of_day = now + timedelta(hours=24 - now.hour)
    due = db.scalar(select(func.count(FollowUp.id)).where(FollowUp.user_id == uid, FollowUp.status == "pending",
                                                          FollowUp.due_at <= end_of_day)) or 0
    scheduled_calls = db.scalar(select(func.count(Call.id)).where(Call.user_id == uid, Call.status == "scheduled")) or 0

    return {
        "since": t0.isoformat(),
        "new": {"count": len(new), "leads": [_brief(l, act) for l in new[:5]],
                "by_source": dict(sorted(((s, sum(1 for l in new if l.source == s)) for s in {l.source for l in new}),
                                         key=lambda kv: -kv[1]))},
        "waiting": {"count": len(waiting), "leads": [_brief(l, act) for l in waiting[:5]]},
        "welcome_not_sent": {"count": len(unsent), "lead_id": unsent[0].id if unsent else None,
                             "why": (wel.get(unsent[0].id) or {}).get("note", "") if unsent else ""},
        "won": {"count": len(won), "value": round(sum(l.value or 0 for l in won), 2)},
        "calls": calls,
        "later": {"follow_ups": due, "calls": scheduled_calls},
    }
