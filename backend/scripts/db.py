"""Database tools for AIMVA: check the connection, apply migrations, load demo data, wipe and rebuild.

Run from the backend folder, with the same .env the app uses (DATABASE_URL picks the database):

    .venv/bin/python scripts/db.py check                 # can we connect? is the schema up to date?
    .venv/bin/python scripts/db.py migrate               # apply Alembic migrations (alembic upgrade head)
    .venv/bin/python scripts/db.py seed                  # demo agency, client workspaces, people in every role, data
    .venv/bin/python scripts/db.py unseed                # remove only the demo data
    .venv/bin/python scripts/db.py reset --confirm NAME  # drop EVERY table, migrate, (and --seed)

Full guide: docs/DATABASE.md. Nothing here touches app/ or migrations/: the schema comes from the Alembic migrations.
"""
import argparse
import os
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from sqlalchemy import MetaData, func, inspect, select, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import IS_SQLITE, Base, SessionLocal, engine, migrate  # noqa: E402
from app import models as M  # noqa: E402
from app.security import hash_password  # noqa: E402

DEMO_DOMAIN = "aimva-demo.example.com"  # example.com is reserved (RFC 2606): no real inbox, but sign-in accepts it
WORKSPACE_DOMAIN = "workspaces.aimva.invalid"  # same as app/workspaces.py
DEFAULT_PASSWORD = "Demo-pass-2026!"
LOCAL_HOSTS = {None, "", "localhost", "127.0.0.1", "::1", "db", "postgres"}


# ---- helpers ------------------------------------------------------------------------------------------------
def describe_url() -> str:
    url = make_url(settings.database_url)
    return url.render_as_string(hide_password=True)


def db_name() -> str:
    url = make_url(settings.database_url)
    return Path(url.database or "").name if IS_SQLITE else (url.database or "")


def is_local() -> bool:
    return IS_SQLITE or make_url(settings.database_url).host in LOCAL_HOSTS


def alembic_heads() -> tuple:
    """(revision in the database or None, newest revision in migrations/)."""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    return current, head


def refuse_in_production(what: str, allow: bool) -> None:
    if settings.is_production and not allow:
        sys.exit(f"Refusing to {what}: ENVIRONMENT=production. This is for test databases only.")


def ok(msg):
    print(f"  OK    {msg}")


def bad(msg):
    print(f"  FAIL  {msg}")


def warn(msg):
    print(f"  WARN  {msg}")


