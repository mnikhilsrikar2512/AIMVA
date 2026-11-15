"""Stopping what runs outside AIMVA before its record disappears.

Deleting a campaign row does not stop the campaign on Meta, Google or LinkedIn: it keeps spending the owner's money
with nothing left in AIMVA to pause it. A page deployed to Netlify stays online after its row is gone. So every delete
path (one campaign, one page, a project, a whole account) first pauses live campaigns and takes pages down.

Everything here is best effort: a provider that fails is logged and reported back by name, never raised, so the
owner can be told exactly what to stop by hand.
"""
import logging
from typing import List

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Campaign, Site, User

log = logging.getLogger("aimva.teardown")
TIMEOUT = 15
GRAPH = "https://graph.facebook.com/v21.0"


def pause_campaign(db: Session, c: Campaign) -> bool:
    """Pause one campaign on its ad platform. True when it is paused (or never ran outside AIMVA)."""
    if not c.external_id or c.platform not in ("meta", "google", "linkedin"):
        return True
    from .routers.integrations import oauth_access_token
    try:
        token = oauth_access_token(db, c.user_id, c.platform)
        if not token:
            log.warning("can't pause %s campaign %s: no connected account", c.platform, c.id)
            return False
        if c.platform == "meta":
            r = httpx.post(f"{GRAPH}/{c.external_id}", data={"status": "PAUSED", "access_token": token}, timeout=TIMEOUT)
            if r.status_code >= 400:
                log.warning("Meta pause for campaign %s returned %s", c.id, r.status_code)
                return False
        else:
            from . import ad_platforms
            set_status = ad_platforms.google_set_status if c.platform == "google" else ad_platforms.linkedin_set_status
            set_status(db, c, token, "paused")
    except Exception as e:  # HTTPException from ad_platforms, httpx errors, a token that can't be decrypted
        log.warning("pausing %s campaign %s failed: %s", c.platform, c.id, e)
        return False
    c.status = "paused"
    return True


def pause_campaigns(db: Session, account: User) -> List[str]:
    """Pause every campaign of an account that runs on an ad platform. Returns the names that could NOT be paused."""
    failed = []
    for c in db.scalars(select(Campaign).where(Campaign.user_id == account.id, Campaign.external_id != "")):
        # Paused in AIMVA doesn't prove paused on the platform (the owner may have switched it on there), so always ask.
        if not pause_campaign(db, c):
            failed.append(c.name)
    db.flush()
    return failed


def take_down_site(db: Session, s: Site) -> bool:
    """Unpublish a page; for a Netlify deploy, delete the Netlify site too. Vercel deployments are left (no project
    id is stored), so they are reported back. True when nothing stays online."""
    s.published = False
    if s.deploy_target == "aimva" or not s.deploy_url:
        return True
    if s.deploy_target == "netlify" and (s.brief or {}).get("_netlify_id"):
        from .services import integration_secret
        token = integration_secret(db, s.user_id, "netlify").get("api_token")
        if token:
            try:
                r = httpx.delete(f"https://api.netlify.com/api/v1/sites/{s.brief['_netlify_id']}",
                                 headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
                if r.status_code < 400 or r.status_code == 404:
                    return True
                log.warning("Netlify delete for site %s returned %s", s.id, r.status_code)
            except httpx.HTTPError as e:
                log.warning("Netlify delete for site %s failed: %s", s.id, e)
    return False


def take_down_sites(db: Session, account: User) -> List[str]:
    """Unpublish every page of an account. Returns the addresses that may still be online elsewhere."""
    left = []
    for s in db.scalars(select(Site).where(Site.user_id == account.id)):
        if not take_down_site(db, s):
            left.append(s.deploy_url or s.name)
    db.flush()
    return left


def stop_everything(db: Session, account: User) -> dict:
    """Before an account or project is deleted: pause its ads, take its pages down."""
    return {"campaigns_not_paused": pause_campaigns(db, account), "pages_still_online": take_down_sites(db, account)}
