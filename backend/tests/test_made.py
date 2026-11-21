"""Release 2 of the idea-first workspace: Calls and Campaigns start from one prompt, every change is a version with the
owner's words and who asked, and older versions come back. Pictures and videos remember who made them. Nothing here
calls a real AI, image or video model."""
import pytest
from sqlalchemy import select

from app import made
from app.models import Campaign, MadeVersion, VoiceAgent

from .conftest import make_client, signup_and_verify
from .test_owner_decisions import _me, mails  # noqa: F401 (fixture)


def _profile(db, **p):
    me = _me(db)
    me.company = "Dr. Rao's Dental"
    me.onboarding_answers = {"profile": {"name": "Dr. Rao's Dental", "industry": "healthcare", "offer": "Implants and braces",
                                         "area": "Kukatpally", **p}}
    db.commit()


# ---- reading a prompt (rules: no AI writer in tests) ---------------------------------------------------------
@pytest.mark.parametrize("text,daily", [
    ("₹500 a day", 500), ("Rs 15,000 a month", 500), ("5k per week", 714.29), ("budget ₹1 lakh a month", 3333.33),
    ("₹300 daily", 300), ("₹15000", 500), ("no money words", None),
])
def test_budgets_are_read_as_a_daily_amount(text, daily):
    assert made.budget_in(text) == daily


def test_place_radius_ages_and_audience_are_read():
    p = made.place_in("A Meta campaign for families within 8 km of Kukatpally, aged 25-45, ₹500 a day")
    assert p == {"radius_km": 8, "locations": "Kukatpally", "age_min": 25, "age_max": 45, "interests": "families"}
    assert made.place_in("ads around Banjara Hills sending them to WhatsApp")["locations"] == "Banjara Hills"
    assert made.langs_in("Call back in Telugu or Hindi, English if they prefer") == ["te-IN", "hi-IN", "en-IN"]


# ---- Calls ----------------------------------------------------------------------------------------------------
def test_call_script_from_one_prompt_then_changes_and_restore(auth_client, db):
    _profile(db)
    r = auth_client.post("/api/calls/script", json={"prompt": "Call back anyone who leaves a number, in Telugu or Hindi, and book a visit."})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["language"] == "te-IN" and a["enabled"] is True
    assert "Speak Telugu or Hindi" in a["instructions"] and "book a visit" in a["instructions"]
    assert a["questions"] and a["greeting"]
    assert db.scalar(select(VoiceAgent.id)) == a["id"]  # one assistant, made for them

    r = auth_client.post("/api/calls/script/change", json={"request": "also ask: which treatment are you interested in"})
    assert r.status_code == 200, r.text
    assert r.json()["questions"][-1] == "Which treatment are you interested in?"
    r = auth_client.post("/api/calls/script/change", json={"request": "speak Tamil instead"})
    assert r.json()["language"] == "ta-IN" and "Speak Tamil." in r.json()["instructions"]
    r = auth_client.post("/api/calls/script/change", json={"request": "mention we're closed on Sundays"})
    assert r.json()["instructions"].endswith("Also: Mention we're closed on Sundays.")  # still changes what it says

    vs = auth_client.get(f"/api/versions/call_script/{a['id']}").json()
    assert [v["number"] for v in vs] == [4, 3, 2, 1] and vs[0]["current"] and not vs[3]["current"]
    assert vs[3]["request"].startswith("Call back anyone") and vs[0]["by"] is None  # null is "you"
    out = auth_client.post(f"/api/versions/{vs[3]['id']}/restore").json()
    assert out["language"] == "te-IN" and out["questions"] == a["questions"]
    vs = auth_client.get(f"/api/versions/call_script/{a['id']}").json()
    assert vs[0]["note"] == "Back to v1" and vs[0]["current"] and len(vs) == 5  # nothing was lost
    assert auth_client.get(f"/api/versions/{vs[2]['id']}").json()["data"]["language"] == "ta-IN"


