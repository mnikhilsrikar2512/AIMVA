"""Google as the backup picture/video engine: used only after fal fails, never shown to customers, never live.

Every Google and fal call here is mocked with respx; no real image or video model is ever reached.
"""
import base64
import io
import logging

import httpx
import pytest
from PIL import Image

from app.discreet import leaks

G = "https://generativelanguage.googleapis.com/v1beta"
IMG_URL = f"{G}/models/gemini-3.1-flash-image:generateContent"
VEO_URL = f"{G}/models/veo-3.1-fast-generate-preview:predictLongRunning"
OP = "models/veo-3.1-fast-generate-preview/operations/op123"


def png():
    b = io.BytesIO()
    Image.new("RGB", (32, 32), (200, 80, 40)).save(b, "PNG")
    return b.getvalue()


def picture_answer():
    return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png",
                                                                  "data": base64.b64encode(png()).decode()}}]}}]}


@pytest.fixture
def google_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-platform-key")


@pytest.fixture
def fal_on(auth_client, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "fal-test")  # the platform's studio key
    return auth_client


# ---- pictures --------------------------------------------------------------------------------------------------
def test_fal_working_never_touches_google(fal_on, mock_http, google_key):
    mock_http.post("https://fal.run/fal-ai/flux/schnell").respond(json={"images": [{"url": "https://cdn.fal/1.png"}]})
    google = mock_http.post(IMG_URL).respond(json=picture_answer())
    r = fal_on.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell"})
    assert r.status_code == 200 and r.json()[0]["url"] == "https://cdn.fal/1.png"
    assert not google.called  # no extra cost on a normal day


@pytest.mark.parametrize("fal_failure", [
    httpx.Response(500, json={"detail": "boom"}),
    httpx.Response(403, json={"detail": "User is locked. Reason: Exhausted balance."}),
    httpx.Response(429, json={"detail": "slow down"}),
    httpx.ConnectTimeout("timeout"),
])
def test_google_steps_in_when_fal_fails(fal_on, mock_http, google_key, fal_failure):
    fal = mock_http.post("https://fal.run/fal-ai/flux/schnell")
    fal.mock(side_effect=fal_failure) if isinstance(fal_failure, Exception) else fal.mock(return_value=fal_failure)
    google = mock_http.post(IMG_URL).respond(json=picture_answer())
    r = fal_on.post("/api/content/image", json={"prompt": "a cat on a sofa", "model": "fal-ai/flux/schnell",
                                                "size": "9:16", "negative_prompt": "blurry"})
    assert r.status_code == 200, r.text
    a = r.json()[0]
    assert a["url"].startswith("/api/files/")  # Google's bytes kept as our own copy
    assert fal_on.get(a["url"]).headers["content-type"].startswith("image/")
    req = google.calls[0].request
    assert req.headers["x-goog-api-key"] == "g-platform-key" and "key=" not in str(req.url)
    body = req.read().decode()
    assert "a cat on a sofa" in body and "Avoid: blurry" in body and '"aspectRatio":"9:16"' in body.replace(" ", "")
    # The customer never learns a backup (or Google) was involved.
    assert not leaks(str(a)) and "served_by" not in a["params"] and "google" not in str(a).lower()


def test_google_makes_each_requested_picture(fal_on, mock_http, google_key):
    mock_http.post("https://fal.run/fal-ai/flux/schnell").respond(503)
    google = mock_http.post(IMG_URL).respond(json=picture_answer())
    r = fal_on.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell", "count": 3})
    assert len(r.json()) == 3 and google.call_count == 3


def test_free_google_key_fails_cleanly_with_the_usual_message(fal_on, mock_http, google_key, caplog):
    mock_http.post("https://fal.run/fal-ai/flux/schnell").respond(500, json={"detail": "boom"})
    mock_http.post(IMG_URL).respond(429, json={"error": {"code": 429, "message": "Quota exceeded. limit: 0", "status": "RESOURCE_EXHAUSTED"}})
    with caplog.at_level(logging.WARNING):
        r = fal_on.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell"})
    assert r.status_code == 502  # the studio's own failure, neutral to the customer
    assert not leaks(r.json()["detail"]) and "google" not in r.json()["detail"].lower()
    assert fal_on.get("/api/content/assets?kind=image").json() == []
    assert "needs billing" in caplog.text and "g-platform-key" not in caplog.text  # owner can see why, key never logged


