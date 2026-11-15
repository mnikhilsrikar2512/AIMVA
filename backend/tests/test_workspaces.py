"""Agency workspaces: separate data per client, switching, roles, invites, client view and approvals."""
import pytest
from sqlalchemy import select

from app.models import User

from .conftest import make_client, signup_and_verify
from .test_sites_leads import BRIEF


@pytest.fixture(autouse=True)
def _agency_features_on(monkeypatch):
    """These tests cover the agency features (client role, approvals), which are off by default for release 1
    but kept in the code; turn them on here so they stay tested."""
    from app.config import settings
    monkeypatch.setattr(settings, "agency_features", True)


def new_ws(c, name="SmileCare Dental"):
    r = c.post("/api/workspaces", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()


def test_each_client_has_its_own_data(auth_client):
    own_site = auth_client.post("/api/sites", json=BRIEF).json()
    ws = new_ws(auth_client)
    assert auth_client.post(f"/api/workspaces/{ws['id']}/switch").json()["active"]
    assert auth_client.get("/api/sites").json() == []  # nothing from the agency's own account
    clinic = auth_client.post("/api/sites", json={**BRIEF, "business": "SmileCare Dental"}).json()
    me = auth_client.get("/api/auth/me").json()
    assert me["user"]["email"] == "owner@example.com" and me["workspace"] == {"id": ws["id"], "name": "SmileCare Dental", "role": "owner"}
    auth_client.post(f"/api/workspaces/{me['user']['id']}/switch")
    assert [s["id"] for s in auth_client.get("/api/sites").json()] == [own_site["id"]]
    assert auth_client.get(f"/api/sites/{clinic['id']}").status_code == 404
    names = [w["name"] for w in auth_client.get("/api/workspaces").json()]
    assert names[1:] == ["SmileCare Dental"] and len(names) == 2


def test_strangers_cannot_switch_in_or_use_the_header(auth_client, other_client):
    ws = new_ws(auth_client)
    assert other_client.post(f"/api/workspaces/{ws['id']}/switch").status_code == 404
    r = other_client.get("/api/sites", headers={"X-AIMVA-Workspace": str(ws["id"])})
    assert r.status_code == 403
    other_client.cookies.set("aimva_ws", str(ws["id"]))
    assert other_client.get("/api/leads").status_code == 403


def test_workspaces_cannot_sign_in(auth_client, client, db):
    ws = new_ws(auth_client)
    email = db.get(User, ws["id"]).email
    assert client.post("/api/auth/login", json={"email": email, "password": "!"}).status_code in (401, 422)
    assert client.post("/api/auth/forgot-password", json={"email": email}).status_code in (200, 400, 422)


def test_invite_a_client_who_signs_up_later(auth_client, db):
    ws = new_ws(auth_client)
    r = auth_client.post(f"/api/workspaces/{ws['id']}/invites", json={"email": "Dr.Rao@smilecare.example", "role": "client"}).json()
    assert r["invited"] and auth_client.get(f"/api/workspaces/{ws['id']}/members").json()["invites"][0]["email"] == "dr.rao@smilecare.example"
    doc = make_client()
    signup_and_verify(doc, email="dr.rao@smilecare.example", name="Dr Rao")
    mine = doc.get("/api/workspaces").json()
    assert [(w["name"], w["role"]) for w in mine[1:]] == [("SmileCare Dental", "client")]


def test_existing_people_are_added_straight_away(auth_client, other_client):
    ws = new_ws(auth_client)
    r = auth_client.post(f"/api/workspaces/{ws['id']}/invites", json={"email": "intruder@example.com", "role": "editor"}).json()
    assert r["added"]
    assert auth_client.post(f"/api/workspaces/{ws['id']}/invites", json={"email": "intruder@example.com", "role": "editor"}).status_code == 409
    other_client.post(f"/api/workspaces/{ws['id']}/switch")
    assert other_client.post("/api/sites", json=BRIEF).status_code == 200  # editors do the work
    assert other_client.post(f"/api/workspaces/{ws['id']}/invites", json={"email": "x@example.com", "role": "admin"}).status_code == 403
    assert other_client.patch(f"/api/workspaces/{ws['id']}", json={"require_approval": True}).status_code == 403


@pytest.fixture
def agency_and_client(auth_client):
    ws = new_ws(auth_client)
    auth_client.post(f"/api/workspaces/{ws['id']}/invites", json={"email": "dr.rao@smilecare.example", "role": "client"})
    doc = make_client()
    signup_and_verify(doc, email="dr.rao@smilecare.example", name="Dr Rao")
    doc.get("/api/workspaces")
    doc.post(f"/api/workspaces/{ws['id']}/switch")
    auth_client.post(f"/api/workspaces/{ws['id']}/switch")
    return auth_client, doc, ws


def test_clients_see_everything_but_change_nothing(agency_and_client):
    agency, doc, ws = agency_and_client
    site = agency.post("/api/sites", json=BRIEF).json()
    assert [s["id"] for s in doc.get("/api/sites").json()] == [site["id"]]
    assert doc.get("/api/leads").status_code == 200 and doc.get("/api/analytics/overview").status_code == 200
    assert doc.post("/api/sites", json=BRIEF).status_code == 403
    assert doc.delete(f"/api/sites/{site['id']}").status_code == 403
    assert doc.patch(f"/api/sites/{site['id']}", json={"name": "Hacked"}).status_code == 403
    assert doc.get("/api/integrations").status_code == 403  # connected accounts stay with the agency
    assert doc.get("/api/billing").status_code == 403


def test_approval_gates_publishing(agency_and_client):
    agency, doc, ws = agency_and_client
    agency.patch(f"/api/workspaces/{ws['id']}", json={"require_approval": True})
    site = agency.post("/api/sites", json=BRIEF).json()
    r = agency.post(f"/api/sites/{site['id']}/deploy", json={"target": "aimva"})
    assert r.status_code == 409 and "approval" in r.json()["detail"]
    assert agency.patch(f"/api/sites/{site['id']}", json={"published": True}).status_code == 409
    a = agency.post("/api/approvals", json={"kind": "site", "ref_id": site["id"], "note": "Hero photo is a placeholder"}).json()
    assert a["status"] == "pending" and a["title"] == site["name"]
    assert doc.post("/api/approvals", json={"kind": "site", "ref_id": site["id"]}).status_code == 403
    assert doc.post(f"/api/approvals/{a['id']}/decide", json={"decision": "changes"}).status_code == 400
    d = doc.post(f"/api/approvals/{a['id']}/decide", json={"decision": "changes", "comment": "Use our clinic photo"}).json()
    assert d["status"] == "changes"
    assert agency.post(f"/api/sites/{site['id']}/deploy", json={"target": "aimva"}).status_code == 409
    a2 = agency.post("/api/approvals", json={"kind": "site", "ref_id": site["id"]}).json()
    assert doc.post(f"/api/approvals/{a2['id']}/decide", json={"decision": "approved"}).json()["status"] == "approved"
    assert doc.post(f"/api/approvals/{a2['id']}/decide", json={"decision": "approved"}).status_code == 409
    assert agency.post(f"/api/sites/{site['id']}/deploy", json={"target": "aimva"}).json()["published"]


def _approve(agency, doc, kind, ref_id):
    a = agency.post("/api/approvals", json={"kind": kind, "ref_id": ref_id}).json()
    assert doc.post(f"/api/approvals/{a['id']}/decide", json={"decision": "approved"}).json()["status"] == "approved"


def test_edits_after_approval_need_a_new_one(agency_and_client):
    agency, doc, ws = agency_and_client
    agency.patch(f"/api/workspaces/{ws['id']}", json={"require_approval": True})
    site = agency.post("/api/sites", json=BRIEF).json()
    _approve(agency, doc, "site", site["id"])
    agency.patch(f"/api/sites/{site['id']}", json={"html": site["html"] + "<p>new price</p>"})
    assert agency.post(f"/api/sites/{site['id']}/deploy", json={"target": "aimva"}).status_code == 409


def test_visits_and_publishing_dont_undo_an_approval(agency_and_client, client):
    agency, doc, ws = agency_and_client
    agency.patch(f"/api/workspaces/{ws['id']}", json={"require_approval": True})
    site = agency.post("/api/sites", json=BRIEF).json()
    _approve(agency, doc, "site", site["id"])
    r = agency.post(f"/api/sites/{site['id']}/publish", json={"name": site["name"], "slug": site["slug"] + "-x",
                                                             "seo_title": "Invisalign in Pune"})
    assert r.status_code == 200, r.text  # moving the address and adding SEO tags is part of the approved launch
    slug = site["slug"] + "-x"
    for _ in range(3):
        assert client.get(f"/s/{slug}").status_code == 200  # page views aren't edits
    assert agency.post(f"/api/sites/{site['id']}/deploy", json={"target": "aimva"}).status_code == 200
    assert agency.post(f"/api/sites/{site['id']}/publish", json={"name": site["name"], "slug": slug}).status_code == 200
    assert agency.get("/api/sites").json()[0]["visits"] == 3


def test_campaign_edits_after_approval_need_a_new_one(agency_and_client):
    agency, doc, ws = agency_and_client
    agency.patch(f"/api/workspaces/{ws['id']}", json={"require_approval": True})
    c = agency.post("/api/campaigns", json={"platform": "meta", "name": "Invisalign leads", "daily_budget": 500}).json()
    _approve(agency, doc, "campaign", c["id"])
    agency.patch(f"/api/campaigns/{c['id']}", json={"daily_budget": 5000})
    assert agency.post(f"/api/campaigns/{c['id']}/publish").status_code == 409
    _approve(agency, doc, "campaign", c["id"])
    r = agency.post(f"/api/campaigns/{c['id']}/publish")
    assert r.status_code == 400 and "Meta" in r.json()["detail"]  # past the approval gate; no Meta account in tests


def test_campaigns_need_approval_too(agency_and_client, db):
    agency, doc, ws = agency_and_client
    agency.patch(f"/api/workspaces/{ws['id']}", json={"require_approval": True})
    c = agency.post("/api/campaigns", json={"platform": "meta", "name": "Invisalign leads", "daily_budget": 500}).json()
    r = agency.post(f"/api/campaigns/{c['id']}/publish")
    assert r.status_code == 409


def test_workspace_email_goes_to_its_people(agency_and_client, db, monkeypatch):
    from app import mailer
    agency, doc, ws = agency_and_client
    sent = []
    monkeypatch.setattr(mailer.settings, "smtp_user", "x")
    monkeypatch.setattr(mailer.settings, "smtp_password", "y")

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self, **k): pass
        def login(self, *a): pass
        def send_message(self, msg): sent.append(msg["To"])
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    assert mailer.send_email(db.get(User, ws["id"]).email, "Your week", "3 new leads")
    assert sorted(sent) == ["dr.rao@smilecare.example", "owner@example.com"]


