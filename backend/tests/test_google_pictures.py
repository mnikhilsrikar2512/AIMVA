"""Google makes pictures and whole-image edits first; fal keeps video (owner decision 2026-11-21).

Every Google and fal call here is mocked with respx; no real image or video model is ever reached.
"""
import base64
import io
import json

import pytest
from PIL import Image

from app import image_edit as IE
from app.discreet import leaks

G = "https://generativelanguage.googleapis.com/v1beta"
IMAGEN_URL = f"{G}/models/imagen-4.0-fast-generate-001:predict"
GEMINI_IMG_URL = f"{G}/models/gemini-3.1-flash-lite-image:generateContent"
SCHNELL = "https://fal.run/fal-ai/flux/schnell"
POLL = "https://image.pollinations.ai/prompt/"


def png(color=(200, 80, 40), size=(64, 64)):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "PNG")
    return b.getvalue()


def imagen_answer(n=1, color=(200, 80, 40)):
    return {"predictions": [{"mimeType": "image/png", "bytesBase64Encoded": base64.b64encode(png(color)).decode()}] * n}


def gemini_answer(color=(10, 10, 40), size=(64, 64)):
    return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png",
                                                                  "data": base64.b64encode(png(color, size)).decode()}}]}}]}


@pytest.fixture(autouse=True)
def imagen_configured(monkeypatch):
    monkeypatch.setenv("GOOGLE_PICTURE_MODEL", "imagen-4.0-fast-generate-001")  # most tests here use Imagen


