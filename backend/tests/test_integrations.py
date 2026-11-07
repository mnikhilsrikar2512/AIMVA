from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy import select

from app.config import settings
from app.models import Integration, utcnow
from app.routers.integrations import oauth_access_token
from app.security import decrypt_json

from .helpers import connect


def test_lists_every_provider_disconnected(auth_client):
    rows = {r["provider"]: r for r in auth_client.get("/api/integrations").json()}
    assert {"meta", "google", "linkedin", "microsoft", "fal", "whatsapp", "twilio", "netlify", "vercel"} <= set(rows)
    assert not any(r["connected"] for r in rows.values())
    assert rows["meta"]["app_configured"] is False  # no META_APP_ID in test env
    assert rows["fal"]["type"] == "api_key" and rows["fal"]["fields"] == ["api_key"]


def test_save_api_key_encrypts_and_never_returns_secret(auth_client, db):
    r = auth_client.post("/api/integrations/whatsapp/key", json={"values": {"access_token": "EAAG-secret", "phone_number_id": "PN1"}})
    assert r.status_code == 200
    row = next(i for i in auth_client.get("/api/integrations").json() if i["provider"] == "whatsapp")
    assert row["connected"] and row["meta"] == {"phone_number_id": "PN1"}
    assert "EAAG-secret" not in str(auth_client.get("/api/integrations").json())
    stored = db.scalar(select(Integration))
    assert "EAAG-secret" not in stored.secret
    assert decrypt_json(stored.secret) == {"access_token": "EAAG-secret"}


def test_save_key_validates_fields_and_provider(auth_client):
    assert auth_client.post("/api/integrations/twilio/key", json={"values": {"account_sid": "AC1"}}).status_code == 400
    assert auth_client.post("/api/integrations/nope/key", json={"values": {}}).status_code == 404


def test_reconnect_replaces_instead_of_duplicating(auth_client, db):
    for k in ("one", "two"):
        auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": k}})
    rows = db.scalars(select(Integration)).all()
    assert len(rows) == 1 and decrypt_json(rows[0].secret) == {"api_key": "two"}


def test_oauth_refuses_when_app_not_configured(auth_client):
    r = auth_client.get("/api/integrations/meta/connect")
    assert r.status_code == 400 and "isn't switched on yet" in r.json()["detail"] and ".env" not in r.json()["detail"]


def test_oauth_full_flow(auth_client, mock_http, monkeypatch, db):
    monkeypatch.setattr(settings, "google_client_id", "gid")
    monkeypatch.setattr(settings, "google_client_secret", "gsecret")
    url = auth_client.get("/api/integrations/google/connect").json()["url"]
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://accounts.google.com/") and q["client_id"] == ["gid"]
    assert q["redirect_uri"] == ["http://testserver/api/integrations/google/callback"]
    assert q["access_type"] == ["offline"]

    token_route = mock_http.post("https://oauth2.googleapis.com/token").respond(
        json={"access_token": "ya29", "refresh_token": "1//r", "expires_in": 3600})
    r = auth_client.get("/api/integrations/google/callback", params={"code": "abc", "state": q["state"][0]},
                        follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].endswith("connected=google")
    assert token_route.called
    assert b"client_secret=gsecret" in token_route.calls[0].request.content
    assert decrypt_json(db.scalar(select(Integration)).secret)["access_token"] == "ya29"


