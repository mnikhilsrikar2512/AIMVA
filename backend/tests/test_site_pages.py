"""Extra pages on a site: same design, shared menu, one address; and the lead form follows an address change."""
import io
import zipfile

from app.routers import sites as S

from .test_site_ai_edit import fake_writer
from .test_sites_leads import make_site


def publish(c, s, slug="skyline"):
    r = c.post(f"/api/sites/{s['id']}/publish", json={"name": s["name"], "slug": slug})
    assert r.status_code == 200, r.text
    return r.json()


def test_add_page_without_ai_reuses_design_and_footer(auth_client):
    s = make_site(auth_client)
    out = auth_client.post(f"/api/sites/{s['id']}/pages", json={"title": "About us", "about": "Family builders since 1998"}).json()
    [p] = out["pages"]
    assert p["slug"] == "about-us" and p["title"] == "About us"
    assert "Family builders since 1998" in p["html"] and "<title>About us · Skyline Homes</title>" in p["html"]
    assert "<footer" in p["html"] and "--p:" in p["html"]  # the home page's styles and footer
    assert "/lead" in p["html"]  # forms on extra pages still reach your leads
    assert auth_client.get("/api/sites").json()[0]["pages"] == [{"slug": "about-us", "title": "About us"}]  # list stays light


def test_add_page_with_ai_uses_sections(auth_client, monkeypatch):
    s = make_site(auth_client)
    monkeypatch.setattr(S, "writer", fake_writer('<section data-aimva-section="plans"><h2 onclick="x()">Our plans</h2></section>'))
    p = auth_client.post(f"/api/sites/{s['id']}/pages", json={"title": "Pricing"}).json()["pages"][0]
    assert "Our plans" in p["html"] and "onclick" not in p["html"]


def test_page_slugs_are_unique_and_reserved_names_avoided(auth_client):
    s = make_site(auth_client)
    for t in ("Gallery", "Gallery", "Brochure"):
        out = auth_client.post(f"/api/sites/{s['id']}/pages", json={"title": t}).json()
    assert [p["slug"] for p in out["pages"]] == ["gallery", "gallery-2", "brochure-page"]


def test_published_pages_share_a_menu(auth_client, client):
    s = make_site(auth_client)
    auth_client.post(f"/api/sites/{s['id']}/pages", json={"title": "About"})
    publish(auth_client, s)
    home, about = client.get("/s/skyline"), client.get("/s/skyline/about")
    assert home.status_code == 200 and about.status_code == 200
    assert 'href="/s/skyline/about"' in home.text and 'href="/s/skyline"' in about.text and "data-aimva-nav" in about.text
    assert about.headers["content-security-policy"].startswith("sandbox")
    assert client.get("/s/skyline/nope").status_code == 404


def test_single_page_sites_get_no_menu(auth_client, client):
    s = make_site(auth_client)
    publish(auth_client, s)
    assert "data-aimva-nav" not in client.get("/s/skyline").text


def test_edit_rename_and_delete_page(auth_client, other_client):
    s = make_site(auth_client)
    auth_client.post(f"/api/sites/{s['id']}/pages", json={"title": "About"})
    url = f"/api/sites/{s['id']}/pages/about"
    assert other_client.patch(url, json={"html": "<p>x</p>"}).status_code == 404
    p = auth_client.patch(url, json={"html": "<html><body><p>Edited</p></body></html>", "title": "Our story"}).json()["pages"][0]
    assert p["title"] == "Our story" and "Edited" in p["html"] and p["slug"] == "about"
    assert auth_client.delete(url).json()["pages"] == []
    assert auth_client.delete(url).status_code == 404


def test_whole_page_ai_edit_on_an_extra_page(auth_client, monkeypatch):
    s = make_site(auth_client)
    auth_client.post(f"/api/sites/{s['id']}/pages", json={"title": "About"})
    monkeypatch.setattr(S, "writer", fake_writer("<html><body><h1>New about</h1><form data-aimva-lead></form></body></html>"))
    out = auth_client.post(f"/api/sites/{s['id']}/ai-edit", json={"instruction": "warmer tone", "page": "about"}).json()["site"]
    assert "New about" in out["pages"][0]["html"] and "/lead" in out["pages"][0]["html"]
    assert "New about" not in out["html"]


def test_page_limit(auth_client, monkeypatch):
    monkeypatch.setattr(S, "MAX_PAGES", 2)
    s = make_site(auth_client)
    for t in ("A1", "B1"):
        auth_client.post(f"/api/sites/{s['id']}/pages", json={"title": t})
    assert auth_client.post(f"/api/sites/{s['id']}/pages", json={"title": "C1"}).status_code == 400


def test_lead_form_follows_a_new_address(auth_client, client):
    s = make_site(auth_client)
    auth_client.post(f"/api/sites/{s['id']}/pages", json={"title": "About"})
    old = s["slug"]
    publish(auth_client, s, "new-address")
    site = auth_client.get(f"/api/sites/{s['id']}").json()
    assert f"/api/public/sites/{old}/" not in site["html"] and "/api/public/sites/new-address/lead" in site["html"]
    assert "/api/public/sites/new-address/lead" in site["pages"][0]["html"]
    assert client.post("/api/public/sites/new-address/lead", data={"name": "Ravi", "phone": "+91 98765 43210"}).json()["ok"]


def test_netlify_deploy_includes_every_page(auth_client, mock_http):
    auth_client.post("/api/integrations/netlify/key", json={"values": {"api_token": "nf"}})
    s = make_site(auth_client)
    auth_client.post(f"/api/sites/{s['id']}/pages", json={"title": "About"})
    mock_http.post("https://api.netlify.com/api/v1/sites").respond(json={"id": "nsite"})
    deploy = mock_http.post("https://api.netlify.com/api/v1/sites/nsite/deploys").respond(json={"ssl_url": "https://x.netlify.app"})
    assert auth_client.post(f"/api/sites/{s['id']}/deploy", json={"target": "netlify"}).status_code == 200
    z = zipfile.ZipFile(io.BytesIO(deploy.calls.last.request.content))
    assert sorted(z.namelist()) == ["about/index.html", "index.html"]
    assert 'href="/about/"' in z.read("index.html").decode()
