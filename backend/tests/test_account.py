"""Your data (DPDP): export everything as a ZIP, delete the account with its client workspaces, erase one lead."""
import io
import json
import zipfile

import httpx
from sqlalchemy import func, select

from app.brand import UPLOADS
from app.models import Call, Integration, Lead, Membership, Site, Subscription, User, VoiceAgent, WaMessage
from app.security import encrypt_json

from .conftest import PASSWORD, make_client, signup_and_verify
from .test_sites_leads import BRIEF


def _me(db, email="owner@example.com"):
    return db.scalar(select(User).where(User.email == email))


def _ws(c, name):
    r = c.post("/api/workspaces", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()


def _lead(c, **kw):
    kw.setdefault("email", f"{kw.get('name', 'priya').split()[0].lower()}@example.com")
    r = c.post("/api/leads", json={"name": "Priya", "phone": "9876543210", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _unzip(r):
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(r.content))


# ---- export ------------------------------------------------------------------------------------------------
def test_export_has_my_data_and_owned_workspaces_but_no_secrets(auth_client, db):
    _lead(auth_client)
    me = _me(db)
    db.add(Integration(user_id=me.id, provider="google", secret=encrypt_json({"refresh_token": "SECRET-REFRESH"})))
    db.commit()
    (UPLOADS / str(me.id)).mkdir(parents=True, exist_ok=True)
    (UPLOADS / str(me.id) / "logo.png").write_bytes(b"png-bytes")
    ws = _ws(auth_client, "Smile Dental")
    auth_client.post(f"/api/workspaces/{ws['id']}/switch")
    _lead(auth_client, name="Ravi", phone="9123456780")
    auth_client.post(f"/api/workspaces/{me.id}/switch")

    z = _unzip(auth_client.get("/api/account/export"))
    names = set(z.namelist())
    assert {"README.txt", "account.json", "my-account/data.json", "my-account/leads.csv", "my-account/files/logo.png"} <= names
    assert f"workspaces/smile-dental-{ws['id']}/leads.csv" in names
    profile = json.loads(z.read("account.json"))
    assert profile["email"] == "owner@example.com" and "password_hash" not in profile
    assert [w["name"] for w in profile["workspaces"]] == ["Smile Dental"]
    data = json.loads(z.read("my-account/data.json"))
    assert [l["name"] for l in data["leads"]] == ["Priya"]
    assert data["integrations"][0]["provider"] == "google" and "secret" not in data["integrations"][0]
    assert "Ravi" in z.read(f"workspaces/smile-dental-{ws['id']}/leads.csv").decode()
    assert "Ravi" not in z.read("my-account/leads.csv").decode()
    everything = b"".join(z.read(n) for n in names)
    assert b"SECRET-REFRESH" not in everything and b"argon2" not in everything
    assert z.read("my-account/files/logo.png") == b"png-bytes"


def test_export_includes_child_rows_like_page_versions(auth_client):
    auth_client.post("/api/sites", json=BRIEF)
    data = json.loads(_unzip(auth_client.get("/api/account/export")).read("my-account/data.json"))
    assert data["sites"] and all(v["site_id"] == data["sites"][0]["id"] for v in data.get("site_versions", []))


def test_export_never_includes_someone_elses_data(auth_client, other_client):
    _lead(other_client, name="Stranger Lead")
    z = _unzip(auth_client.get("/api/account/export"))
    assert b"Stranger Lead" not in b"".join(z.read(n) for n in z.namelist())


def test_export_needs_sign_in_and_is_rate_limited(client, auth_client):
    assert client.get("/api/account/export").status_code == 401
    for _ in range(5):
        assert auth_client.get("/api/account/export").status_code == 200
    assert auth_client.get("/api/account/export").status_code == 429


def test_a_view_only_client_can_export_and_delete_their_own_account(auth_client, db):
    ws = _ws(auth_client, "Smile Dental")
    doc = make_client()
    signup_and_verify(doc, email="dr.rao@example.com", name="Dr Rao")
    auth_client.post(f"/api/workspaces/{ws['id']}/invites", json={"email": "dr.rao@example.com", "role": "client"})
    doc.post(f"/api/workspaces/{ws['id']}/switch")
    z = _unzip(doc.get("/api/account/export"))
    assert not [n for n in z.namelist() if n.startswith("workspaces/")]  # clients don't own the agency's workspace
    r = doc.post("/api/account/delete", json={"password": PASSWORD, "confirm_email": "dr.rao@example.com"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(User, ws["id"]) is not None  # the workspace stays with the agency


# ---- delete ------------------------------------------------------------------------------------------------
def test_delete_needs_the_password_and_the_email_typed(auth_client, db):
    bad = auth_client.post("/api/account/delete", json={"password": "wrong-pass-1", "confirm_email": "owner@example.com"})
    assert bad.status_code == 400
    bad = auth_client.post("/api/account/delete", json={"password": PASSWORD, "confirm_email": "someone@example.com"})
    assert bad.status_code == 400 and "email" in bad.json()["detail"]
    assert _me(db) is not None


def test_delete_removes_everything_and_signs_out(auth_client, client, db):
    _lead(auth_client)
    auth_client.post("/api/sites", json=BRIEF)
    me = _me(db)
    mid = me.id
    (UPLOADS / str(mid)).mkdir(parents=True, exist_ok=True)
    (UPLOADS / str(mid) / "a.png").write_bytes(b"x")
    r = auth_client.post("/api/account/delete", json={"password": PASSWORD, "confirm_email": "Owner@Example.com "})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert _me(db) is None
    for M in (Lead, Site, Integration):
        assert db.scalar(select(func.count()).select_from(M).where(M.user_id == mid)) == 0
    assert not (UPLOADS / str(mid)).exists()
    assert auth_client.get("/api/auth/me").status_code == 401
    # the same email can sign up again from scratch
    signup_and_verify(client)


def test_old_session_tokens_stop_working(auth_client, db):
    token = auth_client.cookies.get("aimva_session")
    auth_client.post("/api/account/delete", json={"password": PASSWORD, "confirm_email": "owner@example.com"})
    fresh = make_client()
    assert fresh.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_sole_owned_workspaces_go_shared_ones_stay(auth_client, db):
    mid = _me(db).id
    solo = _ws(auth_client, "Solo Clinic")
    shared = _ws(auth_client, "Shared Realty")
    partner = make_client()
    signup_and_verify(partner, email="partner@example.com", name="Partner")
    pid = _me(db, "partner@example.com").id
    db.add(Membership(workspace_id=shared["id"], member_id=pid, role="owner"))
    db.commit()
    auth_client.post(f"/api/workspaces/{solo['id']}/switch")
    _lead(auth_client)

    p = auth_client.get("/api/account/delete-preview").json()
    assert [w["name"] for w in p["workspaces_deleted"]] == ["Solo Clinic"] and p["workspaces_deleted"][0]["leads"] == 1
    assert [w["name"] for w in p["workspaces_kept"]] == ["Shared Realty"]

    r = auth_client.post("/api/account/delete", json={"password": PASSWORD, "confirm_email": "owner@example.com"}).json()
    assert r["workspaces_deleted"] == ["Solo Clinic"]
    db.expire_all()
    assert db.get(User, solo["id"]) is None
    assert db.scalar(select(func.count()).select_from(Lead).where(Lead.user_id == solo["id"])) == 0
    assert db.get(User, shared["id"]) is not None
    assert db.scalar(select(func.count()).select_from(Membership).where(Membership.member_id == mid)) == 0
    assert [w["name"] for w in partner.get("/api/workspaces").json()][1:] == ["Shared Realty"]


def test_delete_revokes_oauth_and_cancels_the_plan(auth_client, db, mock_http, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_secret")
    me = _me(db)
    db.add_all([
        Integration(user_id=me.id, provider="google", secret=encrypt_json({"refresh_token": "g-refresh", "access_token": "g"})),
        Integration(user_id=me.id, provider="meta", secret=encrypt_json({"access_token": "m-token"})),
        Integration(user_id=me.id, provider="twilio", secret=encrypt_json({"auth_token": "t"})),
    ])
    db.merge(Subscription(user_id=me.id, plan="growth", status="active", processor="razorpay",
                          processor_subscription_id="sub_123", period_end=me.created_at))
    db.commit()
    google = mock_http.post("https://oauth2.googleapis.com/revoke").mock(return_value=httpx.Response(200))
    meta = mock_http.delete("https://graph.facebook.com/v21.0/me/permissions").mock(return_value=httpx.Response(200, json={"success": True}))
    rzp = mock_http.post("https://api.razorpay.com/v1/subscriptions/sub_123/cancel").mock(return_value=httpx.Response(200, json={}))

    preview = auth_client.get("/api/account/delete-preview").json()
    assert preview["connected"] == ["google", "meta", "twilio"] and preview["paid_plan"]
    r = auth_client.post("/api/account/delete", json={"password": PASSWORD, "confirm_email": "owner@example.com"}).json()
    assert r["revoked"] == ["google", "meta"] and r["plan_cancelled"]
    assert google.calls[0].request.content == b"token=g-refresh"
    assert meta.calls[0].request.url.params["access_token"] == "m-token"
    assert rzp.called


def test_delete_still_works_when_a_provider_is_down(auth_client, db, mock_http):
    me = _me(db)
    db.add(Integration(user_id=me.id, provider="google", secret=encrypt_json({"refresh_token": "g"})))
    db.commit()
    mock_http.post("https://oauth2.googleapis.com/revoke").mock(side_effect=httpx.ConnectError("down"))
    r = auth_client.post("/api/account/delete", json={"password": PASSWORD, "confirm_email": "owner@example.com"})
    assert r.status_code == 200 and r.json()["revoked"] == []
    db.expire_all()
    assert _me(db) is None


def test_disconnect_also_revokes(auth_client, db, mock_http):
    me = _me(db)
    db.add(Integration(user_id=me.id, provider="google", secret=encrypt_json({"refresh_token": "g-refresh"})))
    db.commit()
    route = mock_http.post("https://oauth2.googleapis.com/revoke").mock(return_value=httpx.Response(200))
    assert auth_client.delete("/api/integrations/google").json() == {"ok": True, "revoked": True}
    assert route.called


def test_published_platform_templates_survive_their_author(auth_client, db):
    from app.models import Template
    me = _me(db)
    db.add_all([Template(owner_id=me.id, module="ads", name="For everyone", source="platform"),
                Template(owner_id=me.id, module="ads", name="Mine", source="user")])
    db.commit()
    auth_client.post("/api/account/delete", json={"password": PASSWORD, "confirm_email": "owner@example.com"})
    db.expire_all()
    assert [t.name for t in db.scalars(select(Template))] == ["For everyone"]


# ---- erasing one lead --------------------------------------------------------------------------------------
def test_deleting_a_lead_erases_their_messages_and_calls(auth_client, db):
    lead = _lead(auth_client)
    keep = _lead(auth_client, name="Arjun", phone="9000000001")
    me = _me(db)
    agent = VoiceAgent(user_id=me.id, name="Asha")
    db.add(agent)
    db.flush()
    db.add_all([WaMessage(user_id=me.id, contact="919876543210", direction="in", body="Price?"),
                WaMessage(user_id=me.id, contact="919000000001", direction="in", body="Hi"),
                Call(user_id=me.id, agent_id=agent.id, lead_id=lead["id"], to_number="+919876543210"),
                Call(user_id=me.id, agent_id=agent.id, to_number="+919876543210"),
                Call(user_id=me.id, agent_id=agent.id, lead_id=keep["id"], to_number="+919000000001")])
    db.commit()
    assert auth_client.delete(f"/api/leads/{lead['id']}").status_code == 200
    db.expire_all()
    assert [m.body for m in db.scalars(select(WaMessage))] == ["Hi"]
    assert [c.lead_id for c in db.scalars(select(Call))] == [keep["id"]]


def test_messages_stay_when_another_lead_has_the_same_number(auth_client, db):
    first = _lead(auth_client)
    _lead(auth_client, name="Pri second", phone="+91 98765 43210")
    me = _me(db)
    db.add(WaMessage(user_id=me.id, contact="919876543210", direction="in", body="Price?"))
    db.commit()
    auth_client.delete(f"/api/leads/{first['id']}")
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(WaMessage)) == 1
