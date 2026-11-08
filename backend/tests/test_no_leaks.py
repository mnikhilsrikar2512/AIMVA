"""Every GET endpoint, swept: signed-out visitors get nothing private, and signed-in users never receive a password
hash, a one-time-code hash, an encrypted secret blob or a raw API key/token. Catches a new endpoint that returns a
whole database row by mistake."""
import json
import re

import pytest

from app.main import app

FORBIDDEN_KEYS = {"password_hash", "code_hash", "secret", "api_key", "access_token", "refresh_token",
                  "client_secret", "app_secret", "token_hash", "encrypted"}
KEY_LIKE = re.compile(r"(sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{35}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
                      r"[0-9a-f]{12}:[0-9a-f]{20,}|\$argon2)")
# Meant to be public: health checks, published sites, lead forms, webhooks, sign-in plumbing.
PUBLIC = ("/api/health", "/api/ready", "/api/public/", "/api/auth/", "/api/webhooks", "/api/whatsapp/webhook",
          "/api/voice/", "/api/billing/plans", "/api/integrations/oauth")
STREAMS = ("/api/events",)  # live-update stream never ends; covered by the signed-out check


def _get_routes():
    for path, ops in app.openapi()["paths"].items():
        if "get" in ops and "{" not in path and path.startswith("/api/"):
            yield path


def _bad_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in FORBIDDEN_KEYS and v not in ("", None, False, True, [], {}):
                yield f"{path}.{k}"
            yield from _bad_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:50]):
            yield from _bad_keys(v, f"{path}[{i}]")


ROUTES = sorted(set(_get_routes()))


@pytest.mark.parametrize("path", ROUTES)
def test_signed_out_gets_nothing_private(client, mock_http, path):
    if path.startswith(PUBLIC):
        pytest.skip("public by design")
    r = client.get(path)
    assert r.status_code in (401, 403, 404, 405, 422), f"{path} answered {r.status_code} without sign-in"


@pytest.mark.parametrize("path", ROUTES)
def test_signed_in_never_gets_secrets(auth_client, mock_http, path):
    if path in STREAMS:
        pytest.skip("endless stream")
    r = auth_client.get(path)
    if "json" not in r.headers.get("content-type", ""):
        return
    body = r.json()
    assert not list(_bad_keys(body)), f"{path} returned secret fields: {list(_bad_keys(body))}"
    assert not KEY_LIKE.search(json.dumps(body)), f"{path} returned something that looks like a key or hash"
