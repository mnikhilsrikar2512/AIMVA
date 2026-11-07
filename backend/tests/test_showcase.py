"""Showcase: the premium project-microsite design, its AI copy, the extra enquiry fields and the gated brochure."""
import json


PROJECT = {
    "business": "Wildleaf Villas", "industry": "Real estate", "page_type": "real_estate", "use_ai": False,
    "offer": "4 & 5 BHK villas in a 30-acre forest community", "headline": "A grander way to call home",
    "location_line": "Kollur, West Hyderabad", "chips": ["30 acres", "Gated community"],
    "stats": [{"value": "30", "label": "Acres"}, {"value": "220", "label": "Villas"}],
    "price_from": "₹3.2 Cr onwards", "price_note": "All inclusive",
    "configurations": [{"name": "4 BHK Villa", "area": "4,200 sq ft", "price": "₹3.2 Cr"}, {"name": "5 BHK Villa", "area": "5,600 sq ft"}],
    "amenities": ["Swimming pool", "Clubhouse", "24x7 security"], "distances": [{"place": "ORR Exit 3", "time": "8 min"}],
    "approvals": "HMDA & RERA approved", "announcement": "Phase 2 launch", "address": "Kollur, Hyderabad",
    "hero_image": "https://images.example.com/hero.jpg", "faqs": [{"q": "When is possession?", "a": "December 2027."}],
}


def make(c, **over):
    r = c.post("/api/sites", json={**PROJECT, **over})
    assert r.status_code == 200, r.text
    return r.json()


def test_real_estate_with_a_photo_gets_showcase_and_every_fact(auth_client):
    s = make(auth_client)
    html = s["html"]
    assert s["brief"]["layout"] == "showcase" and 'aimva:layout" content="showcase"' in html
    for fact in ("Kollur, West Hyderabad", "₹3.2 Cr onwards", "4,200 sq ft", "Swimming pool", "ORR Exit 3", "8 min",
                 "HMDA &amp; RERA approved", "Phase 2 launch", "When is possession?", "Book a site visit"):
        assert fact in html, fact
    assert 'name="interest"' in html and 'name="timeline"' in html and 'name="best_time"' in html
    assert 'name="website"' in html and 'type="checkbox" required' in html  # honeypot + consent
    assert '"@type": "RealEstateListing"' in html and 'class="sticky"' in html
    assert "Price on request" in html  # the 5 BHK has no price: nothing is invented


def test_blocks_without_facts_are_left_out(auth_client):
    html = make(auth_client, configurations=[], amenities=[], distances=[], address="", price_from="", stats=[])["html"]
    assert 'id="plans"' not in html and 'id="amenities"' not in html and 'id="location"' not in html
    assert 'class="price-card' not in html and 'class="stats"' not in html


def test_without_a_photo_showcase_is_not_picked_automatically(auth_client):
    s = make(auth_client, hero_image="", layout="auto")
    assert s["brief"]["layout"] not in ("showcase", "immersive")


def test_showcase_lead_keeps_interest_timeline_and_action(auth_client, client):
    s = make(auth_client)
    auth_client.post(f"/api/sites/{s['id']}/deploy", json={"target": "aimva"})
    r = client.post(f"/api/public/sites/{s['slug']}/lead", data={
        "name": "Ravi", "phone": "+919812345678", "interest": "4 BHK Villa", "timeline": "Within 30 days",
        "best_time": "4 – 8 pm", "action": "price"})
    assert r.json() == {"ok": True}
    lead = auth_client.get("/api/leads").json()[0]
    detail = auth_client.get(f"/api/leads/{lead['id']}").json()
    text = json.dumps(detail)
    assert "Asked for the price sheet" in text and "Interested in: 4 BHK Villa" in text and "Planning: Within 30 days" in text


def test_honeypot_drops_bots_silently(auth_client, client):
    s = make(auth_client)
    r = client.post(f"/api/public/sites/{s['slug']}/lead", data={"name": "Bot", "phone": "+919812345678", "website": "spam.example"})
    assert r.json() == {"ok": True} and auth_client.get("/api/leads").json() == []


def test_brochure_is_served_only_for_the_owners_published_page(auth_client, other_client, client):
    pdf = auth_client.post("/api/references", files={"file": ("brochure.txt", b"Wildleaf brochure: villas, plans and prices.", "text/plain")}).json()
    theirs = other_client.post("/api/references", files={"file": ("b.txt", b"Someone else's brochure text here.", "text/plain")}).json()
    assert auth_client.post("/api/sites", json={**PROJECT, "brochure": theirs["id"]}).status_code == 404
    s = make(auth_client, brochure=pdf["id"])
    assert f"/s/{s['slug']}/brochure" in s["html"]
    assert client.get(f"/s/{s['slug']}/brochure").status_code == 404  # not published yet
    auth_client.post(f"/api/sites/{s['id']}/deploy", json={"target": "aimva"})
    r = client.get(f"/s/{s['slug']}/brochure")
    assert r.status_code == 200 and b"Wildleaf brochure" in r.content


def test_ai_writes_only_the_words_and_bad_output_falls_back(auth_client, mock_http):
    auth_client.post("/api/providers", json={"preset": "openai", "api_key": "k", "verify": False})
    copy = {"headline": "Live where the forest begins", "overview": "Villas set among old trees.",
            "highlights": [{"title": "Forest views", "text": "Every villa faces green."}, {"title": "Quiet streets", "text": "No through traffic."}],
            "steps": [["Pick", "Choose a villa."], ["Visit", "See it."], ["Book", "Reserve it."]], "price_label": 5}
    route = mock_http.post("https://api.openai.com/v1/chat/completions").respond(json={"choices": [{"message": {"content": json.dumps(copy)}}]})
    s = make(auth_client, use_ai=True, headline="", layout="showcase")
    prompt = json.loads(route.calls.last.request.content)["messages"][-1]["content"]
    assert "never invent numbers" in prompt and "₹3.2 Cr onwards" in prompt
    assert s["generator"] == "ai" and "Live where the forest <em>begins</em>" in s["html"] and "Quiet streets" in s["html"]
    assert "Indicative launch price" in s["html"]  # a non-text value is ignored
    route.respond(json={"choices": [{"message": {"content": "Sorry, I can't help with that."}}]})
    s2 = make(auth_client, use_ai=True, layout="showcase")
    assert s2["generator"] == "template" and "A grander way to call <em>home</em>" in s2["html"]


def test_map_link_must_be_https(auth_client):
    assert auth_client.post("/api/sites", json={**PROJECT, "map_url": "javascript:alert(1)"}).status_code == 422
