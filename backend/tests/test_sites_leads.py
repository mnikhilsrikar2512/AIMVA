import csv
import io

from sqlalchemy import select

from app.models import Lead

from .helpers import connect

BRIEF = {"business": "Skyline Homes", "industry": "Real estate", "offer": "Free site visit",
         "features": ["RERA approved", "Near metro"], "phone": "+91 99999 00000", "whatsapp": "+91 98765 43210",
         "use_ai": False}


def make_site(c, **over):
    r = c.post("/api/sites", json={**BRIEF, **over})
    assert r.status_code == 200, r.text
    return r.json()


# ---- sites & hosting -------------------------------------------------------
def test_template_site_has_working_lead_form(auth_client):
    s = make_site(auth_client)
    assert s["generator"] == "template" and not s["published"]
    html = s["html"]
    assert "data-aimva-lead" in html and f"/api/public/sites/{s['slug']}/lead" in html
    assert "RERA approved" in html and "https://wa.me/919876543210" in html


def test_site_content_is_html_escaped(auth_client):
    html = make_site(auth_client, business="<script>alert(1)</script>Co", features=['"><img src=x onerror=alert(1)>'])["html"]
    assert "<script>alert(1)" not in html and "<img src=x" not in html
    assert "&lt;script&gt;" in html


def test_colors_must_be_hex(auth_client):
    r = auth_client.post("/api/sites", json={**BRIEF, "primary": "red;}body{display:none"})
    assert r.status_code == 422


def test_unpublished_site_is_not_public(auth_client, client):
    s = make_site(auth_client)
    assert client.get(f"/s/{s['slug']}").status_code == 404


def test_publish_serve_and_count_visits(auth_client, client):
    s = make_site(auth_client)
    d = auth_client.post(f"/api/sites/{s['id']}/deploy", json={"target": "aimva"}).json()
    assert d["published"] and d["deploy_url"] == f"http://testserver/s/{s['slug']}"
    for _ in range(3):
        assert client.get(f"/s/{s['slug']}").status_code == 200
    assert auth_client.get("/api/sites").json()[0]["visits"] == 3


def test_public_form_creates_scored_lead(auth_client, client):
    s = make_site(auth_client)
    r = client.post(f"/api/public/sites/{s['slug']}/lead",
                    data={"name": "Ravi", "phone": "+919812345678", "message": "Interested, want pricing ASAP"})
    assert r.json() == {"ok": True}
    leads = auth_client.get("/api/leads").json()
    assert len(leads) == 1 and leads[0]["source"] == "website" and leads[0]["source_ref"] == s["slug"]
    assert leads[0]["score"] >= 50


def test_public_form_ignores_empty_and_unknown(auth_client, client):
    s = make_site(auth_client)
    assert client.post(f"/api/public/sites/{s['slug']}/lead", data={"name": "No contact"}).json() == {"ok": False}
    assert client.post("/api/public/sites/nope/lead", data={"email": "a@b.co"}).json() == {"ok": False}
    assert auth_client.get("/api/leads").json() == []


def test_edit_regenerate_delete(auth_client):
    s = make_site(auth_client)
    r = auth_client.patch(f"/api/sites/{s['id']}", json={"html": "<h1>Custom</h1>", "custom_domain": "offers.acme.com"})
    assert r.json()["html"] == "<h1>Custom</h1>" and r.json()["custom_domain"] == "offers.acme.com"
    r = auth_client.post(f"/api/sites/{s['id']}/regenerate", json={**BRIEF, "business": "Skyline Villas"})
    assert "Skyline Villas" in r.json()["html"] and r.json()["slug"] == s["slug"]
    assert auth_client.delete(f"/api/sites/{s['id']}").status_code == 200
    assert auth_client.get("/api/sites").json() == []


def test_deploy_needs_hosting_tokens(auth_client):
    s = make_site(auth_client)
    for target in ("netlify", "vercel"):
        assert auth_client.post(f"/api/sites/{s['id']}/deploy", json={"target": target}).status_code == 400
    assert auth_client.post(f"/api/sites/{s['id']}/deploy", json={"target": "ftp"}).status_code == 400


