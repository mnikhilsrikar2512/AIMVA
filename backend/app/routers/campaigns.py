"""Ad campaigns across Meta, Google and LinkedIn.

Campaigns are drafted in AIMVA. Publishing to Meta uses the Marketing API (Graph v21) with the
connected account; Google Ads and LinkedIn go through app/ad_platforms.py, which needs approved
developer access on those platforms. Every platform gets the campaign paused: AIMVA never starts spending.
"""
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Campaign, User
from ..security import current_user
from ..services import get_integration
from .integrations import oauth_access_token
from .leads import create_lead

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])
GRAPH = "https://graph.facebook.com/v21.0"
PLATFORMS = ("meta", "google", "linkedin", "other")  # other: offline, influencer, YouTube… (results entered by hand)


def record_stat(db: Session, c: Campaign, source: str = "manual", day: Optional[str] = None) -> None:
    """Snapshot the campaign's cumulative totals for a day, so periods and trends can be worked out later."""
    from ..models import CampaignStat, utcnow
    day = day or utcnow().date().isoformat()
    st = db.scalar(select(CampaignStat).where(CampaignStat.campaign_id == c.id, CampaignStat.day == day))
    if not st:
        st = CampaignStat(campaign_id=c.id, day=day)
        db.add(st)
    st.spend, st.impressions, st.clicks, st.source = c.spend, c.impressions, c.clicks, source


def campaign_out(c: Campaign) -> dict:
    ctr = round(c.clicks / c.impressions * 100, 2) if c.impressions else 0
    return {"id": c.id, "platform": c.platform, "name": c.name, "objective": c.objective,
            "daily_budget": c.daily_budget, "status": c.status, "creative": c.creative, "targeting": c.targeting,
            "lead_form": c.lead_form, "external_id": c.external_id, "spend": c.spend, "product_id": c.product_id, "started_on": c.started_on,
            "impressions": c.impressions, "clicks": c.clicks, "ctr": ctr, "created_at": c.created_at.isoformat()}


class CampaignIn(BaseModel):
    platform: str
    name: str = Field(min_length=2, max_length=200)
    objective: str = "leads"
    daily_budget: float = Field(0, ge=0)
    creative: dict = {}   # {headline, text, image_url, cta}
    targeting: dict = {}  # {locations, age_min, age_max, interests}
    lead_form: dict = {}  # {fields: [...], privacy_url, thank_you}
    product_id: Optional[int] = None


def _check_product(db: Session, user: User, product_id: Optional[int]) -> None:
    from ..models import Product
    if product_id is not None:
        p = db.get(Product, product_id)
        if not p or p.user_id != user.id:
            raise HTTPException(404, "Product not found.")


