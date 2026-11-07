"""Signature checks for inbound webhooks, so nobody can forge WhatsApp messages or drive phone calls.

- Meta (WhatsApp Cloud API) signs each POST with X-Hub-Signature-256: "sha256=" + HMAC-SHA256(app secret, raw body).
- Twilio signs each request with X-Twilio-Signature: base64(HMAC-SHA1(auth token, full URL + sorted POST params)).
"""
import base64
import hashlib
import hmac
import logging

from fastapi import HTTPException, Request

from .config import settings

log = logging.getLogger(__name__)


def _is_local() -> bool:
    return any(h in settings.public_url for h in ("localhost", "127.0.0.1"))


def check_meta_signature(raw_body: bytes, header: str) -> None:
    secret = settings.meta_app_secret
    if not secret:
        if _is_local():
            log.warning("META_APP_SECRET is not set: accepting an unsigned WhatsApp webhook (local development only).")
            return
        raise HTTPException(403, "Webhook signing isn't set up on this server (META_APP_SECRET).")
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not header or not hmac.compare_digest(expected, header.strip()):
        raise HTTPException(403, "Invalid webhook signature.")


def twilio_signature(auth_token: str, url: str, params: dict) -> str:
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()).decode()


def public_request_url(request: Request) -> str:
    """The URL Twilio called. Behind a proxy request.url is the internal address, so rebuild it from PUBLIC_URL,
    which is also the base we hand to Twilio for every callback."""
    url = settings.public_url.rstrip("/") + request.url.path
    return url + (f"?{request.url.query}" if request.url.query else "")


class TwilioRequest:
    """What's needed to check a Twilio signature, read up front so the endpoint itself can stay synchronous
    (it does database work and may call an AI provider, which must not block the event loop)."""
    def __init__(self, url: str, params: dict, signature: str):
        self.url, self.params, self.signature = url, params, signature

    def verify(self, auth_token: str) -> None:
        if not auth_token:
            raise HTTPException(403, "Twilio isn't connected for this call.")
        if not hmac.compare_digest(twilio_signature(auth_token, self.url, self.params), self.signature):
            raise HTTPException(403, "Invalid Twilio signature.")


async def twilio_request(request: Request) -> TwilioRequest:
    form = await request.form()
    params = {k: v for k, v in form.items() if isinstance(v, str)}
    return TwilioRequest(public_request_url(request), params, request.headers.get("x-twilio-signature", ""))
