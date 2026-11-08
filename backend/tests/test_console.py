"""The AIMVA team console: roles, the staff log, customer lookup and support actions."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import Integration, Lead, StaffAction, StaffMember, User, utcnow
from tests.conftest import make_client, signup_and_verify


@pytest.fixture
def owner(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "admin_emails", {"owner@example.com"})
    c = make_client()
    signup_and_verify(c)
    return c


@pytest.fixture
def support(owner, db):
    assert owner.post("/api/console/team", json={"email": "help@example.com"}).status_code == 200
    c = make_client()
    signup_and_verify(c, email="help@example.com", name="Helper")
    return c


@pytest.fixture
def customer(db):
    c = make_client()
    signup_and_verify(c, email="shop@example.com", name="Shop")
    u = db.scalar(select(User).where(User.email == "shop@example.com"))
    db.add(Lead(user_id=u.id, name="Asha", phone="+919800000001", message="Price?"))
    db.add(Integration(user_id=u.id, provider="gemini", account_name="gemini", secret="enc", meta={}))
    db.add(Integration(user_id=u.id, provider="meta", account_name="meta", secret="enc", meta={}))
    db.commit()
    return u


def log(db, action):
    db.expire_all()
    return list(db.scalars(select(StaffAction).where(StaffAction.action == action)))


def test_customers_and_strangers_are_kept_out(client, other_client):
    assert client.get("/api/console/me").status_code == 401
    assert other_client.get("/api/console/me").status_code == 403
    assert other_client.get("/api/console/customers").status_code == 403
    assert other_client.get("/api/auth/me").json()["user"]["staff_role"] is None


def test_roles_and_permissions(owner, support):
    me = owner.get("/api/console/me").json()
    assert me["role"] == "owner" and "team.manage" in me["permissions"]
    me = support.get("/api/console/me").json()
    assert me["role"] == "support" and "team.manage" not in me["permissions"] and "plan.change" not in me["permissions"]
    assert support.get("/api/auth/me").json()["user"]["staff_role"] == "support"
    # Support never gets owner-only screens.
    assert support.get("/api/admin/metrics").status_code == 403
    assert support.get("/api/console/team").status_code == 403
    assert support.post("/api/console/team", json={"email": "x@example.com"}).status_code == 403


def test_a_teammate_counts_only_after_verifying_their_email(owner, client, db):
    owner.post("/api/console/team", json={"email": "late@example.com"})
    r = client.post("/api/auth/signup", json={"name": "Late", "email": "late@example.com", "password": "Sup3r-secret!"})
    assert r.status_code == 200
    from app import staff
    u = db.scalar(select(User).where(User.email == "late@example.com"))
    assert staff.staff_role(db, u) is None
    team = owner.get("/api/console/team").json()
    assert next(m for m in team["members"] if m["email"] == "late@example.com")["state"] == "not verified"


def test_owner_role_cant_be_given_from_the_app(owner):
    assert owner.post("/api/console/team", json={"email": "boss@example.com", "role": "owner"}).status_code == 422
    assert owner.post("/api/console/team", json={"email": "owner@example.com"}).status_code == 400


def test_removing_a_teammate_takes_effect_at_once(owner, support, db):
    mid = db.scalar(select(StaffMember.id).where(StaffMember.email == "help@example.com"))
    assert owner.post(f"/api/console/team/{mid}/remove").status_code == 200
    assert support.get("/api/console/me").status_code == 403
    assert [a.detail["email"] for a in log(db, "team.remove")] == ["help@example.com"]


def test_customer_search_and_detail(support, customer, db):
    r = support.get("/api/console/customers", params={"q": "shop"}).json()
    assert r["total"] == 1 and r["items"][0]["leads"] == 1 and r["items"][0]["status"] == "new"
    assert support.get("/api/console/customers", params={"q": str(customer.id)}).json()["total"] == 1
    d = support.get(f"/api/console/customers/{customer.id}").json()
    assert d["profile"]["email"] == "shop@example.com" and d["usage"]["leads"]["total"] == 1
    assert d["connected"] == ["meta"]  # AI engine keys are an owner matter
    text = str(d)
    assert "Asha" not in text and "+9198" not in text and "enc" not in text  # no lead contents, no secrets
    # Viewing is logged, once an hour per person.
    again = support.get(f"/api/console/customers/{customer.id}").json()
    assert len(log(db, "customer.view")) == 1
    assert again["history"] == []  # the pane lists changes; views live in the Activity log


def test_owner_sees_ai_connections(owner, customer):
    assert owner.get(f"/api/console/customers/{customer.id}").json()["connected"] == ["gemini", "meta"]


def test_every_change_needs_a_reason(support, customer):
    assert support.post(f"/api/console/customers/{customer.id}/credits", json={"meter": "images", "quantity": 5}).status_code == 422
    assert support.post(f"/api/console/customers/{customer.id}/credits",
                        json={"meter": "images", "quantity": 5, "reason": "ok"}).status_code == 422


def test_support_grants_small_credits_only(support, customer, db):
    r = support.post(f"/api/console/customers/{customer.id}/credits",
                     json={"meter": "images", "quantity": 20, "days": 14, "reason": "Two images failed on their launch"})
    assert r.status_code == 200 and r.json()["credits"][0]["quantity"] == 20
    assert support.post(f"/api/console/customers/{customer.id}/credits",
                        json={"meter": "images", "quantity": 500, "reason": "Big goodwill gesture"}).status_code == 403
    assert support.post(f"/api/console/customers/{customer.id}/plan",
                        json={"plan": "growth", "reason": "They paid by bank transfer"}).status_code == 403
    [a] = log(db, "credits.grant")
    assert a.actor_email == "help@example.com" and a.actor_role == "support" and a.reason.startswith("Two images")
    assert a.detail == {"meter": "images", "quantity": 20, "days": 14} and a.target_label == "shop@example.com"


def test_owner_changes_plan_and_it_is_logged(owner, customer, db):
    r = owner.post(f"/api/console/customers/{customer.id}/plan", json={"plan": "growth", "reason": "Invoice #12 paid"})
    assert r.status_code == 200 and r.json()["billing"]["plan"] == "growth"
    [a] = log(db, "plan.change")
    assert a.detail == {"from": "trial", "to": "growth"} and a.reason == "Invoice #12 paid"


def test_old_admin_billing_endpoints_are_logged_too(owner, customer, db):
    owner.post(f"/api/admin/billing/{customer.id}/credits", json={"meter": "videos", "quantity": 3})
    assert len(log(db, "credits.grant")) == 1


def test_unlock_and_sign_out_everywhere(support, customer, db):
    shop = make_client()
    r = shop.post("/api/auth/login", json={"email": "shop@example.com", "password": "Sup3r-secret!"})
    assert r.status_code == 200
    u = db.get(User, customer.id)
    u.failed_logins, u.locked_until = 5, utcnow() + timedelta(minutes=15)
    db.commit()
    d = support.post(f"/api/console/customers/{customer.id}/unlock", json={"reason": "Called us, forgot password"}).json()
    assert d["profile"]["locked"] is False and d["profile"]["failed_logins"] == 0
    assert shop.get("/api/auth/me").status_code == 200
    support.post(f"/api/console/customers/{customer.id}/sign-out", json={"reason": "Lost their phone"})
    assert shop.get("/api/auth/me").status_code == 401
    assert [a.action for a in log(db, "signin.unlock") + log(db, "signin.revoke")] == ["signin.unlock", "signin.revoke"]


def test_support_cant_act_on_the_team(support, db):
    owner_id = db.scalar(select(User.id).where(User.email == "owner@example.com"))
    helper_id = db.scalar(select(User.id).where(User.email == "help@example.com"))
    for cid in (owner_id, helper_id):
        assert support.post(f"/api/console/customers/{cid}/sign-out", json={"reason": "Just because"}).status_code == 403
        assert support.post(f"/api/console/customers/{cid}/credits",
                            json={"meter": "images", "quantity": 5, "reason": "For myself"}).status_code == 403


def test_activity_log_is_scoped_by_role(owner, support, customer):
    support.post(f"/api/console/customers/{customer.id}/credits", json={"meter": "images", "quantity": 5, "reason": "Goodwill credits"})
    mine = support.get("/api/console/activity").json()["items"]
    assert {a["action"] for a in mine} == {"credits.grant"}  # not the team.add the owner did
    everything = owner.get("/api/console/activity").json()["items"]
    assert {"team.add", "credits.grant"} <= {a["action"] for a in everything}
    only = owner.get("/api/console/activity", params={"target_id": customer.id}).json()["items"]
    assert [a["action"] for a in only] == ["credits.grant"]


def test_activity_pages(owner, db):
    for i in range(5):
        owner.post("/api/console/team", json={"email": f"t{i}@example.com"})
    first = owner.get("/api/console/activity", params={"limit": 3}).json()
    assert len(first["items"]) == 3 and first["more"]
    rest = owner.get("/api/console/activity", params={"limit": 3, "before": first["next"]}).json()
    assert len(rest["items"]) == 2 and not rest["more"]


def test_log_survives_a_customer_deleting_their_account(owner, customer, db):
    owner.post(f"/api/console/customers/{customer.id}/credits", json={"meter": "images", "quantity": 5, "reason": "Goodwill credits"})
    db.delete(db.get(User, customer.id))
    db.commit()
    [a] = log(db, "credits.grant")
    assert a.target_label == "shop@example.com"


def test_workspaces_show_their_agency(owner, db):
    r = owner.post("/api/workspaces", json={"name": "Smile Dental"})
    assert r.status_code == 200, r.text
    items = owner.get("/api/console/customers", params={"kind": "workspace"}).json()["items"]
    assert items[0]["name"] == "Smile Dental" and items[0]["agency"] == "owner@example.com" and items[0]["email"] is None
    d = owner.get(f"/api/console/customers/{items[0]['id']}").json()
    assert d["members"][0]["role"] == "owner"
    assert owner.post(f"/api/console/customers/{items[0]['id']}/unlock", json={"reason": "Locked out today"}).status_code == 400


def teammate(owner, email, role):
    assert owner.post("/api/console/team", json={"email": email, "role": role}).status_code == 200
    c = make_client()
    signup_and_verify(c, email=email, name=role.title())
    return c


def test_management_runs_the_money_side(owner, customer, db):
    mgr = teammate(owner, "boss@example.com", "manager")
    assert mgr.get("/api/console/me").json()["role_label"] == "Management"
    assert mgr.post(f"/api/console/customers/{customer.id}/credits",
                    json={"meter": "images", "quantity": 500, "reason": "Pilot partner"}).status_code == 200
    assert mgr.post(f"/api/console/customers/{customer.id}/plan", json={"plan": "agency", "reason": "Signed contract"}).status_code == 200
    assert mgr.get("/api/admin/metrics").status_code == 200
    assert mgr.get("/api/console/team").status_code == 403
    assert mgr.get("/api/admin/templates").status_code == 403  # owner only
    assert mgr.get(f"/api/console/customers/{customer.id}").json()["connected"] == ["meta"]


def test_development_reads_but_moves_no_money(owner, customer, db):
    dev = teammate(owner, "dev@example.com", "developer")
    assert dev.get(f"/api/console/customers/{customer.id}").status_code == 200
    assert dev.get("/api/admin/metrics").status_code == 200
    assert {a["action"] for a in dev.get("/api/console/activity").json()["items"]} >= {"team.add"}
    assert dev.post(f"/api/console/customers/{customer.id}/credits",
                    json={"meter": "images", "quantity": 1, "reason": "Testing a fix"}).status_code == 403
    assert dev.post(f"/api/console/customers/{customer.id}/plan", json={"plan": "growth", "reason": "Testing a fix"}).status_code == 403
    assert dev.post(f"/api/console/customers/{customer.id}/unlock", json={"reason": "Testing a fix"}).status_code == 403
    assert dev.post(f"/api/console/customers/{customer.id}/sign-out", json={"reason": "Session token leaked in a log"}).status_code == 200


def test_owner_changes_a_teammates_role(owner, db):
    dev = teammate(owner, "dev@example.com", "developer")
    mid = db.scalar(select(StaffMember.id).where(StaffMember.email == "dev@example.com"))
    team = owner.post(f"/api/console/team/{mid}/role", json={"role": "manager"}).json()
    assert next(m for m in team["members"] if m["id"] == mid)["role"] == "manager"
    assert dev.get("/api/console/me").json()["role"] == "manager"
    assert owner.post(f"/api/console/team/{mid}/role", json={"role": "owner"}).status_code == 422
    [a] = log(db, "team.role")
    assert a.detail == {"email": "dev@example.com", "from": "developer", "to": "manager"}


# ---- tasks and overview -----------------------------------------------------------------------------------------
from datetime import date  # noqa: E402

from app.models import StaffTask  # noqa: E402


def test_owner_assigns_a_task_and_the_teammate_works_it(owner, support, customer, db):
    r = owner.post("/api/console/tasks", json={"title": "Call Shop about failed images", "assignees": ["help@example.com"],
                                                "customer_id": customer.id, "priority": "high", "due_on": "2026-11-01"})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["customer"] == "shop@example.com" and t["overdue"] and t["created_by"] == "owner@example.com"
    assert [a["email"] for a in t["assignees"]] == ["help@example.com"] and t["version"] == 1
    mine = support.get("/api/console/tasks").json()["items"]
    assert [x["id"] for x in mine] == [t["id"]]
    assert owner.get("/api/console/tasks").json()["items"] == []  # the owner's own list is empty
    # The assignee moves it along and adds a note, but can't hand it on or retitle it.
    t = support.patch(f"/api/console/tasks/{t['id']}", json={"version": 1, "status": "doing", "note": "Left a voicemail"}).json()
    assert t["version"] == 2 and t["note"] == "Left a voicemail"
    assert support.patch(f"/api/console/tasks/{t['id']}", json={"version": 2, "assignees": ["owner@example.com"]}).status_code == 403
    assert support.patch(f"/api/console/tasks/{t['id']}", json={"version": 2, "status": "done"}).json()["done_at"]
    assert support.get("/api/console/tasks").json()["items"] == []
    assert len(support.get("/api/console/tasks", params={"status": "done"}).json()["items"]) == 1
    assert [a.detail["to"] for a in log(db, "task.status")] == ["doing", "done"]
    assert len(log(db, "task.assign")) == 1


def test_many_people_on_one_task(owner, support):
    names = [f"crew{i}@example.com" for i in range(5)]
    crew = [teammate(owner, e, "developer") for e in names]
    t = owner.post("/api/console/tasks", json={"title": "Fix the Hindi voice", "assignees": ["help@example.com", *names, names[0]]}).json()
    assert [a["email"] for a in t["assignees"]] == ["help@example.com", *names]  # duplicates dropped, order kept
    for c in [support, *crew]:
        assert [x["id"] for x in c.get("/api/console/tasks").json()["items"]] == [t["id"]]
    # Everyone posts a progress note at once: nothing clashes, every note is kept.
    for i, c in enumerate(crew):
        assert c.post(f"/api/console/tasks/{t['id']}/updates", json={"body": f"Checked part {i}"}).status_code == 200
    full = owner.get(f"/api/console/tasks/{t['id']}").json()
    assert full["updates_count"] == 5 and len(full["updates"]) == 5 and full["updates"][0]["body"] == "Checked part 4"
    listed = owner.get("/api/console/tasks", params={"scope": "all"}).json()["items"][0]
    assert listed["updates_count"] == 5 and len(listed["updates"]) == 5
    assert full["version"] == 1  # notes don't touch the task, so they never cause a conflict


def test_two_saves_at_once_dont_overwrite(owner, support, db):
    dev = teammate(owner, "dev@example.com", "developer")
    t = owner.post("/api/console/tasks", json={"title": "Pilot list", "assignees": ["help@example.com", "dev@example.com"]}).json()
    # Both opened version 1. Support saves first; the developer's save on the old version is refused, not merged blindly.
    assert support.patch(f"/api/console/tasks/{t['id']}", json={"version": 1, "note": "Called 3 of 10"}).status_code == 200
    r = dev.patch(f"/api/console/tasks/{t['id']}", json={"version": 1, "note": "Fixed the import"})
    assert r.status_code == 409
    latest = r.json()["detail"]["task"]
    assert latest["note"] == "Called 3 of 10" and latest["version"] == 2
    assert dev.patch(f"/api/console/tasks/{t['id']}", json={"version": 2, "note": "Called 3 of 10. Fixed the import"}).json()["version"] == 3
    # Saving with nothing changed doesn't bump the version.
    assert dev.patch(f"/api/console/tasks/{t['id']}", json={"version": 3, "status": "open"}).json()["version"] == 3


def test_manager_changes_who_is_on_a_task(owner, support, db):
    dev = teammate(owner, "dev@example.com", "developer")
    t = owner.post("/api/console/tasks", json={"title": "Pilot list", "assignees": ["help@example.com"]}).json()
    t = owner.patch(f"/api/console/tasks/{t['id']}", json={"version": 1, "assignees": ["help@example.com", "dev@example.com", "owner@example.com"]}).json()
    assert len(t["assignees"]) == 3 and t["version"] == 2
    t = owner.patch(f"/api/console/tasks/{t['id']}", json={"version": 2, "assignees": ["dev@example.com"]}).json()
    assert [a["email"] for a in t["assignees"]] == ["dev@example.com"]
    assert support.get("/api/console/tasks").json()["items"] == []
    assert support.post(f"/api/console/tasks/{t['id']}/updates", json={"body": "hi"}).status_code == 404
    assert owner.patch(f"/api/console/tasks/{t['id']}", json={"version": 3, "assignees": []}).status_code == 422
    assert [(a.detail["added"], a.detail["removed"]) for a in log(db, "task.people")] == [
        (["dev@example.com", "owner@example.com"], []), ([], ["help@example.com", "owner@example.com"])]
    filtered = owner.get("/api/console/tasks", params={"scope": "all", "assignee": "dev@example.com"}).json()["items"]
    assert [x["id"] for x in filtered] == [t["id"]]
    assert owner.get("/api/console/tasks", params={"scope": "all", "assignee": "help@example.com"}).json()["items"] == []


def test_only_owners_and_managers_assign(owner, support):
    assert support.post("/api/console/tasks", json={"title": "Do a thing", "assignees": ["help@example.com"]}).status_code == 403
    assert support.get("/api/console/tasks", params={"scope": "all"}).status_code == 403
    mgr = teammate(owner, "boss@example.com", "manager")
    assert mgr.post("/api/console/tasks", json={"title": "Review pilot list", "assignees": ["help@example.com"]}).status_code == 200
    every = owner.get("/api/console/tasks", params={"scope": "all"}).json()
    assert len(every["items"]) == 1 and "help@example.com" in every["assignees"]


def test_tasks_go_only_to_the_team(owner):
    r = owner.post("/api/console/tasks", json={"title": "Do a thing", "assignees": ["owner@example.com", "stranger@example.com"]})
    assert r.status_code == 400 and "stranger@example.com" in r.json()["detail"]
    assert owner.post("/api/console/tasks", json={"title": "Do a thing", "assignees": []}).status_code == 422


def test_someone_elses_task_is_invisible(owner, support, db):
    t = owner.post("/api/console/tasks", json={"title": "Owner's own", "assignees": ["owner@example.com"]}).json()
    assert support.patch(f"/api/console/tasks/{t['id']}", json={"version": 1, "status": "done"}).status_code == 404
    assert support.get(f"/api/console/tasks/{t['id']}").status_code == 404


def test_overview(owner, support, customer, db):
    support.post(f"/api/console/customers/{customer.id}/credits", json={"meter": "images", "quantity": 5, "reason": "Goodwill credits"})
    support.get(f"/api/console/customers/{customer.id}")
    owner.post("/api/console/tasks", json={"title": "Follow up", "assignees": ["help@example.com", "owner@example.com"], "due_on": "2026-01-01"})
    o = owner.get("/api/console/overview").json()
    assert o["platform"]["leads"] == 1 and o["platform"]["customers"] >= 3
    helper = next(r for r in o["team"] if r["email"] == "help@example.com")
    assert helper["role"] == "support" and helper["actions"] == 1 and helper["customers_opened"] == 1
    assert helper["tasks"]["open"] == 1 and helper["tasks"]["overdue"] == 1
    assert next(r for r in o["team"] if r["email"] == "owner@example.com")["tasks"]["open"] == 1  # shared task counts for both
    assert support.get("/api/console/overview").status_code == 403
    dev = teammate(owner, "dev@example.com", "developer")
    assert dev.get("/api/console/overview").status_code == 403


def test_accounts_sees_money_and_changes_nothing(owner, customer, db):
    acc = teammate(owner, "books@example.com", "accountant")
    owner.post(f"/api/console/customers/{customer.id}/plan", json={"plan": "growth", "reason": "Invoice #12 paid"})
    owner.post(f"/api/console/customers/{customer.id}/credits", json={"meter": "images", "quantity": 5, "reason": "Goodwill credits"})
    b = acc.get("/api/console/billing").json()
    assert b["totals"]["mrr_inr"] == 4999 and b["totals"]["invoiced"] == 1 and b["live_payments"] is False
    row = next(r for r in b["subscriptions"] if r["id"] == customer.id)
    assert row["plan"] == "growth" and row["processor"] == "manual"
    assert b["credits"][0]["quantity"] == 5
    assert acc.get(f"/api/console/customers/{customer.id}").status_code == 200
    for path, body in (("credits", {"meter": "images", "quantity": 1, "reason": "Testing it out"}),
                       ("plan", {"plan": "starter", "reason": "Testing it out"}), ("unlock", {"reason": "Testing it out"}),
                       ("sign-out", {"reason": "Testing it out"})):
        assert acc.post(f"/api/console/customers/{customer.id}/{path}", json=body).status_code == 403
    assert acc.get("/api/console/overview").status_code == 403
    assert acc.get("/api/admin/metrics").status_code == 403


def test_billing_is_hidden_from_support_and_development(owner, support):
    assert support.get("/api/console/billing").status_code == 403
    dev = teammate(owner, "dev@example.com", "developer")
    assert dev.get("/api/console/billing").status_code == 403
    assert owner.get("/api/console/billing").status_code == 200