def _own(db: Session, user: User, cid: int) -> Campaign:
    c = db.get(Campaign, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found.")
    return c


@router.get("")
def list_campaigns(platform: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Campaign).where(Campaign.user_id == user.id).order_by(Campaign.created_at.desc())
    if platform:
        q = q.where(Campaign.platform == platform)
    return [campaign_out(c) for c in db.scalars(q)]


@router.post("")
def create_campaign(body: CampaignIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.platform not in PLATFORMS:
        raise HTTPException(400, "Platform must be meta, google, linkedin or other.")
    _check_product(db, user, body.product_id)
    c = Campaign(user_id=user.id, **body.model_dump())
    db.add(c)
    db.commit()
    return campaign_out(c)


class CampaignPatch(BaseModel):
    name: Optional[str] = None
    daily_budget: Optional[float] = None
    status: Optional[Literal["draft", "active", "paused"]] = None
    creative: Optional[dict] = None
    targeting: Optional[dict] = None
    lead_form: Optional[dict] = None
    product_id: Optional[int] = Field(None, ge=0)  # 0 = unassign


@router.patch("/{cid}")
def update_campaign(cid: int, body: CampaignPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _own(db, user, cid)
    changes = body.model_dump(exclude_none=True)
    if "product_id" in changes:
        changes["product_id"] = changes["product_id"] or None
        _check_product(db, user, changes["product_id"])
    if changes.get("daily_budget") is not None and changes["daily_budget"] < 0:
        raise HTTPException(400, "Budget can't be negative.")
    for k, v in changes.items():
        setattr(c, k, v)
    if c.external_id and c.platform == "meta" and body.status in ("active", "paused"):
        token = oauth_access_token(db, user.id, "meta")
        r = httpx.post(f"{GRAPH}/{c.external_id}", data={"status": body.status.upper(), "access_token": token}, timeout=30)
        if r.status_code >= 400:  # before: ignored, so AIMVA said "paused" while Meta kept spending
            db.rollback()
            raise HTTPException(502, "Meta didn't accept the change. Try again, or change it in Meta Ads Manager.")
    elif c.external_id and c.platform in ("google", "linkedin") and body.status in ("active", "paused"):
        from .. import ad_platforms
        set_status = ad_platforms.google_set_status if c.platform == "google" else ad_platforms.linkedin_set_status
        set_status(db, c, oauth_access_token(db, user.id, c.platform), body.status)
    db.commit()
    return campaign_out(c)


@router.delete("/{cid}")
def delete_campaign(cid: int, force: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Pause it on the ad platform first: a deleted row can't pause a campaign that keeps spending.
    force=true deletes it anyway (the owner has stopped it on the platform themselves)."""
    from ..teardown import pause_campaign
    c = _own(db, user, cid)
    if not pause_campaign(db, c) and not force:
        db.rollback()
        raise HTTPException(409, "Couldn't pause this campaign on the ad platform, so it may still be spending. "
                                 "Pause it there, then delete it here.")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.get("/meta/ad-accounts")
def meta_ad_accounts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    token = oauth_access_token(db, user.id, "meta")
    if not token:
        raise HTTPException(400, "Connect your Meta account first.")
    r = httpx.get(f"{GRAPH}/me/adaccounts", params={"fields": "id,name,currency,account_status", "access_token": token}, timeout=30)
    if r.status_code >= 400:
        raise HTTPException(502, f"Meta error: {r.text[:200]}")
    return r.json().get("data", [])


@router.post("/{cid}/publish")
def publish(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..workspaces import require_approved
    c = _own(db, user, cid)
    require_approved(db, user, "campaign", c.id)
    if c.platform == "other":
        raise HTTPException(400, "This campaign runs outside AIMVA. Mark it active and enter its results by hand.")
    if c.platform != "meta":
        from .. import ad_platforms
        label = "Google Ads" if c.platform == "google" else "LinkedIn Campaign Manager"
        if not get_integration(db, user.id, c.platform):
            raise HTTPException(400, f"Connect your {label} account in Settings → Integrations first.")
        if c.external_id:
            raise HTTPException(400, "This campaign is already published.")
        publish_to = ad_platforms.google_publish if c.platform == "google" else ad_platforms.linkedin_publish
        publish_to(db, c, oauth_access_token(db, user.id, c.platform))
        db.commit()
        return campaign_out(c)
    token = oauth_access_token(db, user.id, "meta")
    integ = get_integration(db, user.id, "meta")
    account = (integ.meta or {}).get("ad_account_id") if integ else None
    if not token or not account:
        raise HTTPException(400, "Connect Meta and choose an ad account first.")
    r = httpx.post(f"{GRAPH}/{account}/campaigns", data={
        "name": c.name, "objective": "OUTCOME_LEADS" if c.objective == "leads" else "OUTCOME_TRAFFIC",
        "status": "PAUSED", "special_ad_categories": "[]", "access_token": token}, timeout=30)
    if r.status_code >= 400:
        raise HTTPException(502, f"Meta error: {r.text[:300]}")
    c.external_id, c.status = r.json()["id"], "paused"
    db.commit()
    return campaign_out(c)


@router.post("/{cid}/sync")
def sync_insights(cid: int, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Pull spend/impressions/clicks and (if a lead form id is set) new leads from Meta."""
    c = _own(db, user, cid)
    if c.platform in ("google", "linkedin") and c.external_id:
        from .. import ad_platforms
        sync = ad_platforms.google_sync if c.platform == "google" else ad_platforms.linkedin_sync
        sync(db, c, oauth_access_token(db, user.id, c.platform))
        record_stat(db, c, c.platform)
        db.commit()
        return {**campaign_out(c), "new_leads": 0}
    if c.platform != "meta" or not c.external_id:
        raise HTTPException(400, "Publish this campaign first; campaigns run outside AIMVA take their results by hand.")
    token = oauth_access_token(db, user.id, "meta")
    r = httpx.get(f"{GRAPH}/{c.external_id}/insights",
                  params={"fields": "spend,impressions,clicks", "date_preset": "maximum", "access_token": token}, timeout=30)
    rows = r.json().get("data", []) if r.status_code < 400 else []
    if rows:
        c.spend, c.impressions, c.clicks = float(rows[0].get("spend", 0)), int(rows[0].get("impressions", 0)), int(rows[0].get("clicks", 0))
        record_stat(db, c, "meta")
    new = 0
    form_id = (c.lead_form or {}).get("form_id")
    if form_id:
        lr = httpx.get(f"{GRAPH}/{form_id}/leads", params={"access_token": token}, timeout=30)
        for item in lr.json().get("data", []) if lr.status_code < 400 else []:
            f = {d["name"]: (d.get("values") or [""])[0] for d in item.get("field_data", [])}
            create_lead(db, user.id, bg, name=f.get("full_name", ""), email=f.get("email", ""),
                        phone=f.get("phone_number", ""), source="meta", source_ref=item.get("id", ""),
                        event={"title": f"Lead form · {c.name}"}, campaign_id=c.id, product_id=c.product_id)
            new += 1
    db.commit()
    return {**campaign_out(c), "new_leads": new}
