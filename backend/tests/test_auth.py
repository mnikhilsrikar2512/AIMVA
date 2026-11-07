from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import EmailCode, User, utcnow
from app.security import COOKIE_NAME

from .conftest import PASSWORD, make_client, signup_and_verify


def signup(client, email="new@example.com", password=PASSWORD, name="New User"):
    return client.post("/api/auth/signup", json={"name": name, "email": email, "password": password})


# ---- sign up & verification ------------------------------------------------
def test_signup_returns_dev_code_when_smtp_missing(client):
    r = signup(client)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["email"] == "new@example.com"
    assert len(body["dev_code"]) == 6 and body["dev_code"].isdigit()


def test_password_and_code_are_never_stored_in_plain_text(client, db):
    code = signup(client).json()["dev_code"]
    user = db.scalar(select(User))
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash
    rec = db.scalar(select(EmailCode))
    assert rec.code_hash != code and len(rec.code_hash) == 64


@pytest.mark.parametrize("pw,msg", [
    ("short1", "at least 8"),
    ("onlyletters", "mix"),
    ("12345678", "mix"),
    ("a1" * 70, "too long"),
])
def test_weak_passwords_rejected(client, pw, msg):
    r = signup(client, password=pw)
    assert r.status_code == 400
    assert msg in r.json()["detail"]


@pytest.mark.parametrize("email", ["not-an-email", "a@b", "x@reserved.test", ""])
def test_invalid_emails_rejected(client, email):
    assert signup(client, email=email).status_code == 422


def test_email_is_case_insensitive(client):
    code = signup(client, email="MiXeD@Example.com").json()["dev_code"]
    r = client.post("/api/auth/verify-email", json={"email": "mixed@example.com", "code": code})
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "mixed@example.com"


def test_unverified_user_cannot_use_the_app(client):
    signup(client)
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"email": "new@example.com", "password": PASSWORD})
    assert r.status_code == 403
    assert r.json()["needs_verification"] is True


def test_verify_sets_session_cookie(client):
    code = signup(client).json()["dev_code"]
    r = client.post("/api/auth/verify-email", json={"email": "new@example.com", "code": code})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert COOKIE_NAME in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/auth/me").json()["user"]["name"] == "New User"


def test_wrong_code_counts_down_then_blocks(client):
    code = signup(client).json()["dev_code"]
    wrong = "000000" if code != "000000" else "111111"
    for left in (4, 3, 2, 1, 0):
        r = client.post("/api/auth/verify-email", json={"email": "new@example.com", "code": wrong})
        assert r.status_code == 400 and f"{left} attempts left" in r.json()["detail"]
    # Even the right code is refused after 5 misses.
    r = client.post("/api/auth/verify-email", json={"email": "new@example.com", "code": code})
    assert r.status_code == 400 and "Too many" in r.json()["detail"]


def test_expired_code_rejected(client, db):
    code = signup(client).json()["dev_code"]
    rec = db.scalar(select(EmailCode))
    rec.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    r = client.post("/api/auth/verify-email", json={"email": "new@example.com", "code": code})
    assert r.status_code == 400 and "expired" in r.json()["detail"]


def test_resend_has_cooldown_and_replaces_old_code(client, db):
    old = signup(client).json()["dev_code"]
    assert client.post("/api/auth/resend-code", json={"email": "new@example.com"}).status_code == 429
    rec = db.scalar(select(EmailCode))
    rec.created_at = utcnow() - timedelta(minutes=2)
    db.commit()
    new = client.post("/api/auth/resend-code", json={"email": "new@example.com"}).json()["dev_code"]
    if new != old:
        r = client.post("/api/auth/verify-email", json={"email": "new@example.com", "code": old})
        assert r.status_code == 400
    assert client.post("/api/auth/verify-email", json={"email": "new@example.com", "code": new}).status_code == 200


def test_resend_does_not_reveal_unknown_accounts(client):
    r = client.post("/api/auth/resend-code", json={"email": "ghost@example.com"})
    assert r.status_code == 200 and "dev_code" not in r.json()


def test_duplicate_verified_signup_conflicts(auth_client):
    r = make_client().post("/api/auth/signup", json={"name": "X", "email": "owner@example.com", "password": PASSWORD})
    assert r.status_code == 409


# ---- login / logout / lockout ------------------------------------------------
def test_login_and_logout(auth_client):
    c = make_client()
    r = c.post("/api/auth/login", json={"email": "OWNER@example.com", "password": PASSWORD})
    assert r.status_code == 200
    assert c.get("/api/auth/me").status_code == 200
    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").status_code == 401


def test_wrong_password_and_unknown_user_look_the_same(auth_client):
    c = make_client()
    a = c.post("/api/auth/login", json={"email": "owner@example.com", "password": "Wrong-pass1"})
    b = c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Wrong-pass1"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_account_locks_after_repeated_failures(auth_client):
    c = make_client()
    for _ in range(8):
        assert c.post("/api/auth/login", json={"email": "owner@example.com", "password": "Wrong-pass1"}).status_code == 401
    r = c.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    assert r.status_code == 423


def test_login_rate_limited_per_ip(client):
    codes = [client.post("/api/auth/login", json={"email": f"u{i}@example.com", "password": "Wrong-pass1"}).status_code
             for i in range(21)]
    assert codes[-1] == 429 and set(codes[:-1]) == {401}


