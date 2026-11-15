import logging

import httpx

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles

from . import discreet
from .config import BASE_DIR, settings
from .db import check_database, migrate
from .security import current_user
from .domains import CustomDomainMiddleware, router as domains_router
from .team_host import TEAM_DIST, TeamHostMiddleware, is_team_host
from .observability import RequestContextMiddleware, request_id_var, setup_logging, setup_sentry
from .routers import agents, analytics, auth, brand, campaigns, command, templates, providers, references, content, events, feedback, integrations, leads, onboarding, sites, voice, whatsapp, story, today

setup_logging()
log = logging.getLogger("aimva")
if settings.is_production and settings.problems():
    raise SystemExit("AIMVA won't start in production with these settings:\n  - " + "\n  - ".join(settings.problems()))
for problem in settings.problems() if settings.environment != "test" else ():
    log.debug("Not production-safe (fine for development): %s", problem)
setup_sentry()
migrate()

# The interactive API docs are handy in development; on a public server they only advertise the attack surface.
_docs = {} if not settings.is_production else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title="AIMVA API", version="1.0.0", **_docs)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_url] + ([settings.team_url] if settings.team_url else []), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"])
app.add_middleware(CustomDomainMiddleware)
app.add_middleware(TeamHostMiddleware)  # outermost of the two: team-only APIs never reach the customer address
app.add_middleware(RequestContextMiddleware)  # added last = runs first, so every response gets its id and headers

for r in (auth, onboarding, events, brand, providers, references, integrations, content, sites, feedback, templates, leads, campaigns, command, whatsapp, voice, analytics, agents, story, today):
    app.include_router(r.router)
app.include_router(domains_router)
from .alerts import router as alerts_router  # noqa: E402
app.include_router(alerts_router)
from .billing import router as billing_router  # noqa: E402
app.include_router(billing_router)
from .workspaces import router as workspaces_router  # noqa: E402
app.include_router(workspaces_router)
from .account import router as account_router  # noqa: E402
app.include_router(account_router)
from .console import router as console_router  # noqa: E402
app.include_router(console_router)
from .projects import router as projects_router  # noqa: E402
app.include_router(projects_router)
from .made import router as made_router  # noqa: E402
app.include_router(made_router)


@app.on_event("startup")
def start_background():
    from . import live
    from .agents.scheduler import start
    start()
    live.start_listener()


@app.on_event("shutdown")
def stop_background():
    from .agents.scheduler import stop
    stop()


@app.get("/api/health")
def health():
    """Liveness: the process answers. Cheap, no database, safe for an uptime checker to hit every minute."""
    return {"ok": True}  # public: says nothing about which services or keys are configured


@app.get("/api/capabilities")
def capabilities(user=Depends(current_user)):
    """What's switched on, for the app to enable features: booleans and language codes only, never a supplier or key."""
    from .ai_registry import capabilities as caps
    return caps()


@app.get("/api/ready")
def ready():
    """Readiness: the process can serve real requests (the database answers). Load balancers route traffic on this."""
    try:
        check_database()
    except Exception:
        log.exception("Readiness check: database unreachable")
        return JSONResponse({"ok": False, "database": False}, status_code=503)
    return {"ok": True, "database": True}


# Owner-only screens keep the real wording (the owner configures the suppliers); everyone else gets neutral text.
OWNER_PATHS = ("/api/providers", "/api/admin", "/api/integrations/fal", "/api/integrations/gemini")


@app.exception_handler(StarletteHTTPException)
async def discreet_http_errors(request: Request, exc: StarletteHTTPException):
    """No error a customer sees names a supplier, a model or a server setting; the real text goes to the log."""
    path = request.url.path
    try:  # the request's session may be closed by now; a detached user can't always be read
        person = getattr(request.state, "person", None)
        owner = bool(person and (person.email or "").lower() in settings.admin_emails)
    except Exception:
        owner = False
    if isinstance(exc.detail, str) and not owner and not path.startswith(OWNER_PATHS) and discreet.leaks(exc.detail):
        log.warning("Supplier detail hidden from the client on %s (%s): %s", path, exc.status_code, exc.detail)
        exc = StarletteHTTPException(exc.status_code, discreet.neutral_error(path, exc.detail), headers=exc.headers)
    return await http_exception_handler(request, exc)


@app.exception_handler(httpx.HTTPError)
async def upstream_unreachable(request: Request, exc: httpx.HTTPError):
    log.warning("Upstream request failed on %s: %r", request.url.path, exc)
    return JSONResponse({"detail": "Couldn't reach the connected service. Please try again.",
                         "request_id": request_id_var.get()}, status_code=502)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    rid = request_id_var.get()
    # The request id lets the owner match what a user saw with the log line and the Sentry event.
    return JSONResponse({"detail": "Something went wrong on our side. Please try again.", "request_id": rid},
                        status_code=500, headers={"X-Request-ID": rid})


# Serve the built React app (frontend/dist) in production; in dev Vite serves it on :5173.
DIST = BASE_DIR.parent / "frontend" / "dist"
if TEAM_DIST.exists():  # the team app's own files (built with assetsDir "team-assets", see frontend/vite.team.config.js)
    app.mount("/team-assets", StaticFiles(directory=TEAM_DIST / "team-assets"), name="team-assets")
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str, request: Request):
        if path.startswith(("api/", "s/")):
            return JSONResponse({"detail": "Not found."}, status_code=404)
        # The team address serves the team app (frontend/dist-team), everything else the customer app.
        root = TEAM_DIST if is_team_host(request.headers.get("host", "")) and TEAM_DIST.exists() else DIST
        f = (root / path).resolve()
        ok = path and f.is_file() and root.resolve() in f.parents
        if ok and root is DIST and path == "sw.js":  # the phone must pick up a new service worker straight away
            return FileResponse(f, media_type="text/javascript", headers={"Cache-Control": "no-cache"})
        if ok and path.endswith(".webmanifest"):
            return FileResponse(f, media_type="application/manifest+json")
        return FileResponse(f if ok else root / "index.html")
