"""Feedback on generated work, and the owner's quality & usage dashboard.

The north-star metric is "first-time-right": the share of published pages that went live without a
manual HTML edit, regenerate or restore. Feedback reasons show what to fix in prompts and playbooks.
"""
from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import staff
from ..config import settings
from ..db import get_db
from ..models import Asset, Feedback, Site, SiteVersion, User, utcnow
from ..security import current_person, current_user, rate_limit

router = APIRouter(tags=["feedback"])

Kind = Literal["site", "image", "video"]
Reason = Literal["", "wrong_facts", "off_brand", "low_quality", "text_errors", "not_what_i_asked", "too_generic", "other"]
REASON_LABELS = {"wrong_facts": "Wrong or invented facts", "off_brand": "Off-brand", "low_quality": "Low quality",
                 "text_errors": "Text errors", "not_what_i_asked": "Not what I asked for", "too_generic": "Too generic",
                 "other": "Other"}


class FeedbackIn(BaseModel):
    kind: Kind
    id: int
    rating: Literal[1, -1]
    reason: Reason = ""
    note: str = Field("", max_length=500)


def _owns(db: Session, user: User, kind: str, target_id: int) -> bool:
    if kind == "site":
        s = db.get(Site, target_id)
        return bool(s and s.user_id == user.id)
    a = db.get(Asset, target_id)
    return bool(a and a.user_id == user.id and a.kind == kind)


@router.post("/api/feedback")
def give_feedback(body: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(f"feedback:{user.id}", 60, 300)
    if not _owns(db, user, body.kind, body.id):
        raise HTTPException(404, "Item not found.")
    fb = db.scalar(select(Feedback).where(Feedback.user_id == user.id, Feedback.target_kind == body.kind,
                                          Feedback.target_id == body.id))
    if not fb:
        fb = Feedback(user_id=user.id, target_kind=body.kind, target_id=body.id)
        db.add(fb)
    fb.rating, fb.reason, fb.note = body.rating, body.reason if body.rating < 0 else "", body.note.strip()
    fb.created_at = utcnow()
    db.commit()
    return {"ok": True, "rating": fb.rating, "reason": fb.reason}


@router.get("/api/feedback")
def my_feedback(kind: Kind, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Feedback).where(Feedback.user_id == user.id, Feedback.target_kind == kind)
    return {str(f.target_id): {"rating": f.rating, "reason": f.reason} for f in db.scalars(q)}


# ---- owner dashboard ---------------------------------------------------------------------------------
def require_admin(user: User = Depends(current_person)) -> User:
    if user.email.lower() not in settings.admin_emails:
        raise HTTPException(403, "Only the AIMVA team can see this page.")
    return user


def _pct(a: int, b: int):
    return round(100 * a / b) if b else None


@router.get("/api/admin/metrics")
def metrics(days: int = 30, user: User = Depends(staff.require("quality.view")), db: Session = Depends(get_db)):
    days = max(1, min(days, 365))
    since = utcnow() - timedelta(days=days)

    users = list(db.scalars(select(User)))
    sites = list(db.scalars(select(Site).where(Site.created_at >= since)))
    versions = defaultdict(list)
    if sites:
        for v in db.scalars(select(SiteVersion).where(SiteVersion.site_id.in_([s.id for s in sites])).order_by(SiteVersion.number)):
            versions[v.site_id].append(v)
    published = [s for s in sites if s.published]
    reworked = lambda s: any(v.note.startswith(("Edited", "Regenerated", "Restored")) for v in versions[s.id])
    first_time_right = [s for s in published if not reworked(s)]
    regens = sum(1 for s in sites for v in versions[s.id] if v.note == "Regenerated")
    edits = sum(1 for s in sites for v in versions[s.id] if v.note.startswith("Edited"))
    ai_pages = sum(1 for s in sites if versions[s.id] and versions[s.id][0].generator == "ai")
    to_publish = [(s.published_at - s.created_at).total_seconds() / 60 for s in published if s.published_at]

    assets = list(db.scalars(select(Asset).where(Asset.created_at >= since)))
    images = [a for a in assets if a.kind == "image" and not (a.params or {}).get("parent")]
    adsets = {(a.params or {}).get("adset") for a in assets if (a.params or {}).get("adset")}
    videos = [a for a in assets if a.kind == "video"]
    failed_videos = [a for a in videos if a.status == "failed"]

    providers = defaultdict(lambda: {"images": 0, "videos": 0, "failed": 0})
    for a in images + videos:
        p = (a.params or {}).get("provider_label") or a.model or "unknown"
        providers[p]["images" if a.kind == "image" else "videos"] += 1
        providers[p]["failed"] += a.status == "failed"

    fbs = list(db.scalars(select(Feedback).where(Feedback.created_at >= since)))
    fb_kind = {k: {"up": sum(f.rating > 0 for f in fbs if f.target_kind == k), "down": sum(f.rating < 0 for f in fbs if f.target_kind == k)}
               for k in ("site", "image", "video")}
    reasons = Counter(f.reason or "other" for f in fbs if f.rating < 0)
    recent_down = [{"kind": f.target_kind, "reason": REASON_LABELS.get(f.reason, "Other"), "note": f.note,
                    "at": f.created_at.isoformat()} for f in sorted(fbs, key=lambda f: f.created_at, reverse=True) if f.rating < 0][:10]

    per_user = Counter()
    for s in sites:
        per_user[s.user_id] += 1
    for a in images + videos:
        per_user[a.user_id] += 1
    emails = {u.id: u.email for u in users}
    return {
        "days": days,
        "users": {"total": len(users), "verified": sum(u.is_verified for u in users),
                  "new": sum(u.created_at >= since for u in users),
                  "active": len(per_user)},
        "websites": {"created": len(sites), "published": len(published), "ai_written": ai_pages,
                     "first_time_right": _pct(len(first_time_right), len(published)),
                     "regenerate_rate": round(regens / len(sites), 2) if sites else None,
                     "manual_edits": edits,
                     "median_minutes_to_publish": round(median(to_publish), 1) if to_publish else None},
        "images": {"generated": len(images), "ad_sets": len(adsets)},
        "videos": {"generated": len(videos), "failed": len(failed_videos), "fail_rate": _pct(len(failed_videos), len(videos))},
        "providers": sorted(({"name": k, **v} for k, v in providers.items()), key=lambda x: -(x["images"] + x["videos"]))[:12],
        "feedback": {"by_kind": fb_kind, "reasons": [{"reason": REASON_LABELS.get(r, r), "count": c} for r, c in reasons.most_common()],
                     "recent_negative": recent_down},
        "top_users": [{"email": emails.get(uid, "deleted"), "generations": n} for uid, n in per_user.most_common(10)],
    }
