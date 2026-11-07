"""Fixes from the agency/client walk-through (2026-11-06)."""
from app.agents.launch import _headline, clip

from .helpers import connect
from .test_quality import BASE


def test_launch_works_without_a_profile_name(auth_client):
    j = auth_client.post("/api/agents/launch", json={
        "description": "SmileCare Dental, Kondapur Hyderabad. Invisalign and implants, free first consultation.",
        "product": "Invisalign", "platforms": ["meta"]}).json()
    job = auth_client.get(f"/api/agents/jobs/{j['id']}").json()
    assert job["status"] == "done", job
    site = auth_client.get(f"/api/sites/{job['result']['site_id']}").json()
    assert site["brief"]["business"] == "SmileCare Dental"
    ad = auth_client.get("/api/campaigns").json()[0]["creative"]
    assert ad["headline"] == "Invisalign at SmileCare Dental"


def test_an_explicit_business_name_wins(auth_client):
    auth_client.patch("/api/auth/profile", json={"company": "Priya's Agency"})
    j = auth_client.post("/api/agents/launch", json={"business": "Green Acres Villas", "description": "Luxury villas in Shamshabad",
                                                     "platforms": []}).json()
    job = auth_client.get(f"/api/agents/jobs/{j['id']}").json()
    assert auth_client.get(f"/api/sites/{job['result']['site_id']}").json()["brief"]["business"] == "Green Acres Villas"


def test_headlines_are_never_cut_mid_word():
    assert clip("SmileCare Dental, Kondapur Hyderabad. Invisalign and implants", 40) == "SmileCare Dental, Kondapur Hyderabad"
    assert clip("Short one", 40) == "Short one"
    assert clip("Book your free site visit this weekend and save", 40) == "Book your free site visit this weekend"
    h = _headline({"business": "Skyline Homes", "offer": "3 BHK flats in Kokapet from ₹1.2 Cr, ready by 2027 with clubhouse"})
    assert len(h) <= 40 and not h.endswith(("In", ","))


def test_call_me_now_is_not_pre_ticked_and_hidden_without_a_phone_line(auth_client, client, db):
    s = auth_client.post("/api/sites", json=BASE).json()
    assert 'name="callback" value="yes">' in s["html"] and "checked>" not in s["html"].split('name="callback"')[1][:20]
    auth_client.post(f"/api/sites/{s['id']}/publish", json={"name": "Smile", "slug": "smile-line"})
    assert 'name="callback"' not in client.get("/s/smile-line").text  # no phone line: no promise of a call
    connect(db, "owner@example.com", "twilio", {"account_sid": "AC1", "auth_token": "t"}, {"from_number": "+14155550100"})
    assert 'name="callback"' in client.get("/s/smile-line").text
