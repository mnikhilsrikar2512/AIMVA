"""Password hashing (argon2id), session JWTs in httpOnly cookies, one-time codes, rate limiting."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

COOKIE_NAME = "aimva_session"
_ph = PasswordHasher()  # argon2id with library-recommended parameters


# ---- passwords -------------------------------------------------------------
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_problem(password: str):
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password) > 128:
        return "Password is too long."
    if password.isalpha() or password.isdigit():
        return "Use a mix of letters and numbers or symbols."
    return None


# ---- one-time codes --------------------------------------------------------
def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hmac.new(settings.secret_key.encode(), code.encode(), hashlib.sha256).hexdigest()


def code_matches(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(code.strip()), code_hash)


# ---- encryption for stored third-party tokens -----------------------------
# Tokens are encrypted with the first key in TOKEN_ENCRYPTION_KEYS. Older keys in the list, and the key derived from
# SECRET_KEY (what AIMVA used before TOKEN_ENCRYPTION_KEYS existed), still decrypt, so a rotation never cuts anyone
# off. `scripts/db.py tokens rotate` re-encrypts everything with the first key; after that the old keys (and
# SECRET_KEY) can change without touching connected accounts.
def legacy_token_key(secret_key: str = "") -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256((secret_key or settings.secret_key).encode()).digest()))


def _build_token_keys(keys: list) -> tuple:
    try:
        configured = [Fernet(k.encode()) for k in keys]
    except (ValueError, TypeError):
        raise RuntimeError("TOKEN_ENCRYPTION_KEYS must be Fernet keys (44 characters each, comma-separated). "
                           "Generate one: python scripts/db.py tokens new-key") from None
    legacy = legacy_token_key()
    return MultiFernet(configured + [legacy]), (configured or [legacy])[0]


def reload_token_keys() -> None:
    """Re-read settings.token_encryption_keys (tests and the db script change them at runtime)."""
    global _tokens, _primary
    _tokens, _primary = _build_token_keys(settings.token_encryption_keys)


reload_token_keys()


def encrypt_json(data: dict) -> str:
    return _tokens.encrypt(json.dumps(data).encode()).decode() if data else ""


def decrypt_json(token: str) -> dict:
    return json.loads(_tokens.decrypt(token.encode())) if token else {}


def token_key_status(token: str) -> str:
    """Which key opens this secret: current (the first key), old (an older key or SECRET_KEY), or unreadable."""
    try:
        _primary.decrypt(token.encode())
        return "current"
    except InvalidToken:
        pass
    try:
        _tokens.decrypt(token.encode())
        return "old"
    except InvalidToken:
        return "unreadable"


def rotate_token(token: str) -> str:
    """The same secret, re-encrypted with the first key. Raises InvalidToken if no known key opens it."""
    return _tokens.rotate(token.encode()).decode()


# ---- sessions --------------------------------------------------------------
def session_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=settings.session_days)
    return jwt.encode({"sub": str(user.id), "v": user.token_version, "exp": exp}, settings.secret_key, "HS256")


APP_CLIENT_HEADER = "x-aimva-client"  # the mobile app sends "app" and gets its session token in the response body


def wants_token(request: Request) -> bool:
    return request.headers.get(APP_CLIENT_HEADER, "").lower() == "app"


def set_session(response: Response, user: User) -> None:
    token = session_token(user)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, secure=settings.cookie_secure, samesite="lax",
        max_age=settings.session_days * 86400, path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie("aimva_ws", path="/")


def current_person(request: Request, db: Session = Depends(get_db)) -> User:
    """The person who is signed in, whatever workspace they're working in (for sign-in, password, workspace lists)."""
    # The web app uses the httpOnly cookie; the mobile app sends the same signed token as "Authorization: Bearer".
    token = request.cookies.get(COOKIE_NAME)
    auth = request.headers.get("authorization", "")
    if not token and auth[:7].lower() == "bearer ":
        token = auth[7:].strip()
    if not token:
        raise HTTPException(401, "Not signed in.")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired. Please sign in again.")
    user = db.get(User, int(payload["sub"]))
    if not user or user.token_version != payload.get("v") or not user.is_verified or user.kind != "person":
        raise HTTPException(401, "Session expired. Please sign in again.")
    return user


WORKSPACE_COOKIE = "aimva_ws"
# What a client (role "client") may change: deciding approvals, and their own sign-in. Everything else is view-only.
CLIENT_WRITES = ("/api/approvals/", "/api/auth/", "/api/workspaces/", "/api/feedback")
CLIENT_HIDDEN = ("/api/integrations", "/api/providers", "/api/billing", "/api/admin")


def current_user(request: Request, db: Session = Depends(get_db), person: User = Depends(current_person)) -> User:
    """The account whose data a request works on: the person's own, or the client workspace they switched to
    (cookie aimva_ws, or the X-AIMVA-Workspace header from the app). Every module scopes its data to this."""
    from .models import Membership
    raw = request.headers.get("x-aimva-workspace") or request.cookies.get(WORKSPACE_COOKIE) or ""
    request.state.person, request.state.role = person, "owner"
    if not raw.isdigit() or int(raw) == person.id:
        return person
    m = db.scalar(select(Membership).where(Membership.workspace_id == int(raw), Membership.member_id == person.id))
    ws = db.get(User, int(raw)) if m else None
    if not ws:
        raise HTTPException(403, "You don't have access to that workspace any more. Switch to another one.")
    request.state.role = m.role
    if m.role == "client":
        path, method = request.url.path, request.method
        if path.startswith(CLIENT_HIDDEN) or (method not in ("GET", "HEAD") and not path.startswith(CLIENT_WRITES)):
            raise HTTPException(403, "Your access is view-only. Ask your agency to make this change.")
    return ws


# ---- rate limiter (database-backed, so limits hold across server processes) ----------------
_last_prune = 0.0
PRUNE_EVERY_S = 300
KEEP_HITS_S = 86400  # longer than any window in use


def rate_limit(key: str, limit: int, window_s: int) -> None:
    """Allow at most `limit` calls per `window_s` seconds for `key`. Uses its own session so a rollback in the
    caller can't undo the count. Under heavy concurrency a key can overshoot by a request or two, which is fine here."""
    global _last_prune
    from .db import SessionLocal
    from .models import RateHit, utcnow

    now = utcnow()
    db = SessionLocal()
    try:
        if time.monotonic() - _last_prune > PRUNE_EVERY_S:
            _last_prune = time.monotonic()
            db.execute(delete(RateHit).where(RateHit.at < now - timedelta(seconds=KEEP_HITS_S)))
        used = db.scalar(select(func.count()).select_from(RateHit)
                         .where(RateHit.key == key, RateHit.at > now - timedelta(seconds=window_s)))
        if used >= limit:
            db.commit()
            raise HTTPException(429, "Too many attempts. Please wait a minute and try again.")
        db.add(RateHit(key=key[:200], at=now))
        db.commit()
    finally:
        db.close()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
