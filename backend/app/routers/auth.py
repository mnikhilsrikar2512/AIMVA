from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..mailer import send_code_email
from ..models import EmailCode, User, utcnow
from ..security import (
    clear_session, client_ip, code_matches, current_person, current_user, hash_code, hash_password, new_code,
    WORKSPACE_COOKIE, password_problem, rate_limit, session_token, set_session, verify_password, wants_token,
)
from ..workspaces import landing_workspace, role_in

router = APIRouter(prefix="/api/auth", tags=["auth"])
CODE_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_CODE_ATTEMPTS = 5
MAX_FAILED_LOGINS = 8


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str
    company: str = ""


class EmailIn(BaseModel):
    email: EmailStr


class VerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ResetIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    password: str


class ProfileIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    company: Optional[str] = Field(default=None, max_length=160)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "company": u.company, "industry": u.industry,
            "goal": u.goal, "created_at": u.created_at.isoformat(), "is_admin": u.email.lower() in settings.admin_emails,
            "can_simulate": not settings.is_production or u.email.lower() in settings.admin_emails}


def _issue_code(db: Session, user: User, purpose: str, bg: BackgroundTasks) -> dict:
    last = db.scalar(select(EmailCode).where(EmailCode.user_id == user.id, EmailCode.purpose == purpose)
                     .order_by(EmailCode.created_at.desc()))
    if last and utcnow() - last.created_at < RESEND_COOLDOWN:
        wait = int((RESEND_COOLDOWN - (utcnow() - last.created_at)).total_seconds()) + 1
        raise HTTPException(429, f"Please wait {wait}s before requesting another code.")
    db.execute(update(EmailCode).where(EmailCode.user_id == user.id, EmailCode.purpose == purpose,
                                       EmailCode.used.is_(False)).values(used=True))
    code = new_code()
    db.add(EmailCode(user_id=user.id, purpose=purpose, code_hash=hash_code(code), expires_at=utcnow() + CODE_TTL))
    db.commit()
    bg.add_task(send_code_email, user.email, user.name, code, purpose)
    out = {"ok": True, "email": user.email}
    if not settings.smtp_configured and not settings.is_production:
        out["dev_code"] = code  # dev mode only: no SMTP configured, so surface the code
    return out


def _consume_code(db: Session, user: User, purpose: str, code: str) -> None:
    rec = db.scalar(select(EmailCode).where(EmailCode.user_id == user.id, EmailCode.purpose == purpose,
                                            EmailCode.used.is_(False)).order_by(EmailCode.created_at.desc()))
    if not rec or rec.expires_at < utcnow():
        raise HTTPException(400, "Code expired. Request a new one.")
    if rec.attempts >= MAX_CODE_ATTEMPTS:
        raise HTTPException(400, "Too many wrong attempts. Request a new code.")
    if not code_matches(code, rec.code_hash):
        rec.attempts += 1
        db.commit()
        raise HTTPException(400, f"Incorrect code. {MAX_CODE_ATTEMPTS - rec.attempts} attempts left.")
    rec.used = True


def _session_reply(request: Request, user: User) -> dict:
    """The signed-in reply. The web app's session lives only in the httpOnly cookie; the mobile app (which can't use
    cookies) asks for the token with the X-AIMVA-Client: app header and sends it back as a Bearer token."""
    out = {"user": user_out(user)}
    if wants_token(request):
        out["token"] = session_token(user)
    return out


def _find(db: Session, email: str) -> Optional[User]:
    return db.scalar(select(User).where(User.email == email.lower().strip()))


@router.post("/signup")
def signup(body: SignupIn, request: Request, bg: BackgroundTasks, db: Session = Depends(get_db)):
    rate_limit(f"signup:{client_ip(request)}", 10, 3600)
    if problem := password_problem(body.password):
        raise HTTPException(400, problem)
    email = body.email.lower().strip()
    user = _find(db, email)
    if user and user.is_verified:
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    if user:  # unverified re-signup: refresh details and resend code
        user.name, user.company, user.password_hash = body.name.strip(), body.company.strip(), hash_password(body.password)
    else:
        user = User(name=body.name.strip(), email=email, company=body.company.strip(),
                    password_hash=hash_password(body.password))
        db.add(user)
    db.commit()
    return _issue_code(db, user, "verify", bg)


@router.post("/resend-code")
def resend_code(body: EmailIn, request: Request, bg: BackgroundTasks, db: Session = Depends(get_db)):
    rate_limit(f"resend:{client_ip(request)}", 10, 3600)
    user = _find(db, body.email)
    if not user or user.is_verified:
        return {"ok": True, "email": body.email}  # don't reveal whether the account exists
    return _issue_code(db, user, "verify", bg)


