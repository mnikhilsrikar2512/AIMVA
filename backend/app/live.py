"""Live updates (new leads, agent progress), delivered to browsers over Server-Sent Events.

Each server process keeps the open tabs it serves in memory. publish() hands a message to this process's tabs at once
and, on Postgres, also sends it through NOTIFY so every other worker or container delivers it to its own tabs. A
listener thread per process (start_listener, run on startup) receives those. On SQLite there is only one process, so
the in-memory part is the whole story.

publish() is safe to call from sync route handlers (thread pool) and from the event loop.
"""
import asyncio
import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from datetime import timedelta

log = logging.getLogger("aimva.live")
CHANNEL = "aimva_live"
NOTIFY_LIMIT = 7000  # Postgres caps a NOTIFY payload just under 8000 bytes; bigger messages go through live_events
KEEP_LARGE = timedelta(minutes=5)
ORIGIN = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"  # so a process ignores its own messages coming back

_subs = defaultdict(set)  # user_id -> {(loop, queue)}
_lock = threading.Lock()
_listener_started = False


def subscribe(user_id: int):
    sub = (asyncio.get_running_loop(), asyncio.Queue(maxsize=100))
    with _lock:
        _subs[user_id].add(sub)
    return sub


def unsubscribe(user_id: int, sub) -> None:
    with _lock:
        _subs[user_id].discard(sub)
        if not _subs[user_id]:
            _subs.pop(user_id, None)


def subscriber_count(user_id: int) -> int:
    with _lock:
        return len(_subs.get(user_id, ()))


def _put(queue: asyncio.Queue, msg: dict) -> None:
    try:
        queue.put_nowait(msg)
    except asyncio.QueueFull:
        pass  # a stalled tab shouldn't block everyone else


def deliver_local(user_id: int, event: str, data: dict) -> None:
    """Hand a message to the tabs this process serves."""
    with _lock:
        subs = list(_subs.get(user_id, ()))
    msg = {"event": event, "data": data}
    for loop, queue in subs:
        try:
            loop.call_soon_threadsafe(_put, queue, msg)
        except RuntimeError:
            pass  # loop already closed (tab gone)


def _shared() -> bool:
    from .db import IS_SQLITE
    return not IS_SQLITE


def _notify(user_id: int, event: str, data: dict) -> None:
    from sqlalchemy import delete, insert, select, text

    from .db import engine
    from .models import LiveEvent, utcnow

    payload = json.dumps({"o": ORIGIN, "u": user_id, "e": event, "d": data}, default=str)
    with engine.begin() as conn:
        if len(payload.encode()) > NOTIFY_LIMIT:
            now = utcnow()
            conn.execute(delete(LiveEvent).where(LiveEvent.created_at < now - KEEP_LARGE))
            ref = conn.execute(insert(LiveEvent).values(payload=payload, created_at=now).returning(LiveEvent.id)).scalar_one()
            payload = json.dumps({"o": ORIGIN, "ref": ref})
        conn.execute(select(text("pg_notify(:c, :p)")).params(c=CHANNEL, p=payload))


def publish(user_id: int, event: str, data: dict) -> None:
    deliver_local(user_id, event, data)
    if _shared():
        try:
            _notify(user_id, event, data)
        except Exception:
            log.exception("Couldn't share a live update with the other server processes")


def handle_notification(payload: str) -> None:
    """Deliver a message another process published (called by the listener thread)."""
    msg = json.loads(payload)
    if msg.get("o") == ORIGIN:
        return
    if "ref" in msg:
        from .db import SessionLocal
        from .models import LiveEvent
        with SessionLocal() as db:
            row = db.get(LiveEvent, msg["ref"])
            if not row:
                return
            msg = json.loads(row.payload)
    deliver_local(int(msg["u"]), msg["e"], msg["d"])


def _listen(stop: threading.Event) -> None:
    import psycopg

    from .db import engine

    conninfo = engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    backoff = 1
    while not stop.is_set():
        try:
            with psycopg.connect(conninfo, autocommit=True) as conn:
                conn.execute(f"LISTEN {CHANNEL}")
                backoff = 1
                while not stop.is_set():
                    for n in conn.notifies(timeout=5):
                        try:
                            handle_notification(n.payload)
                        except Exception:
                            log.exception("Bad live update")
        except Exception:
            if stop.is_set():
                break
            log.warning("Live update listener lost its database connection; retrying in %ss", backoff, exc_info=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)


def start_listener(stop: threading.Event | None = None) -> threading.Event | None:
    """Start receiving other processes' live updates (Postgres only). Returns the event that stops it."""
    global _listener_started
    if not _shared() or _listener_started:
        return None
    _listener_started = True
    stop = stop or threading.Event()
    threading.Thread(target=_listen, args=(stop,), name="aimva-live", daemon=True).start()
    log.info("Live update listener started")
    return stop
