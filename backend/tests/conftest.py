"""Test harness: throwaway SQLite DB, no SMTP/AI keys, fresh tables and rate limits per test.

External HTTP (Meta, Google, fal.ai, Netlify, Twilio...) is mocked with respx, so the suite never
touches the network.
"""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="aimva-test-")
os.environ.update({
    # TEST_DATABASE_URL=postgresql+psycopg://... runs the whole suite on Postgres (what production uses).
    "DATABASE_URL": os.getenv("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db",
    "UPLOADS_DIR": f"{_tmp}/uploads",
    "ALLOW_PRIVATE_PROVIDERS": "true",
    "SECRET_KEY": "test-secret-key-that-is-long-enough-123",
    "SMTP_USER": "", "SMTP_PASSWORD": "",
    "GEMINI_API_KEY": "", "FAL_KEY": "", "FREE_AI": "false", "AGENTS_SCHEDULER": "false", "POLLINATIONS_TOKEN": "",
    "META_APP_ID": "", "META_APP_SECRET": "test-meta-app-secret", "GOOGLE_CLIENT_ID": "", "LINKEDIN_CLIENT_ID": "", "MICROSOFT_CLIENT_ID": "",
    "TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "",
    "PUBLIC_URL": "http://testserver", "FRONTEND_URL": "http://frontend.test",
})

import pytest  # noqa: E402
import respx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import security  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "Sup3r-secret!"


@pytest.fixture(autouse=True)
def fresh_state():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    security._last_prune = 0.0
    yield


@pytest.fixture(autouse=True)
def hermetic_dns(monkeypatch):
    """No real DNS in tests: the SSRF guard (providers.safe_url) resolves names, which fails offline or behind a proxy.
    Public names resolve to a public documentation IP; files that need private ranges override this fixture."""
    import socket

    def getaddrinfo(host, port, *a, **k):
        if str(host).endswith(".invalid"):
            raise socket.gaierror("not found")
        ip = "127.0.0.1" if host in ("localhost", "127.0.0.1", "testserver") else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 443))]
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


@pytest.fixture(autouse=True)
def no_live_key_checks(monkeypatch, request):
    if "real_verify" not in request.keywords:
        from app.routers import integrations
        monkeypatch.setattr(integrations, "verify_key", lambda provider, values: None)


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def mock_http():
    with respx.mock(assert_all_called=False) as router:
        yield router


def make_client() -> TestClient:
    return TestClient(app)


def signup_and_verify(client: TestClient, email="owner@example.com", name="Owner", password=PASSWORD) -> dict:
    r = client.post("/api/auth/signup", json={"name": name, "email": email, "password": password})
    assert r.status_code == 200, r.text
    r = client.post("/api/auth/verify-email", json={"email": email, "code": r.json()["dev_code"]})
    assert r.status_code == 200, r.text
    return r.json()["user"]


@pytest.fixture
def client():
    return make_client()


@pytest.fixture
def auth_client():
    c = make_client()
    signup_and_verify(c)
    return c


@pytest.fixture
def other_client():
    """A second, unrelated verified user, for data-isolation checks."""
    c = make_client()
    signup_and_verify(c, email="intruder@example.com", name="Intruder")
    return c
