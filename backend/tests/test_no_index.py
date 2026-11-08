"""App pages and the API tell search engines and AI crawlers to stay out; customers' sites stay indexable."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_api_is_noindex():
    r = client.get("/api/health")
    assert "noindex" in r.headers["x-robots-tag"] and "noai" in r.headers["x-robots-tag"]


def test_published_sites_and_landing_stay_indexable():
    assert "x-robots-tag" not in client.get("/s/some-site").headers
    assert "x-robots-tag" not in client.get("/").headers


def test_customer_domain_pages_stay_indexable():
    r = client.get("/about", headers={"host": "shop.example.in"})
    assert "x-robots-tag" not in r.headers
