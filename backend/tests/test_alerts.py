from app import alerts
from tests.test_agents import lead_form, publish


def test_owner_is_emailed_the_moment_a_lead_arrives(auth_client, client, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, text, html="": sent.append((to, subject, text, html)) or True)
    s = publish(auth_client)
    lead_form(client, s["slug"], message="Do you have 3 BHK on a high floor?")
    assert len(sent) == 1
    to, subject, text, html = sent[0]
    assert to == "owner@example.com" and subject.startswith("New lead: Ravi Kumar")
    assert "high floor" in text and "https://wa.me/919812345678?text=Hi%20Ravi" in text and "/app/leads?lead=" in text
    assert "Reply on WhatsApp" in html

    assert auth_client.put("/api/agents/lead_alerts", json={"enabled": False}).status_code == 200
    lead_form(client, s["slug"], name="Sita", phone="+919800000001")
    assert len(sent) == 1  # switched off


def test_alerts_are_capped_and_skip_leads_you_typed_in(auth_client, client, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "send_email", lambda *a, **k: sent.append(a) or True)
    auth_client.post("/api/leads", json={"name": "Typed in", "phone": "+919800000002"})
    assert sent == []
    s = publish(auth_client)
    for i in range(alerts.ALERTS_PER_HOUR + 3):
        lead_form(client, s["slug"], name=f"P{i}", phone=f"+9198000001{i:02d}")
    assert len(sent) == alerts.ALERTS_PER_HOUR


def test_whatsapp_link_adds_india_code():
    assert alerts.wa_link("98123 45678", "Hi").startswith("https://wa.me/919812345678?text=Hi")
    assert alerts.wa_link("123", "Hi") == ""


def _decrypt(body: bytes, ua_key, auth: bytes) -> bytes:
    """The receiving browser's side of RFC 8291, to prove the message really decrypts."""
    import struct
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from app.push import _hkdf, _raw_public
    salt, (rs, idlen) = body[:16], struct.unpack("!IB", body[16:21])
    as_pub = body[21:21 + idlen]
    shared = ua_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
    ikm = _hkdf(auth, shared, b"WebPush: info\x00" + _raw_public(ua_key) + as_pub, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    return AESGCM(cek).decrypt(nonce, body[21 + idlen:], None).rstrip(b"\x02")


def test_phone_alert_is_encrypted_for_the_device_and_signed(auth_client, client, monkeypatch, mock_http, tmp_path):
    import json
    import os
    import jwt
    from cryptography.hazmat.primitives.asymmetric import ec
    from app import push
    monkeypatch.setattr(push, "KEY_FILE", tmp_path / "vapid.key")
    monkeypatch.setattr(alerts, "send_email", lambda *a, **k: True)
    ua = ec.generate_private_key(ec.SECP256R1())
    auth = os.urandom(16)
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": push.b64u(push._raw_public(ua)), "auth": push.b64u(auth)}}
    assert auth_client.post("/api/alerts/devices", json={**sub, "endpoint": "https://evil.example.com/x"}).status_code == 400
    assert auth_client.post("/api/alerts/devices", json=sub).json() == {"devices": 1}
    agents = {a["kind"]: a for a in auth_client.get("/api/agents").json()}
    assert agents["lead_alerts"]["config"]["push_devices"] == 1 and "push" not in agents["lead_alerts"]["config"]
    route = mock_http.post("https://fcm.googleapis.com/fcm/send/abc").respond(201)
    s = publish(auth_client)
    lead_form(client, s["slug"], message="Is parking included?")
    req = route.calls.last.request
    msg = json.loads(_decrypt(req.content, ua, auth))
    assert msg["title"] == "New lead: Ravi Kumar" and msg["body"] == "Is parking included?" and msg["url"].startswith("/app/leads?lead=")
    assert req.headers["Content-Encoding"] == "aes128gcm"
    token = req.headers["Authorization"].split("t=")[1].split(",")[0]
    k = req.headers["Authorization"].split("k=")[1]
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), push.unb64u(k))
    assert jwt.decode(token, pub, algorithms=["ES256"], audience="https://fcm.googleapis.com")["sub"].startswith("mailto:")
    assert k == auth_client.get("/api/alerts/push-key").json()["key"]

    mock_http.post("https://fcm.googleapis.com/fcm/send/abc").respond(410)  # the phone unsubscribed
    lead_form(client, s["slug"], name="Gone", phone="+919800000077")
    assert {a["kind"]: a for a in auth_client.get("/api/agents").json()}["lead_alerts"]["config"]["push_devices"] == 0


def test_push_encryption_matches_the_rfc_8291_example():
    from cryptography.hazmat.primitives.asymmetric import ec
    from app import push
    as_key = ec.derive_private_key(int.from_bytes(push.unb64u("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"), ec.SECP256R1())
    out = push.encrypt(b"When I grow up, I want to be a watermelon",
                       "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
                       "BTBZMqHH6r4Tts7J_aSIgg", salt=push.unb64u("DGv6ra1nlYgDCS1FRnbzlw"), server_key=as_key)
    assert push.b64u(out) == ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_"
                              "yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")
