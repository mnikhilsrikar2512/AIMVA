"""Phone alerts through Web Push (the browser's own push service: Google on Android/Chrome, Apple on iPhone once
AIMVA is added to the home screen, Mozilla on Firefox). No extra library: the message is encrypted here as
RFC 8291 (aes128gcm) and signed with a VAPID key (RFC 8292), using `cryptography` and PyJWT we already ship.

Keys: VAPID_PRIVATE_KEY (base64url of the raw 32-byte P-256 key) if set, else one is made once and kept in
data/vapid.key next to the uploads, so subscriptions survive restarts. Subscriptions live in the lead_alerts
agent setting (config["push"]), at most MAX_DEVICES per account.
"""
import base64
import hashlib
import hmac
import logging
import os
import struct
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .brand import UPLOADS

log = logging.getLogger("aimva.push")
MAX_DEVICES = 5
# Only real push services: the endpoint comes from the browser, so anything else could point us at any server.
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", ".push.apple.com", ".notify.windows.com",
              "android.googleapis.com")
KEY_FILE = Path(os.getenv("VAPID_KEY_FILE") or UPLOADS.parent / "vapid.key")


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _private_key() -> ec.EllipticCurvePrivateKey:
    raw = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    if not raw and KEY_FILE.exists():
        raw = KEY_FILE.read_text().strip()
    if raw:
        return ec.derive_private_key(int.from_bytes(unb64u(raw), "big"), ec.SECP256R1())
    key = ec.generate_private_key(ec.SECP256R1())
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(b64u(key.private_numbers().private_value.to_bytes(32, "big")))
    os.chmod(KEY_FILE, 0o600)
    return key


def _raw_public(key) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def public_key() -> str:
    """What the browser needs to subscribe (applicationServerKey)."""
    return b64u(_raw_public(_private_key()))


def allowed_endpoint(url: str) -> bool:
    u = urlparse(url or "")
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or (h.startswith(".") and host.endswith(h)) for h in PUSH_HOSTS)


def _hkdf(salt: bytes, ikm: bytes, info: bytes, n: int) -> bytes:
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:n]  # n <= 32: one block is enough


def encrypt(payload: bytes, p256dh: str, auth: str, salt: Optional[bytes] = None,
            server_key: Optional[ec.EllipticCurvePrivateKey] = None) -> bytes:
    """RFC 8291 message body: salt | record size | key id | AES-128-GCM ciphertext."""
    ua_pub = unb64u(p256dh)
    secret = unb64u(auth)
    as_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_pub = _raw_public(as_key)
    shared = as_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub))
    ikm = _hkdf(secret, shared, b"WebPush: info\x00" + ua_pub + as_pub, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack("!IB", 4096, len(as_pub)) + as_pub + body


def _vapid_header(endpoint: str) -> str:
    from .config import settings
    key = _private_key()
    u = urlparse(endpoint)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    sub = settings.mail_from or "alerts@aimva.app"
    token = jwt.encode({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": f"mailto:{sub}"},
                       pem, algorithm="ES256")
    return f"vapid t={token}, k={b64u(_raw_public(key))}"


def send(sub: dict, payload: bytes, ttl: int = 86400) -> int:
    """Deliver one message. Returns the push service's status (201 = accepted, 404/410 = device gone)."""
    if not allowed_endpoint(sub.get("endpoint", "")):
        return 400
    keys = sub.get("keys") or {}
    body = encrypt(payload, keys["p256dh"], keys["auth"])
    r = httpx.post(sub["endpoint"], content=body, timeout=10, headers={
        "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": str(ttl), "Urgency": "high",
        "Authorization": _vapid_header(sub["endpoint"])})
    return r.status_code
