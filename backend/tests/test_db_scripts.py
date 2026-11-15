import pytest
"""scripts/db.py: the demo data must work through the real API (sign-in, roles, workspaces, approvals, public pages),
and unseed must remove all of it while leaving real accounts alone."""
from sqlalchemy import func, select

from app import models as M
from scripts import db as dbtool

from .conftest import make_client, signup_and_verify


@pytest.fixture(autouse=True)
def _agency_features_on(monkeypatch):
    """These tests cover the agency features (client role, approvals), which are off by default for release 1
    but kept in the code; turn them on here so they stay tested."""
    from app.config import settings
    monkeypatch.setattr(settings, "agency_features", True)

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
    assert len(leads if isinstance(leads, list) else leads["leads"]) == 55
    assert len(owner.get("/api/sites").json()) == 3

    editor = login("editor@aimva-demo.example.com")
    assert editor.post(f"/api/workspaces/{dental}/switch").status_code == 200
    assert editor.post(f"/api/workspaces/{coaching}/switch").status_code == 404  # not a member there

    client = login("client.dental@aimva-demo.example.com")
    client.post(f"/api/workspaces/{dental}/switch")
    assert client.get("/api/sites").status_code == 200
    lead_id = db.scalar(select(M.Lead.id).where(M.Lead.user_id == dental))
    assert client.patch(f"/api/leads/{lead_id}", json={"stage": "won"}).status_code == 403  # view-only
    pending = client.get("/api/approvals", params={"status": "pending"}).json()
    assert sorted(a["kind"] for a in pending) == ["campaign", "site"]

    solo = login("solo@aimva-demo.example.com")
    assert len(solo.get("/api/sites").json()) == 3
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
    assert removed == 7 + 3
    assert not dbtool.is_seeded(db)
    assert db.scalar(select(func.count()).select_from(M.User)) == 1
    for table in (M.Lead, M.Site, M.Campaign, M.CampaignStat, M.Membership, M.WaMessage, M.Call, M.SiteVersion, M.Invite,
                  M.Asset, M.WaScheduled, M.Decision, M.BrandKit):
        assert db.scalar(select(func.count()).select_from(table)) == 0, table.__tablename__
    seeded(db)  # can load again after removing


def test_every_screen_has_data_and_one_account_stays_empty(db):
    """Owner's own business, pictures that load, multilingual calls, 60 days of leads; empty@ has nothing."""
    from datetime import timedelta
    seeded(db)
    owner = login("owner@aimva-demo.example.com")
    own_id = owner.get("/api/auth/me").json()["user"]["id"]
    assert len(owner.get("/api/leads").json()) == 28 and len(owner.get("/api/sites").json()) == 3
    pics = owner.get("/api/content/assets?kind=image").json()
    assert len(pics) == 4 and owner.get(pics[0]["url"]).status_code == 200  # placeholder pictures are real files
    langs = {c.transcript[0].get("lang") for c in db.scalars(select(M.Call).where(M.Call.user_id == own_id))}
    assert "en-IN" in langs and len(langs) >= 2
    oldest = db.scalar(select(func.min(M.Lead.created_at)).where(M.Lead.user_id == own_id))
    assert M.utcnow() - oldest > timedelta(days=35)  # trends span about two months

    empty = login("empty@aimva-demo.example.com")
    assert empty.get("/api/leads").json() == [] and empty.get("/api/sites").json() == []
    assert empty.get("/api/content/assets?kind=image").json() == []