def test_tampered_or_forged_cookie_rejected(auth_client):
    token = auth_client.cookies.get(COOKIE_NAME)
    c = make_client()
    c.cookies.set(COOKIE_NAME, token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb"))
    assert c.get("/api/auth/me").status_code == 401
    import jwt
    forged = jwt.encode({"sub": "1", "v": 0, "exp": 9999999999}, "a-completely-different-signing-key-1234", "HS256")
    c.cookies.set(COOKIE_NAME, forged)
    assert c.get("/api/auth/me").status_code == 401


# ---- password reset / change ---------------------------------------------------
def test_forgot_password_unknown_email_is_silent(client):
    r = client.post("/api/auth/forgot-password", json={"email": "ghost@example.com"})
    assert r.status_code == 200 and "dev_code" not in r.json()


def test_reset_password_flow_revokes_old_sessions(auth_client):
    other_device = make_client()
    other_device.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    assert other_device.get("/api/auth/me").status_code == 200

    c = make_client()
    code = c.post("/api/auth/forgot-password", json={"email": "owner@example.com"}).json()["dev_code"]
    assert c.post("/api/auth/reset-password", json={"email": "owner@example.com", "code": code, "password": "weak"}).status_code == 400
    r = c.post("/api/auth/reset-password", json={"email": "owner@example.com", "code": code, "password": "N3w-password!"})
    assert r.status_code == 200
    assert c.get("/api/auth/me").status_code == 200
    assert other_device.get("/api/auth/me").status_code == 401
    assert auth_client.get("/api/auth/me").status_code == 401
    # Code is single-use; old password no longer works.
    assert c.post("/api/auth/reset-password", json={"email": "owner@example.com", "code": code, "password": "An0ther-pass!"}).status_code == 400
    assert make_client().post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).status_code == 401


def test_change_password(auth_client):
    r = auth_client.post("/api/auth/change-password", json={"current_password": "nope-nope1", "new_password": "N3w-password!"})
    assert r.status_code == 400
    r = auth_client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "N3w-password!"})
    assert r.status_code == 200
    assert auth_client.get("/api/auth/me").status_code == 200  # this session is re-issued
    assert make_client().post("/api/auth/login", json={"email": "owner@example.com", "password": "N3w-password!"}).status_code == 200


def test_update_profile(auth_client):
    r = auth_client.patch("/api/auth/profile", json={"name": "  Renamed  ", "company": "Acme"})
    assert r.json()["user"]["name"] == "Renamed" and r.json()["user"]["company"] == "Acme"
    r = auth_client.patch("/api/auth/profile", json={"name": "   "})
    assert r.json()["user"]["name"] == "Renamed"  # blank names ignored


# ---- every protected route requires a session ---------------------------------
PROTECTED = [
    ("get", "/api/auth/me"), ("get", "/api/integrations"), ("get", "/api/content/models"),
    ("post", "/api/content/image"), ("get", "/api/content/assets"), ("get", "/api/sites"),
    ("post", "/api/sites"), ("get", "/api/leads"), ("get", "/api/leads/export.csv"),
    ("get", "/api/campaigns"), ("get", "/api/whatsapp/conversations"), ("post", "/api/whatsapp/send"),
    ("get", "/api/voice/agents"), ("get", "/api/voice/calls"), ("get", "/api/analytics/overview"),
    ("get", "/api/analytics/insights"), ("delete", "/api/integrations/meta"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_routes_require_login(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_health(client):
    r = client.get("/api/health")
    assert r.json() == {"ok": True}  # says nothing about which services are configured


# ---- account takeover through verify-email (regression) ----------------------------------------
def test_verify_email_cannot_sign_in_to_a_verified_account(auth_client):
    from .conftest import make_client
    attacker = make_client()
    r = attacker.post("/api/auth/verify-email", json={"email": "owner@example.com", "code": "000000"})
    assert r.status_code == 400
    assert attacker.get("/api/auth/me").status_code == 401


# ---- mobile app: Bearer tokens ----------------------------------------------------------------------
APP = {"X-AIMVA-Client": "app"}


def test_web_logins_never_expose_the_token(auth_client):
    from .conftest import PASSWORD
    r = auth_client.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    assert r.status_code == 200 and "token" not in r.json()


def test_app_signs_in_with_a_bearer_token(auth_client):
    from fastapi.testclient import TestClient
    from app.main import app
    from .conftest import PASSWORD
    phone = TestClient(app)
    r = phone.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD}, headers=APP)
    token = r.json()["token"]
    phone.cookies.clear()  # the app has no cookie jar
    assert phone.get("/api/auth/me").status_code == 401
    me = phone.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["user"]["email"] == "owner@example.com"
    assert phone.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_changing_password_revokes_old_app_tokens(auth_client):
    from fastapi.testclient import TestClient
    from app.main import app
    from .conftest import PASSWORD
    phone = TestClient(app)
    old = phone.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD}, headers=APP).json()["token"]
    phone.cookies.clear()
    bearer = {"Authorization": f"Bearer {old}", **APP}
    r = phone.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "N3w-password!"}, headers=bearer)
    new = r.json()["token"]
    phone.cookies.clear()
    assert phone.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert phone.get("/api/auth/me", headers={"Authorization": f"Bearer {new}"}).status_code == 200