def test_oauth_callback_rejects_bad_state(client):
    r = client.get("/api/integrations/google/callback", params={"code": "x", "state": "forged"}, follow_redirects=False)
    assert "error=invalid_state" in r.headers["location"]
    r = client.get("/api/integrations/google/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert "error=access_denied" in r.headers["location"]


def test_oauth_state_for_one_provider_cannot_complete_another(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "gid")
    state = parse_qs(urlparse(auth_client.get("/api/integrations/google/connect").json()["url"]).query)["state"][0]
    r = auth_client.get("/api/integrations/meta/callback", params={"code": "x", "state": state}, follow_redirects=False)
    assert "error=invalid_state" in r.headers["location"]


def test_expired_oauth_token_is_refreshed(auth_client, db, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "gid")
    integ = connect(db, "owner@example.com", "google", {"access_token": "old", "refresh_token": "r1", "expires_in": 3600})
    integ.connected_at = utcnow() - timedelta(hours=2)
    db.commit()
    mock_http.post("https://oauth2.googleapis.com/token").respond(json={"access_token": "fresh", "expires_in": 3600})
    assert oauth_access_token(db, integ.user_id, "google") == "fresh"
    db.refresh(integ)
    assert decrypt_json(integ.secret)["refresh_token"] == "r1"  # kept across refresh


def test_update_meta_and_disconnect(auth_client, db):
    assert auth_client.patch("/api/integrations/google/meta", json={"meta": {"sheet_id": "S"}}).status_code == 400
    connect(db, "owner@example.com", "google", {"access_token": "t"})
    r = auth_client.patch("/api/integrations/google/meta", json={"meta": {"sheet_id": "S", "auto_sync": True}})
    assert r.json()["meta"] == {"sheet_id": "S", "auto_sync": True}
    assert auth_client.delete("/api/integrations/google").status_code == 200
    assert db.scalar(select(Integration)) is None


def test_integrations_are_per_user(auth_client, other_client):
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "k"}})
    assert "fal" not in {i["provider"] for i in other_client.get("/api/integrations").json()}  # platform engines: owner only
    other_client.delete("/api/integrations/fal")
    assert next(i for i in auth_client.get("/api/integrations").json() if i["provider"] == "fal")["connected"]


import pytest


@pytest.mark.real_verify
def test_fal_key_is_verified_before_saving(auth_client, mock_http):
    route = mock_http.get(url__startswith="https://queue.fal.run/").mock(side_effect=[
        httpx.Response(401, json={"detail": "Authentication is required"}),
        httpx.Response(404, json={"status": "NOT_FOUND"}),
    ])
    bad = auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "only-part-of-a-key"}})
    assert bad.status_code == 400 and "contain a colon" in bad.json()["detail"]
    assert not next(i for i in auth_client.get("/api/integrations").json() if i["provider"] == "fal")["connected"]
    good = auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "abc-123:secret456"}})
    assert good.status_code == 200 and route.calls[1].request.headers["authorization"] == "Key abc-123:secret456"


@pytest.mark.real_verify
def test_key_saved_when_provider_unreachable(auth_client, mock_http):
    mock_http.get(url__startswith="https://queue.fal.run/").mock(side_effect=httpx.ConnectError("offline"))
    assert auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "a:b"}}).status_code == 200


def test_fal_hint_exposed(auth_client):
    fal = next(i for i in auth_client.get("/api/integrations").json() if i["provider"] == "fal")
    assert "colon" in fal["hints"]["api_key"]


def test_oauth_callback_must_finish_in_the_browser_that_started_it(auth_client, other_client, mock_http, monkeypatch, db):
    """Regression: the state carried the starter's user id and the callback trusted it from any browser, so a victim
    opening someone else's connect link linked their ad account into the other person's AIMVA login."""
    monkeypatch.setattr(settings, "google_client_id", "gid")
    monkeypatch.setattr(settings, "google_client_secret", "gsecret")
    state = parse_qs(urlparse(auth_client.get("/api/integrations/google/connect").json()["url"]).query)["state"][0]
    token_route = mock_http.post("https://oauth2.googleapis.com/token").respond(json={"access_token": "victim"})
    r = other_client.get("/api/integrations/google/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    assert "error=invalid_state" in r.headers["location"]
    assert not token_route.called and db.scalar(select(Integration)) is None
    # The browser that started it still finishes, and the nonce can't be replayed afterwards.
    r = auth_client.get("/api/integrations/google/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    assert r.headers["location"].endswith("connected=google")
    r = auth_client.get("/api/integrations/google/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    assert "error=invalid_state" in r.headers["location"]