def test_a_hand_edit_is_a_version_and_call_backs_can_be_switched_off(auth_client, db):
    _profile(db)
    a = auth_client.post("/api/calls/script", json={"prompt": "Call back new leads in Hindi"}).json()
    r = auth_client.put(f"/api/voice/agents/{a['id']}", json={**{k: a[k] for k in made.SCRIPT_KEYS}, "greeting": "Namaste!"})
    assert r.status_code == 200, r.text
    assert auth_client.put(f"/api/voice/agents/{a['id']}", json={k: r.json()[k] for k in made.SCRIPT_KEYS}).status_code == 200
    vs = auth_client.get(f"/api/versions/call_script/{a['id']}").json()
    assert [v["note"] for v in vs] == ["Edited by hand", ""]  # saving without a change adds nothing
    assert auth_client.patch(f"/api/voice/agents/{a['id']}/enabled", json={"enabled": False}).json()["enabled"] is False
    db.expire_all()
    assert db.get(VoiceAgent, a["id"]).enabled is False


def test_the_first_change_to_an_old_script_keeps_the_old_one(auth_client, db):
    _profile(db)
    old = VoiceAgent(user_id=_me(db).id, name="Old", language="en-IN", greeting="Hello", instructions="Be nice.", questions=["Name?"])
    db.add(old)
    db.commit()
    auth_client.post("/api/calls/script/change", json={"request": "add a question: when can you visit"})
    vs = auth_client.get(f"/api/versions/call_script/{old.id}").json()
    assert [v["note"] for v in vs] == ["", "Before your changes"]
    assert auth_client.get(f"/api/versions/{vs[1]['id']}").json()["data"]["questions"] == ["Name?"]


def test_call_backs_wait_when_switched_off(auth_client, db, monkeypatch):
    from app.models import Lead
    from app.routers import sites
    _profile(db)
    a = auth_client.post("/api/calls/script", json={"prompt": "Call back new leads"}).json()
    auth_client.patch(f"/api/voice/agents/{a['id']}/enabled", json={"enabled": False})
    lead = Lead(user_id=_me(db).id, name="Ravi", phone="+919876543210")
    db.add(lead)
    db.commit()
    dialled = []
    monkeypatch.setattr("app.routers.voice.place_phone_call", lambda *a, **k: dialled.append(a))
    sites._dial_back(_me(db).id, lead.id, "+919876543210", None)
    assert dialled == []


def test_the_ai_writer_writes_the_script_when_there_is_one(auth_client, db, monkeypatch):
    _profile(db)
    reply = '{"greeting": "Hello from Dr. Rao\'s Dental", "questions": ["your name", "Which treatment?", "When can you come"], "instructions": "Be kind."}'
    monkeypatch.setattr("app.ai_engine.agent_writer", lambda *a, **k: (lambda *x, **y: reply))
    a = auth_client.post("/api/calls/script", json={"prompt": "Call back in Telugu and book a visit"}).json()
    assert a["greeting"] == "Hello from Dr. Rao's Dental." and a["questions"] == ["Your name?", "Which treatment?", "When can you come?"]
    assert a["instructions"].startswith("Be kind.") and a["language"] == "te-IN"


# ---- Campaigns ------------------------------------------------------------------------------------------------
def test_campaign_draft_from_one_prompt_then_changes_and_restore(auth_client, db):
    _profile(db)
    r = auth_client.post("/api/campaigns/draft", json={
        "prompt": "A Meta campaign for families within 8 km of Kukatpally, ₹500 a day, sending people to my page.", "platform": "meta"})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["status"] == "draft" and c["platform"] == "meta" and c["daily_budget"] == 500
    assert c["targeting"]["locations"] == "Kukatpally" and c["targeting"]["radius_km"] == 8 and c["targeting"]["interests"] == "families"
    assert c["creative"]["headline"] and c["creative"]["destination"] == "page" and c["lead_form"]["fields"]
    assert "campaign" not in (c["creative"]["headline"] + c["creative"]["text"]).lower()  # about the business, not the request
    assert c["creative"]["link"] == ""  # no page yet: nothing to send people to
    from .test_sites_leads import BRIEF
    site = auth_client.post("/api/sites", json=BRIEF).json()
    c2 = auth_client.post("/api/campaigns/draft", json={"prompt": "Ads in Kukatpally"}).json()
    assert c2["creative"]["link"] == f"http://testserver/s/{site['slug']}?aimva_c={c2['id']}"

    assert auth_client.post(f"/api/campaigns/{c['id']}/change", json={"request": "make it ₹800 a day"}).json()["daily_budget"] == 800
    out = auth_client.post(f"/api/campaigns/{c['id']}/change", json={"request": "send them to WhatsApp instead"}).json()
    assert out["creative"]["cta"] == "Send message" and out["creative"]["destination"] == "whatsapp"
    out = auth_client.post(f"/api/campaigns/{c['id']}/change", json={"request": 'headline "Smile again in Kukatpally"'}).json()
    assert out["creative"]["headline"] == "Smile again in Kukatpally"
    r = auth_client.post(f"/api/campaigns/{c['id']}/change", json={"request": "make it feel more premium"})
    assert r.status_code == 422  # rules can't do that one; nothing pretends it did
    vs = auth_client.get(f"/api/versions/campaign/{c['id']}").json()
    assert [v["number"] for v in vs] == [4, 3, 2, 1]
    back = auth_client.post(f"/api/versions/{vs[-1]['id']}/restore").json()
    assert back["daily_budget"] == 500 and back["creative"]["headline"] == c["creative"]["headline"]
    # a hand edit (budget typed on the ad) is a version; pausing is not
    auth_client.patch(f"/api/campaigns/{c['id']}", json={"daily_budget": 650})
    auth_client.patch(f"/api/campaigns/{c['id']}", json={"status": "paused"})
    vs = auth_client.get(f"/api/versions/campaign/{c['id']}").json()
    assert [v["note"] for v in vs[:2]] == ["Edited by hand", "Back to v1"]


