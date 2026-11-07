import logging

import httpx

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, settings
from .db import check_database, migrate
from .domains import CustomDomainMiddleware, router as domains_router
from .observability import RequestContextMiddleware, request_id_var, setup_logging, setup_sentry
from .routers import agents, analytics, auth, brand, campaigns, command, templates, providers, references, content, events, feedback, integrations, leads, onboarding, sites, voice, whatsapp

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
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_url], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"])
app.add_middleware(CustomDomainMiddleware)
app.add_middleware(RequestContextMiddleware)  # added last = runs first, so every response gets its id and headers

for r in (auth, onboarding, events, brand, providers, references, integrations, content, sites, feedback, templates, leads, campaigns, command, whatsapp, voice, analytics, agents):
    app.include_router(r.router)
app.include_router(domains_router)
from .billing import router as billing_router  # noqa: E402
app.include_router(billing_router)
from .workspaces import router as workspaces_router  # noqa: E402
app.include_router(workspaces_router)


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
    return {"ok": True, "smtp": settings.smtp_configured, "gemini": bool(settings.gemini_api_key)}


@app.get("/api/ready")
def ready():
    """Readiness: the process can serve real requests (the database answers). Load balancers route traffic on this."""
    try:
        check_database()
    except Exception:
        log.exception("Readiness check: database unreachable")
        return JSONResponse({"ok": False, "database": False}, status_code=503)
    return {"ok": True, "database": True}


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
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str):
        if path.startswith(("api/", "s/")):
            return JSONResponse({"detail": "Not found."}, status_code=404)
        f = (DIST / path).resolve()
        ok = path and f.is_file() and DIST.resolve() in f.parents
        return FileResponse(f if ok else DIST / "index.html")
