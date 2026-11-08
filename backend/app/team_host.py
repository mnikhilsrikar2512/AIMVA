"""Keeps the AIMVA team app apart from the customer app.

With TEAM_URL set (e.g. https://team.aimva.in):
- the console and admin APIs (/api/console, /api/admin) answer only on the team address; on the customer
  address they are a plain 404, as if they didn't exist;
- the team address serves the team app (frontend/dist-team), the customer address the customer app.
Sign-in cookies are per address, so a teammate signs in to the team app separately.
The role checks in app/staff.py still run on every request: the address is an extra wall, not the only one.
"""
from .config import BASE_DIR, settings
from .domains import team_host

TEAM_DIST = BASE_DIR.parent / "frontend" / "dist-team"
TEAM_ONLY = ("/api/console", "/api/admin")


def _host(raw: str) -> str:
    raw = (raw or "").lower()
    return raw.rsplit(":", 1)[0] if raw.count(":") == 1 else raw


def is_team_host(raw: str) -> bool:
    th = team_host()
    return bool(th) and _host(raw) == th


class TeamHostMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and team_host():
            path = scope.get("path", "")
            if path.startswith(TEAM_ONLY):
                raw = dict(scope.get("headers") or []).get(b"host", b"").decode("latin-1")
                if not is_team_host(raw):
                    body = b'{"detail":"Not found."}'
                    await send({"type": "http.response.start", "status": 404,
                                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                    return await send({"type": "http.response.body", "body": body})
        return await self.app(scope, receive, send)
