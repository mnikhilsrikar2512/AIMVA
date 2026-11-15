"""The owner's decisions of 2026-11-15: invite one person to the projects the owner picks, the AI reads the idea
first (rules as backup), Telugu and Tamil typed in English letters get replies the same way, the WhatsApp auto-reply
follows the owner's instructions, and one plan covers all of an owner's projects."""
import pytest
from sqlalchemy import select

from app import billing, idea_sense, lead_reply, speech
from app.agents import concierge
from app.models import Invite, Lead, Membership, User

from .conftest import make_client, signup_and_verify
from .test_agents import lead_form, profile, publish
from .test_discreet import clean_env  # noqa: F401 (fixture)
from .test_projects import _bench


def _me(db, email="owner@example.com"):
    return db.scalar(select(User).where(User.email == email))


@pytest.fixture
def mails(monkeypatch):
    sent = []
    monkeypatch.setattr("app.mailer.send_email", lambda to, subject, body, *a, **k: sent.append((to, subject, body)) or True)
    return sent


# ---- 3. invite one person to the projects the owner picks ----------------------------------------------------
def test_invite_to_the_projects_the_owner_picks(auth_client, db, mails):
    a = auth_client.post("/api/projects", json={"name": "Clinic"}).json()
    b = auth_client.post("/api/projects", json={"name": "Bakery"}).json()
    c = auth_client.post("/api/projects", json={"name": "Gym"}).json()
    r = auth_client.post("/api/projects/invite", json={"email": "Asha@Example.com", "project_ids": [a["id"], b["id"], a["id"]]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["email"] == "asha@example.com" and out["role"] == "editor"
    assert [(p["name"], p["result"]) for p in out["projects"]] == [("Clinic", "invited"), ("Bakery", "invited")]
    invited = {i.workspace_id for i in db.scalars(select(Invite).where(Invite.email == "asha@example.com"))}
    assert invited == {a["id"], b["id"]} and c["id"] not in invited  # the Gym wasn't ticked
    assert len(mails) == 1 and "Clinic, Bakery" in mails[0][1]  # one email, naming both
    # once she has an account she joins both projects, and a second invite to them changes nothing
    asha = make_client()
    signup_and_verify(asha, email="asha@example.com", name="Asha")
    assert {p["name"] for p in asha.get("/api/projects").json()} >= {"Clinic", "Bakery"}
    db.expire_all()
    roles = {m.workspace_id: m.role for m in db.scalars(select(Membership).where(Membership.member_id == _me(db, "asha@example.com").id))}
    assert roles.get(a["id"]) == "editor" and roles.get(b["id"]) == "editor" and c["id"] not in roles
    out = auth_client.post("/api/projects/invite", json={"email": "asha@example.com", "role": "admin",
                                                        "project_ids": [a["id"], c["id"]]}).json()
    assert [(p["name"], p["result"]) for p in out["projects"]] == [("Clinic", "already"), ("Gym", "added")]
    assert "Gym" in mails[-1][1] and "Clinic" not in mails[-1][1]


def test_invite_changes_nothing_unless_every_project_is_yours(auth_client, other_client, db, mails):
    mine = auth_client.post("/api/projects", json={"name": "Clinic"}).json()
    theirs = other_client.post("/api/projects", json={"name": "Not yours"}).json()
    r = auth_client.post("/api/projects/invite", json={"email": "asha@example.com", "project_ids": [mine["id"], theirs["id"]]})
    assert r.status_code == 404
    assert db.scalar(select(Invite).where(Invite.email == "asha@example.com")) is None and mails == []
    assert auth_client.post("/api/projects/invite", json={"email": "asha@example.com", "project_ids": []}).status_code == 422
    assert auth_client.post("/api/projects/invite", json={"email": "asha@example.com", "role": "client",
                                                          "project_ids": [mine["id"]]}).status_code == 422  # no client role
    # an editor can work in the project but can't bring other people in
    auth_client.post("/api/projects/invite", json={"email": "ed@example.com", "project_ids": [mine["id"]]})
    ed = make_client()
    signup_and_verify(ed, email="ed@example.com", name="Ed")
    ed.get("/api/projects")  # signing in turns the invite into a membership
    r = ed.post("/api/projects/invite", json={"email": "x@example.com", "project_ids": [mine["id"]]})
    assert r.status_code == 403 and "admin" in r.json()["detail"]


# ---- 1. the AI reads the idea first, the rules are the backup ---------------------------------------------------
def test_the_ai_kind_wins_and_the_rules_fill_the_rest():
    idea = "Dr. Rao's Dental, implants and braces in Kukatpally"
    assert idea_sense.read_idea(idea)["profile"]["kind"] == "local_service"
    read = idea_sense.read_idea(idea, write=lambda p, s, n: "personal_brand")
    assert read["profile"]["kind"] == "personal_brand" and read["profile"]["industry"] == "healthcare"
    assert read["profile"]["city"] == "Hyderabad" and read["profile"]["area"] == "Kukatpally"  # the rules still read these
    assert read["modules"] == idea_sense.REVEAL["personal_brand"]


@pytest.mark.parametrize("answer", ["unclear", "local_service or b2b", "a shop", "", None])
def test_an_unsure_or_off_script_ai_answer_leaves_the_rules_answer(answer):
    read = idea_sense.read_idea("Dental clinic in Kukatpally", write=lambda p, s, n: answer)
    assert read["profile"]["kind"] == "local_service"


def test_a_failing_ai_leaves_the_rules_answer():
    def broken(prompt, system, n):
        raise RuntimeError("engine down")
    assert idea_sense.read_idea("Dental clinic in Kukatpally", write=broken)["profile"]["kind"] == "local_service"


def test_start_asks_the_ai_first(auth_client, monkeypatch):
    monkeypatch.setattr("app.routers.agents._run_launch", lambda job_id: None)
    asked = []
    monkeypatch.setattr("app.ai_engine.agent_writer",
                        lambda *a, **k: (lambda prompt, system, n: asked.append(prompt) or "product_seller"))
    out = auth_client.post("/api/start", json={"idea": "Ammamma's pickles from Guntur"}).json()
    assert asked and "Guntur" in asked[0] and out["profile"]["kind"] == "product_seller"
    assert out["profile"]["industry"] == "retail"


# ---- 2. Telugu and Tamil typed in English letters ---------------------------------------------------------------
def test_telugu_and_tamil_in_english_letters():
    assert lead_reply.detect("rate entha andi") == "te-Latn"
    assert lead_reply.detect("price evlo sir") == "ta-Latn"
    assert lead_reply.detect("naaku details pampandi") == "te-Latn"
    assert lead_reply.detect("location anuppunga please") == "ta-Latn"
    assert lead_reply.detect("main Sunday ko aaunga") == "hi-Latn"  # a Hindi word beats a Tamil-looking ending
    assert lead_reply.detect("Andi is my name, call me") is None  # a name in an English message
    assert lead_reply.detect("Anna Nagar branch timings?") is None
    assert lead_reply.detect("Do you have EMI options?") is None
    lead = type("L", (), {"name": "Ravi Kumar"})()
    assert lead_reply.ready_made("te-Latn", "welcome", lead, "Clinic").startswith("Namaskaram Ravi, Clinic")
    assert lead_reply.ready_made("ta-Latn", "pricing", lead, "Clinic").startswith("Vanakkam Ravi")
    assert lead_reply.fits_language("Namaskaram Ravi, meeku eppudu veelavutundi?", "te-Latn")
    assert not lead_reply.fits_language("నమస్కారం రవి, మీకు ఎప్పుడు వీలవుతుంది?", "te-Latn")  # asked for English letters
    assert "English letters" in lead_reply.language_instruction("ta-Latn")
    integ = type("I", (), {"meta": {"first_message_template": "hello_lead", "template_languages": ["en", "te"]}})()
    assert lead_reply.template_for(integ, "first", "te-Latn")["lang"] == "en"  # the template in English letters


def test_a_lead_typing_telugu_in_english_letters_gets_a_telugu_call(clean_env):
    clean_env.setenv("SARVAM_API_KEY", "k")
    assert speech.call_language("en-IN", "rate entha andi, call cheyandi", written=True) == "te-IN"
    assert speech.call_language("en-IN", "price evlo, call pannunga", written=True) == "ta-IN"
    assert speech.call_language("en-IN", "rate entha andi, call cheyandi") == "en-IN"  # not from mid-call speech
    assert speech.call_language("en-IN", "What is the price?", written=True) == "en-IN"


def test_the_lead_language_can_be_set_to_english_letters(auth_client, client):
    profile(auth_client)
    s = publish(auth_client)
    lead_form(client, s["slug"], message="flat entha andi")
    lead = auth_client.get("/api/leads").json()[0]
    assert lead["language"] == "te-Latn" and lead["language_name"] == "Telugu (English letters)"
    r = auth_client.patch(f"/api/leads/{lead['id']}", json={"language": "ta-Latn"})
    assert r.status_code == 200, r.text
    d = auth_client.post(f"/api/leads/{lead['id']}/reply-draft", json={"intent": "welcome"}).json()
    assert d["language"] == "ta-Latn" and d["text"].startswith("Vanakkam Ravi")


def test_roman_scores_hold():
    bench = _bench("lead_language_bench")
    for split, floor in {"roman_dev": 1.0, "roman_test": 0.96, "roman_fresh": 0.9}.items():  # fresh: written after tuning
        acc, n = bench.score(f"leads_{split}.tsv", show=False)
        assert n and acc >= floor, (split, acc)


# ---- 4. the WhatsApp auto-reply follows the owner's instructions -------------------------------------------------
def test_the_owner_brief_is_saved_and_shapes_replies(auth_client, client, db, monkeypatch):
    profile(auth_client)
    brief = "We are open 9 to 9, free parking in the basement. Always offer a site visit."
    r = auth_client.put("/api/agents/concierge", json={"config": {"brief": "  " + brief + "  ", "evil": "x"}})
    assert r.status_code == 200 and r.json()["config"]["brief"] == brief and "evil" not in r.json()["config"]
    assert next(a for a in auth_client.get("/api/agents").json() if a["kind"] == "concierge")["config"]["brief"] == brief
    prompts = []
    monkeypatch.setattr("app.ai_engine.agent_writer", lambda *a, **k: (
        lambda prompt, system, n: prompts.append(prompt) or "Hi Ravi, thanks! Free parking is in the basement. Shall we fix a site visit?"))
    s = publish(auth_client)
    lead_form(client, s["slug"])
    lead = db.scalar(select(Lead).where(Lead.user_id == _me(db).id))
    assert any(brief in p for p in prompts)  # the welcome message was written with the owner's instructions
    assert "Free parking" in concierge.message(db, _me(db), lead, "day2")
    assert concierge.message(db, _me(db), lead, "day7").endswith("Reply STOP and we won't message again.")
    # "" clears it, and the standard wording comes back
    assert auth_client.put("/api/agents/concierge", json={"config": {"brief": ""}}).json()["config"]["brief"] == ""
    assert lead_reply.owner_brief(db, _me(db)) == ""


def test_a_brief_without_an_ai_writer_keeps_the_standard_message(auth_client, client, db):
    profile(auth_client)
    auth_client.put("/api/agents/concierge", json={"config": {"brief": "Mention free parking."}})
    s = publish(auth_client)
    lead_form(client, s["slug"])
    lead = db.scalar(select(Lead).where(Lead.user_id == _me(db).id))
    text = concierge.message(db, _me(db), lead, "day2")
    assert text and "parking" not in text.lower()  # no AI: never paste the owner's notes into a message


def test_a_brief_is_capped(auth_client):
    r = auth_client.put("/api/agents/concierge", json={"config": {"brief": "x" * 5000}})
    assert len(r.json()["config"]["brief"]) == 1000


# ---- 6. one plan covers all of an owner's projects --------------------------------------------------------------
def test_one_plan_covers_every_project(auth_client, db):
    me = _me(db)
    a = auth_client.post("/api/projects", json={"name": "Clinic"}).json()
    b = auth_client.post("/api/projects", json={"name": "Bakery"}).json()
    billing.charge(db, me, "images", 2)
    billing.charge(db, db.get(User, a["id"]), "images", 3)
    billing.charge(db, db.get(User, b["id"]), "images", 4)
    for uid in (me.id, a["id"], b["id"]):
        assert billing.allowance(db, uid, "images")["used"] == 9  # one allowance, seen the same from every project
    out = auth_client.get("/api/billing", headers={"X-AIMVA-Workspace": str(a["id"])}).json()
    assert out["account_id"] == me.id and out["projects_covered"] == 3 and not out["pays_here"]
    assert next(u for u in out["usage"] if u["meter"] == "images")["used"] == 9
    own = auth_client.get("/api/billing", headers={"X-AIMVA-Workspace": str(me.id)}).json()  # their own account
    assert own["pays_here"] and own["account_id"] == me.id
    assert billing.subscription(db, a["id"]) is not None  # harmless, but the plan that counts is the owner's
    assert billing.payer(db, db.get(User, a["id"])).id == me.id


def test_only_the_owner_changes_the_plan(auth_client, db, mails):
    a = auth_client.post("/api/projects", json={"name": "Clinic"}).json()
    auth_client.post("/api/projects/invite", json={"email": "ed@example.com", "role": "admin", "project_ids": [a["id"]]})
    ed = make_client()
    signup_and_verify(ed, email="ed@example.com", name="Ed")
    ed.get("/api/projects")
    r = ed.post("/api/billing/checkout", json={"plan": "growth"}, headers={"X-AIMVA-Workspace": str(a["id"])})
    assert r.status_code == 403
    # the teammate's own usage in the owner's project counts against the owner's plan, not theirs
    billing.charge(db, db.get(User, a["id"]), "videos", 1)
    assert billing.allowance(db, _me(db).id, "videos")["used"] == 1
    assert billing.allowance(db, _me(db, "ed@example.com").id, "videos")["used"] == 0


def test_admin_plan_changes_land_on_the_owner(auth_client, db, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "admin_emails", {"owner@example.com"})
    a = auth_client.post("/api/projects", json={"name": "Clinic"}).json()
    billing.set_plan(db, _me(db), a["id"], "growth", "pilot")
    assert billing.effective_plan(billing.subscription(db, _me(db).id)) == "growth"
    assert auth_client.get("/api/billing", headers={"X-AIMVA-Workspace": str(a["id"])}).json()["plan"] == "growth"


def test_a_project_left_without_owners_pays_for_itself(auth_client, db):
    a = auth_client.post("/api/projects", json={"name": "Clinic"}).json()
    for m in db.scalars(select(Membership).where(Membership.workspace_id == a["id"])):
        db.delete(m)
    db.commit()
    ws = db.get(User, a["id"])
    assert billing.payer(db, ws).id == ws.id and billing.covered_ids(db, ws) == [ws.id]


# ---- collaboration: each page version says who made it and what they asked the AI for ---------------------------
def _team_site(auth_client, mails):
    from .test_sites_leads import BRIEF
    p = auth_client.post("/api/projects", json={"name": "Skyline"}).json()
    h = {"X-AIMVA-Workspace": str(p["id"])}
    site = auth_client.post("/api/sites", json=BRIEF, headers=h).json()
    auth_client.post("/api/projects/invite", json={"email": "ed@example.com", "project_ids": [p["id"]]})
    ed = make_client()
    signup_and_verify(ed, email="ed@example.com", name="Ed")
    ed.get("/api/projects")
    return site, h, ed


def test_versions_name_the_teammate_and_keep_the_owners_words(auth_client, mails):
    site, h, ed = _team_site(auth_client, mails)
    sid = site["id"]
    r = auth_client.patch(f"/api/sites/{sid}", headers=h, json={
        "html": site["html"].replace("Skyline Homes", "Skyline Homes Ltd", 1), "note": "Edited with AI",
        "request": "  Make the   name sound more official " + "x" * 200})
    assert r.status_code == 200, r.text
    assert ed.patch(f"/api/sites/{sid}", headers=h, json={"html": r.json()["html"] + "<!-- ed -->", "note": "Edited visually"}).status_code == 200
    mine = auth_client.get(f"/api/sites/{sid}/versions", headers=h).json()
    assert [(v["note"], v["by"]) for v in mine[:3]] == [("Edited visually", "Ed"), ("Edited with AI", None), ("Generated", None)]
    assert mine[1]["request"].startswith("Make the name sound more official x") and len(mine[1]["request"]) == 120
    assert mine[0]["request"] == "" and mine[0]["page"] == ""
    theirs = ed.get(f"/api/sites/{sid}/versions", headers=h).json()
    assert [v["by"] for v in theirs[:2]] == [None, "Owner"]  # null is "you"
    # the owner's visual autosave right after Ed's is a new version, never folded into Ed's
    auth_client.patch(f"/api/sites/{sid}", headers=h, json={"html": r.json()["html"] + "<!-- owner -->", "note": "Edited visually"})
    assert [v["by"] for v in auth_client.get(f"/api/sites/{sid}/versions", headers=h).json()[:2]] == [None, "Ed"]


def test_extra_pages_keep_a_history_with_ai_requests(auth_client, monkeypatch):
    from app.routers import sites as S
    from .test_site_ai_edit import fake_writer
    from .test_sites_leads import make_site
    s = make_site(auth_client)
    page = auth_client.post(f"/api/sites/{s['id']}/pages", json={"title": "Pricing"}).json()["pages"][0]
    first = page["html"]
    monkeypatch.setattr(S, "writer", fake_writer(
        "<!doctype html><html><body><h1>Plans</h1><form data-aimva-lead><input name=phone></form></body></html>"))
    r = auth_client.post(f"/api/sites/{s['id']}/ai-edit", json={"instruction": "list three plans", "page": "pricing"})
    assert r.status_code == 200, r.text
    v = auth_client.get(f"/api/sites/{s['id']}/versions?page=pricing").json()
    assert [(x["note"], x["request"], x["page"], x["current"]) for x in v] == [("Edited with AI", "list three plans", "pricing", True)]
    assert all(x["page"] == "" for x in auth_client.get(f"/api/sites/{s['id']}/versions?page=").json())
    # a hand edit to the extra page is kept too, and restoring the AI version puts back only that page
    auth_client.patch(f"/api/sites/{s['id']}/pages/pricing", json={"html": first, "note": "Edited HTML"})
    v = auth_client.get(f"/api/sites/{s['id']}/versions?page=pricing").json()
    assert [x["note"] for x in v] == ["Edited HTML", "Edited with AI"] and not v[1]["current"]
    main_before = auth_client.get(f"/api/sites/{s['id']}").json()["html"]
    out = auth_client.post(f"/api/sites/{s['id']}/versions/{v[1]['id']}/restore").json()
    assert "Plans" in next(p["html"] for p in out["pages"] if p["slug"] == "pricing") and out["html"] == main_before
    assert auth_client.get(f"/api/sites/{s['id']}/versions/{v[1]['id']}").json()["page"] == "pricing"


def test_a_teammates_newer_save_is_never_replaced_silently(auth_client, mails):
    site, h, ed = _team_site(auth_client, mails)
    sid = site["id"]
    loaded = auth_client.get(f"/api/sites/{sid}", headers=h).json()
    base = loaded["version"]
    assert base >= 1
    r = ed.patch(f"/api/sites/{sid}", headers=h, json={"html": loaded["html"] + "<!-- ed -->", "base_version": base})
    assert r.status_code == 200 and r.json()["version"] == base + 1
    r = auth_client.patch(f"/api/sites/{sid}", headers=h, json={"html": loaded["html"] + "<!-- owner -->", "base_version": base})
    assert r.status_code == 409 and r.json()["detail"].startswith("Ed changed this page just now.")
    assert "<!-- ed -->" in auth_client.get(f"/api/sites/{sid}", headers=h).json()["html"]  # nothing was replaced
    r = auth_client.patch(f"/api/sites/{sid}", headers=h, json={"html": loaded["html"] + "<!-- owner -->", "base_version": base, "force": True})
    assert r.status_code == 200
    mine = r.json()["version"]
    assert [v["by"] for v in auth_client.get(f"/api/sites/{sid}/versions", headers=h).json()[:2]] == [None, "Ed"]  # both kept
    # your own newer saves never block you, and an editor that doesn't send base_version saves as before
    assert auth_client.patch(f"/api/sites/{sid}", headers=h, json={"html": loaded["html"] + "<!-- 2 -->", "base_version": base,
                                                                    "note": "Edited visually"}).status_code == 200
    assert ed.patch(f"/api/sites/{sid}", headers=h, json={"html": loaded["html"] + "<!-- 3 -->"}).status_code == 200
    assert mine > base


def test_extra_pages_have_the_same_save_check(auth_client, mails):
    site, h, ed = _team_site(auth_client, mails)
    sid = site["id"]
    auth_client.post(f"/api/sites/{sid}/pages", headers=h, json={"title": "Pricing"})
    page = next(p for p in auth_client.get(f"/api/sites/{sid}", headers=h).json()["pages"] if p["slug"] == "pricing")
    base = page["version"]
    assert ed.patch(f"/api/sites/{sid}/pages/pricing", headers=h, json={"html": page["html"] + "<!-- ed -->", "base_version": base}).status_code == 200
    r = auth_client.patch(f"/api/sites/{sid}/pages/pricing", headers=h, json={"html": page["html"] + "<!-- me -->", "base_version": base})
    assert r.status_code == 409 and "Ed changed this page" in r.json()["detail"]
    # a title change alone never clashes
    assert auth_client.patch(f"/api/sites/{sid}/pages/pricing", headers=h, json={"title": "Plans", "base_version": base}).status_code == 200
