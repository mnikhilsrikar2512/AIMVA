from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Asset, Call, Campaign, Integration, Lead, Site, User, WaMessage, utcnow
from ..security import current_user
from .providers import writer

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
def overview(days: int = Query(30, ge=1, le=365), user: User = Depends(current_user), db: Session = Depends(get_db)):
    since = utcnow() - timedelta(days=days)
    uid = user.id
    leads = list(db.scalars(select(Lead).where(Lead.user_id == uid)))
    recent = [l for l in leads if l.created_at >= since]
    prev = [l for l in leads if since - timedelta(days=days) <= l.created_at < since]
    campaigns = list(db.scalars(select(Campaign).where(Campaign.user_id == uid)))
    calls = list(db.scalars(select(Call).where(Call.user_id == uid)))
    sites = list(db.scalars(select(Site).where(Site.user_id == uid)))

    per_day = Counter(l.created_at.date().isoformat() for l in recent)
    series = [{"date": (since + timedelta(days=i + 1)).date().isoformat(),
               "leads": per_day.get((since + timedelta(days=i + 1)).date().isoformat(), 0)} for i in range(days)]
    spend = sum(c.spend for c in campaigns)
    won_value = sum(l.value for l in leads if l.stage == "won")
    by_source = Counter(l.source for l in leads)
    stages = ["new", "contacted", "qualified", "won", "lost"]
    stage_counts = Counter(l.stage for l in leads)
    scored = sorted(leads, key=lambda l: -l.score)[:5]

    return {
        "kpis": {
            "leads": len(recent),
            "leads_change": (round((len(recent) - len(prev)) / len(prev) * 100) if prev else None),
            "avg_score": round(sum(l.score for l in leads) / len(leads)) if leads else 0,
            "hot_leads": sum(1 for l in leads if l.score >= 70),
            "spend": round(spend, 2),
            "cpl": round(spend / len(leads), 2) if leads and spend else None,
            "roi": round((won_value - spend) / spend * 100) if spend else None,
            "won_value": won_value,
            "calls": len(calls),
            "avg_sentiment": round(sum(c.sentiment for c in calls) / len(calls), 2) if calls else None,
            "site_visits": sum(s.visits for s in sites),
            # Leads can arrive without a counted visit (cached page, form posted from a Netlify/Vercel copy), so cap at 100%.
            "conversion": min(100.0, round(sum(1 for l in leads if l.source == "website") / max(1, sum(s.visits for s in sites)) * 100, 1)),
        },
        "series": series,
        "by_source": [{"source": k, "count": v} for k, v in by_source.most_common()],
        "funnel": [{"stage": s, "count": stage_counts.get(s, 0)} for s in stages],
        "campaigns": [{"name": c.name, "platform": c.platform, "spend": c.spend, "clicks": c.clicks,
                       "impressions": c.impressions} for c in campaigns],
        "top_leads": [{"id": l.id, "name": l.name or l.email or l.phone, "score": l.score, "source": l.source} for l in scored],
        "counts": {
            "assets": db.query(Asset).filter(Asset.user_id == uid).count(),
            "sites": len(sites),
            "campaigns": len(campaigns),
            "wa_messages": db.query(WaMessage).filter(WaMessage.user_id == uid).count(),
            "integrations": db.query(Integration).filter(Integration.user_id == uid).count(),
        },
    }


def best_or_none(x) -> str:
    return f"{x[1]} of {x[0]}" if x[1] else f"none of {x[0]}"


@router.get("/insights")
def insights(user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = overview(30, user, db)  # direct call: pass days explicitly
    k, src = data["kpis"], data["by_source"]
    write = writer(db, user.id, agent="analyst")
    ai = write and write(f"You are a marketing analyst. Given these KPIs {k} and lead sources {src} and funnel {data['funnel']}, "
             f"give 3 short, specific, actionable recommendations (one line each, no preamble) on where to focus budget. "
             f"Only claim what these numbers support; treat any source with fewer than 5 leads as too small to judge.")
    if ai:
        return {"source": "ai", "items": [l.strip("-•* ").strip() for l in ai.splitlines() if l.strip()][:3]}
    items = []
    leads = list(db.scalars(select(Lead).where(Lead.user_id == user.id)))
    if not leads:
        items.append("No leads yet. Publish a landing page or run a test call to start collecting them.")
    else:
        # Rank channels by how often their leads buy, not by how many leads they send: a channel full of
        # tyre-kickers looks great by count. Channels with under 5 leads are too few to compare.
        per = {}
        for l in leads:
            n, w, v = per.get(l.source, (0, 0, 0.0))
            per[l.source] = (n + 1, w + (l.stage == "won"), v + (l.value or 0 if l.stage == "won" else 0))
        enough = {k: x for k, x in per.items() if x[0] >= 5}
        if len(enough) >= 2 and any(x[1] for x in enough.values()):
            rate = lambda x: x[1] / x[0]  # noqa: E731
            best, worst = max(enough.items(), key=lambda kv: rate(kv[1])), min(enough.items(), key=lambda kv: rate(kv[1]))
            if rate(best[1]) >= 1.5 * rate(worst[1]) + 0.02:
                items.append(f"{best[1][1]} of {best[1][0]} '{best[0]}' leads bought ({rate(best[1]):.0%}) against "
                             f"{best_or_none(worst[1])} for '{worst[0]}'. Put your follow-up time into '{best[0]}' first.")
        if not items:
            top = max(per.items(), key=lambda kv: kv[1][0])
            items.append(f"'{top[0]}' sends the most leads ({top[1][0]}). Mark the ones who buy as won, so AIMVA can tell which "
                         "channel brings buyers, not just enquiries.")
    if k["avg_sentiment"] is not None and k["avg_sentiment"] < 0 and k["calls"] >= 5:
        items.append("Callers sound unhappy on average over the last calls. Review the call script and turn on hand-over to you.")
    if k["site_visits"] >= 200 and k["conversion"] < 2:
        items.append(f"Only {k['conversion']}% of {k['site_visits']:,} page visits became leads. Try a shorter form or a clearer offer at the top.")
    if not k["spend"]:
        items.append("Connect Meta or Google Ads so AIMVA can see spend and work out what each lead and sale costs.")
    return {"source": "rules", "items": items[:3]}