def test_free_engine_is_the_last_step_where_allowed(fal_on, mock_http, google_key, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "free_ai", True)
    mock_http.post("https://fal.run/fal-ai/flux/schnell").respond(500)
    mock_http.post(IMG_URL).respond(400, json={"error": {"message": "Imagen API is only accessible to billed users"}})
    free = mock_http.get(url__startswith="https://image.pollinations.ai/prompt/").respond(200, content=png(),
                                                                                         headers={"content-type": "image/png"})
    r = fal_on.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell", "smart_prompt": False})
    assert r.status_code == 200 and free.called


def test_no_google_key_keeps_todays_behaviour(fal_on, mock_http):
    mock_http.post("https://fal.run/fal-ai/flux/schnell").respond(500)
    google = mock_http.post(IMG_URL).respond(json=picture_answer())
    assert fal_on.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell"}).status_code == 502
    assert not google.called


def test_backup_can_be_switched_off(fal_on, mock_http, google_key, monkeypatch):
    monkeypatch.setenv("GOOGLE_MEDIA_FALLBACK", "false")
    mock_http.post("https://fal.run/fal-ai/flux/schnell").respond(500)
    google = mock_http.post(IMG_URL).respond(json=picture_answer())
    assert fal_on.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell"}).status_code == 502
    assert not google.called


def test_google_is_not_used_when_studio_isnt_set_up(auth_client, mock_http, google_key):
    # No fal key is a setup gap, not a failure: paying Google for every picture would cost more.
    google = mock_http.post(IMG_URL).respond(json=picture_answer())
    r = auth_client.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell"})
    assert r.status_code == 400 and not google.called


def test_own_media_key_and_model_override(fal_on, mock_http, google_key, monkeypatch):
    monkeypatch.setenv("GOOGLE_MEDIA_API_KEY", "g-media-key")
    monkeypatch.setenv("GOOGLE_IMAGE_MODEL", "gemini-2.5-flash-image")
    mock_http.post("https://fal.run/fal-ai/flux/schnell").respond(500)
    google = mock_http.post(f"{G}/models/gemini-2.5-flash-image:generateContent").respond(json=picture_answer())
    assert fal_on.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell"}).status_code == 200
    assert google.calls[0].request.headers["x-goog-api-key"] == "g-media-key"


# ---- video -----------------------------------------------------------------------------------------------------
def _veo_done(mock_http, video=b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64):
    mock_http.get(f"{G}/{OP}").mock(side_effect=[
        httpx.Response(200, json={"name": OP, "done": False}),
        httpx.Response(200, json={"name": OP, "done": True, "response": {"generateVideoResponse": {
            "generatedSamples": [{"video": {"uri": f"{G}/files/abc:download?alt=media"}}]}}})])
    return mock_http.get(f"{G}/files/abc:download?alt=media").respond(200, content=video)


def test_video_goes_to_veo_when_fal_wont_queue(fal_on, mock_http, google_key):
    mock_http.post("https://queue.fal.run/fal-ai/luma-dream-machine/ray-2").respond(
        403, json={"detail": "User is locked. Reason: Exhausted balance."})
    veo = mock_http.post(VEO_URL).respond(json={"name": OP})
    dl = _veo_done(mock_http)
    a = fal_on.post("/api/content/video", json={"prompt": "drone shot over a beach", "model": "fal-ai/luma-dream-machine/ray-2",
                                                "aspect_ratio": "1:1", "duration": "9s"}).json()
    assert a["status"] == "queued" and not leaks(str(a)) and "retry" not in a["params"]
    sent = veo.calls[0].request
    assert sent.headers["x-goog-api-key"] == "g-platform-key"
    body = sent.read().decode().replace(" ", "")
    assert '"aspectRatio":"16:9"' in body and '"durationSeconds":8' in body and '"resolution":"720p"' in body
    assert fal_on.get(f"/api/content/video/{a['id']}").json()["status"] == "queued"
    done = fal_on.get(f"/api/content/video/{a['id']}").json()
    assert done["status"] == "done" and done["url"].startswith("/api/files/") and not leaks(str(done))
    assert dl.calls[0].request.headers["x-goog-api-key"] == "g-platform-key"


