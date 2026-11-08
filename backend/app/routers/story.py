"""How the modules connect, so each screen can say what its work led to.

A picture or video is "used" when a campaign's creative points at its url, or a page's html contains it. A page's
leads are website leads whose source_ref is its slug; a campaign's leads carry its campaign_id. Nothing here is
stored: it is all read from links the app already keeps, so it cannot drift out of date.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Asset, Campaign, Lead, Site, User
from ..security import current_user

router = APIRouter(prefix="/api/story", tags=["story"])


def _tally(leads) -> dict:
    won = [l for l in leads if l.stage == "won"]
    return {"leads": len(leads), "won": len(won), "value": round(sum(l.value or 0 for l in won), 2)}


def _site_html(s: Site) -> str:
    return (s.html or "") + "".join(p.get("html", "") for p in (s.pages or []) if isinstance(p, dict))


@router.get("")
def story(user: User = Depends(current_user), db: Session = Depends(get_db)):
    uid = user.id
    leads = list(db.scalars(select(Lead).where(Lead.user_id == uid)))
    sites = list(db.scalars(select(Site).where(Site.user_id == uid)))
    campaigns = list(db.scalars(select(Campaign).where(Campaign.user_id == uid)))
    assets = list(db.scalars(select(Asset).where(Asset.user_id == uid, Asset.status == "done")))

    by_campaign, by_slug = {}, {}
    for l in leads:
        if l.campaign_id:
            by_campaign.setdefault(l.campaign_id, []).append(l)
        if l.source == "website" and l.source_ref:
            by_slug.setdefault(l.source_ref, []).append(l)

    camp_out = {c.id: {"name": c.name, "platform": c.platform, "status": c.status, "spend": round(c.spend or 0, 2),
                       **_tally(by_campaign.get(c.id, []))} for c in campaigns}
    site_out = {s.id: {"name": s.name, "slug": s.slug, "live": s.published, "visits": s.visits or 0,
                       **_tally(by_slug.get(s.slug, []))} for s in sites}
    htmls = {s.id: _site_html(s) for s in sites}

    uses = {}
    for a in assets:
        if not a.url:
            continue
        used = []
        for c in campaigns:
            cr = c.creative or {}
            if a.url in (cr.get("image_url"), cr.get("video_url")):
                used.append({"kind": "campaign", "id": c.id, **camp_out[c.id]})
        ref = f"asset:{a.id}"
        for s in sites:
            b = s.brief or {}
            # The builder embeds library pictures into the page, so the brief's "asset:<id>" is the link, not the url.
            if b.get("hero_image") == ref or ref in (b.get("gallery") or []) or a.url in htmls[s.id]:
                used.append({"kind": "page", "id": s.id, **site_out[s.id]})
        if used:
            uses[a.id] = used

    def kind_summary(kind: str) -> dict:
        mine = [a for a in assets if a.kind == kind]
        used = [a for a in mine if a.id in uses]
        # A lead reached through two places that share a picture is still one lead.
        seen = {}
        for a in used:
            for u in uses[a.id]:
                pool = by_campaign.get(u["id"], []) if u["kind"] == "campaign" else by_slug.get(u.get("slug", ""), [])
                for l in pool:
                    seen[l.id] = l
        return {"made": len(mine), "used": len(used), **_tally(list(seen.values()))}

    sources, sales = {}, {}
    for l in leads:
        sources[l.source] = sources.get(l.source, 0) + 1
        if l.stage == "won":
            n, v = sales.get(l.source, (0, 0))
            sales[l.source] = (n + 1, v + (l.value or 0))
    spend = round(sum(c.spend or 0 for c in campaigns), 2)
    total = _tally(leads)
    return {
        "pictures": kind_summary("image"),
        "videos": kind_summary("video"),
        "pages": {"made": len(sites), "live": sum(1 for s in sites if s.published), "visits": sum(s.visits or 0 for s in sites),
                  **_tally([l for s in sites for l in by_slug.get(s.slug, [])])},
        "campaigns": {"made": len(campaigns), "active": sum(1 for c in campaigns if c.status == "active"), "spend": spend,
                      **_tally([l for c in campaigns for l in by_campaign.get(c.id, [])])},
        "leads": {**total, "waiting": sum(1 for l in leads if l.stage == "new" and not l.opted_out_at), "sources": sources},
        "results": {**total, "spend": spend,
                    "sales_by_source": sorted(({"source": k, "won": n, "value": round(v, 2)} for k, (n, v) in sales.items()),
                                              key=lambda x: -x["value"])},
        "uses": {str(k): v for k, v in uses.items()},
        "per_campaign": {str(k): v for k, v in camp_out.items()},
        "per_page": {str(k): v for k, v in site_out.items()},
    }