@pytest.fixture
def both_keys(auth_client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-platform-key")
    monkeypatch.setenv("FAL_KEY", "fal-test")
    return auth_client


# ---- pictures --------------------------------------------------------------------------------------------------
def test_google_draws_first_and_fal_is_not_charged(both_keys, mock_http):
    google = mock_http.post(IMAGEN_URL).respond(json=imagen_answer(4))
    fal = mock_http.post(SCHNELL).respond(json={"images": [{"url": "https://cdn.fal/1.png"}]})
    r = both_keys.post("/api/content/image", json={"prompt": "a cup of filter coffee", "model": "fal-ai/flux/schnell",
                                                   "count": 4, "size": "9:16", "smart_prompt": False})
    assert r.status_code == 200, r.text
    assert len(r.json()) == 4 and google.call_count == 1 and not fal.called
    sent = google.calls[0].request
    assert sent.headers["x-goog-api-key"] == "g-platform-key" and "key=" not in str(sent.url)
    assert '"aspectRatio":"9:16"' in sent.read().decode().replace(" ", "")
    a = r.json()[0]
    assert a["url"].startswith("/api/files/")  # our own copy
    assert not leaks(str(a)) and "served_by" not in a["params"] and "google" not in str(a).lower()


def test_default_picture_model_is_the_gemini_lite_image_model(both_keys, mock_http, monkeypatch):
    monkeypatch.setenv("GOOGLE_PICTURE_MODEL", "")  # Imagen isn't offered to every key, so it isn't the default
    imagen = mock_http.post(IMAGEN_URL).respond(json=imagen_answer())
    lite = mock_http.post(GEMINI_IMG_URL).respond(json=gemini_answer())
    r = both_keys.post("/api/content/image", json={"prompt": "a cat", "count": 2, "smart_prompt": False})
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2 and lite.call_count == 2 and not imagen.called


def test_free_engine_choice_also_goes_to_google(both_keys, mock_http):
    google = mock_http.post(IMAGEN_URL).respond(json=imagen_answer())
    free = mock_http.get(url__startswith=POLL).respond(200, content=png(), headers={"content-type": "image/png"})
    r = both_keys.post("/api/content/image", json={"prompt": "a cat", "model": "pollinations/flux", "smart_prompt": False})
    assert r.status_code == 200 and google.called and not free.called


def test_fal_stands_in_when_google_fails_and_google_is_tried_once(both_keys, mock_http):
    google = mock_http.post(IMAGEN_URL).respond(429, json={"error": {"message": "Quota exceeded. limit: 0"}})
    fal = mock_http.post(SCHNELL).respond(json={"images": [{"url": "https://cdn.fal/1.png"}]})
    r = both_keys.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell", "smart_prompt": False})
    assert r.status_code == 200 and r.json()[0]["url"] == "https://cdn.fal/1.png"
    assert google.call_count == 1 and fal.called  # no second paid try on the backup path


def test_google_failure_on_free_choice_goes_to_paid_fal_not_free(both_keys, mock_http):
    mock_http.post(IMAGEN_URL).respond(500)
    fal = mock_http.post(SCHNELL).respond(json={"images": [{"url": "https://cdn.fal/1.png"}]})
    free = mock_http.get(url__startswith=POLL).respond(200, content=png(), headers={"content-type": "image/png"})
    r = both_keys.post("/api/content/image", json={"prompt": "a cat", "model": "pollinations/flux", "smart_prompt": False})
    assert r.status_code == 200 and fal.called and not free.called


def test_reference_picture_goes_to_the_gemini_image_model(both_keys, mock_http):
    ref = both_keys.post("/api/references", files={"file": ("ref.png", png(), "image/png")}).json()
    imagen = mock_http.post(IMAGEN_URL).respond(json=imagen_answer())
    gemini = mock_http.post(GEMINI_IMG_URL).respond(json=gemini_answer())
    r = both_keys.post("/api/content/image", json={"prompt": "same style, Diwali lights", "reference": ref["ref"],
                                                   "smart_prompt": False})
    assert r.status_code == 200, r.text
    assert gemini.called and not imagen.called
    assert '"inlineData"' in gemini.calls[0].request.read().decode()


def test_picture_engine_fal_puts_fal_back_first(both_keys, mock_http, monkeypatch):
    monkeypatch.setenv("PICTURE_ENGINE", "fal")
    google = mock_http.post(IMAGEN_URL).respond(json=imagen_answer())
    fal = mock_http.post(SCHNELL).respond(json={"images": [{"url": "https://cdn.fal/1.png"}]})
    r = both_keys.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell", "smart_prompt": False})
    assert r.status_code == 200 and fal.called and not google.called


def test_no_google_key_keeps_fal(auth_client, mock_http, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "fal-test")
    google = mock_http.post(IMAGEN_URL).respond(json=imagen_answer())
    fal = mock_http.post(SCHNELL).respond(json={"images": [{"url": "https://cdn.fal/1.png"}]})
    r = auth_client.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell", "smart_prompt": False})
    assert r.status_code == 200 and fal.called and not google.called


def test_customers_own_connection_is_never_rerouted(both_keys, mock_http, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "admin_emails", {"owner@example.com"})  # only the platform owner adds engines
    c = both_keys.post("/api/providers", json={"preset": "openai_images", "api_key": "sk-x", "model": "gpt-image-1",
                                               "verify": False}).json()
    google = mock_http.post(IMAGEN_URL).respond(json=imagen_answer())
    own = mock_http.post("https://api.openai.com/v1/images/generations").respond(
        json={"data": [{"b64_json": base64.b64encode(png()).decode()}]})
    r = both_keys.post("/api/content/image", json={"prompt": "a cat", "provider": f"conn:{c['id']}", "smart_prompt": False})
    assert r.status_code == 200, r.text
    assert own.called and not google.called


# ---- whole-image edits -----------------------------------------------------------------------------------------
def _picture(client, mock_http):
    mock_http.post(IMAGEN_URL).respond(json=imagen_answer(color=(20, 40, 200)))
    r = client.post("/api/content/image", json={"prompt": "a living room", "size": "1:1", "smart_prompt": False})
    assert r.status_code == 200, r.text
    return r.json()[0]


def test_whole_image_edit_goes_to_google_first(both_keys, mock_http):
    a = _picture(both_keys, mock_http)
    gemini = mock_http.post(GEMINI_IMG_URL).respond(json=gemini_answer(size=(512, 512)))
    kontext = mock_http.post(f"https://fal.run/{IE.FAL_INSTRUCT}").respond(json={"images": [{"url": "https://fal.media/n.png"}]})
    r = both_keys.post(f"/api/content/image/{a['id']}/edit", json={"instruction": "make it night time"})
    assert r.status_code == 200, r.text
    assert gemini.called and not kontext.called
    assert "make it night time" in gemini.calls[0].request.read().decode()
    e = r.json()
    assert (e["params"]["width"], e["params"]["height"]) == (64, 64)  # same size as the original
    assert "google" not in str(e).lower() and "gemini" not in str(e).lower()


def test_whole_image_edit_falls_back_to_fal(both_keys, mock_http):
    a = _picture(both_keys, mock_http)
    mock_http.post(GEMINI_IMG_URL).respond(500)
    kontext = mock_http.post(f"https://fal.run/{IE.FAL_INSTRUCT}").respond(json={"images": [{"url": "https://fal.media/n.png"}]})
    mock_http.get("https://fal.media/n.png").respond(200, content=png((10, 10, 40)), headers={"content-type": "image/png"})
    r = both_keys.post(f"/api/content/image/{a['id']}/edit", json={"instruction": "make it night time"})
    assert r.status_code == 200, r.text
    assert json.loads(kontext.calls[0].request.content)["prompt"] == "make it night time"


# ---- video stays on fal ----------------------------------------------------------------------------------------
def test_video_still_goes_to_fal_first(both_keys, mock_http):
    fal = mock_http.post("https://queue.fal.run/fal-ai/ltx-2/text-to-video").respond(
        json={"request_id": "r1", "status_url": "https://queue.fal.run/x/status", "response_url": "https://queue.fal.run/x"})
    veo = mock_http.post(url__startswith=f"{G}/models/veo").respond(json={"name": "models/veo/operations/op1"})
    r = both_keys.post("/api/content/video", json={"prompt": "chai being poured", "model": "fal-ai/ltx-2/text-to-video",
                                                   "duration": "6"})
    assert r.status_code == 200, r.text
    assert fal.called and not veo.called
