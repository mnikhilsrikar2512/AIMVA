"""Connect third-party accounts.

Two connection styles:
- OAuth (meta, google, linkedin, microsoft): needs the app client id/secret in .env.
- API key (fal, netlify, vercel, cloudflare, whatsapp, twilio, github): the user pastes a token in the UI;
  it is stored Fernet-encrypted and never returned to the browser.
"""
import secrets
import time
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Integration, User, utcnow
from ..security import current_user, encrypt_json
from ..services import get_integration

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

OAUTH = {
    "meta": {
        "label": "Meta (Facebook & Instagram Ads)",
        "auth_url": "https://www.facebook.com/v21.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v21.0/oauth/access_token",
        "scope": "ads_management,ads_read,leads_retrieval,pages_show_list,pages_manage_ads,business_management",
        "client_id": lambda: settings.meta_app_id, "client_secret": lambda: settings.meta_app_secret,
        "docs": "https://developers.facebook.com/docs/marketing-apis/get-started",
    },
    "google": {
        "label": "Google (Ads, Sheets, Business)",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "openid email profile https://www.googleapis.com/auth/adwords https://www.googleapis.com/auth/spreadsheets",
        "extra": {"access_type": "offline", "prompt": "consent"},
        "client_id": lambda: settings.google_client_id, "client_secret": lambda: settings.google_client_secret,
        "docs": "https://developers.google.com/google-ads/api/docs/oauth/overview",
    },
    "linkedin": {
        "label": "LinkedIn (Campaign Manager)",
        "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "scope": "r_ads rw_ads r_ads_reporting r_organization_social",
        "client_id": lambda: settings.linkedin_client_id, "client_secret": lambda: settings.linkedin_client_secret,
        "docs": "https://learn.microsoft.com/en-us/linkedin/marketing/getting-started",
    },
    "microsoft": {
        "label": "Microsoft (OneDrive / Excel)",
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "offline_access Files.ReadWrite User.Read",
        "client_id": lambda: settings.microsoft_client_id, "client_secret": lambda: settings.microsoft_client_secret,
        "docs": "https://learn.microsoft.com/en-us/graph/auth-v2-user",
    },
}

API_KEY = {
    "fal": {"label": "fal.ai (image & video models)", "fields": ["api_key"], "docs": "https://fal.ai/dashboard/keys",
            "hints": {"api_key": "Paste the whole key, including the part after the colon (key-id:key-secret)."}},
    "gemini": {"label": "Google Gemini (AI writing)", "fields": ["api_key"], "docs": "https://aistudio.google.com/apikey",
               "hints": {"api_key": "Create a free key at aistudio.google.com/apikey. Powers AI landing pages, ad copy, voice replies and insights."}},
    "whatsapp": {"label": "WhatsApp Cloud API", "fields": ["access_token", "phone_number_id"],
                 "docs": "https://developers.facebook.com/docs/whatsapp/cloud-api/get-started"},
    "twilio": {"label": "Twilio (phone calls)", "fields": ["account_sid", "auth_token", "from_number"],
               "docs": "https://www.twilio.com/docs/voice/quickstart"},
    "netlify": {"label": "Netlify hosting", "fields": ["api_token"], "docs": "https://app.netlify.com/user/applications#personal-access-tokens"},
    "vercel": {"label": "Vercel hosting", "fields": ["api_token"], "docs": "https://vercel.com/account/tokens"},
    "cloudflare": {"label": "Cloudflare Pages", "fields": ["api_token", "account_id"], "docs": "https://dash.cloudflare.com/profile/api-tokens"},
    "github": {"label": "GitHub Pages", "fields": ["api_token"], "docs": "https://github.com/settings/tokens"},
}
NON_SECRET = {"phone_number_id", "account_id", "from_number"}


def _redirect_uri(provider: str) -> str:
    return f"{settings.public_url}/api/integrations/{provider}/callback"


@router.get("")
def list_integrations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = {i.provider: i for i in db.scalars(select(Integration).where(Integration.user_id == user.id))}
    out = []
    for key, p in {**OAUTH, **API_KEY}.items():
        i = rows.get(key)
        out.append({
            "provider": key, "label": p["label"], "type": "oauth" if key in OAUTH else "api_key",
            "fields": p.get("fields", []), "hints": p.get("hints", {}), "docs": p["docs"],
            "app_configured": bool(p["client_id"]()) if key in OAUTH else True,
            "connected": bool(i), "account_name": i.account_name if i else "", "meta": i.meta if i else {},
            "connected_at": i.connected_at.isoformat() if i else None,
        })
    return out


class KeyIn(BaseModel):
    values: dict
    account_name: Optional[str] = ""


def _verify_fal(values: dict) -> None:
    """Ask fal.ai whether the key authenticates. A status lookup for a made-up request id is free:
    fal answers 401 for a bad key and 404 (not found) once the key is accepted."""
    r = httpx.get("https://queue.fal.run/fal-ai/ltx-video/requests/00000000-0000-0000-0000-000000000000/status",
                  headers={"Authorization": f"Key {values['api_key']}"}, timeout=20)
    if r.status_code in (401, 403):
        hint = "" if ":" in values["api_key"] else " It looks incomplete: fal.ai keys contain a colon (key-id:key-secret)."
        raise HTTPException(400, f"fal.ai didn't accept this key.{hint}")