def test_netlify_deploy(auth_client, mock_http):
    auth_client.post("/api/integrations/netlify/key", json={"values": {"api_token": "nf"}})
    s = make_site(auth_client)
    create = mock_http.post("https://api.netlify.com/api/v1/sites").respond(json={"id": "nsite"})
    deploy = mock_http.post("https://api.netlify.com/api/v1/sites/nsite/deploys").respond(
        json={"ssl_url": "https://skyline.netlify.app"})
    d = auth_client.post(f"/api/sites/{s['id']}/deploy", json={"target": "netlify"}).json()
    assert d["deploy_url"] == "https://skyline.netlify.app" and d["deploy_target"] == "netlify"
    assert deploy.calls[0].request.headers["content-type"] == "application/zip"
    # Redeploy reuses the same Netlify site.
    auth_client.post(f"/api/sites/{s['id']}/deploy", json={"target": "netlify"})
    assert create.call_count == 1 and deploy.call_count == 2


def test_vercel_deploy(auth_client, mock_http):
    auth_client.post("/api/integrations/vercel/key", json={"values": {"api_token": "vc"}})
    s = make_site(auth_client)
    mock_http.post("https://api.vercel.com/v13/deployments").respond(json={"url": "skyline.vercel.app"})
    d = auth_client.post(f"/api/sites/{s['id']}/deploy", json={"target": "vercel"}).json()
    assert d["deploy_url"] == "https://skyline.vercel.app"


def test_sites_are_private(auth_client, other_client):
    s = make_site(auth_client)
    assert other_client.get("/api/sites").json() == []
    for call in (lambda: other_client.get(f"/api/sites/{s['id']}"),
                 lambda: other_client.patch(f"/api/sites/{s['id']}", json={"html": "pwned"}),
                 lambda: other_client.post(f"/api/sites/{s['id']}/deploy", json={"target": "aimva"}),
                 lambda: other_client.delete(f"/api/sites/{s['id']}")):
        assert call().status_code == 404


# ---- leads ------------------------------------------------------------------
def test_lead_needs_contact(auth_client):
    assert auth_client.post("/api/leads", json={"name": "Nobody"}).status_code == 400


def test_duplicate_leads_are_merged(auth_client):
    auth_client.post("/api/leads", json={"name": "Asha", "email": "Asha@Corp.com", "message": "first"})
    auth_client.post("/api/leads", json={"email": "asha@corp.com", "phone": "+919000000001", "message": "second"})
    auth_client.post("/api/leads", json={"phone": "+919000000001", "message": "third"})
    leads = auth_client.get("/api/leads").json()
    assert len(leads) == 1
    l = leads[0]
    assert l["email"] == "asha@corp.com" and l["phone"] == "+919000000001"
    assert l["message"].split("\n") == ["first", "second", "third"]


def test_lead_scoring_rewards_intent_and_contact(auth_client):
    weak = auth_client.post("/api/leads", json={"email": "x@gmail.com"}).json()["score"]
    strong = auth_client.post("/api/leads", json={"email": "cto@bigco.com", "phone": "+919876543210",
                                                  "message": "We have budget and want a demo today, please send pricing",
                                                  "source": "voice"}).json()["score"]
    assert 0 <= weak < strong <= 100 and strong >= 70


def test_filters_patch_delete(auth_client):
    a = auth_client.post("/api/leads", json={"name": "Asha", "email": "a@x.com", "source": "website"}).json()
    auth_client.post("/api/leads", json={"name": "Bala", "phone": "+911111111111", "source": "voice"})
    assert [l["name"] for l in auth_client.get("/api/leads?source=voice").json()] == ["Bala"]
    assert [l["name"] for l in auth_client.get("/api/leads?q=ash").json()] == ["Asha"]
    r = auth_client.patch(f"/api/leads/{a['id']}", json={"stage": "won", "value": 5000})
    assert r.json()["stage"] == "won" and r.json()["value"] == 5000
    assert [l["name"] for l in auth_client.get("/api/leads?stage=won").json()] == ["Asha"]
    auth_client.delete(f"/api/leads/{a['id']}")
    assert len(auth_client.get("/api/leads").json()) == 1


