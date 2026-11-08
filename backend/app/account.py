"""Your data: download everything AIMVA holds about your account, or delete the account for good (DPDP Act 2023).

Export: a ZIP with your profile, every record of your own account and of each client workspace you own, the
leads as a spreadsheet, and the files you uploaded or generated. Secrets (password hash, stored tokens and keys,
one-time codes) are never included.

Delete: needs your password and your email typed again. It revokes connected Meta / Google / LinkedIn sign-ins
with those services (best effort), cancels a paid plan with Razorpay (best effort), deletes uploaded files, then
deletes the account. Client workspaces you are the only owner of go with it; workspaces with another owner stay
and only your access is removed. The database cascades (ON DELETE CASCADE) remove every row that belongs to a
deleted account.
"""
import csv
import io
import json
import logging
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from typing import Iterable

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .brand import UPLOADS
from .db import Base, get_db
from .models import Campaign, Integration, Lead, Membership, Site, Subscription, Template, User, utcnow
from .security import clear_session, client_ip, current_person, decrypt_json, rate_limit, verify_password

log = logging.getLogger("aimva.account")
router = APIRouter(prefix="/api/account", tags=["account"])

OWNER_COLUMNS = ("user_id", "workspace_id", "owner_id")  # the column that says "this row belongs to that account"
SKIP_TABLES = {"email_codes", "rate_hits", "scheduler_leases", "live_events", "alembic_version"}
SECRET_COLUMNS = {"password_hash", "secret", "code_hash"}
USER_FIELDS = ("id", "name", "email", "company", "industry", "goal", "kind", "is_verified", "require_approval",
               "onboarding_answers", "created_at")


# ---- which accounts go with a person ---------------------------------------------------------------------
def owned_workspaces(db: Session, person: User) -> list:
    """Client workspaces where this person is an owner, with whether anyone else owns them too."""
    out = []
    for ws in db.scalars(select(User).join(Membership, Membership.workspace_id == User.id)
                         .where(Membership.member_id == person.id, Membership.role == "owner", User.kind == "workspace")
                         .order_by(func.lower(User.company))):
        others = db.scalar(select(func.count()).select_from(Membership).where(
            Membership.workspace_id == ws.id, Membership.role == "owner", Membership.member_id != person.id)) or 0
        out.append((ws, others > 0))
    return out


def _counts(db: Session, account_id: int) -> dict:
    return {name: db.scalar(select(func.count()).select_from(M).where(M.user_id == account_id)) or 0
            for name, M in (("leads", Lead), ("sites", Site), ("campaigns", Campaign))}


# ---- export ------------------------------------------------------------------------------------------------
def _plain(v):
    if isinstance(v, datetime):
        return v.isoformat() + "Z"
    return v


def account_records(db: Session, account_id: int) -> dict:
    """Every row that belongs to one account, table by table, plus rows hanging off those (page versions, daily
    campaign stats). Secret columns are left out."""
    out, ids = {}, {}
    tables = [t for t in Base.metadata.sorted_tables if t.name not in SKIP_TABLES and t.name != "users"]
    for t in tables:  # rows owned directly
        col = next((t.c[c] for c in OWNER_COLUMNS if c in t.c), None)
        if col is None:
            continue
        rows = db.execute(select(t).where(col == account_id).order_by(t.primary_key.columns.values()[0])).mappings().all()
        out[t.name] = [{k: _plain(v) for k, v in r.items() if k not in SECRET_COLUMNS} for r in rows]
        if "id" in t.c:
            ids[t.name] = [r["id"] for r in rows]
    for t in tables:  # child rows of those (site_versions -> sites, campaign_stats -> campaigns)
        if t.name in out:
            continue
        for fk in t.foreign_keys:
            parent = fk.column.table.name
            if parent in ids and parent != "users":
                rows = db.execute(select(t).where(fk.parent.in_(ids[parent]))).mappings().all() if ids[parent] else []
                out[t.name] = [{k: _plain(v) for k, v in r.items() if k not in SECRET_COLUMNS} for r in rows]
                break
    return {k: v for k, v in out.items() if v}


def _leads_csv(db: Session, account_id: int) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = ("id", "name", "email", "phone", "message", "source", "stage", "value", "language", "created_at")
    w.writerow(cols)
    for lead in db.scalars(select(Lead).where(Lead.user_id == account_id).order_by(Lead.id)):
        w.writerow([_plain(getattr(lead, c)) for c in cols])
    return buf.getvalue()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40] or "workspace"