def test_video_that_fails_later_on_fal_moves_to_veo(fal_on, mock_http, google_key):
    mock_http.post("https://queue.fal.run/fal-ai/luma-dream-machine/ray-2").respond(
        json={"status_url": "https://queue.fal.run/s/r1", "response_url": "https://queue.fal.run/r/r1"})
    mock_http.get("https://queue.fal.run/s/r1").respond(json={"status": "FAILED"})
    veo = mock_http.post(VEO_URL).respond(json={"name": OP})
    _veo_done(mock_http)
    a = fal_on.post("/api/content/video", json={"prompt": "drone shot", "model": "fal-ai/luma-dream-machine/ray-2",
                                                "aspect_ratio": "9:16"}).json()
    assert not veo.called
    assert fal_on.get(f"/api/content/video/{a['id']}").json()["status"] == "queued"  # handed over quietly
    assert '"aspectRatio":"9:16"' in veo.calls[0].request.read().decode().replace(" ", "")
    fal_on.get(f"/api/content/video/{a['id']}")
    assert fal_on.get(f"/api/content/video/{a['id']}").json()["status"] == "done"


def test_video_backup_with_free_key_fails_cleanly(fal_on, mock_http, google_key):
    mock_http.post("https://queue.fal.run/fal-ai/luma-dream-machine/ray-2").respond(500, text="down")
    mock_http.post(VEO_URL).respond(429, json={"error": {"message": "limit: 0"}})
    r = fal_on.post("/api/content/video", json={"prompt": "drone shot", "model": "fal-ai/luma-dream-machine/ray-2"})
    assert r.status_code == 502 and not leaks(r.json()["detail"])
    assert fal_on.get("/api/content/assets?kind=video").json() == []


def test_veo_refusal_marks_the_clip_failed_once(fal_on, mock_http, google_key):
    mock_http.post("https://queue.fal.run/fal-ai/luma-dream-machine/ray-2").respond(500)
    veo = mock_http.post(VEO_URL).respond(json={"name": OP})
    mock_http.get(f"{G}/{OP}").respond(json={"name": OP, "done": True, "response": {"generateVideoResponse": {
        "raiMediaFilteredReasons": ["blocked"]}}})
    a = fal_on.post("/api/content/video", json={"prompt": "drone shot", "model": "fal-ai/luma-dream-machine/ray-2"}).json()
    done = fal_on.get(f"/api/content/video/{a['id']}").json()
    assert done["status"] == "failed" and veo.call_count == 1 and not leaks(str(done))


def test_video_start_image_reaches_veo(fal_on, mock_http, google_key):
    mock_http.post("https://fal.run/fal-ai/flux/schnell").respond(500)
    mock_http.post(IMG_URL).respond(json=picture_answer())
    pic = fal_on.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell"}).json()[0]
    mock_http.post("https://queue.fal.run/fal-ai/luma-dream-machine/ray-2/image-to-video").respond(500)
    veo = mock_http.post(VEO_URL).respond(json={"name": OP})
    r = fal_on.post("/api/content/video", json={"prompt": "the cat waves", "model": "fal-ai/luma-dream-machine/ray-2",
                                                "start_asset_id": pic["id"]})
    assert r.status_code == 200
    assert '"bytesBase64Encoded"' in veo.calls[0].request.read().decode()


# ---- keys out of logs ------------------------------------------------------------------------------------------
def test_log_filter_masks_keys_in_urls():
    from app.observability import _SecretFilter
    rec = logging.LogRecord("httpx", logging.INFO, "", 0, 'HTTP Request: POST %s "HTTP/1.1 200 OK"',
                            ("https://x.googleapis.com/v1beta/models/m:generateContent?key=AIzaSECRET&alt=1",), None)
    _SecretFilter().filter(rec)
    assert "AIzaSECRET" not in rec.getMessage() and "key=***" in rec.getMessage()


def test_httpx_request_logs_are_quiet_after_setup():
    from app.observability import setup_logging
    setup_logging()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