def test_invalid_stage_rejected(auth_client):
    a = auth_client.post("/api/leads", json={"email": "a@x.com"}).json()
    assert auth_client.patch(f"/api/leads/{a['id']}", json={"stage": "banana"}).status_code == 422


def test_csv_export(auth_client):
    auth_client.post("/api/leads", json={"name": "Asha, Jr.", "email": "a@x.com", "message": 'said "hi"\nthen left'})
    r = auth_client.get("/api/leads/export.csv")
    assert r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][:3] == ["id", "created_at", "name"] and rows[1][2] == "Asha, Jr."


def test_csv_export_neutralises_formula_injection(auth_client):
    auth_client.post("/api/leads", json={"name": "=HYPERLINK(\"http://evil\")", "email": "a@x.com"})
    rows = list(csv.reader(io.StringIO(auth_client.get("/api/leads/export.csv").text)))
    assert not rows[1][2].startswith("=")


def test_google_sheets_sync(auth_client, db, mock_http):
    assert auth_client.post("/api/leads/sync/google").status_code == 200  # no leads -> no-op
    auth_client.post("/api/leads", json={"name": "Asha", "email": "a@x.com"})
    assert auth_client.post("/api/leads/sync/google").status_code == 400  # not connected
    connect(db, "owner@example.com", "google", {"access_token": "ya29", "expires_in": 3600}, {"sheet_id": "SHEET"})
    route = mock_http.post("https://sheets.googleapis.com/v4/spreadsheets/SHEET/values/A1:append").respond(json={})
    r = auth_client.post("/api/leads/sync/google")
    assert r.json() == {"ok": True, "count": 1}
    assert route.calls[0].request.headers["authorization"] == "Bearer ya29"
    assert auth_client.get("/api/leads").json()[0]["synced"] == {"google_sheets": True}


def test_auto_sync_on_new_lead(auth_client, db, mock_http):
    connect(db, "owner@example.com", "google", {"access_token": "ya29", "expires_in": 3600},
            {"sheet_id": "SHEET", "auto_sync": True})
    route = mock_http.post("https://sheets.googleapis.com/v4/spreadsheets/SHEET/values/A1:append").respond(json={})
    auth_client.post("/api/leads", json={"email": "a@x.com"})
    assert route.called
    assert auth_client.get("/api/leads").json()[0]["synced"] == {"google_sheets": True}


def test_onedrive_sync(auth_client, db, mock_http):
    auth_client.post("/api/leads", json={"email": "a@x.com"})
    assert auth_client.post("/api/leads/sync/onedrive").status_code == 400
    connect(db, "owner@example.com", "microsoft", {"access_token": "ms", "expires_in": 3600})
    route = mock_http.put("https://graph.microsoft.com/v1.0/me/drive/root:/AIMVA/leads.csv:/content").respond(json={})
    assert auth_client.post("/api/leads/sync/onedrive").json()["count"] == 1
    assert b"a@x.com" in route.calls[0].request.content


def test_leads_are_private(auth_client, other_client):
    a = auth_client.post("/api/leads", json={"email": "a@x.com"}).json()
    other_client.post("/api/leads", json={"email": "a@x.com"})  # same email, different tenant: no merge
    assert len(auth_client.get("/api/leads").json()) == 1
    assert other_client.patch(f"/api/leads/{a['id']}", json={"stage": "lost"}).status_code == 404
    other_client.delete(f"/api/leads/{a['id']}")
    assert auth_client.get("/api/leads").json()[0]["stage"] == "new"
    assert "a@x.com" in auth_client.get("/api/leads/export.csv").text
    assert other_client.get("/api/leads/export.csv").text.count("a@x.com") == 1