def test_delete_a_client_workspace(auth_client, other_client):
    ws = new_ws(auth_client)
    auth_client.post(f"/api/workspaces/{ws['id']}/switch")
    auth_client.post("/api/sites", json=BRIEF)
    assert auth_client.request("DELETE", f"/api/workspaces/{ws['id']}", json={"confirm_name": "wrong"}).status_code == 400
    assert other_client.request("DELETE", f"/api/workspaces/{ws['id']}", json={"confirm_name": "SmileCare Dental"}).status_code == 404
    assert auth_client.request("DELETE", f"/api/workspaces/{ws['id']}", json={"confirm_name": "smilecare dental"}).json()["ok"]
    assert len(auth_client.get("/api/workspaces").json()) == 1
    assert auth_client.get("/api/sites").status_code == 200  # back on the own account


def test_admin_pages_still_work_inside_a_workspace(auth_client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "admin_emails", {"owner@example.com"})
    ws = new_ws(auth_client)
    auth_client.post(f"/api/workspaces/{ws['id']}/switch")
    assert auth_client.get("/api/admin/metrics").status_code == 200


def test_a_client_with_an_empty_own_account_lands_in_their_workspace(auth_client):
    from .conftest import PASSWORD
    ws = new_ws(auth_client)
    auth_client.post(f"/api/workspaces/{ws['id']}/invites", json={"email": "dr.rao@smilecare.example", "role": "client"})
    doc = make_client()
    signup_and_verify(doc, email="dr.rao@smilecare.example", name="Dr Rao")
    doc.post("/api/auth/logout")
    doc.cookies.clear()
    r = doc.post("/api/auth/login", json={"email": "dr.rao@smilecare.example", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["workspace"] == {"id": ws["id"], "name": "SmileCare Dental", "role": "client"}
    assert doc.get("/api/auth/me").json()["workspace"]["id"] == ws["id"]
    # Once they have something of their own, or have picked a workspace, sign-in leaves them where they are.
    doc.post(f"/api/workspaces/{doc.get('/api/auth/me').json()['user']['id']}/switch")
    assert "workspace" not in doc.post("/api/auth/login", json={"email": "dr.rao@smilecare.example", "password": PASSWORD}).json()
    doc.post("/api/auth/logout"); doc.cookies.clear()
    assert doc.post("/api/leads", json={"name": "Own lead"}).status_code == 401
    # The agency owner (owner of their own workspaces) is never moved.
    auth_client.post("/api/auth/logout"); auth_client.cookies.clear()
    assert "workspace" not in auth_client.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).json()


def test_profile_in_a_client_workspace_keeps_the_person(auth_client):
    ws = new_ws(auth_client)
    auth_client.post(f"/api/workspaces/{ws['id']}/switch")
    r = auth_client.patch("/api/auth/profile", json={"name": "Priya", "company": "SmileCare Dental Clinic"}).json()
    assert r["user"]["email"] == "owner@example.com" and r["user"]["name"] == "Priya"
    assert r["workspace"] == {"id": ws["id"], "name": "SmileCare Dental Clinic", "role": "owner"}
    me = auth_client.get("/api/auth/me").json()
    assert me["user"]["name"] == "Priya" and me["workspace"]["name"] == "SmileCare Dental Clinic"
    # A client can change their own name but not rename the agency's workspace.
    auth_client.post(f"/api/workspaces/{ws['id']}/invites", json={"email": "dr.rao@smilecare.example", "role": "client"})
    doc = make_client()
    signup_and_verify(doc, email="dr.rao@smilecare.example", name="Dr Rao")
    doc.get("/api/workspaces")
    doc.post(f"/api/workspaces/{ws['id']}/switch")
    assert doc.patch("/api/auth/profile", json={"company": "Hijacked"}).status_code == 403
    r = doc.patch("/api/auth/profile", json={"name": "Dr Meera Rao", "company": "SmileCare Dental Clinic"})
    assert r.status_code == 200 and r.json()["user"]["name"] == "Dr Meera Rao"


def test_approval_status_drives_the_publish_button(agency_and_client):
    agency, doc, ws = agency_and_client
    site = agency.post("/api/sites", json=BRIEF).json()
    st = lambda who: who.get("/api/approvals/status", params={"kind": "site", "ref_id": site["id"]}).json()
    assert st(agency) == {"required": False, "state": "approved", "approval": None}  # approval off: Publish as usual
    agency.patch(f"/api/workspaces/{ws['id']}", json={"require_approval": True})
    assert st(agency)["state"] == "none"
    a = agency.post("/api/approvals", json={"kind": "site", "ref_id": site["id"], "note": "First draft"}).json()
    assert st(agency)["state"] == "pending" and st(doc)["state"] == "pending"
    doc.post(f"/api/approvals/{a['id']}/decide", json={"decision": "changes", "comment": "Use our clinic photo"})
    s = st(agency)
    assert s["state"] == "changes" and s["approval"]["comment"] == "Use our clinic photo"
    a2 = agency.post("/api/approvals", json={"kind": "site", "ref_id": site["id"]}).json()
    doc.post(f"/api/approvals/{a2['id']}/decide", json={"decision": "approved"})
    assert st(agency)["state"] == "approved"
    agency.patch(f"/api/sites/{site['id']}", json={"html": site["html"] + "<p>new price</p>"})
    assert st(agency)["state"] == "edited"  # changed after the client said yes: send it again
    assert agency.get("/api/approvals/status", params={"kind": "site", "ref_id": 999999}).status_code == 404


def test_client_sees_what_they_are_approving(agency_and_client):
    agency, doc, ws = agency_and_client
    agency.patch(f"/api/workspaces/{ws['id']}", json={"require_approval": True})
    site = agency.post("/api/sites", json=BRIEF).json()
    c = agency.post("/api/campaigns", json={"platform": "meta", "name": "Invisalign leads", "daily_budget": 500,
                                            "creative": {"headline": "Straight teeth, no braces", "text": "Book a free scan"}}).json()
    agency.post("/api/approvals", json={"kind": "site", "ref_id": site["id"]})
    agency.post("/api/approvals", json={"kind": "campaign", "ref_id": c["id"], "note": "Starts Monday"})
    rows = doc.get("/api/approvals", params={"status": "pending", "preview": True}).json()
    by = {r["kind"]: r for r in rows}
    assert by["campaign"]["preview"]["headline"] == "Straight teeth, no braces" and by["campaign"]["preview"]["daily_budget"] == 500
    assert by["campaign"]["note"] == "Starts Monday" and by["campaign"]["requested_by"]
    assert by["site"]["preview"]["preview_url"] == f"/api/sites/{site['id']}/preview"
    assert doc.get(by["site"]["preview"]["preview_url"]).status_code == 200  # the client can open the draft
    assert "preview" not in doc.get("/api/approvals").json()[0]  # plain list stays as it was
