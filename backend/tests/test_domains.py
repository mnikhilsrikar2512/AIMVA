"""Custom domains: add, verify via DNS, serve on the customer's host, and gate HTTPS certificates."""
import pytest

from app import domains

from .test_sites_leads import make_site

APP_IP, OTHER_IP = "203.0.113.10", "198.51.100.7"


@pytest.fixture
def dns(monkeypatch):
    """Which addresses each name resolves to; the app host (testserver) is APP_IP."""
    table = {"testserver": {APP_IP}}
    monkeypatch.setattr(domains, "_addresses", lambda host: table.get(host, set()))
    domains._cache.clear()
    return table


def published(c, **over):
    s = make_site(c, **over)
    assert c.post(f"/api/sites/{s['id']}/deploy", json={"target": "aimva"}).status_code == 200
    return s


def test_domain_is_served_only_after_dns_points_here(auth_client, client, dns):
    s = published(auth_client)
    r = auth_client.patch(f"/api/sites/{s['id']}", json={"custom_domain": "https://Offers.Skyline.example/"})
    assert r.json()["custom_domain"] == "offers.skyline.example" and r.json()["domain_verified"] is False
    d = auth_client.get(f"/api/sites/{s['id']}/domain").json()
    assert d["records"] == [{"type": "CNAME", "name": "offers", "value": "testserver"}] and not d["verified"]

    dns["offers.skyline.example"] = {OTHER_IP}  # still pointing at the old host
    v = auth_client.post(f"/api/sites/{s['id']}/domain/verify").json()
    assert not v["verified"] and "doesn't point to AIMVA" in v["detail"]
    assert client.get("/", headers={"Host": "offers.skyline.example"}).status_code == 404
    assert client.get("/api/public/domains/allowed?domain=offers.skyline.example").status_code == 404

    dns["offers.skyline.example"] = {APP_IP}
    v = auth_client.post(f"/api/sites/{s['id']}/domain/verify").json()
    assert v["verified"] and v["url"] == "https://offers.skyline.example"
    assert client.get("/api/public/domains/allowed?domain=offers.skyline.example").status_code == 200
    home = client.get("/", headers={"Host": "offers.skyline.example"})
    assert home.status_code == 200 and "Skyline Homes" in home.text


def test_customer_domain_never_serves_the_app_or_its_api(auth_client, client, dns):
    s = published(auth_client)
    auth_client.patch(f"/api/sites/{s['id']}", json={"custom_domain": "skyline.example"})
    dns["skyline.example"] = {APP_IP}
    auth_client.post(f"/api/sites/{s['id']}/domain/verify")
    h = {"Host": "skyline.example"}
    assert client.get("/api/auth/me", headers=h).status_code == 404
    assert client.post("/api/auth/login", headers=h, json={"email": "a@b.c", "password": "x"}).status_code == 404
    assert client.get("/api/health", headers=h).status_code == 404
    lead = client.post(f"/api/public/sites/{s['slug']}/lead", headers=h, data={"name": "Ravi", "phone": "+91 90000 11111"})
    assert lead.status_code == 200  # the site's own form still works
    assert client.get("/no/such/deep/path", headers=h).status_code == 404


def test_bare_domain_gets_an_a_record(auth_client, dns):
    s = published(auth_client)
    auth_client.patch(f"/api/sites/{s['id']}", json={"custom_domain": "skyline.example"})
    assert auth_client.get(f"/api/sites/{s['id']}/domain").json()["records"] == [{"type": "A", "name": "@", "value": APP_IP}]


def test_changing_the_domain_needs_verifying_again(auth_client, client, dns):
    s = published(auth_client)
    auth_client.patch(f"/api/sites/{s['id']}", json={"custom_domain": "a.skyline.example"})
    dns["a.skyline.example"] = dns["b.skyline.example"] = {APP_IP}
    assert auth_client.post(f"/api/sites/{s['id']}/domain/verify").json()["verified"]
    r = auth_client.patch(f"/api/sites/{s['id']}", json={"custom_domain": "b.skyline.example"}).json()
    assert r["domain_verified"] is False
    assert client.get("/", headers={"Host": "a.skyline.example"}).status_code == 404


def test_domain_rules(auth_client, other_client, dns):
    s = published(auth_client)
    for bad in ("not a domain", "testserver", "x.testserver", "localhost"):
        assert auth_client.patch(f"/api/sites/{s['id']}", json={"custom_domain": bad}).status_code == 400, bad
    assert auth_client.patch(f"/api/sites/{s['id']}", json={"custom_domain": "taken.example"}).status_code == 200
    s2 = published(other_client, business="Other Co")
    assert other_client.patch(f"/api/sites/{s2['id']}", json={"custom_domain": "TAKEN.example"}).status_code == 409
    assert other_client.get(f"/api/sites/{s['id']}/domain").status_code == 404
    assert other_client.post(f"/api/sites/{s['id']}/domain/verify").status_code == 404


def test_unpublished_site_is_not_served_on_its_domain(auth_client, client, dns):
    s = published(auth_client)
    auth_client.patch(f"/api/sites/{s['id']}", json={"custom_domain": "skyline.example"})
    dns["skyline.example"] = {APP_IP}
    auth_client.post(f"/api/sites/{s['id']}/domain/verify")
    auth_client.patch(f"/api/sites/{s['id']}", json={"published": False})
    domains._cache.clear()
    assert client.get("/", headers={"Host": "skyline.example"}).status_code == 404
    assert client.get("/api/public/domains/allowed?domain=skyline.example").status_code == 404