def _add_account(z: zipfile.ZipFile, db: Session, account: User, folder: str) -> None:
    z.writestr(f"{folder}/data.json", json.dumps(account_records(db, account.id), indent=2, ensure_ascii=False, default=str))
    z.writestr(f"{folder}/leads.csv", _leads_csv(db, account.id))
    root = UPLOADS / str(account.id)
    if root.is_dir():
        for f in sorted(root.rglob("*")):
            if f.is_file():
                z.write(f, f"{folder}/files/{f.relative_to(root).as_posix()}")


README = """Your AIMVA data, exported {when}.

account.json             your profile (no password or other secrets)
my-account/              your own business: data.json (every record, table by table), leads.csv, files/
workspaces/<name>-<id>/  each client workspace you own, laid out the same way

Connected-account tokens, API keys and passwords are never exported. To delete your account, go to
Settings > Profile > Delete account.
"""


def build_export(db: Session, person: User) -> Iterable[bytes]:
    spool = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024)
    with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", README.format(when=utcnow().strftime("%d %b %Y %H:%M UTC")))
        profile = {k: _plain(getattr(person, k)) for k in USER_FIELDS}
        profile["workspaces"] = [{"id": ws.id, "name": ws.company or ws.name, "role": role}
                                 for ws, role in db.execute(select(User, Membership.role)
                                                            .join(Membership, Membership.workspace_id == User.id)
                                                            .where(Membership.member_id == person.id))]
        z.writestr("account.json", json.dumps(profile, indent=2, ensure_ascii=False, default=str))
        _add_account(z, db, person, "my-account")
        for ws, _shared in owned_workspaces(db, person):
            _add_account(z, db, ws, f"workspaces/{_slug(ws.company or ws.name)}-{ws.id}")
    spool.seek(0)

    def chunks():
        try:
            while block := spool.read(64 * 1024):
                yield block
        finally:
            spool.close()
    return chunks()