# ---- check --------------------------------------------------------------------------------------------------
def cmd_check(args) -> int:
    """Exit 0 when the database is reachable and fully migrated, 1 otherwise. Safe to run anytime (read-only)."""
    print(f"Database: {describe_url()}")
    failures = 0
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            version = conn.execute(text("SELECT sqlite_version()" if IS_SQLITE else "SHOW server_version")).scalar()
        ok(f"connected ({'SQLite' if IS_SQLITE else 'PostgreSQL'} {version})")
    except Exception as e:  # noqa: BLE001  (show the driver's own words: wrong password, host, SSL...)
        bad(f"cannot connect: {str(e).splitlines()[0]}")
        print("\nCheck DATABASE_URL in backend/.env, that the server is running, and the user/password/database name.")
        return 1

    if IS_SQLITE:
        warn("this is SQLite (the local default). Production runs on Postgres: set DATABASE_URL to test against it.")
    elif version and int(str(version).split(".")[0]) < 14:
        warn(f"PostgreSQL {version} is old; AIMVA is tested on 16.")

    current, head = alembic_heads()
    if current is None:
        bad(f"no migrations applied yet (newest is {head}). Run: scripts/db.py migrate")
        failures += 1
    elif current != head:
        bad(f"schema is at {current}, newest is {head}. Run: scripts/db.py migrate")
        failures += 1
    else:
        ok(f"migrations applied (at {head})")

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    missing_tables = [t.name for t in Base.metadata.sorted_tables if t.name not in tables]
    missing_cols = []
    for t in Base.metadata.sorted_tables:
        if t.name in tables:
            have = {c["name"] for c in insp.get_columns(t.name)}
            missing_cols += [f"{t.name}.{c.name}" for c in t.columns if c.name not in have]
    if current is not None:
        if missing_tables or missing_cols:
            bad("database doesn't match the app's models: missing " + ", ".join(missing_tables + missing_cols))
            failures += 1
        else:
            ok(f"all {len(Base.metadata.sorted_tables)} tables and their columns are present")

    if current is not None and not missing_tables:
        with engine.connect() as conn:
            counts = {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                      for t in ("users", "memberships", "sites", "campaigns", "leads")}
            demo = conn.execute(text("SELECT COUNT(*) FROM users WHERE email LIKE :p"), {"p": f"%@{DEMO_DOMAIN}"}).scalar()
        ok("rows: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        print(f"  INFO  demo data {'is loaded' if demo else 'is not loaded (scripts/db.py seed)'}")
        if not IS_SQLITE:
            with engine.begin() as conn:  # can this user write? (rolled back: nothing is kept)
                try:
                    conn.execute(text("CREATE TEMP TABLE aimva_write_check (x int)"))
                    ok("this database user can write")
                except Exception as e:  # noqa: BLE001
                    bad(f"this database user can't write: {str(e).splitlines()[0]}")
                    failures += 1

    print("\nReady for testing." if not failures else f"\n{failures} problem(s) above.")
    return 1 if failures else 0


# ---- migrate ------------------------------------------------------------------------------------------------
def cmd_migrate(args) -> int:
    print(f"Database: {describe_url()}")
    before, head = alembic_heads()
    migrate()  # the app's own path: advisory lock on Postgres, adopts a pre-Alembic database, upgrade head
    after, _ = alembic_heads()
    print(f"Migrations: {before or 'empty database'} -> {after}" if before != after else f"Already at {after}, nothing to do.")
    return 0 if after == head else 1


# ---- seed ---------------------------------------------------------------------------------------------------
def demo_email(local: str) -> str:
    return f"{local}@{DEMO_DOMAIN}"


def is_seeded(db) -> bool:
    return db.scalar(select(M.User.id).where(M.User.email == demo_email("owner"))) is not None


PEOPLE = [
    # key, name, company, industry
    ("owner", "Priya Sharma", "Brightline Digital", "services"),      # agency owner
    ("admin", "Rahul Verma", "Brightline Digital", "services"),       # agency admin
    ("editor", "Sneha Iyer", "Brightline Digital", "services"),       # agency editor
    ("client.dental", "Dr. Arjun Mehta", "Smile Dental Clinic", "healthcare"),  # client (view + approve)
    ("client.realty", "Kavya Reddy", "Greenleaf Realty", "real_estate"),        # client
    ("solo", "Imran Khan", "Khan's Fitness Studio", "services"),       # small business, no agency
]

WORKSPACES = [
    {
        "key": "dental", "company": "Smile Dental Clinic", "industry": "healthcare", "require_approval": True,
        "colors": ["#0E7490", "#F59E0B"], "audience": "Families and working adults in Hyderabad",
        "products": [("Teeth whitening", "service", 6500, 250), ("Dental implants", "service", 45000, 900)],
        "offer": "Free consultation this month", "cta": "Book a free check-up",
        "features": ["Painless treatment", "Open on Sundays", "EMI available"],
        "members": [("admin", "admin"), ("editor", "editor"), ("client.dental", "client")],
        "lead_count": 18,
    },
    {
        "key": "realty", "company": "Greenleaf Realty", "industry": "real_estate", "require_approval": False,
        "colors": ["#166534", "#CA8A04"], "audience": "First-time home buyers, 28-45, Bengaluru",
        "products": [("2 BHK at Whitefield", "product", 8500000, 1200), ("3 BHK villas", "product", 21000000, 2500)],
        "offer": "Site visits every weekend", "cta": "Book a site visit",
        "features": ["RERA approved", "Near metro", "Bank loans pre-approved"],
        "members": [("admin", "admin"), ("editor", "editor"), ("client.realty", "client")],
        "lead_count": 24,
    },
    {
        "key": "coaching", "company": "BrightPath Coaching", "industry": "education", "require_approval": False,
        "colors": ["#4338CA", "#F97316"], "audience": "Class 11-12 students preparing for JEE, and their parents",
        "products": [("JEE 2027 batch", "service", 85000, 400)],
        "offer": "Free scholarship test", "cta": "Register for the test",
        "features": ["IIT faculty", "Small batches", "Weekly mock tests"],
        "members": [("admin", "admin")],
        "lead_count": 12,
    },
]

SOLO = {"key": "solo", "company": "Khan's Fitness Studio", "industry": "services", "colors": ["#B91C1C", "#111827"],
        "audience": "Working professionals in Pune, 25-40", "products": [("12-week transformation", "service", 18000, 300)],
        "offer": "First week free", "cta": "Claim your free week",
        "features": ["Certified trainers", "6 am batches", "Diet plans"], "lead_count": 10}

FIRST = ["Aarav", "Ananya", "Vikram", "Meera", "Rohan", "Isha", "Karthik", "Divya", "Siddharth", "Pooja", "Nikhil",
         "Lakshmi", "Aditya", "Fatima", "Harish", "Neha", "Suresh", "Tanvi", "Manoj", "Riya", "Deepak", "Sana"]
LAST = ["Patel", "Rao", "Nair", "Gupta", "Singh", "Menon", "Joshi", "Das", "Kulkarni", "Shetty", "Ali", "Bose"]
STAGES = ["new"] * 5 + ["contacted"] * 4 + ["qualified"] * 3 + ["won"] * 2 + ["lost"] * 2
MESSAGES = ["Please call me after 6 pm", "What is the price?", "Is this available on weekends?", "Interested, send details",
            "Can I get a callback in Hindi?", "Looking for something next month", ""]


def site_html(company: str, slug: str, ws: dict) -> str:
    """The real builder's no-AI template, so seeded pages look and behave like generated ones (working lead form)."""
    try:
        from app.routers.sites import Brief, template_html
        b = Brief(business=company, headline=ws["offer"], industry=ws["industry"], audience=ws["audience"][:160],
                  offer=ws["offer"], cta=ws["cta"], features=ws["features"], contact_mode="own_phone",
                  phone="+91 98765 43210", primary=ws["colors"][0], accent=ws["colors"][1], use_ai=False)
        return template_html(b, slug)
    except Exception:  # noqa: BLE001  (the builder changed shape: a plain page is still a valid test page)
        return f"<!doctype html><html><body><h1>{company}</h1><p>{ws['offer']}</p></body></html>"


def seed_business(db, rng, owner_id: int, ws: dict, now: datetime, person_ids: dict) -> dict:
    """Brand kit, products, a published and a draft site, campaigns with daily stats, leads with history, WhatsApp
    threads, a voice agent with calls, and a trial subscription, all owned by owner_id (a workspace or a person)."""
    company = ws["company"]
    db.add(M.BrandKit(user_id=owner_id, name=company, tagline=ws["offer"], colors=ws["colors"], voice="friendly",
                      style=["clean", "warm"], audience=ws["audience"]))
    products = []
    for name, kind, price, cpl in ws["products"]:
        p = M.Product(user_id=owner_id, name=name, kind=kind, price=price, target_cpl=cpl, monthly_budget=cpl * 60)
        db.add(p)
        products.append(p)
    db.flush()

    sites = []
    for i, published in enumerate((True, False)):
        slug = f"demo-{ws['key']}" + ("" if published else "-draft")
        created = now - timedelta(days=40 - i * 10)
        html = site_html(company, slug, ws)
        s = M.Site(user_id=owner_id, name=company + ("" if published else " (new offer)"), slug=slug,
                   brief={"business": company, "offer": ws["offer"], "cta": ws["cta"]}, html=html, published=published,
                   deploy_target="aimva", visits=rng.randint(300, 2500) if published else 0, product_id=products[0].id,
                   published_at=created + timedelta(hours=2) if published else None, created_at=created, updated_at=created)
        db.add(s)
        db.flush()
        db.add(M.SiteVersion(site_id=s.id, number=1, html=html, brief=s.brief, note="Seeded", generator="template",
                             created_at=created))
        sites.append(s)

    campaigns = []
    for platform, status, budget, days in (("meta", "active", 1500, 21), ("google", "paused", 2000, 14), ("linkedin", "draft", 3000, 0)):
        started = now - timedelta(days=days)
        c = M.Campaign(user_id=owner_id, platform=platform, name=f"{company} - {ws['offer']} ({platform.title()})",
                       objective="leads", daily_budget=budget, status=status, product_id=products[0].id,
                       creative={"headline": ws["offer"], "primary_text": f"{company}: {', '.join(ws['features'])}.",
                                 "cta": ws["cta"]},
                       targeting={"locations": ["IN"], "age_min": 25, "age_max": 55, "interests": [ws["industry"]]},
                       external_id=f"demo_{platform}_{uuid.uuid4().hex[:10]}" if status != "draft" else "",
                       started_on=started.date().isoformat() if days else None, created_at=started)
        db.add(c)
        db.flush()
        spend = impressions = clicks = 0
        for d in range(days):  # cumulative totals per day, like a platform sync writes them
            spend += round(budget * rng.uniform(0.7, 1.0), 2)
            impressions += rng.randint(1800, 5200)
            clicks += rng.randint(30, 140)
            db.add(M.CampaignStat(campaign_id=c.id, day=(started + timedelta(days=d)).date().isoformat(),
                                  spend=spend, impressions=impressions, clicks=clicks,
                                  source="meta" if platform == "meta" else "manual"))
        c.spend, c.impressions, c.clicks = spend, impressions, clicks
        campaigns.append(c)

    agent = M.VoiceAgent(user_id=owner_id, name=f"{company} assistant", language="en-IN",
                         greeting=f"Hi, this is the assistant from {company}. Is now a good time?",
                         instructions=f"Qualify the lead for {products[0].name}. Be brief and polite.",
                         questions=["What are you looking for?", "When would you like to start?", "What is your budget?"],
                         handoff_number="+919876543210")
    db.add(agent)
    db.flush()

    leads = []
    sources = [("website", sites[0].slug, None), ("meta", campaigns[0].external_id, campaigns[0].id),
               ("google", campaigns[1].external_id, campaigns[1].id), ("whatsapp", "", None), ("voice", "", None)]
    for i in range(ws["lead_count"]):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        source, ref, campaign_id = rng.choice(sources)
        stage = rng.choice(STAGES)
        created = now - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        product = rng.choice(products)
        value = product.price if stage == "won" else 0
        phone = f"+9198{rng.randint(10000000, 99999999)}"
        lead = M.Lead(user_id=owner_id, name=f"{first} {last}", phone=phone,
                      email=f"{first.lower()}.{last.lower()}{i}@example.com", message=rng.choice(MESSAGES),
                      source=source, source_ref=ref, score=rng.randint(20, 95), stage=stage, value=value,
                      product_id=product.id, campaign_id=campaign_id, created_at=created)
        db.add(lead)
        db.flush()
        kind = {"website": "form", "meta": "ad", "google": "ad"}.get(source, "created")
        db.add(M.LeadEvent(user_id=owner_id, lead_id=lead.id, kind=kind, title=f"New lead from {source}",
                           body=lead.message, created_at=created))
        if stage != "new":
            db.add(M.LeadEvent(user_id=owner_id, lead_id=lead.id, kind="stage", title=f"Moved to {stage}",
                               meta={"from": "new", "to": stage}, created_at=created + timedelta(hours=rng.randint(1, 48))))
        if stage == "won":
            db.add(M.LeadEvent(user_id=owner_id, lead_id=lead.id, kind="value", title=f"Sale value Rs {value:,.0f}",
                               meta={"value": value}, created_at=created + timedelta(days=2)))
        if i % 3 == 0:  # a WhatsApp thread on every third lead
            t = created + timedelta(minutes=1)
            db.add(M.WaMessage(user_id=owner_id, contact=phone, contact_name=lead.name, direction="out", status="simulated",
                               body=f"Hi {first}, thanks for your interest in {company}! When is a good time to talk?",
                               created_at=t))
            db.add(M.WaMessage(user_id=owner_id, contact=phone, contact_name=lead.name, direction="in", status="delivered",
                               body="Tomorrow 11 am works", created_at=t + timedelta(minutes=rng.randint(3, 90))))
        if source == "voice" or i % 5 == 0:
            db.add(M.Call(user_id=owner_id, agent_id=agent.id, lead_id=lead.id, channel="browser", status="completed",
                          sentiment=round(rng.uniform(-0.2, 0.8), 2),
                          transcript=[{"role": "agent", "text": agent.greeting, "sentiment": 0},
                                      {"role": "caller", "text": "Yes, tell me more.", "sentiment": 0.4}],
                          answers={"What are you looking for?": product.name}, created_at=created + timedelta(minutes=5)))
        leads.append(lead)

    db.add(M.Subscription(user_id=owner_id, plan="trial", status="trialing", period_start=now - timedelta(days=3),
                          period_end=now + timedelta(days=11), note="Seeded demo"))
    db.flush()
    return {"sites": sites, "campaigns": campaigns, "leads": leads}


def approved_fingerprint(kind: str, obj):
    """The fingerprint the app stores when a client approves (migration 0010); None on older code = status-only."""
    try:
        from app.workspaces import fingerprint
    except ImportError:
        return None
    return fingerprint(kind, obj)


def load_demo(db, password: str = DEFAULT_PASSWORD, random_seed: int = 42) -> list:
    """Add the demo agency, its client workspaces, people in every role and their data. Commits. Returns
    [(workspace name, id, lead count)]. Callers check the schema first (cmd_seed) or build it themselves (tests)."""
    rng = random.Random(random_seed)
    now = M.utcnow()
    pw = hash_password(password)  # argon2 is slow on purpose: hash once, share it
    people = {}
    for key, name, company, industry in PEOPLE:
        u = M.User(name=name, email=demo_email(key), password_hash=pw, company=company, industry=industry,
                   goal="more_leads", is_verified=True, onboarding_dismissed=True, kind="person",
                   created_at=now - timedelta(days=45))
        db.add(u)
        people[key] = u
    db.flush()
    ids = {k: u.id for k, u in people.items()}

    summary = []
    for ws in WORKSPACES:
        w = M.User(name=ws["company"], company=ws["company"], industry=ws["industry"], kind="workspace",
                   email=f"ws-{uuid.uuid4().hex}@{WORKSPACE_DOMAIN}", password_hash="!", is_verified=True,
                   require_approval=ws["require_approval"], onboarding_dismissed=True,
                   created_at=now - timedelta(days=45))
        db.add(w)
        db.flush()
        db.add(M.Membership(workspace_id=w.id, member_id=ids["owner"], role="owner"))
        for person, role in ws["members"]:
            db.add(M.Membership(workspace_id=w.id, member_id=ids[person], role=role))
        data = seed_business(db, rng, w.id, ws, now, ids)
        if ws["require_approval"]:
            site, draft_campaign = data["sites"][0], data["campaigns"][2]
            decided = site.updated_at + timedelta(minutes=30)
            db.add(M.Approval(workspace_id=w.id, kind="site", ref_id=site.id, title=site.name, status="approved",
                              content_hash=approved_fingerprint("site", site),  # the page as approved: edits re-ask
                              note="Please check the offer wording", comment="Looks good, go ahead",
                              requested_by=ids["editor"], decided_by=ids["client.dental"],
                              created_at=site.updated_at, decided_at=decided))
            db.add(M.Approval(workspace_id=w.id, kind="campaign", ref_id=draft_campaign.id, title=draft_campaign.name,
                              status="pending", note="New LinkedIn campaign, Rs 3,000/day", requested_by=ids["editor"],
                              created_at=now - timedelta(hours=5)))
        summary.append((ws["company"], w.id, len(data["leads"])))

    db.add(M.Invite(workspace_id=summary[1][1], email=demo_email("newhire"), role="editor", invited_by=ids["owner"],
                    expires_at=now + timedelta(days=14)))
    seed_business(db, rng, ids["solo"], SOLO, now, ids)
    db.add(M.Subscription(user_id=ids["owner"], plan="agency", status="active", processor="manual",
                          period_start=now - timedelta(days=10), period_end=now + timedelta(days=20), note="Seeded demo"))
    db.commit()
    return summary


def cmd_seed(args) -> int:
    refuse_in_production("seed demo data", args.allow_production)
    current, head = alembic_heads()
    if current != head:
        sys.exit(f"The schema is at {current or 'nothing'}, not {head}. Run: scripts/db.py migrate")
    db = SessionLocal()
    try:
        if is_seeded(db):
            if not args.fresh:
                print("Demo data is already loaded. Use --fresh to remove and load it again.")
                return 0
            _unseed(db)
        summary = load_demo(db, args.password, args.random_seed)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"Demo data loaded into {describe_url()}\n")
    print(f"Sign in with any of these (password: {args.password}):")
    roles = {"owner": "agency owner, owns all 3 client workspaces", "admin": "admin in all 3 workspaces",
             "editor": "editor in Smile Dental and Greenleaf", "client.dental": "client (view + approve) in Smile Dental",
             "client.realty": "client in Greenleaf Realty", "solo": "small business, own data, no agency"}
    for key, name, *_ in PEOPLE:
        print(f"  {demo_email(key):34} {name:18} {roles[key]}")
    print("\nClient workspaces:")
    for company, wid, n in summary:
        print(f"  {company:22} id {wid:<5} {n} leads")
    print(f"\nPending invite: {demo_email('newhire')} as editor in Greenleaf Realty (sign up with that email to accept).")
    print("Published demo pages: /s/demo-dental  /s/demo-realty  /s/demo-coaching  /s/demo-solo")
    return 0