@router.post("/verify-email")
def verify_email(body: VerifyIn, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(f"verify:{client_ip(request)}", 30, 600)
    user = _find(db, body.email)
    if not user:
        raise HTTPException(400, "Code expired. Request a new one.")
    if user.is_verified:
        # Never sign in from this endpoint without a fresh code: it used to skip the check for verified accounts,
        # which let anyone who knew an email address take over that account.
        raise HTTPException(400, "This email is already verified. Sign in instead.")
    _consume_code(db, user, "verify", body.code)
    user.is_verified = True
    db.commit()
    set_session(response, user)
    return _session_reply(request, user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, bg: BackgroundTasks, db: Session = Depends(get_db)):
    rate_limit(f"login:{client_ip(request)}", 20, 300)
    user = _find(db, body.email)
    if user and user.locked_until and user.locked_until > utcnow():
        raise HTTPException(423, "Account temporarily locked after too many attempts. Try again in 15 minutes.")
    if not user or not verify_password(user.password_hash, body.password):
        if user:
            user.failed_logins += 1
            if user.failed_logins >= MAX_FAILED_LOGINS:
                user.locked_until, user.failed_logins = utcnow() + timedelta(minutes=15), 0
            db.commit()
        raise HTTPException(401, "Incorrect email or password.")
    user.failed_logins, user.locked_until = 0, None
    db.commit()
    if not user.is_verified:
        try:
            info = _issue_code(db, user, "verify", bg)
        except HTTPException:
            info = {}
        response.status_code = 403
        return {"needs_verification": True, "email": user.email, **{k: v for k, v in info.items() if k == "dev_code"}}
    set_session(response, user)
    out = _session_reply(request, user)
    if not request.cookies.get(WORKSPACE_COOKIE) and (ws := landing_workspace(db, user)):
        response.set_cookie(WORKSPACE_COOKIE, str(ws.id), httponly=True, secure=settings.cookie_secure, samesite="lax",
                            max_age=settings.session_days * 86400, path="/")
        out["workspace"] = {"id": ws.id, "name": ws.company or ws.name, "role": role_in(db, user, ws.id)}
    return out


@router.post("/logout")
def logout(response: Response):
    clear_session(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request, user: User = Depends(current_user)):
    """The signed-in person, plus the workspace they're working in when it's a client's."""
    person = request.state.person
    out = {"user": user_out(person)}
    if user.id != person.id:
        out["workspace"] = {"id": user.id, "name": user.company or user.name, "role": request.state.role}
    return out


@router.post("/forgot-password")
def forgot_password(body: EmailIn, request: Request, bg: BackgroundTasks, db: Session = Depends(get_db)):
    rate_limit(f"forgot:{client_ip(request)}", 5, 900)
    user = _find(db, body.email)
    if not user:
        return {"ok": True, "email": body.email}
    return _issue_code(db, user, "reset", bg)


@router.post("/reset-password")
def reset_password(body: ResetIn, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(f"reset:{client_ip(request)}", 20, 900)
    if problem := password_problem(body.password):
        raise HTTPException(400, problem)
    user = _find(db, body.email)
    if not user:
        raise HTTPException(400, "Code expired. Request a new one.")
    _consume_code(db, user, "reset", body.code)
    user.password_hash = hash_password(body.password)
    user.is_verified = True  # proving inbox ownership also verifies the email
    user.token_version += 1  # sign out other sessions
    user.failed_logins, user.locked_until = 0, None
    db.commit()
    set_session(response, user)
    return _session_reply(request, user)


@router.patch("/profile")
def update_profile(body: ProfileIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Your name always belongs to you. The company is the business you're working in: your own, or the client
    workspace you switched to (only its owner or an admin may rename that)."""
    person = db.get(User, request.state.person.id)
    if body.name is not None and body.name.strip():
        person.name = body.name.strip()
    if body.company is not None:
        company = body.company.strip()
        if user.id == person.id:
            person.company = company
        elif company != (user.company or user.name):
            if request.state.role not in ("owner", "admin"):
                raise HTTPException(403, "Only the workspace's owner or an admin can rename it.")
            if len(company) < 2:
                raise HTTPException(400, "Give the business a name.")
            ws = db.get(User, user.id)
            ws.company = ws.name = company
    db.commit()
    out = {"user": user_out(person)}
    if user.id != person.id:
        ws = db.get(User, user.id)
        out["workspace"] = {"id": ws.id, "name": ws.company or ws.name, "role": request.state.role}
    return out


@router.post("/change-password")
def change_password(body: ChangePasswordIn, request: Request, response: Response, user: User = Depends(current_person),
                    db: Session = Depends(get_db)):
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(400, "Current password is incorrect.")
    if problem := password_problem(body.new_password):
        raise HTTPException(400, problem)
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    db.merge(user)
    db.commit()
    set_session(response, user)
    return {"ok": True, **({"token": session_token(user)} if wants_token(request) else {})}  # old tokens stop working
