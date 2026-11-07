"""scripts/db.py: the demo data must work through the real API (sign-in, roles, workspaces, approvals, public pages),
and unseed must remove all of it while leaving real accounts alone."""
from sqlalchemy import func, select

from app import models as M
from scripts import db as dbtool

from .conftest import make_client, signup_and_verify

PW = dbtool.DEFAULT_PASSWORD


def login(email):
    c = make_client()
    r = c.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return c


def seeded(db):
    summary = dbtool.load_demo(db, PW)
    return {name: wid for name, wid, _ in summary}


def test_seed_gives_every_role_working_access(db):
    ws = seeded(db)
    dental, realty, coaching = ws["Smile Dental Clinic"], ws["Greenleaf Realty"], ws["BrightPath Coaching"]

    owner = login("owner@aimva-demo.example.com")
    names = {w["name"] for w in owner.get("/api/workspaces").json()}
    assert {"Smile Dental Clinic", "Greenleaf Realty", "BrightPath Coaching"} <= names
    assert owner.post(f"/api/workspaces/{realty}/switch").status_code == 200
    leads = owner.get("/api/leads").json()
    assert len(leads if isinstance(leads, list) else leads["leads"]) == 24
    assert len(owner.get("/api/sites").json()) == 2

    editor = login("editor@aimva-demo.example.com")
    assert editor.post(f"/api/workspaces/{dental}/switch").status_code == 200
    assert editor.post(f"/api/workspaces/{coaching}/switch").status_code == 404  # not a member there

    client = login("client.dental@aimva-demo.example.com")
    client.post(f"/api/workspaces/{dental}/switch")
    assert client.get("/api/sites").status_code == 200
    lead_id = db.scalar(select(M.Lead.id).where(M.Lead.user_id == dental))
    assert client.patch(f"/api/leads/{lead_id}", json={"stage": "won"}).status_code == 403  # view-only
    pending = client.get("/api/approvals", params={"status": "pending"}).json()
    assert len(pending) == 1 and pending[0]["kind"] == "campaign"

    solo = login("solo@aimva-demo.example.com")
    assert len(solo.get("/api/sites").json()) == 2
    assert solo.get(f"/api/sites", headers={"X-AIMVA-Workspace": str(dental)}).status_code == 403


def test_seeded_pages_serve_and_the_approved_one_can_publish(db):
    ws = seeded(db)
    c = make_client()
    r = c.get("/s/demo-dental")  # a page view must not cancel the client's approval
    assert r.status_code == 200 and "Smile Dental Clinic" in r.text
    assert c.get("/s/demo-dental-draft").status_code == 404  # drafts aren't public
    assert c.get("/s/demo-solo").status_code == 200

    owner = login("owner@aimva-demo.example.com")
    owner.post(f"/api/workspaces/{ws['Smile Dental Clinic']}/switch")
    site = db.scalar(select(M.Site).where(M.Site.slug == "demo-dental"))
    r = owner.post(f"/api/sites/{site.id}/publish", json={"name": site.name, "slug": site.slug})
    assert r.status_code == 200, r.text  # the page still matches what the client approved
    draft = db.scalar(select(M.Site).where(M.Site.slug == "demo-dental-draft"))
    r = owner.post(f"/api/sites/{draft.id}/publish", json={"name": draft.name, "slug": draft.slug})
    assert r.status_code == 409  # never approved


def test_pending_invite_is_accepted_on_signup(db):
    ws = seeded(db)
    c = make_client()
    signup_and_verify(c, email="newhire@aimva-demo.example.com", name="New Hire")
    ids = {w["id"] for w in c.get("/api/workspaces").json()}
    assert ws["Greenleaf Realty"] in ids


def test_unseed_removes_only_demo_data(db):
    real = make_client()
    signup_and_verify(real, email="real@example.com", name="Real User")
    seeded(db)
    assert dbtool.is_seeded(db)
    removed = dbtool._unseed(db)
    db.commit()
    assert removed == 6 + 3
    assert not dbtool.is_seeded(db)
    assert db.scalar(select(func.count()).select_from(M.User)) == 1
    for table in (M.Lead, M.Site, M.Campaign, M.CampaignStat, M.Membership, M.WaMessage, M.Call, M.SiteVersion, M.Invite):
        assert db.scalar(select(func.count()).select_from(table)) == 0, table.__tablename__
    seeded(db)  # can load again after removing
