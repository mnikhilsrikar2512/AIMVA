"""Platform keys stay on the server: capability resolution, multilingual voice, and nothing leaking to customers."""
import base64
import re
import time
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

from app import ai_registry, speech
from app.config import settings

SECRETS = {"SARVAM_API_KEY": "sv-SECRET-111", "AI_API_KEY": "shared-SECRET-222"}
VENDOR = re.compile(r"\b(sarvam|fal|fal\.ai|gemini|pollinations|flux|ltx|kling|luma)\b", re.I)


@pytest.fixture
def clean_env(monkeypatch):
    for k in ai_registry.env_variables():
        if k not in ("FREE_AI", "ALLOW_USER_AI_KEYS"):
            monkeypatch.setenv(k, "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "fal_key", "")
    monkeypatch.setattr(settings, "free_ai", False)
    return monkeypatch


# ---- resolution order --------------------------------------------------------------------------
def test_each_capability_resolves_own_then_legacy_then_shared_then_fallback(clean_env):
    m = clean_env
    assert ai_registry.resolve("tts").provider == "builtin" and not ai_registry.resolve("tts").live
    assert ai_registry.resolve("text").provider == "rules" and ai_registry.resolve("video").provider == ""

    m.setenv("AI_PROVIDER", "fal"); m.setenv("AI_API_KEY", "shared")            # one key for everything
    img = ai_registry.resolve("image")
    assert (img.provider, img.key, img.source) == ("fal", "shared", "shared") and ai_registry.resolve("video").live
    assert not ai_registry.resolve("tts").live                                  # fal can't speak: not used for voice
    assert ai_registry.resolve("text").provider == "rules"

    m.setenv("SARVAM_API_KEY", "legacy")                                         # legacy variable beats the shared key
    assert (ai_registry.resolve("tts").provider, ai_registry.resolve("tts").source) == ("sarvam", "legacy")
    m.setenv("TTS_PROVIDER", "sarvam"); m.setenv("TTS_API_KEY", "own"); m.setenv("TTS_MODEL", "bulbul:v4-flash")
    tts = ai_registry.resolve("tts")                                             # its own key beats everything
    assert (tts.key, tts.source, tts.model) == ("own", "own", "bulbul:v4-flash")

    m.setenv("IMAGE_PROVIDER", "sarvam"); m.setenv("IMAGE_API_KEY", "nope")      # a provider that can't do it is skipped
    assert ai_registry.resolve("image").provider == "fal"
    m.setattr(settings, "free_ai", True); m.setenv("AI_PROVIDER", ""); m.setenv("AI_API_KEY", "")
    assert ai_registry.resolve("image").provider == "free" and not ai_registry.resolve("image").live


def test_customers_own_keys_are_ignored_while_the_flag_is_off(clean_env, auth_client):
    from app.db import SessionLocal
    from app.models import Integration
    from app.security import encrypt_json
    from app.services import gemini_key
    uid = auth_client.get("/api/auth/me").json()["user"]["id"]
    with SessionLocal() as db:
        db.add(Integration(user_id=uid, provider="gemini", secret=encrypt_json({"api_key": "users-own"}), meta={}))
        db.commit()
        clean_env.setenv("GEMINI_API_KEY", "platform")
        clean_env.setenv("ALLOW_USER_AI_KEYS", "false")
        assert gemini_key(db, uid) == "platform"
        clean_env.setenv("ALLOW_USER_AI_KEYS", "true")                           # a later version can turn it back on
        assert gemini_key(db, uid) == "users-own"


# ---- multilingual voice ------------------------------------------------------------------------
def test_language_list_grows_when_the_voice_engine_is_switched_on(clean_env, auth_client):
    before = auth_client.get("/api/voice/languages").json()
    assert "kn-IN" not in before and "hi-IN" in before                           # browser practice languages
    assert auth_client.get("/api/capabilities").json()["multilingual_voice"] is False
    clean_env.setenv("SARVAM_API_KEY", SECRETS["SARVAM_API_KEY"])
    after = auth_client.get("/api/voice/languages")
    caps = auth_client.get("/api/capabilities")
    assert {"kn-IN", "ml-IN", "od-IN", "bn-IN"} <= set(after.json()) and caps.json()["multilingual_voice"] is True
    assert "hi-IN" in caps.json()["phone_languages"]
    for r in (after, caps):
        assert SECRETS["SARVAM_API_KEY"] not in r.text and not VENDOR.search(r.text)


def _agent_call(lang):
    return SimpleNamespace(language=lang, handoff_number="", instructions="", questions=[]), \
        SimpleNamespace(id=7, status="active", transcript=[{"role": "agent", "text": "Hi", "lang": lang}])


def test_phone_calls_play_natural_voice_with_the_key_and_say_without(clean_env, mock_http, client, tmp_path):
    from app.routers.voice import _twiml
    clean_env.setattr(speech, "CACHE_DIR", tmp_path)
    agent, call = _agent_call("hi-IN")
    without = _twiml(agent, call, "नमस्ते, आप कैसे हैं?", True).body.decode()
    assert '<Say language="hi-IN">' in without and "<Play>" not in without

    clean_env.setenv("SARVAM_API_KEY", SECRETS["SARVAM_API_KEY"])
    route = mock_http.post("https://api.sarvam.ai/text-to-speech").respond(json={"audios": [base64.b64encode(b"ID3fake-mp3").decode()]})
    xml = _twiml(agent, call, "नमस्ते, आप कैसे हैं?", True).body.decode()
    sent = route.calls.last.request
    assert sent.headers["api-subscription-key"] == SECRETS["SARVAM_API_KEY"]
    assert b'"language_code":"hi-IN"' in sent.content.replace(b" ", b"")
    url = re.search(r"<Play>(.*?)</Play>", xml).group(1)
    assert url.startswith("http://testserver/api/public/voice/audio/") and SECRETS["SARVAM_API_KEY"] not in xml
    assert 'language="hi-IN"' in xml                                             # listening stays in the caller's language
    r = client.get(url.replace("http://testserver", ""))
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == b"ID3fake-mp3"
    _twiml(agent, call, "नमस्ते, आप कैसे हैं?", True)                               # cached: no second request
    assert route.call_count == 1


def test_voice_engine_failure_falls_back_quietly(clean_env, mock_http, tmp_path):
    from app.routers.voice import _twiml
    clean_env.setattr(speech, "CACHE_DIR", tmp_path)
    clean_env.setenv("SARVAM_API_KEY", "k")
    mock_http.post("https://api.sarvam.ai/text-to-speech").respond(500, text="upstream exploded: sarvam internal")
    xml = _twiml(*_agent_call("ta-IN"), "வணக்கம்", True).body.decode()
    assert '<Say language="ta-IN">' in xml and "sarvam" not in xml.lower()


def test_audio_links_expire_and_cannot_be_forged(client, clean_env, tmp_path):
    clean_env.setattr(speech, "CACHE_DIR", tmp_path)
    digest = "0" * 32
    (tmp_path / f"{digest}.mp3").write_bytes(b"x")
    good = jwt.encode({"a": digest, "exp": int(time.time()) + 60, "p": "voice-audio"}, settings.secret_key, "HS256")
    expired = jwt.encode({"a": digest, "exp": int(time.time()) - 1, "p": "voice-audio"}, settings.secret_key, "HS256")
    forged = jwt.encode({"a": digest, "exp": int(time.time()) + 60, "p": "voice-audio"}, "not-the-key", "HS256")
    traversal = jwt.encode({"a": "../../secret", "exp": int(time.time()) + 60, "p": "voice-audio"}, settings.secret_key, "HS256")
    assert client.get(f"/api/public/voice/audio/{good}").status_code == 200
    for t in (expired, forged, traversal, good[:-2] + "xx"):
        assert client.get(f"/api/public/voice/audio/{t}").status_code == 404


def test_calls_speak_the_language_the_lead_writes_or_asks_for(clean_env):
    assert speech.detect_language("Can I get a callback in Hindi?") == "hi-IN"
    assert speech.detect_language("मुझे 2 BHK चाहिए") == "hi-IN"
    assert speech.detect_language("வணக்கம், விலை என்ன?") == "ta-IN"
    assert speech.detect_language("Please call me in kannada") == "kn-IN"
    assert speech.detect_language("What is the price?") is None
    assert speech.call_language("en-IN", "callback in Hindi?") == "en-IN"         # engine off: phone voice can't do Hindi well
    clean_env.setenv("SARVAM_API_KEY", "k")
    assert speech.call_language("en-IN", "callback in Hindi?") == "hi-IN"         # engine on: speak their language
    assert speech.call_language("en-IN", "హలో, ఇది ఎంత?") == "te-IN"              # first reply in Telugu switches the call
    assert speech.call_language("hi-IN", "Sounds good, thanks") == "hi-IN"


def test_transcription_uses_the_documented_shape(clean_env, mock_http):
    clean_env.setenv("SARVAM_API_KEY", "k")
    route = mock_http.post("https://api.sarvam.ai/speech-to-text").respond(json={"transcript": "नमस्ते", "language_code": "hi-IN"})
    assert speech.transcribe(b"RIFF....", "a.wav") == {"text": "नमस्ते", "language": "hi-IN"}
    assert b'name="model"' in route.calls.last.request.content and b"saaras:v4" in route.calls.last.request.content


# ---- nothing reaches customers -----------------------------------------------------------------
def test_no_customer_response_names_a_supplier_or_carries_a_key(clean_env, auth_client):
    m = clean_env
    m.setenv("SARVAM_API_KEY", SECRETS["SARVAM_API_KEY"]); m.setenv("AI_PROVIDER", "fal"); m.setenv("AI_API_KEY", SECRETS["AI_API_KEY"])
    m.setattr(settings, "gemini_api_key", "gm-SECRET-333")
    auth_client.post("/api/voice/agents", json={"name": "Desk", "language": "hi-IN", "greeting": "Hi", "questions": ["Name?"]})
    for path in ["/api/health", "/api/capabilities", "/api/auth/me", "/api/voice/languages", "/api/voice/agents",
                 "/api/providers/options?kind=image", "/api/providers/options?kind=video", "/api/providers/options?kind=text",
                 "/api/content/models", "/api/content/image/edit-engines", "/api/integrations", "/api/integrations/ai/status",
                 "/api/onboarding"]:
        r = auth_client.get(path)
        assert r.status_code == 200, path
        for secret in [*SECRETS.values(), "gm-SECRET-333"]:
            assert secret not in r.text, path
        assert not VENDOR.search(r.text), (path, VENDOR.search(r.text))
    assert auth_client.get("/api/providers").status_code == 404 and auth_client.get("/api/providers/presets").status_code == 404


def test_supplier_errors_are_neutral_for_customers_but_logged(client, auth_client, caplog):
    from app.main import app

    @app.get("/api/content/_leak_test")
    def leak():
        raise HTTPException(502, "fal.ai error: invalid FAL_KEY (key 254b6efa-76e6-4397-910b-deace53df3c6:b2eeabdaeef11dd88)")

    @app.get("/api/voice/_leak_test")
    def leak_voice():
        raise HTTPException(400, "Connect Sarvam in Settings first.")
    app.router.routes.insert(0, app.router.routes.pop())
    app.router.routes.insert(0, app.router.routes.pop())
    try:
        r = auth_client.get("/api/content/_leak_test")
        assert r.status_code == 502 and r.json()["detail"] == "The image engine is busy right now. Please try again in a minute."
        assert auth_client.get("/api/voice/_leak_test").json()["detail"] == "This voice feature isn't switched on for your account yet."
        assert any("fal.ai error" in rec.getMessage() for rec in caplog.records)   # the real text stays in the server log
    finally:
        app.router.routes = [rt for rt in app.router.routes if "_leak_test" not in getattr(rt, "path", "")]