# ---- unseed -------------------------------------------------------------------------------------------------
def _unseed(db) -> int:
    """Delete the demo people and the workspaces they own; ON DELETE CASCADE removes everything those rows own."""
    demo_ids = list(db.scalars(select(M.User.id).where(M.User.email.like(f"%@{DEMO_DOMAIN}"))))
    if not demo_ids:
        return 0
    owned = select(M.Membership.workspace_id).where(M.Membership.member_id.in_(demo_ids), M.Membership.role == "owner")
    ws_ids = list(db.scalars(select(M.User.id).where(M.User.kind == "workspace", M.User.id.in_(owned))))
    # A workspace someone outside the demo also belongs to is left alone (it isn't only demo data any more).
    shared = set(db.scalars(select(M.Membership.workspace_id).where(M.Membership.workspace_id.in_(ws_ids),
                                                                   M.Membership.member_id.not_in(demo_ids))))
    gone = [i for i in ws_ids if i not in shared] + demo_ids
    db.query(M.Invite).filter(M.Invite.email.like(f"%@{DEMO_DOMAIN}")).delete(synchronize_session=False)
    # Sites' site_versions and campaigns' campaign_stats cascade from their parents, which cascade from users.
    db.query(M.User).filter(M.User.id.in_(gone)).delete(synchronize_session=False)
    db.flush()
    if shared:
        warn(f"kept workspace(s) {sorted(shared)}: people outside the demo are members")
    return len(gone)


