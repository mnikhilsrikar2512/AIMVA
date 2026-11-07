"""Campaign Autopilot: a daily look at every campaign using the Command Center's own recommendations.

suggest mode (default): nothing changes; the day's top fixes are lined up for one click.
auto mode: safe, reversible fixes run by themselves within guardrails (a few actions a day, budget increases
capped, never placing calls or spending more than the product's budget allows). Every action is logged as a
Command Center decision, so it shows in the decision log and can be undone like any other."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import Job, setting
from ..models import Campaign, Decision, User, utcnow

SAFE = {"pause_campaign", "trim_budgets"}  # always reversible and never increase spend
SCALING = {"scale_budget", "move_budget"}  # only when the user allows it, and within the cap


def run(db: Session, user: User, force: bool = False) -> dict:
    from ..routers.command import compute, execute, recommendations
    s = setting(db, user.id, "autopilot")
    if not (s.enabled or force):
        return {"skipped": "Autopilot is off."}
    cfg = s.config or {}
    job = Job(db, user.id, "autopilot", "Autopilot is checking your campaigns")
    ctx = compute(db, user, 30)
    recs = recommendations(db, user, ctx)
    live = [c for c in ctx["campaigns"].values() if c["status"] == "active"]
    job.step(f"Checked {len(ctx['campaigns'])} campaign{'s' if len(ctx['campaigns']) != 1 else ''} ({len(live)} running)")
    done, waiting = [], []
    allowed = SAFE | (SCALING if cfg.get("allow_scale") else set())
    cap = 1 + max(0, min(100, int(cfg.get("max_scale_pct", 20)))) / 100
    for r in recs:
        t = r["action"]["type"]
        ok = s.mode == "auto" and t in allowed and len(done) < int(cfg.get("max_actions", 3))
        if ok and t == "scale_budget":
            c = db.get(Campaign, int(r["campaign_id"]))
            ok = bool(c and c.daily_budget and float(r["action"]["daily_budget"]) <= c.daily_budget * cap)
        if not ok:
            if t not in ("open", "ack"):
                waiting.append({"key": r["key"], "title": r["title"], "priority": r["priority"]})
            continue
        try:
            result = execute(db, user, r)
        except HTTPException as e:
            job.step(r["title"], "failed", str(e.detail))
            continue
        db.add(Decision(user_id=user.id, key=r["key"], title=r["title"], decision="accepted", result=result,
                        note="Done by Autopilot", until=utcnow() + timedelta(days=7)))
        db.commit()
        done.append({"title": r["title"], "result": result})
        job.step(r["title"], "done", result)
    if waiting:
        job.step(f"{len(waiting)} suggestion{'s' if len(waiting) != 1 else ''} waiting for your OK in Command Center", "skipped",
                 "; ".join(w["title"] for w in waiting[:3]))
    s.last_run_at = utcnow()
    title = (f"Autopilot made {len(done)} change{'s' if len(done) != 1 else ''}" if done else
             f"Autopilot found {len(waiting)} thing{'s' if len(waiting) != 1 else ''} to review" if waiting else
             "Autopilot: all campaigns look healthy")
    job.finish({"done": done, "waiting": waiting[:6], "mode": s.mode}, title=title)
    return {"done": done, "waiting": waiting, "job_id": job.row.id}
