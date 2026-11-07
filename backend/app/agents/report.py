"""Weekly Report: every Monday, what happened last week and the next few things to do, in plain language."""
import html as H
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import Job, setting
from ..mailer import send_email
from ..models import Lead, User, utcnow


def build(db: Session, user: User) -> dict:
    from ..routers.command import CUR, compute, money, recommendations, summary
    ctx = compute(db, user, 7)
    recs = recommendations(db, user, ctx)
    since = utcnow() - timedelta(days=7)
    leads = db.scalar(select(func.count(Lead.id)).where(Lead.user_id == user.id, Lead.created_at >= since)) or 0
    won = db.scalar(select(func.count(Lead.id)).where(Lead.user_id == user.id, Lead.created_at >= since, Lead.stage == "won")) or 0
    k = ctx["kpis"]
    text = summary(ctx, recs)
    from ..routers.providers import writer
    write = writer(db, user.id, agent="analyst")
    if write:
        facts = {"leads_this_week": leads, "won": won, "kpis": k, "next_steps": [r["title"] for r in recs[:4]]}
        ai = write("You are a calm, practical marketing advisor for a small business. In under 110 words, using only these numbers "
                   f"(currency {CUR}), say how the week went and what to do next. No preamble.\n{facts}", max_tokens=350)
        if ai:
            text = ai.strip()
    return {"leads": leads, "won": won, "spend": money(k.get("spend", 0)), "cpl": money(k["cpl"]) if k.get("cpl") else "—",
            "summary": text, "next": [{"title": r["title"], "why": r["why"]} for r in recs[:4]]}


def run(db: Session, user: User, force: bool = False) -> dict:
    s = setting(db, user.id, "weekly_report")
    if not (s.enabled or force):
        return {"skipped": "The weekly report is off."}
    job = Job(db, user.id, "weekly_report", "Writing your weekly report")
    r = build(db, user)
    job.step(f"{r['leads']} new lead{'s' if r['leads'] != 1 else ''}, {r['spend']} spent, {r['cpl']} per lead")
    if (s.config or {}).get("email", True) and user.email:
        items = "".join(f"<li><b>{H.escape(n['title'])}</b><br><span style='color:#666'>{H.escape(n['why'])}</span></li>" for n in r["next"])
        html = (f"<div style='font-family:Arial,sans-serif;max-width:560px'><h2>Your week with AIMVA</h2>"
                f"<p><b>{r['leads']}</b> new leads · <b>{r['spend']}</b> spent · <b>{r['cpl']}</b> per lead</p>"
                f"<p>{H.escape(r['summary'])}</p>{f'<h3>Next steps</h3><ol>{items}</ol>' if items else ''}</div>")
        plain = f"{r['leads']} new leads, {r['spend']} spent, {r['cpl']} per lead.\n\n{r['summary']}\n\n" + "\n".join(f"- {n['title']}" for n in r["next"])
        if send_email(user.email, f"Your week: {r['leads']} new lead{'s' if r['leads'] != 1 else ''}", plain, html):
            job.step(f"Emailed to {user.email}")
        else:
            job.step("Not emailed: email sending isn't set up on this server", "skipped", "It's on your dashboard instead.")
    s.last_run_at = utcnow()
    job.finish(r, title=f"Weekly report: {r['leads']} new lead{'s' if r['leads'] != 1 else ''}, {r['spend']} spent")
    return r