def cmd_unseed(args) -> int:
    refuse_in_production("remove demo data", args.allow_production)
    db = SessionLocal()
    try:
        n = _unseed(db)
        db.commit()
    finally:
        db.close()
    print(f"Removed {n} demo accounts and workspaces (and everything they owned)." if n else "No demo data found.")
    return 0


# ---- reset --------------------------------------------------------------------------------------------------
def cmd_reset(args) -> int:
    """Drop every table in the database (AIMVA's and anything else in it), then migrate from scratch."""
    refuse_in_production("reset the database", False)  # never, not even with a flag
    name = db_name()
    if args.confirm != name:
        sys.exit(f"This deletes ALL data in '{name}' at {describe_url()}.\n"
                 f"To go ahead, run again with: --confirm {name}")
    if not is_local() and not args.remote:
        sys.exit(f"'{name}' is on a remote server ({make_url(settings.database_url).host}). If it's a throwaway test "
                 "database, add --remote as well.")
    meta = MetaData()
    with engine.begin() as conn:
        meta.reflect(conn)
        if not IS_SQLITE:
            conn.exec_driver_sql("SELECT pg_advisory_xact_lock(727274)")  # don't race an app that's migrating
        meta.drop_all(conn)
    print(f"Dropped {len(meta.tables)} tables.")
    migrate()
    print(f"Migrated to {alembic_heads()[0]}.")
    if args.seed:
        args.fresh, args.allow_production = False, False
        return cmd_seed(args)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="scripts/db.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="connection, migrations and tables (read-only)")
    sub.add_parser("migrate", help="apply Alembic migrations")
    for name in ("seed", "reset"):
        s = sub.add_parser(name)
        s.add_argument("--password", default=os.getenv("DEMO_PASSWORD", DEFAULT_PASSWORD), help="password for the demo accounts")
        s.add_argument("--random-seed", type=int, default=42, help="same number = same demo data")
        if name == "seed":
            s.add_argument("--fresh", action="store_true", help="remove existing demo data first")
            s.add_argument("--allow-production", action="store_true", help="seed a staging server running ENVIRONMENT=production")
        else:
            s.add_argument("--confirm", default="", help="the database name, to prove you mean it")
            s.add_argument("--remote", action="store_true", help="allow a database that isn't on this machine / in docker")
            s.add_argument("--seed", action="store_true", help="load demo data afterwards")
    u = sub.add_parser("unseed", help="remove only the demo data")
    u.add_argument("--allow-production", action="store_true")
    args = p.parse_args(argv)
    if args.cmd == "seed" and len(args.password) < 8:
        sys.exit("--password must be at least 8 characters.")
    return {"check": cmd_check, "migrate": cmd_migrate, "seed": cmd_seed, "unseed": cmd_unseed, "reset": cmd_reset}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
