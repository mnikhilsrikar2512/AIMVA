"""The team app's own address: team-only APIs answer only there (TEAM_URL)."""
import pytest

from tests.conftest import make_client, signup_and_verify


@pytest.fixture
def team_url(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "team_url", "https://team.aimva.test")
    monkeypatch.setattr(settings, "admin_emails", {"owner@example.com"})


def test_console_answers_only_on_the_team_address(team_url):
    c = make_client()
    signup_and_verify(c)
    assert c.get("/api/console/me").status_code == 404  # the customer address (testserver)
    assert c.get("/api/admin/metrics").status_code == 404
    team = make_client()
    team.headers["host"] = "team.aimva.test"
    signup_and_verify(team, email="owner2@example.com")  # sign-in works on the team address too
    team.cookies.clear()
    r = team.post("/api/auth/login", json={"email": "owner@example.com", "password": "Sup3r-secret!"})
    assert r.status_code == 200
    assert team.get("/api/console/me").json()["role"] == "owner"
    assert c.get("/api/auth/me").status_code == 200  # customer APIs still work on the customer address


def test_without_team_url_everything_answers_everywhere(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "admin_emails", {"owner@example.com"})
    c = make_client()
    signup_and_verify(c)
    assert c.get("/api/console/me").status_code == 200


def test_team_address_is_not_a_customer_domain(team_url):
    from app.domains import team_host
    assert team_host() == "team.aimva.test"