def test_a_campaign_can_start_from_a_chosen_picture_or_video(auth_client, db):
    from app.models import Asset
    _profile(db)
    me = _me(db)
    pic = Asset(user_id=me.id, kind="image", prompt="p", model="m", url="/api/files/pic.png", status="done", params={})
    vid = Asset(user_id=me.id, kind="video", prompt="v", model="m", url="https://v.example/a.mp4", status="done", params={})
    db.add_all([pic, vid])
    db.commit()
    c = auth_client.post("/api/campaigns/draft", json={"prompt": "Ads in Kukatpally", "asset_id": pic.id}).json()
    assert c["creative"]["image_url"] == "/api/files/pic.png"
    c = auth_client.post("/api/campaigns/draft", json={"prompt": "Ads in Kukatpally", "asset_id": vid.id}).json()
    assert c["creative"]["video_url"] == "https://v.example/a.mp4"
    assert auth_client.post("/api/campaigns/draft", json={"prompt": "Ads", "asset_id": 999}).status_code == 404


def test_the_ai_writer_rewrites_ad_copy_for_a_free_form_change(auth_client, db, monkeypatch):
    _profile(db)
    c = auth_client.post("/api/campaigns/draft", json={"prompt": "Ads around Kukatpally", "platform": "google"}).json()
    monkeypatch.setattr("app.ai_engine.agent_writer", lambda *a, **k: (lambda *x, **y: '{"headline": "Premium dental care", "text": "Calm, careful treatment."}'))
    out = auth_client.post(f"/api/campaigns/{c['id']}/change", json={"request": "make it feel more premium"})
    assert out.status_code == 200 and out.json()["creative"]["headline"] == "Premium dental care"


def test_versions_are_private_to_the_project_and_name_the_teammate(auth_client, db, mails):  # noqa: F811
    p = auth_client.post("/api/projects", json={"name": "Clinic"}).json()
    h = {"X-AIMVA-Workspace": str(p["id"])}
    c = auth_client.post("/api/campaigns/draft", json={"prompt": "Ads in Kukatpally ₹400 a day"}, headers=h).json()
    auth_client.post("/api/projects/invite", json={"email": "ed@example.com", "project_ids": [p["id"]]})
    ed = make_client()
    signup_and_verify(ed, email="ed@example.com", name="Ed")
    ed.get("/api/projects")
    assert ed.post(f"/api/campaigns/{c['id']}/change", json={"request": "₹600 a day"}, headers=h).status_code == 200
    mine = auth_client.get(f"/api/versions/campaign/{c['id']}", headers=h).json()
    assert [(v["by"], v["request"]) for v in mine] == [("Ed", "₹600 a day"), (None, "Ads in Kukatpally ₹400 a day")]
    assert [v["by"] for v in ed.get(f"/api/versions/campaign/{c['id']}", headers=h).json()] == [None, "Owner"]
    # someone outside the project sees nothing
    out = make_client()
    signup_and_verify(out, email="x@example.com", name="X")
    assert out.get(f"/api/versions/campaign/{c['id']}").status_code == 404
    assert out.post(f"/api/versions/{mine[0]['id']}/restore").status_code == 404
    assert db.scalar(select(MadeVersion.user_id).where(MadeVersion.ref_id == c["id"])) == p["id"]
    assert db.get(Campaign, c["id"]).user_id == p["id"]


