"""Command center: every product, campaign and page in one place, with explainable next steps.

Products group the campaigns (Meta, Google, LinkedIn or anything else) and landing pages that sell them.
Leads are attributed to a product/campaign when they arrive (ad lead forms, or ?aimva_c=<id> on the page link).
Recommendations are plain rules over those numbers, so every suggestion says exactly why it was made;
the user accepts (safe actions run in one click), snoozes or dismisses each, and every decision is logged.
"""
import calendar
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Campaign, CampaignStat, Decision, Lead, Product, Site, User, VoiceAgent, utcnow
from ..security import current_user, rate_limit
from .campaigns import CampaignPatch, campaign_out, record_stat, update_campaign
from .providers import writer

router = APIRouter(tags=["command"])
CUR = "₹"
HOT = 70


def money(v: float) -> str:
    return f"{CUR}{v:,.0f}" if v >= 100 or v == int(v) else f"{CUR}{v:,.2f}"


# ---- products ------------------------------------------------------------------------------------------
class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    kind: Literal["product", "service", "offer"] = "product"
    price: float = Field(0, ge=0, le=1e9)
    target_cpl: float = Field(0, ge=0, le=1e7)
    monthly_budget: float = Field(0, ge=0, le=1e9)
    status: Literal["active", "paused", "archived"] = "active"
    notes: str = Field("", max_length=2000)


def product_out(p: Product) -> dict:
    return {"id": p.id, "name": p.name, "kind": p.kind, "price": p.price, "target_cpl": p.target_cpl,
            "monthly_budget": p.monthly_budget, "status": p.status, "notes": p.notes, "created_at": p.created_at.isoformat()}


