"""Custom domains for published sites.

1. The owner adds a domain to a site and points DNS at this server (a CNAME to the app's host, or an A record for a
   bare domain like brand.com).
2. Verify checks that the domain resolves to the same addresses as the app. Only then is it served.
3. Requests whose Host is a verified domain are served that site: "/" is the home page, "/<page>" an extra page.
   Nothing else of AIMVA (the app, its API, sign-in) answers on a customer's domain, except the site's lead form.
4. Caddy asks /api/public/domains/allowed before issuing an HTTPS certificate, so it only gets certificates for
   verified domains (otherwise anyone could point a domain at the server and make it request certificates).
"""
import ipaddress
import re
import socket
import time
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal, get_db
from .models import Site, User, utcnow
from .security import current_user

router = APIRouter(tags=["domains"])
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
CACHE_S = 30
_cache: dict = {}  # host -> (expires, slug or None)


def app_host() -> str:
    return (urlsplit(settings.public_url).hostname or "localhost").lower()


NOT_SET_UP = ("Custom domains aren't switched on yet: this AIMVA server doesn't have its public web address set. "
              "Ask your AIMVA admin to finish server setup, then come back and check again.")


def target_ready() -> bool:
    """True when the app has a real public host for customers to point DNS at (not localhost or a private address)."""
    host = app_host()
    if host in ("localhost", "0.0.0.0") or host.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified)


def normalize(domain: str) -> str:
    d = (domain or "").strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0].rstrip(".")
    return d


def is_valid(domain: str) -> bool:
    return bool(DOMAIN_RE.match(domain)) and domain != app_host() and not domain.endswith("." + app_host())


def _addresses(host: str) -> set:
    try:
        return {info[4][0] for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)}
    except (socket.gaierror, UnicodeError, OSError):
        return set()


def records_for(domain: str) -> list:
    """The DNS record the owner should add at their registrar."""
    if not target_ready():
        return []  # there is no real address to point at yet; domain_out explains why
    if domain.count(".") == 1:  # a bare domain (brand.com) can't have a CNAME
        ips = sorted(_addresses(app_host()))
        return [{"type": "A", "name": "@", "value": ip} for ip in ips if ":" not in ip] or \
               [{"type": "A", "name": "@", "value": ip} for ip in ips[:1]]
    return [{"type": "CNAME", "name": domain.split(".")[0], "value": app_host()}]


def points_here(domain: str) -> bool:
    if not target_ready():
        return False
    mine = _addresses(app_host())
    return bool(mine) and bool(_addresses(domain) & mine)


def setup_issue(domain: str = "") -> Optional[str]:
    """Why no DNS record can be shown yet, in words for the business owner, or None when records are ready."""
    if not target_ready():
        return NOT_SET_UP
    if domain and not records_for(domain):
        return ("AIMVA couldn't look up its own server address just now, so it can't show the record for a bare domain. "
                "Use a subdomain like offers.yourbrand.com, or try again in a few minutes.")
    return None


def domain_out(s: Site) -> dict:
    d = s.custom_domain or ""
    records = records_for(d) if d else []
    return {"domain": d, "verified": bool(d and s.domain_verified_at), "records": records,
            "url": f"https://{d}" if d and s.domain_verified_at else None,
            "verified_at": s.domain_verified_at.isoformat() if s.domain_verified_at else None,
            "target_host": app_host() if target_ready() else None, "target_ready": target_ready(),
            "published": bool(s.published), "setup_issue": setup_issue(d) if d else (None if target_ready() else NOT_SET_UP)}


def set_domain(db: Session, s: Site, domain: str) -> None:
    """Change a site's domain (empty removes it). A new domain must be verified again."""
    domain = normalize(domain)
    if domain == (s.custom_domain or ""):
        return
    if domain and not is_valid(domain):
        raise HTTPException(400, "Enter a domain like offers.yourbrand.com (no https:// or paths).")
    if domain and db.scalar(select(Site.id).where(func.lower(Site.custom_domain) == domain, Site.id != s.id)):
        raise HTTPException(409, "That domain is already connected to another site.")
    s.custom_domain, s.domain_verified_at = domain, None
    _cache.clear()


def _own(db: Session, user: User, site_id: int) -> Site:
    s = db.get(Site, site_id)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Site not found.")
    return s


@router.get("/api/sites/{site_id}/domain")
def get_domain(site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return domain_out(_own(db, user, site_id))


@router.post("/api/sites/{site_id}/domain/verify")
def verify_domain(site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _own(db, user, site_id)
    if not s.custom_domain:
        raise HTTPException(400, "Add a domain to this site first.")
    if not target_ready():
        out = domain_out(s)
        out["detail"] = NOT_SET_UP
        return out
    if not points_here(s.custom_domain):
        out = domain_out(s)
        out["detail"] = (f"{s.custom_domain} doesn't point to AIMVA yet. Add the record below at your domain registrar; "
                         "DNS changes can take up to an hour to show up. If you use Cloudflare, set this record to "
                         "DNS only (grey cloud), or the check can't see it.")
        return out
    s.domain_verified_at = utcnow()
    db.commit()
    _cache.clear()
    return domain_out(s)


@router.get("/api/public/domains/allowed", include_in_schema=False)
def allowed(domain: str = "", db: Session = Depends(get_db)):
    """Caddy's on-demand TLS check: 200 = issue a certificate for this domain, anything else = don't."""
    d = normalize(domain)
    if d == app_host() or _site_slug(d, db):
        return Response(status_code=200)
    return Response(status_code=404)


def _site_slug(host: str, db: Optional[Session] = None) -> Optional[str]:
    now = time.monotonic()
    hit = _cache.get(host)
    if hit and hit[0] > now:
        return hit[1]
    own = db is None
    db = db or SessionLocal()
    try:
        slug = db.scalar(select(Site.slug).where(func.lower(Site.custom_domain) == host, Site.published.is_(True),
                                                 Site.domain_verified_at.is_not(None)))
    finally:
        if own:
            db.close()
    _cache[host] = (now + CACHE_S, slug)
    return slug


_LOCAL = {"localhost", "127.0.0.1", "testserver", "app", "::1"}


class CustomDomainMiddleware:
    """Serves a verified customer domain's site; leaves every other request alone."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        raw = dict(scope.get("headers") or []).get(b"host", b"").decode("latin-1").lower()
        host = raw.rsplit(":", 1)[0] if raw.count(":") == 1 else raw
        if not host or host == app_host() or host in _LOCAL or not DOMAIN_RE.match(host):
            return await self.app(scope, receive, send)
        from starlette.concurrency import run_in_threadpool
        slug = await run_in_threadpool(_site_slug, host)
        path = scope.get("path", "/")
        if slug is None:
            return await _not_found(send)
        if path.startswith((f"/s/{slug}/", f"/api/public/sites/{slug}/")) or path == f"/s/{slug}":
            return await self.app(scope, receive, send)  # the site's own links, brochure and lead form
        parts = [p for p in path.split("/") if p]
        if len(parts) > 1:
            return await _not_found(send)
        new_path = f"/s/{slug}" + (f"/{parts[0]}" if parts else "")
        scope = {**scope, "path": new_path, "raw_path": new_path.encode()}
        return await self.app(scope, receive, send)


async def _not_found(send):
    body = b"<h1 style='font-family:sans-serif;padding:40px'>Page not found</h1>"
    await send({"type": "http.response.start", "status": 404,
                "headers": [(b"content-type", b"text/html; charset=utf-8"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
