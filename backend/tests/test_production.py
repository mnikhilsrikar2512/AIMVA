"""Production layer: config checks, request ids, security headers, readiness, long text on Postgres, live updates
across processes."""
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import select

from app import live
from app.config import _database_url
from app.db import IS_SQLITE
from app.models import SiteVersion, User

BACKEND = Path(__file__).resolve().parent.parent
pg_only = pytest.mark.skipif(IS_SQLITE, reason="needs Postgres (TEST_DATABASE_URL)")


def test_postgres_urls_from_hosts_use_psycopg(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@db:5432/aimva")
    assert _database_url() == "postgresql+psycopg://u:p@db:5432/aimva"
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/aimva")
    assert _database_url() == "postgresql+psycopg://u:p@db/aimva"


def test_production_refuses_unsafe_settings():
    env = {"PATH": "/usr/bin:/bin", "ENVIRONMENT": "production", "SECRET_KEY": "", "DATABASE_URL": "sqlite:////tmp/x.db",
           "PUBLIC_URL": "http://example.com", "AGENTS_SCHEDULER": "false"}
    out = subprocess.run([sys.executable, "-c", "import app.main"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert out.returncode != 0
    for word in ("SECRET_KEY", "SQLite", "https://", "COOKIE_SECURE", "META_APP_SECRET", "WHATSAPP_VERIFY_TOKEN", "SMTP"):
        assert word in out.stderr


def test_safe_production_settings_start():
    env = {"PATH": "/usr/bin:/bin", "ENVIRONMENT": "production", "SECRET_KEY": "s" * 40,
           "DATABASE_URL": "postgresql://u:p@db.invalid/aimva", "PUBLIC_URL": "https://app.example.com",
           "COOKIE_SECURE": "true", "ALLOW_PRIVATE_PROVIDERS": "false", "META_APP_SECRET": "m",
           "WHATSAPP_VERIFY_TOKEN": "random-token", "SMTP_USER": "a@b.com", "SMTP_PASSWORD": "x"}
    out = subprocess.run([sys.executable, "-c", "from app.config import settings; print(settings.problems())"],
                         cwd=BACKEND, env=env, capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.strip() == "[]", out.stderr


def test_no_dev_code_in_production(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "environment", "production")
    r = client.post("/api/auth/signup", json={"name": "A", "email": "a@example.com", "password": "Sup3r-secret!"})
    assert r.status_code == 200 and "dev_code" not in r.json()


def test_every_response_has_request_id_and_security_headers(client):
    r = client.get("/api/health")
    assert len(r.headers["x-request-id"]) == 16
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert "strict-transport-security" not in r.headers  # only in production over https
    assert client.get("/api/health", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"] == "abc-123"
    assert client.get("/api/health", headers={"X-Request-ID": "bad id\n"}).headers["x-request-id"] != "bad id\n"


def test_server_errors_carry_the_request_id(client, monkeypatch):
    from app.routers import onboarding
    from fastapi.testclient import TestClient
    from app.main import app

    @app.get("/api/_boom_test")
    def boom():
        raise RuntimeError("boom")
    app.router.routes.insert(0, app.router.routes.pop())  # ahead of the SPA catch-all when frontend/dist exists
    try:
        r = TestClient(app, raise_server_exceptions=False).get("/api/_boom_test", headers={"X-Request-ID": "trace-1"})
        assert r.status_code == 500 and r.json() == {"detail": "Something went wrong on our side. Please try again.",
                                                     "request_id": "trace-1"}
    finally:
        app.router.routes = [rt for rt in app.router.routes if getattr(rt, "path", "") != "/api/_boom_test"]


def test_ready_checks_the_database(client, monkeypatch):
    assert client.get("/api/ready").json() == {"ok": True, "database": True}
    import app.main as main

    def down():
        raise OSError("db down")
    monkeypatch.setattr(main, "check_database", down)
    r = client.get("/api/ready")
    assert r.status_code == 503 and r.json()["database"] is False


def test_too_long_text_is_shortened_not_a_crash(db, auth_client):
    """SQLite ignores VARCHAR lengths and Postgres rejects the write: the guard shortens it on both."""
    from app.models import Site
    s = Site(user_id=db.scalar(select(User)).id, name="Acme " * 100, slug="acme-long")
    db.add(s)
    db.flush()
    v = SiteVersion(site_id=s.id, number=1, html="<p>x</p>", brief={}, note="n" * 500, generator="test")
    db.add(v)
    db.commit()
    assert len(s.name) == 160 and len(v.note) == 120 and v.note.endswith("\u2026")
    s.slug = "x" * 200  # unique keys are never shortened: those must fail loudly (on Postgres; SQLite stores it)
    if IS_SQLITE:
        db.commit()
        assert len(s.slug) == 200
    else:
        with pytest.raises(Exception):
            db.commit()
        db.rollback()


def test_json_log_lines(capsys):
    import logging
    from app.observability import JsonFormatter
    rec = logging.LogRecord("aimva", logging.INFO, __file__, 1, "hello %s", ("x",), None)
    rec.request_id = "r1"
    line = json.loads(JsonFormatter().format(rec))
    assert line["message"] == "hello x" and line["request_id"] == "r1" and line["level"] == "INFO"


def _collect(user_id, action, timeout=5):
    async def main():
        sub = live.subscribe(user_id)
        try:
            await asyncio.get_running_loop().run_in_executor(None, action)
            return await asyncio.wait_for(sub[1].get(), timeout)
        finally:
            live.unsubscribe(user_id, sub)
    return asyncio.run(main())


def _publish_from_another_process(user_id, data):
    """A second server process (another worker or container) publishes; this process must deliver it."""
    script = f"from app import live; live.publish({user_id}, 'lead', {data!r})"
    env = {**os.environ, "AGENTS_SCHEDULER": "false"}
    out = subprocess.run([sys.executable, "-c", script], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


@pg_only
@pytest.mark.parametrize("size", [10, 20000])  # a small message rides in NOTIFY; a big one goes through live_events
def test_live_updates_reach_tabs_on_other_processes(size, monkeypatch):
    monkeypatch.setattr(live, "_listener_started", False)
    stop = live.start_listener()
    try:
        time.sleep(0.5)  # LISTEN is registered
        data = {"x": "y" * size}
        msg = _collect(777, lambda: _publish_from_another_process(777, data))
        assert msg == {"event": "lead", "data": data}
    finally:
        stop.set()


@pg_only
def test_own_messages_are_not_delivered_twice(monkeypatch):
    monkeypatch.setattr(live, "_listener_started", False)
    stop = live.start_listener()
    try:
        time.sleep(0.5)

        async def main():
            sub = live.subscribe(778)
            try:
                await asyncio.get_running_loop().run_in_executor(None, lambda: live.publish(778, "lead", {"n": 1}))
                first = await asyncio.wait_for(sub[1].get(), 3)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(sub[1].get(), 1.5)
                return first
            finally:
                live.unsubscribe(778, sub)
        assert asyncio.run(main()) == {"event": "lead", "data": {"n": 1}}
    finally:
        stop.set()