def _product(db: Session, user: User, pid: int) -> Product:
    p = db.get(Product, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Product not found.")
    return p


@router.get("/api/products")
def list_products(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [product_out(p) for p in db.scalars(select(Product).where(Product.user_id == user.id).order_by(Product.created_at))]


@router.post("/api/products")
def create_product(body: ProductIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.query(Product).filter(Product.user_id == user.id).count() >= 200:
        raise HTTPException(400, "You can have up to 200 products. Archive or delete some first.")
    p = Product(user_id=user.id, **body.model_dump())
    db.add(p)
    db.commit()
    return product_out(p)


@router.put("/api/products/{pid}")
def update_product(pid: int, body: ProductIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _product(db, user, pid)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.commit()
    return product_out(p)


@router.delete("/api/products/{pid}")
def delete_product(pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _product(db, user, pid)
    for model in (Campaign, Site, Lead):  # keep the campaigns, pages and leads; just unlink them
        for row in db.scalars(select(model).where(model.user_id == user.id, model.product_id == p.id)):
            row.product_id = None
    db.delete(p)
    db.commit()
    return {"ok": True}


class LinkIn(BaseModel):
    kind: Literal["campaign", "site"]
    id: int
    product_id: Optional[int] = None  # None = unlink


@router.post("/api/products/link")
def link(body: LinkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Attach a campaign or landing page to a product (or detach it)."""
    if body.product_id is not None:
        _product(db, user, body.product_id)
    row = db.get(Campaign if body.kind == "campaign" else Site, body.id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Not found.")
    row.product_id = body.product_id
    db.commit()
    return {"ok": True}


# ---- manual results (Google / LinkedIn / offline ads that don't sync yet) --------------------------------
class ResultsIn(BaseModel):
    spend: float = Field(ge=0, le=1e9)
    impressions: int = Field(0, ge=0, le=10**11)
    clicks: int = Field(0, ge=0, le=10**10)
    mode: Literal["total", "add"] = "add"  # add today's numbers, or set the running totals
    day: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    since: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")  # with totals: when the campaign started running


@router.post("/api/campaigns/{cid}/results")
def enter_results(cid: int, body: ResultsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Campaign, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Campaign not found.")
    today = utcnow().date().isoformat()
    if (body.day and body.day > today) or (body.since and body.since > today):
        raise HTTPException(400, "That date is in the future.")
    if body.since and body.mode == "total":
        c.started_on = body.since
    if body.mode == "add":
        c.spend, c.impressions, c.clicks = c.spend + body.spend, c.impressions + body.impressions, c.clicks + body.clicks
    else:
        if body.spend < c.spend * 0.5 and c.spend > 0:
            raise HTTPException(400, "Running totals can't drop by half. Use “add” to enter one day's numbers.")
        c.spend, c.impressions, c.clicks = body.spend, body.impressions, body.clicks
    if c.clicks > c.impressions and c.impressions:
        raise HTTPException(400, "Clicks can't be more than impressions.")
    record_stat(db, c, "manual", body.day)
    db.commit()
    return campaign_out(c)


# ---- performance ---------------------------------------------------------------------------------------------
def _ord(day: str) -> int:
    return datetime.fromisoformat(day).toordinal()


def _window(stats: list, c: Campaign, start: str, end: Optional[str]) -> tuple:
    """Spend/impressions/clicks between two days.

    Totals are running totals sampled now and then (platform syncs, hand-entered numbers). Between two samples
    we assume an even spread, starting from zero on the day the campaign started. So typing a month of lifetime
    totals today doesn't make this week look expensive.
    """
    today = utcnow().date().isoformat()
    pts = [(s.day, s.spend, s.impressions, s.clicks) for s in stats if s.day < today]
    pts.append((today, c.spend, c.impressions, c.clicks))
    zero_day = c.started_on or c.created_at.date().isoformat()
    if zero_day < pts[0][0]:
        pts.insert(0, (zero_day, 0.0, 0, 0))

    def at(day: Optional[str]) -> tuple:
        if day is None or day >= pts[-1][0]:
            return pts[-1][1:]
        if day < pts[0][0]:
            return (0.0, 0, 0)
        for (d0, *v0), (d1, *v1) in zip(pts, pts[1:]):
            if d0 <= day <= d1:
                f = (_ord(day) - _ord(d0)) / max(1, _ord(d1) - _ord(d0))
                return tuple(a + (b - a) * f for a, b in zip(v0, v1))
        return pts[-1][1:]

    a, b = at(start), at(end)
    return round(max(0.0, b[0] - a[0]), 2), max(0, round(b[1] - a[1])), max(0, round(b[2] - a[2]))


def _rate(a, b, pct=False):
    if not b:
        return None
    return round(a / b * (100 if pct else 1), 2)


def _change(now, before):
    return round((now - before) / before * 100) if before else None


def compute(db: Session, user: User, days: int) -> dict:
    now = utcnow()
    since, prev_since = now - timedelta(days=days), now - timedelta(days=days * 2)
    d_since, d_prev = since.date().isoformat(), prev_since.date().isoformat()
    products = list(db.scalars(select(Product).where(Product.user_id == user.id, Product.status != "archived").order_by(Product.created_at)))
    campaigns = list(db.scalars(select(Campaign).where(Campaign.user_id == user.id).order_by(Campaign.created_at)))
    sites = list(db.scalars(select(Site).where(Site.user_id == user.id)))
    leads = list(db.scalars(select(Lead).where(Lead.user_id == user.id)))
    stats = defaultdict(list)
    if campaigns:
        for s in db.scalars(select(CampaignStat).where(CampaignStat.campaign_id.in_([c.id for c in campaigns])).order_by(CampaignStat.day)):
            stats[s.campaign_id].append(s)
    price = {p.id: p.price for p in products}
    in_period = [l for l in leads if l.created_at >= since]
    in_prev = [l for l in leads if prev_since <= l.created_at < since]

    def lead_stats(rows, product_id=None):
        won = [l for l in rows if l.stage == "won"]
        revenue = sum(l.value or price.get(l.product_id or product_id, 0) for l in won)
        return {"leads": len(rows), "qualified": sum(l.stage in ("qualified", "won") for l in rows), "won": len(won),
                "revenue": round(revenue, 2), "hot": sum(l.score >= HOT and l.stage == "new" for l in rows)}

    rows_by_campaign = defaultdict(list)
    for l in in_period:
        if l.campaign_id:
            rows_by_campaign[l.campaign_id].append(l)
    prev_by_campaign = defaultdict(int)
    for l in in_prev:
        if l.campaign_id:
            prev_by_campaign[l.campaign_id] += 1

    camp = {}
    for c in campaigns:
        spend, imp, clicks = _window(stats[c.id], c, d_since, None)
        pspend, _, _ = _window(stats[c.id], c, d_prev, d_since)
        ls = lead_stats(rows_by_campaign[c.id], c.product_id)
        camp[c.id] = {**campaign_out(c), **ls, "period_spend": round(spend, 2), "period_impressions": imp, "period_clicks": clicks,
                      "ctr": _rate(clicks, imp, True), "cpl": _rate(spend, ls["leads"]), "conv": _rate(ls["leads"], clicks, True),
                      "roas": _rate(ls["revenue"], spend), "prev_spend": round(pspend, 2), "prev_leads": prev_by_campaign[c.id],
                      "leads_change": _change(ls["leads"], prev_by_campaign[c.id]),
                      "trend": _trend(stats[c.id], c, rows_by_campaign[c.id], days, now),
                      "tracked": bool(stats[c.id]) or c.spend > 0}
    cpls = [x["cpl"] for x in camp.values() if x["cpl"]]
    account_cpl = median(cpls) if cpls else None

    def target_for(c) -> Optional[float]:
        p = next((p for p in products if p.id == c["product_id"]), None)
        return (p.target_cpl if p and p.target_cpl else None) or account_cpl

    names = {p.id: p.name for p in products}
    for x in camp.values():
        x["target_cpl"] = target_for(x)
        x["health"] = _health(x)
        x["product_name"] = names.get(x["product_id"])

    out_products = []
    for p in products:
        cs = [camp[c.id] for c in campaigns if c.product_id == p.id]
        rows = [l for l in in_period if l.product_id == p.id]
        prev_rows = [l for l in in_prev if l.product_id == p.id]
        ls = lead_stats(rows, p.id)
        spend = round(sum(c["period_spend"] for c in cs), 2)
        month_spend = _month_spend(stats, [c for c in campaigns if c.product_id == p.id], now)
        out_products.append({**product_out(p), **ls, "spend": spend, "cpl": _rate(spend, ls["leads"]),
                             "roas": _rate(ls["revenue"], spend), "leads_change": _change(len(rows), len(prev_rows)),
                             "month_spend": month_spend, "month_projection": _project(month_spend, now),
                             "campaigns": cs, "pages": [_page(s) for s in sites if s.product_id == p.id]})
    unassigned = {"campaigns": [camp[c.id] for c in campaigns if not c.product_id],
                  "pages": [_page(s) for s in sites if not s.product_id]}
    total_spend = round(sum(x["period_spend"] for x in camp.values()), 2)
    prev_spend = round(sum(x["prev_spend"] for x in camp.values()), 2)
    totals = lead_stats(in_period)
    kpis = {**totals, "spend": total_spend, "spend_change": _change(total_spend, prev_spend),
            "leads_change": _change(len(in_period), len(in_prev)), "cpl": _rate(total_spend, totals["leads"]),
            "roas": _rate(totals["revenue"], total_spend), "active_campaigns": sum(c.status == "active" for c in campaigns)}
    kpis["hot"] = sum(l.score >= HOT and l.stage == "new" for l in leads)  # every hot lead still waiting, however old
    return {"days": days, "kpis": kpis, "products": out_products, "unassigned": unassigned, "campaigns": camp,
            "account_cpl": account_cpl, "leads": leads, "sites": sites, "now": now, "raw_products": products,
            "raw_campaigns": campaigns}


def _page(s: Site) -> dict:
    return {"id": s.id, "name": s.name, "published": s.published, "visits": s.visits, "url": f"{settings.public_url}/s/{s.slug}",
            "product_id": s.product_id}


def _trend(stats: list, c: Campaign, leads: list, days: int, now: datetime) -> list:
    """Per-day leads and spend for a sparkline (spend from snapshot differences)."""
    n = min(days, 30)
    out = []
    prev = None
    start = (now - timedelta(days=n + 1)).date()  # end at yesterday: today is still a partial day
    by_day = {s.day: s for s in stats}
    base = [s for s in stats if s.day < start.isoformat()]
    prev = base[-1].spend if base else (0.0 if stats else None)
    for i in range(1, n + 1):
        d = (start + timedelta(days=i)).isoformat()
        spend = None
        if d in by_day and prev is not None:
            spend, prev = round(max(0.0, by_day[d].spend - prev), 2), by_day[d].spend
        out.append({"day": d, "leads": sum(l.created_at.date().isoformat() == d for l in leads), "spend": spend})
    return out


def _health(x: dict) -> str:
    if x["status"] == "draft":
        return "draft"
    if x["status"] == "paused":
        return "paused"
    if not x["period_spend"] and not x["period_impressions"]:
        return "no_data"
    t = x["target_cpl"]
    if x["platform"] == "other" and not x["period_clicks"] and not x["leads"]:
        return "untracked"
    if not x["leads"]:
        return "attention" if x["period_clicks"] >= 30 or (t and x["period_spend"] >= 2 * t) else "learning"
    if t and x["cpl"] > 1.5 * t:
        return "attention"
    if t and x["cpl"] <= 0.8 * t:
        return "great"
    return "ok"


def _month_spend(stats: dict, cs: list, now: datetime) -> float:
    first = now.date().replace(day=1)
    before = (first - timedelta(days=1)).isoformat()
    total = 0.0
    for c in cs:
        snaps = stats[c.id]
        if not snaps:
            continue
        base = [s for s in snaps if s.day <= before]
        total += max(0.0, c.spend - (base[-1].spend if base else 0.0))
    return round(total, 2)


def _project(month_spend: float, now: datetime) -> float:
    dim = calendar.monthrange(now.year, now.month)[1]
    return round(month_spend / max(1, now.day) * dim, 2)


# ---- next steps ------------------------------------------------------------------------------------------
def rec(key, priority, title, why, action, impact="", product_id=None, campaign_id=None, group="fix", alt=None, notes=None):
    return {"key": key, "priority": priority, "group": group, "title": title, "why": why, "impact": impact, "action": action,
            "alt": alt, "notes": notes or [], "product_id": product_id, "campaign_id": campaign_id}


PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def recommendations(db: Session, user: User, ctx: dict) -> list:
    """Explainable next steps. One card per campaign (its biggest issue, other issues as notes); budget moves stay
    inside a product (leads for different products aren't worth the same); no "scale" while a product is over pace."""
    now, out, days = ctx["now"], [], ctx["days"]
    camp = ctx["campaigns"]
    over_pace = {p["id"] for p in ctx["products"]
                 if p["status"] == "active" and p["monthly_budget"] and p["month_projection"] > 1.15 * p["monthly_budget"]}

    # 1. Hot leads waiting: the fastest money on the table.
    hot = [l for l in ctx["leads"] if l.score >= HOT and l.stage == "new" and now - l.created_at > timedelta(minutes=30)]
    if hot:
        n = min(len(hot), 5)
        out.append(rec(f"call_hot:{now.date()}", "high", f"Call your {n} hottest lead{'s' if n > 1 else ''} now",
                       f"{len(hot)} lead{'s' if len(hot) > 1 else ''} scored {HOT}+ {'are' if len(hot) > 1 else 'is'} still marked new. "
                       "Leads called within an hour are far more likely to buy.",
                       {"type": "call_hot_leads", "label": f"Voice agent calls the top {n}", "count": n},
                       impact=f"{len(hot)} waiting", group="leads"))

    # 2. Budget moves inside each product: from its most to its least expensive leads.
    moves = {}
    for p in ctx["products"]:
        live_ = [c for c in p["campaigns"] if c["status"] == "active" and c["leads"] >= 2 and c["cpl"] and c["daily_budget"] > 0]
        if len(live_) < 2:
            continue
        best, worst = min(live_, key=lambda c: c["cpl"]), max(live_, key=lambda c: c["cpl"])
        if worst["cpl"] > 1.3 * best["cpl"]:
            shift = max(1, round(worst["daily_budget"] * 0.3))
            gain = shift * 7 / best["cpl"] - shift * 7 / worst["cpl"]
            moves[worst["id"]] = {"type": "move_budget", "label": f"Move {money(shift)}/day to “{best['name']}”",
                                  "from": worst["id"], "to": best["id"], "amount": shift,
                                  "gain": max(1, round(gain)), "best": best}

    # 3. Campaigns: the biggest issue becomes the card, the rest become notes.
    for c in camp.values():
        cid, pid, name = c["id"], c["product_id"], c["name"]
        if c["status"] == "draft":
            if now - datetime.fromisoformat(c["created_at"]) > timedelta(days=3):
                out.append(rec(f"draft:{cid}", "low", f"Launch or delete the draft “{name}”", "It's been a draft for over 3 days.",
                               {"type": "open", "label": "Open campaign", "to": f"/app/ads/{c['platform']}"},
                               campaign_id=cid, product_id=pid, group="tidy"))
            continue
        if c["status"] != "active":
            continue
        t, spend, leads, clicks = c["target_cpl"], c["period_spend"], c["leads"], c["period_clicks"]
        weekly = money(spend / days * 7)
        found = []  # (rec, note text)
        if c["platform"] == "other" and not clicks and not leads and spend > 0:
            found.append((rec(f"track:{cid}", "medium", f"Track the leads from “{name}”",
                              f"{money(spend)} spent and no leads linked to it yet. Put its tracking link or a QR code in the ad, "
                              "and set the lead's campaign when people say how they heard of you.",
                              {"type": "ack", "label": "Got it"}, campaign_id=cid, product_id=pid, group="tidy"), None))
        elif not leads and spend > 0 and (clicks >= 30 or (t and spend >= 3 * t)):
            found.append((rec(f"pause:{cid}", "high", f"Pause “{name}”: {money(spend)} spent, no leads",
                              f"{clicks} clicks and {money(spend)} in {days} days without a single lead.",
                              {"type": "pause_campaign", "label": "Pause campaign"}, impact=f"Save about {weekly}/week",
                              campaign_id=cid, product_id=pid), None))
        elif leads and t and c["cpl"] > 1.5 * t and spend >= 2 * t:
            mv = moves.pop(cid, None)
            alt = {k: v for k, v in mv.items() if k not in ("gain", "best")} if mv else None
            found.append((rec(f"fix:{cid}", "high", f"“{name}” costs {money(c['cpl'])} per lead",
                              f"That's {round(c['cpl'] / t, 1)}× the {money(t)} target."
                              + (f" “{mv['best']['name']}” gets them for {money(mv['best']['cpl'])}." if mv else ""),
                              {"type": "pause_campaign", "label": "Pause campaign"}, alt=alt,
                              impact=(f"≈ +{mv['gain']} leads/week by moving budget" if mv else f"Save about {weekly}/week"),
                              campaign_id=cid, product_id=pid), None))
        elif leads >= 3 and t and c["cpl"] <= 0.7 * t and c["daily_budget"] > 0 and pid not in over_pace:
            new = round(c["daily_budget"] * 1.2)
            extra = (new - c["daily_budget"]) * 7 / c["cpl"]
            found.append((rec(f"scale:{cid}", "medium", f"Scale “{name}”: your cheapest leads",
                              f"{money(c['cpl'])} per lead vs a {money(t)} target. Raise the daily budget {money(c['daily_budget'])} → {money(new)}.",
                              {"type": "scale_budget", "label": f"Raise to {money(new)}/day", "daily_budget": new},
                              impact=f"≈ +{max(1, round(extra))} leads/week", campaign_id=cid, product_id=pid, group="grow"), None))
        if c["period_impressions"] >= 2000 and c["ctr"] is not None and c["ctr"] < 0.8:
            found.append((rec(f"creative:{cid}", "medium", f"Refresh the ad creative for “{name}”",
                              f"Only {c['ctr']}% of people who saw it clicked (good is above 1%).",
                              {"type": "open", "label": "Make new creatives", "to": "/app/images"}, impact="More clicks for the same spend",
                              campaign_id=cid, product_id=pid, group="grow"),
                          f"Only {c['ctr']}% click the ad: refresh the creative."))
        if clicks >= 50 and c["conv"] is not None and c["conv"] < 2:
            found.append((rec(f"page:{cid}", "medium", f"The landing page behind “{name}” converts {c['conv']}%",
                              f"{clicks} clicks turned into {leads} lead{'s' if leads != 1 else ''}. Shorten the form or sharpen the offer.",
                              {"type": "open", "label": "Improve the page", "to": "/app/websites"}, impact="Same clicks, more leads",
                              campaign_id=cid, product_id=pid, group="grow"),
                          f"The page converts {c['conv']}% of clicks: shorten the form or sharpen the offer."))
        if found:
            found.sort(key=lambda x: PRIORITY_ORDER[x[0]["priority"]])
            main = found[0][0]
            main["notes"] = [note for r, note in found[1:] if note]
            out.append(main)

    # Moves not already offered on a "fix" card.
    for wid, mv in moves.items():
        w = camp[wid]
        out.append(rec(f"move:{wid}:{mv['to']}", "medium", f"Move {money(mv['amount'])}/day from “{w['name']}” to “{mv['best']['name']}”",
                       f"Both sell the same product: {money(w['cpl'])} vs {money(mv['best']['cpl'])} per lead. Same total budget, cheaper leads.",
                       {k: v for k, v in mv.items() if k not in ("gain", "best")} | {"label": "Move the budget"},
                       impact=f"≈ +{mv['gain']} leads/week", product_id=w["product_id"], group="grow"))

    # 4. Products: pacing, profit and coverage.
    for p in ctx["products"]:
        if p["status"] != "active":
            continue
        if p["id"] in over_pace:
            ratio = p["monthly_budget"] / p["month_projection"]
            out.append(rec(f"pace:{p['id']}:{now:%Y-%m}", "high", f"“{p['name']}” is on pace to overspend",
                           f"Projected {money(p['month_projection'])} this month against a {money(p['monthly_budget'])} budget.",
                           {"type": "trim_budgets", "label": f"Trim its daily budgets {round((1 - ratio) * 100)}%", "product_id": p["id"], "ratio": round(ratio, 3)},
                           impact=f"Stay within {money(p['monthly_budget'])}", product_id=p["id"]))
        if p["spend"] > 0 and p["won"] and p["roas"] is not None and p["roas"] < 1:
            out.append(rec(f"roas:{p['id']}", "high", f"“{p['name']}” is losing money on ads",
                           f"{money(p['revenue'])} won from {money(p['spend'])} spent (return {p['roas']}×).",
                           {"type": "scroll", "label": "Review its campaigns", "to": f"#product-{p['id']}"}, product_id=p["id"]))
        if not p["campaigns"]:
            out.append(rec(f"advertise:{p['id']}", "medium", f"Start advertising “{p['name']}”", "No campaign is selling it yet.",
                           {"type": "open", "label": "Create a campaign", "to": "/app/ads/meta"}, product_id=p["id"], group="grow"))
        if not p["pages"]:
            out.append(rec(f"landing:{p['id']}", "medium", f"Give “{p['name']}” its own landing page",
                           "A focused page converts better than a generic one, and lets AIMVA credit leads to the right campaign.",
                           {"type": "open", "label": "Create a page", "to": "/app/websites"}, product_id=p["id"], group="grow"))

    # 5. Follow-ups and housekeeping.
    stale = [l for l in ctx["leads"] if l.stage == "contacted" and now - l.created_at > timedelta(days=7)]
    if stale:
        out.append(rec(f"followup:{now.date()}", "medium", f"Follow up {len(stale)} lead{'s' if len(stale) > 1 else ''} waiting over a week",
                       "They were contacted but haven't moved on. A WhatsApp nudge revives many of them.",
                       {"type": "open", "label": "Open these leads", "to": "/app/leads?stage=contacted"}, group="leads"))
    loose = ctx["unassigned"]["campaigns"]
    if loose and ctx["raw_products"]:
        out.append(rec("link:campaigns", "low", f"Link {len(loose)} campaign{'s' if len(loose) > 1 else ''} to a product",
                       "So their spend and leads count towards the right product.",
                       {"type": "scroll", "label": "Show them", "to": "#campaigns"}, group="tidy"))
    # Hide what the user snoozed, dismissed or recently acted on.
    hidden = {d.key for d in db.scalars(select(Decision).where(Decision.user_id == user.id, Decision.until > now))}
    return sorted([r for r in out if r["key"] not in hidden], key=lambda r: PRIORITY_ORDER[r["priority"]])


def plan(ctx: dict) -> dict:
    """The next 7 days at the current pace."""
    k, d = ctx["kpis"], ctx["days"]
    leads_week = round(k["leads"] / d * 7, 1)
    spend_week = round(k["spend"] / d * 7, 2)
    budget_week = round(sum(c["daily_budget"] for c in ctx["campaigns"].values() if c["status"] == "active") * 7, 2)
    return {"leads_next_7": leads_week, "spend_next_7": spend_week, "planned_budget_7": budget_week,
            "cpl_next_7": round(spend_week / leads_week, 2) if leads_week else None}


def summary(ctx: dict, recs: list) -> str:
    k, d = ctx["kpis"], ctx["days"]
    if not ctx["raw_campaigns"] and not k["leads"]:
        return "No campaigns or leads yet. Add what you sell, then launch a campaign and a landing page for it."
    parts = [f"In the last {d} days you got {k['leads']} lead{'s' if k['leads'] != 1 else ''}"]
    if k["leads_change"] is not None:
        parts[-1] += f" ({'+' if k['leads_change'] >= 0 else ''}{k['leads_change']}% vs the period before)"
    if k["spend"]:
        parts.append(f"spent {money(k['spend'])}" + (f" at {money(k['cpl'])} a lead" if k["cpl"] else ""))
    best = min((c for c in ctx["campaigns"].values() if c["cpl"]), key=lambda c: c["cpl"], default=None)
    if best:
        parts.append(f"“{best['name']}” brings the cheapest leads")
    text = ", ".join(parts) + "."
    if recs:
        text += f" Top priority: {recs[0]['title'].rstrip('.')}."
    return text


def _public(ctx: dict) -> dict:
    return {k: v for k, v in ctx.items() if k in ("days", "kpis", "products", "unassigned", "account_cpl")}


@router.get("/api/command/overview")
def overview(days: int = Query(30, ge=7, le=90), user: User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = compute(db, user, days)
    recs = recommendations(db, user, ctx)
    log = [{"id": d.id, "title": d.title, "decision": d.decision, "result": d.result, "note": d.note, "at": d.created_at.isoformat()}
           for d in db.scalars(select(Decision).where(Decision.user_id == user.id).order_by(Decision.created_at.desc()).limit(20))]
    return {**_public(ctx), "recommendations": recs, "plan": plan(ctx), "summary": summary(ctx, recs), "decisions": log}


@router.get("/api/command/brief")
def ai_brief(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """An optional AI-written weekly brief over the same numbers (falls back to the rule-based summary)."""
    rate_limit(f"brief:{user.id}", 10, 600)
    ctx = compute(db, user, 7)
    recs = recommendations(db, user, ctx)
    base = summary(ctx, recs)
    write = writer(db, user.id, agent="analyst")
    if not write:
        return {"source": "rules", "text": base}
    facts = {"kpis": ctx["kpis"], "products": [{k: p[k] for k in ("name", "leads", "spend", "cpl", "won", "revenue", "roas")} for p in ctx["products"]],
             "campaigns": [{k: c[k] for k in ("name", "platform", "status", "period_spend", "leads", "cpl", "ctr", "health")} for c in ctx["campaigns"].values()],
             "next_steps": [r["title"] for r in recs[:5]]}
    text = write("You are a calm, practical marketing advisor for a small business. In under 120 words, using only these numbers "
                 f"(currency {CUR}), say how the week went and what to do next, in plain language. No preamble.\n{facts}", max_tokens=400)
    return {"source": "ai", "text": text.strip()} if text else {"source": "rules", "text": base}


class DecideIn(BaseModel):
    decision: Literal["accepted", "snoozed", "dismissed"]
    note: str = Field("", max_length=500)
    alt: bool = False  # accept the card's alternative action instead (e.g. move budget instead of pausing)


def _camp(db: Session, user: User, cid) -> Campaign:
    c = db.get(Campaign, int(cid)) if str(cid).isdigit() else None
    if not c or c.user_id != user.id:
        raise HTTPException(404, "That campaign no longer exists.")
    return c


def execute(db: Session, user: User, r: dict) -> str:
    """Run a recommendation's action. Only safe, reversible changes run here; everything else opens a page."""
    a = r["action"]
    t = a["type"]
    if t == "pause_campaign":
        c = _camp(db, user, r["campaign_id"])
        update_campaign(c.id, CampaignPatch(status="paused"), user, db)
        return f"Paused “{c.name}”. You can resume it any time."
    if t == "scale_budget":
        c = _camp(db, user, r["campaign_id"])
        old = c.daily_budget
        update_campaign(c.id, CampaignPatch(daily_budget=float(a["daily_budget"])), user, db)
        return f"“{c.name}” daily budget {money(old)} → {money(a['daily_budget'])}."
    if t == "move_budget":
        src, dst = _camp(db, user, a["from"]), _camp(db, user, a["to"])
        amount = min(float(a["amount"]), src.daily_budget)
        update_campaign(src.id, CampaignPatch(daily_budget=round(src.daily_budget - amount, 2)), user, db)
        update_campaign(dst.id, CampaignPatch(daily_budget=round(dst.daily_budget + amount, 2)), user, db)
        return f"Moved {money(amount)}/day from “{src.name}” to “{dst.name}”."
    if t == "trim_budgets":
        p = _product(db, user, a["product_id"])
        ratio = max(0.1, min(1.0, float(a["ratio"])))
        changed = 0
        for c in db.scalars(select(Campaign).where(Campaign.user_id == user.id, Campaign.product_id == p.id, Campaign.status == "active")):
            update_campaign(c.id, CampaignPatch(daily_budget=round(c.daily_budget * ratio, 2)), user, db)
            changed += 1
        return f"Trimmed {changed} daily budget{'s' if changed != 1 else ''} for “{p.name}” by {round((1 - ratio) * 100)}%."
    if t == "call_hot_leads":
        from .voice import place_phone_call
        agent = db.scalar(select(VoiceAgent).where(VoiceAgent.user_id == user.id).order_by(VoiceAgent.id))
        if not agent:
            raise HTTPException(400, "Create a voice agent first (Voice Agent page), then try again.")
        now = utcnow()
        hot = [l for l in db.scalars(select(Lead).where(Lead.user_id == user.id, Lead.stage == "new", Lead.score >= HOT)
                                     .order_by(Lead.score.desc())) if l.phone and now - l.created_at > timedelta(minutes=30)][:5]
        if not hot:
            raise HTTPException(400, "None of the hot leads has a phone number. Open them in Leads to reach them another way.")
        placed = 0
        for l in hot:
            place_phone_call(db, user, agent, l.phone, lead_id=l.id)  # raises a clear error if Twilio isn't connected
            l.stage = "contacted"
            placed += 1
        db.commit()
        return f"{agent.name} is calling {placed} hot lead{'s' if placed != 1 else ''}."
    return "Noted." if t == "ack" else "Opened."


@router.post("/api/command/recommendations/{key}/decide")
def decide(key: str, body: DecideIn, days: int = Query(30, ge=7, le=90), user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    rate_limit(f"decide:{user.id}", 60, 300)
    ctx = compute(db, user, days)
    r = next((x for x in recommendations(db, user, ctx) if x["key"] == key), None)
    if not r:
        raise HTTPException(404, "That suggestion is no longer current. Refresh to see the latest.")
    if body.alt:
        if not r.get("alt"):
            raise HTTPException(400, "That suggestion has no alternative action.")
        r = {**r, "action": r["alt"]}
    result = execute(db, user, r) if body.decision == "accepted" else ""
    hide = {"accepted": 7, "snoozed": 7, "dismissed": 30}[body.decision]
    d = Decision(user_id=user.id, key=key, title=r["title"], decision=body.decision, result=result, note=body.note.strip(),
                 until=utcnow() + timedelta(days=hide))
    db.add(d)
    db.commit()
    return {"ok": True, "result": result, "action": r["action"]}
