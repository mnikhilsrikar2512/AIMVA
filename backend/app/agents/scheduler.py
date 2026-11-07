"""Runs the agents that work on a clock: due follow-ups every minute, Autopilot once a day after 9:00,
the Weekly Report on Monday mornings. One background thread per server process (turn off with AGENTS_SCHEDULER=false).

With several server processes, only the one holding the database lease does the work, so nothing runs twice."""
import logging
import os
import socket
import threading
import uuid
from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..db import SessionLocal
from ..models import AgentSetting, SchedulerLease, User, utcnow

log = logging.getLogger("aimva.agents")
TICK = 60
LEASE_NAME = "agents"
LEASE_S = 3 * TICK  # a crashed holder is replaced within three minutes
HOLDER = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
_started = False
_stop = threading.Event()


def take_lease(holder: str = HOLDER, now=None) -> bool:
    """Claim or renew the scheduler lease. True if this process should run the agents now.
    The conditional UPDATE is atomic in SQLite and Postgres, so two processes can't both win."""
    now = now or utcnow()
    expires = now + timedelta(seconds=LEASE_S)
    db = SessionLocal()
    try:
        r = db.execute(update(SchedulerLease)
                       .where(SchedulerLease.name == LEASE_NAME,
                              or_(SchedulerLease.holder == holder, SchedulerLease.expires_at < now))
                       .values(holder=holder, expires_at=expires))
        if r.rowcount:
            db.commit()
            return True
        if db.get(SchedulerLease, LEASE_NAME):
            db.rollback()
            return False  # someone else holds a live lease
        db.add(SchedulerLease(name=LEASE_NAME, holder=holder, expires_at=expires))
        try:
            db.commit()
            return True
        except IntegrityError:  # another process created it first
            db.rollback()
            return False
    finally:
        db.close()


def due_daily(s, now) -> bool:
    local = now + timedelta(minutes=settings.tz_offset_minutes)
    last = s.last_run_at + timedelta(minutes=settings.tz_offset_minutes) if s.last_run_at else None
    return local.hour >= 9 and (not last or last.date() < local.date())


def due_weekly(s, now) -> bool:
    local = now + timedelta(minutes=settings.tz_offset_minutes)
    return local.weekday() == 0 and due_daily(s, now) and (not s.last_run_at or now - s.last_run_at > timedelta(days=6))


def tick(now=None) -> dict:
    from . import autopilot, concierge, report
    now = now or utcnow()
    db = SessionLocal()
    out = {"follow_ups": 0, "autopilot": 0, "reports": 0, "whatsapp": 0}
    try:
        out["follow_ups"] = concierge.run_due(db, now)
        from ..routers.whatsapp import send_due
        try:
            out["whatsapp"] = send_due(db, now)
        except Exception:
            db.rollback()
            log.exception("Scheduled WhatsApp messages failed")
        for s in list(db.scalars(select(AgentSetting).where(AgentSetting.enabled.is_(True),
                                                             AgentSetting.kind.in_(("autopilot", "weekly_report"))))):
            user = db.get(User, s.user_id)
            if not user:
                continue
            try:
                if s.kind == "autopilot" and due_daily(s, now):
                    autopilot.run(db, user)
                    s.last_run_at = now
                    out["autopilot"] += 1
                elif s.kind == "weekly_report" and due_weekly(s, now):
                    report.run(db, user)
                    s.last_run_at = now
                    out["reports"] += 1
                db.commit()
            except Exception:
                db.rollback()
                log.exception("%s failed for user %s", s.kind, s.user_id)
    finally:
        db.close()
    return out


def _loop(stop: threading.Event) -> None:
    while not stop.wait(TICK):
        try:
            if take_lease():
                tick()
        except Exception:
            log.exception("Agent scheduler tick failed")


def start() -> None:
    global _started
    if _started or not settings.agents_scheduler:
        return
    _started = True
    _stop.clear()
    threading.Thread(target=_loop, args=(_stop,), name="aimva-agents", daemon=True).start()
    log.info("Agent scheduler started")


def stop() -> None:
    """Called on shutdown: finish the current tick, start no new one, and let another process take the lease."""
    global _started
    if not _started:
        return
    _stop.set()
    _started = False
    db = SessionLocal()
    try:
        db.execute(update(SchedulerLease).where(SchedulerLease.name == LEASE_NAME, SchedulerLease.holder == HOLDER)
                   .values(expires_at=utcnow()))
        db.commit()
    except Exception:
        log.warning("Couldn't release the scheduler lease", exc_info=True)
    finally:
        db.close()