def _verify_gemini(values: dict) -> None:
    """Listing models is free and needs a valid key: 200 when accepted, 400/403 for a bad key."""
    from ..services import GEMINI_API
    r = httpx.get(f"{GEMINI_API}/models", params={"key": values["api_key"], "pageSize": 1}, timeout=20)
    if r.status_code in (400, 401, 403):
        raise HTTPException(400, "Google didn't accept this Gemini key. Copy it again from aistudio.google.com/apikey.")


# Providers whose keys can be checked cheaply before saving.
VERIFY = {"fal": _verify_fal, "gemini": _verify_gemini}


def verify_key(provider: str, values: dict) -> None:
    fn = VERIFY.get(provider)
    if not fn:
        return
    try:
        fn(values)
    except httpx.HTTPError:
        pass  # provider unreachable: save anyway rather than block the user


@router.post("/{provider}/key")
def save_key(provider: str, body: KeyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    spec = API_KEY.get(provider)
    if not spec:
        raise HTTPException(404, "Unknown provider.")
    values = {k: str(body.values.get(k, "")).strip() for k in spec["fields"]}
    if missing := [k for k, v in values.items() if not v]:
        raise HTTPException(400, f"Missing: {', '.join(missing)}")
    verify_key(provider, values)
    integ = get_integration(db, user.id, provider) or Integration(user_id=user.id, provider=provider)
    integ.secret = encrypt_json({k: v for k, v in values.items() if k not in NON_SECRET})
    integ.meta = {k: v for k, v in values.items() if k in NON_SECRET}
    integ.account_name = body.account_name or spec["label"]
    integ.connected_at = utcnow()
    db.add(integ)
    db.commit()
    return {"ok": True}


@router.get("/ai/status")
def ai_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Which Gemini key AI features will use for this user: their own, the server's, or none (templates)."""
    own = bool(get_integration(db, user.id, "gemini"))
    return {"gemini": own or bool(settings.gemini_api_key), "source": "yours" if own else ("server" if settings.gemini_api_key else None),
            "model": settings.gemini_model, "free": settings.free_ai}


@router.get("/{provider}/connect")
def oauth_start(provider: str, user: User = Depends(current_user)):
    p = OAUTH.get(provider)
    if not p:
        raise HTTPException(404, "Unknown provider.")
    if not p["client_id"]():
        raise HTTPException(400, f"{p['label']} app is not configured yet. Add its client id/secret to backend/.env.")
    state = jwt.encode({"uid": user.id, "p": provider, "n": secrets.token_urlsafe(8),
                        "exp": int(time.time()) + 600}, settings.secret_key, "HS256")
    params = {"client_id": p["client_id"](), "redirect_uri": _redirect_uri(provider), "response_type": "code",
              "scope": p["scope"], "state": state, **p.get("extra", {})}
    return {"url": f"{p['auth_url']}?{urlencode(params)}"}


@router.get("/{provider}/callback")
def oauth_callback(provider: str, code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    back = f"{settings.frontend_url}/app/settings?tab=integrations"
    p = OAUTH.get(provider)
    if error or not p:
        return RedirectResponse(f"{back}&error={error or 'unknown'}")
    try:
        st = jwt.decode(state, settings.secret_key, algorithms=["HS256"])
        assert st["p"] == provider
    except Exception:
        return RedirectResponse(f"{back}&error=invalid_state")
    r = httpx.post(p["token_url"], data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": _redirect_uri(provider),
        "client_id": p["client_id"](), "client_secret": p["client_secret"](),
    }, timeout=30)
    if r.status_code >= 400:
        return RedirectResponse(f"{back}&error=token_exchange_failed")
    tokens = r.json()
    integ = get_integration(db, st["uid"], provider) or Integration(user_id=st["uid"], provider=provider)
    integ.secret = encrypt_json(tokens)
    integ.account_name = p["label"]
    integ.connected_at = utcnow()
    db.add(integ)
    db.commit()
    return RedirectResponse(f"{back}&connected={provider}")


def oauth_access_token(db: Session, user_id: int, provider: str) -> Optional[str]:
    """Return a valid access token for an OAuth integration, refreshing it when expired."""
    from ..security import decrypt_json
    integ = get_integration(db, user_id, provider)
    if not integ:
        return None
    tok = decrypt_json(integ.secret)
    age = (utcnow() - integ.connected_at).total_seconds()
    if tok.get("refresh_token") and age > int(tok.get("expires_in", 3600)) - 120:
        p = OAUTH[provider]
        r = httpx.post(p["token_url"], data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
            "client_id": p["client_id"](), "client_secret": p["client_secret"](),
        }, timeout=30)
        if r.status_code < 400:
            tok = {**tok, **r.json()}
            integ.secret, integ.connected_at = encrypt_json(tok), utcnow()
            db.commit()
    return tok.get("access_token")


class MetaIn(BaseModel):
    meta: dict


@router.patch("/{provider}/meta")
def update_meta(provider: str, body: MetaIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Non-secret per-integration settings, e.g. google {sheet_id, auto_sync}, meta {ad_account_id}."""
    integ = get_integration(db, user.id, provider)
    if not integ:
        raise HTTPException(400, "Connect this account first.")
    integ.meta = {**(integ.meta or {}), **body.meta}
    db.commit()
    return {"ok": True, "meta": integ.meta}


@router.delete("/{provider}")
def disconnect(provider: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    integ = get_integration(db, user.id, provider)
    if integ:
        db.delete(integ)
        db.commit()
    return {"ok": True}