# ---- Pictures and videos: who made it, and a typed change to a whole clip --------------------------------------
def test_pictures_say_which_teammate_made_them(auth_client, db, mails, mock_http):  # noqa: F811
    from .test_content import jpeg
    mock_http.get(url__startswith="https://image.pollinations.ai/").respond(200, content=jpeg(), headers={"content-type": "image/jpeg"})
    p = auth_client.post("/api/projects", json={"name": "Clinic"}).json()
    h = {"X-AIMVA-Workspace": str(p["id"])}
    auth_client.post("/api/projects/invite", json={"email": "ed@example.com", "project_ids": [p["id"]]})
    ed = make_client()
    signup_and_verify(ed, email="ed@example.com", name="Ed")
    ed.get("/api/projects")
    r = ed.post("/api/content/image", json={"prompt": "A smiling family at the dentist"}, headers=h)
    assert r.status_code == 200, r.text
    mine = auth_client.get("/api/content/assets?kind=image", headers=h).json()
    assert mine[0]["by"] == "Ed" and "by_id" in mine[0]["params"]
    assert ed.get("/api/content/assets?kind=image", headers=h).json()[0]["by"] is None


def test_a_typed_change_to_a_whole_video_goes_into_the_new_version(auth_client, db, mock_http):
    import httpx
    from app.models import Asset
    from app.routers import content
    me = _me(db)
    parent = Asset(user_id=me.id, kind="video", prompt="A family smiling", model="fal-ai/ltx-2/text-to-video", url="https://v.example/a.mp4",
                   status="done", params={"aspect_ratio": "9:16", "duration": "6s"})
    db.add(parent)
    db.commit()
    sent = {}
    route = mock_http.post(url__regex=r"https://queue\.fal\.run/.*").mock(side_effect=lambda req: (
        sent.update(body=req.content.decode()) or httpx.Response(200, json={"request_id": "r1", "status_url": "https://q/s", "response_url": "https://q/r"})))
    from app.routers import providers  # noqa: F401
    import app.routers.content as C
    C_key = C._fal_key
    try:
        C._fal_key = lambda db, user: "k"
        r = auth_client.post("/api/content/video", json={"prompt": "A family smiling", "parent_id": parent.id,
                                                          "request": "make it brighter", "model": content.VIDEO_MODELS[0]["id"]})
    finally:
        C._fal_key = C_key
    assert r.status_code == 200, r.text
    assert route.called and "- make it brighter" in sent["body"]
    out = r.json()
    assert out["params"]["parent"] == parent.id and out["params"]["request"] == "make it brighter"


def test_a_reel_prompt_gets_a_vertical_video(auth_client, db, mock_http):
    import httpx
    import app.routers.content as C
    mock_http.post(url__regex=r"https://queue\.fal\.run/.*").mock(return_value=httpx.Response(200, json={"request_id": "r", "status_url": "s", "response_url": "r"}))
    key = C._fal_key
    try:
        C._fal_key = lambda db, user: "k"
        r = auth_client.post("/api/content/video", json={"prompt": "A 20-second reel of our clinic", "aspect_auto": True,
                                                          "model": C.VIDEO_MODELS[0]["id"]})
    finally:
        C._fal_key = key
    assert r.status_code == 200, r.text
    assert r.json()["params"]["aspect_ratio"] in ("9:16", "")  # models that pick their own shape leave it blank


def test_ad_draft_uses_the_offer_in_the_owners_sentence(auth_client):
    from app.made import offer_in
    assert offer_in("Run an ad for our Sankranti offer: 20% off membership") == "Sankranti offer: 20% off membership"
    assert offer_in("make a google ad for free dental checkup camp on Sunday") == "free dental checkup camp on Sunday"
    for bare in ("run ads", "Run a ₹500 ad this week", "ads chalao 2000 ka budget", "An ad that brings people to my page", "Ads in Kukatpally"):
        assert offer_in(bare) == ""
    c = auth_client.post("/api/campaigns/draft", json={"prompt": "Run an ad for our Sankranti offer: 20% off membership", "platform": "meta"}).json()
    assert "Sankranti" in c["creative"]["headline"] + c["creative"]["text"]
