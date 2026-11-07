"""Logging, request ids, error tracking and security headers: what you need to find out what went wrong in production."""
import contextvars
import json
import logging
import sys
import time
import uuid

from .config import settings

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
access_log = logging.getLogger("aimva.access")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname, "logger": record.name,
               "message": record.getMessage(), "request_id": getattr(record, "request_id", "-")}
        for key in ("method", "path", "status", "duration_ms"):
            if hasattr(record, key):
                out[key] = getattr(record, key)
        if record.exc_info:
            out["exception"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] [%(request_id)s] %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)
    # uvicorn's own access log would duplicate ours (which carries the request id and duration)
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)


def setup_sentry() -> bool:
    if not settings.sentry_dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, release=settings.release or None,
                    send_default_pii=False,  # no emails, cookies or IPs leave the server
                    traces_sample_rate=float(__import__("os").getenv("SENTRY_TRACES_SAMPLE_RATE", "0") or 0))
    return True


SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), geolocation=(), microphone=(self)"),
]


class RequestContextMiddleware:
    """Gives every request an id (kept from X-Request-ID if a proxy set one), returns it as a header, adds security
    headers and writes one access-log line. Plain ASGI, so streaming responses (live updates) pass straight through."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if 0 < len(incoming) <= 64 and incoming.replace("-", "").isalnum() else uuid.uuid4().hex[:16]
        request_id_var.set(rid)
        path = scope.get("path", "")
        start = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                extra = [(b"x-request-id", rid.encode())] + SECURITY_HEADERS
                if not path.startswith("/s/"):  # published sites may be framed elsewhere; the app may not
                    extra.append((b"x-frame-options", b"SAMEORIGIN"))
                if settings.is_production and settings.public_url.startswith("https://"):
                    extra.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                existing = list(message.get("headers", []))
                have = {k.lower() for k, _ in existing}
                message["headers"] = existing + [(k, v) for k, v in extra if k not in have]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if path not in ("/api/health", "/api/ready"):
                ms = round((time.perf_counter() - start) * 1000, 1)
                access_log.info("%s %s %s %sms", scope.get("method"), path, status["code"], ms,
                                extra={"method": scope.get("method"), "path": path, "status": status["code"], "duration_ms": ms})