@router.get("/export")
def export(request: Request, person: User = Depends(current_person), db: Session = Depends(get_db)):
    """Download a ZIP of everything in your account and in the client workspaces you own."""
    rate_limit(f"export:{person.id}", 5, 3600)
    name = f"aimva-data-{utcnow():%Y-%m-%d}.zip"
    log.info("data export for user %s", person.id)
    return StreamingResponse(build_export(db, person), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


# ---- delete ------------------------------------------------------------------------------------------------
REVOKE_TIMEOUT = 8


def revoke_integration(integ: Integration) -> bool:
    """Tell the provider to drop the access AIMVA was given. Best effort: a failure is logged, never raised, because
    the stored token is deleted either way. API keys the user pasted (WhatsApp, Twilio, hosting) can't be revoked
    from here; the user rotates those in that service if they want."""
    from .routers.integrations import OAUTH
    try:
        tok = decrypt_json(integ.secret)
    except Exception:
        return False
    token = tok.get("refresh_token") or tok.get("access_token")
    if not token or integ.provider not in OAUTH:
        return False
    p = OAUTH[integ.provider]
    try:
        if integ.provider == "meta":
            r = httpx.delete("https://graph.facebook.com/v21.0/me/permissions",
                             params={"access_token": tok.get("access_token") or token}, timeout=REVOKE_TIMEOUT)
        elif integ.provider == "google":
            r = httpx.post("https://oauth2.googleapis.com/revoke", data={"token": token}, timeout=REVOKE_TIMEOUT)
        elif integ.provider == "linkedin":
            r = httpx.post("https://www.linkedin.com/oauth/v2/revoke", timeout=REVOKE_TIMEOUT,
                           data={"token": tok.get("access_token") or token, "client_id": p["client_id"](),
                                 "client_secret": p["client_secret"]()})
        else:  # Microsoft has no per-token revoke for this kind of app; the refresh token is deleted with the row
            return False
        if r.status_code >= 400:
            log.warning("revoking %s for account %s returned %s", integ.provider, integ.user_id, r.status_code)
            return False
        return True
    except httpx.HTTPError as e:
        log.warning("revoking %s for account %s failed: %s", integ.provider, integ.user_id, e)
        return False


def cancel_subscription(sub: Subscription) -> bool:
    """Stop future charges for a paid plan before the account disappears. Best effort, like revoking."""
    from .billing import RAZORPAY, _rz
    if sub.processor != "razorpay" or not sub.processor_subscription_id or sub.status not in ("active", "past_due"):
        return False
    key, secret = _rz("RAZORPAY_KEY_ID"), _rz("RAZORPAY_KEY_SECRET")
    if not (key and secret):
        log.warning("can't cancel Razorpay subscription %s: no Razorpay keys", sub.processor_subscription_id)
        return False
    try:
        r = httpx.post(f"{RAZORPAY}/subscriptions/{sub.processor_subscription_id}/cancel", auth=(key, secret),
                       json={"cancel_at_cycle_end": 0}, timeout=REVOKE_TIMEOUT)
        if r.status_code >= 400:
            log.warning("Razorpay cancel for %s returned %s", sub.processor_subscription_id, r.status_code)
        return r.status_code < 400
    except httpx.HTTPError as e:
        log.warning("Razorpay cancel for %s failed: %s", sub.processor_subscription_id, e)
        return False


def erase_account(db: Session, account: User) -> dict:
    """Revoke, cancel, remove files and delete one account (a person or a client workspace) with all its rows."""
    revoked = [i.provider for i in db.scalars(select(Integration).where(Integration.user_id == account.id))
               if revoke_integration(i)]
    sub = db.scalar(select(Subscription).where(Subscription.user_id == account.id))
    cancelled = bool(sub and cancel_subscription(sub))
    # Templates an owner published for everyone stay available to everyone; they just lose their author.
    db.execute(update(Template).where(Template.owner_id == account.id, Template.source == "platform").values(owner_id=None))
    shutil.rmtree(UPLOADS / str(account.id), ignore_errors=True)
    db.delete(account)
    db.flush()
    return {"revoked": revoked, "plan_cancelled": cancelled}


@router.get("/delete-preview")
def delete_preview(person: User = Depends(current_person), db: Session = Depends(get_db)):
    """What deleting the account would remove, so the confirmation can say it in plain words."""
    goes, stays = [], []
    for ws, shared in owned_workspaces(db, person):
        (stays if shared else goes).append({"id": ws.id, "name": ws.company or ws.name, **_counts(db, ws.id)})
    member_of = db.scalar(select(func.count()).select_from(Membership).where(Membership.member_id == person.id,
                                                                             Membership.role != "owner")) or 0
    ids = [person.id] + [w["id"] for w in goes]
    connected = sorted(set(db.scalars(select(Integration.provider).where(Integration.user_id.in_(ids)))))
    sub = db.scalar(select(Subscription).where(Subscription.user_id == person.id))
    return {"email": person.email, "own": _counts(db, person.id), "workspaces_deleted": goes, "workspaces_kept": stays,
            "member_of": member_of, "connected": connected,
            "paid_plan": bool(sub and sub.processor == "razorpay" and sub.status in ("active", "past_due"))}


class DeleteAccountIn(BaseModel):
    password: str
    confirm_email: str


@router.post("/delete")
def delete_account(body: DeleteAccountIn, request: Request, response: Response, bg: BackgroundTasks,
                   person: User = Depends(current_person), db: Session = Depends(get_db)):
    """Delete the signed-in person's account and everything in it. Cannot be undone."""
    rate_limit(f"delete-account:{client_ip(request)}", 5, 900)
    if body.confirm_email.strip().lower() != person.email.lower():
        raise HTTPException(400, "Type your account's email address exactly to confirm.")
    if not verify_password(person.password_hash, body.password):
        raise HTTPException(400, "That password isn't right.")
    from .mailer import send_email
    email, name, pid = person.email, person.name, person.id
    deleted_ws = [ws for ws, shared in owned_workspaces(db, person) if not shared]
    result = {"revoked": [], "workspaces_deleted": [ws.company or ws.name for ws in deleted_ws], "plan_cancelled": False}
    for ws in deleted_ws:
        r = erase_account(db, ws)
        result["revoked"] += r["revoked"]
    r = erase_account(db, person)
    result["revoked"] = sorted(set(result["revoked"] + r["revoked"]))
    result["plan_cancelled"] = r["plan_cancelled"]
    db.commit()
    log.info("account %s deleted (%d client workspaces with it)", pid, len(deleted_ws))
    clear_session(response)
    bg.add_task(send_email, email, "Your AIMVA account has been deleted",
                f"Hi {name},\n\nYour AIMVA account ({email}) and everything in it have been deleted, as you asked. "
                "Nothing can be recovered from it now.\n\nIf you didn't do this, reply to this email straight away.")
    return {"ok": True, **result}
