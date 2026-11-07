"""Bring-your-own providers: guardrails, adapters (text/image/video) and expanded generator options."""
import base64
import io
import json
import socket

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app import providers as P
from app.config import settings
from app.models import ProviderConnection

FAKE_DNS = {"localhost": "127.0.0.1", "internal.example": "10.0.0.5", "metadata.example": "169.254.169.254"}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """Hermetic name resolution: public names resolve to a public IP, a few names map to private ranges."""
    def getaddrinfo(host, port, *a, **k):
        if host.endswith(".invalid"):
            raise socket.gaierror("not found")
        ip = FAKE_DNS.get(host, "93.184.216.34")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 443))]
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


def png_bytes(color=(200, 50, 50), size=(64, 64), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def add(c, preset, **kw):
    body = {"preset": preset, "api_key": "sk-test", "verify": False, **kw}
    r = c.post("/api/providers", json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ---- catalogue, CRUD, guardrails ------------------------------------------------------
def test_presets_cover_text_image_video(auth_client):
    kinds = {p["kind"] for p in auth_client.get("/api/providers/presets").json()}
    assert kinds == {"text", "image", "video"}


def test_add_verifies_key_and_never_returns_it(auth_client, mock_http, db):
    route = mock_http.get("https://api.openai.com/v1/models").respond(json={"data": []})
    r = auth_client.post("/api/providers", json={"preset": "openai", "api_key": "sk-secret-123"})
    assert r.status_code == 200 and route.calls[0].request.headers["authorization"] == "Bearer sk-secret-123"
    out = r.json()
    assert out["has_key"] and "sk-secret" not in json.dumps(out) and out["is_default"]  # first text provider = default
    assert "sk-secret" not in db.scalar(select(ProviderConnection)).secret


def test_bad_key_rejected_with_clear_message(auth_client, mock_http):
    mock_http.get("https://api.groq.com/openai/v1/models").respond(401, json={"error": {"message": "Invalid API Key"}})
    r = auth_client.post("/api/providers", json={"preset": "groq", "api_key": "nope"})
    assert r.status_code == 400 and "rejected your API key" in r.json()["detail"]


@pytest.mark.parametrize("url,msg", [
    ("http://metadata.example/latest", "isn't allowed"),
    ("http://api.example.com/v1", "must use https"),
    ("https://user:pw@api.example.com/v1", "credentials"),
    ("ftp://api.example.com", "https://"),
    ("https://nowhere.invalid/v1", "Couldn't find"),
])
def test_base_url_guardrails(auth_client, url, msg):
    r = auth_client.post("/api/providers", json={"preset": "custom_text", "base_url": url, "model": "m", "verify": False})
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_private_addresses_follow_server_setting(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "allow_private_providers", False)
    r = auth_client.post("/api/providers", json={"preset": "ollama", "verify": False})
    assert r.status_code == 400 and "disabled" in r.json()["detail"]
    monkeypatch.setattr(settings, "allow_private_providers", True)
    assert auth_client.post("/api/providers", json={"preset": "ollama", "verify": False}).status_code == 200  # no key needed


def test_key_required_and_model_validated(auth_client):
    assert "API key" in auth_client.post("/api/providers", json={"preset": "openai", "verify": False}).json()["detail"]
    r = auth_client.post("/api/providers", json={"preset": "openai", "api_key": "k", "model": "bad model; rm -rf", "verify": False})
    assert r.status_code == 400 and "model name" in r.json()["detail"]


def test_update_default_and_delete(auth_client):
    a = add(auth_client, "openai")
    b = add(auth_client, "anthropic", is_default=True)
    rows = {c["id"]: c for c in auth_client.get("/api/providers").json()}
    assert rows[b["id"]]["is_default"] and not rows[a["id"]]["is_default"]
    r = auth_client.patch(f"/api/providers/{a['id']}", json={"is_default": True, "model": "gpt-4.1", "name": "My OpenAI"}).json()
    assert r["is_default"] and r["model"] == "gpt-4.1" and r["name"] == "My OpenAI"
    assert auth_client.delete(f"/api/providers/{b['id']}").json() == {"ok": True}
    assert len(auth_client.get("/api/providers").json()) == 1


def test_providers_are_private(auth_client, other_client):
    c = add(auth_client, "openai")
    assert other_client.get("/api/providers").json() == []
    assert other_client.patch(f"/api/providers/{c['id']}", json={"name": "x"}).status_code == 404
    assert other_client.post("/api/content/image", json={"prompt": "a cat", "provider": f"conn:{c['id']}"}).status_code == 404
    assert other_client.post("/api/sites", json={"business": "XY", "offer": "Free trial", "writer": f"conn:{c['id']}"}).status_code == 404


def test_options_list_builtins_and_own(auth_client):
    add(auth_client, "replicate_image")
    refs = [o["ref"] for o in auth_client.get("/api/providers/options?kind=image").json()]
    assert refs[:2] == ["builtin:pollinations", "builtin:fal"] and refs[2].startswith("conn:")
    assert auth_client.get("/api/providers/options?kind=nope").status_code == 422


# ---- text ------------------------------------------------------------------------------------
def test_default_text_provider_writes_ad_copy(auth_client, mock_http):
    route = mock_http.post("https://api.openai.com/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "Headline: Homes by the sea\nText: Book a visit."}}]})
    add(auth_client, "openai")
    r = auth_client.post("/api/content/ad-copy", json={"product": "Skyline"}).json()
    assert r["source"] == "ai" and r["variants"][0]["headline"] == "Homes by the sea"
    assert json.loads(route.calls[0].request.content)["model"] == "gpt-4o-mini"


def test_anthropic_adapter_shape(auth_client, mock_http):
    route = mock_http.post("https://api.anthropic.com/v1/messages").respond(
        json={"content": [{"type": "text", "text": "Headline: Calm homes\nText: Visit us."}]})
    add(auth_client, "anthropic")
    assert auth_client.post("/api/content/ad-copy", json={"product": "Skyline"}).json()["source"] == "ai"
    req = route.calls[0].request
    assert req.headers["x-api-key"] == "sk-test" and req.headers["anthropic-version"] == "2023-06-01"
    assert json.loads(req.content)["model"] == "claude-haiku-5-5"


def test_failing_text_provider_falls_back_to_template(auth_client, mock_http):
    mock_http.post("https://api.openai.com/v1/chat/completions").respond(500, json={"error": "boom"})
    add(auth_client, "openai")
    assert auth_client.post("/api/content/ad-copy", json={"product": "Skyline"}).json()["source"] == "template"


def test_test_endpoint_reports_reply(auth_client, mock_http):
    c = add(auth_client, "openai")
    mock_http.get("https://api.openai.com/v1/models").respond(json={"data": []})
    mock_http.post("https://api.openai.com/v1/chat/completions").respond(json={"choices": [{"message": {"content": "ready"}}]})
    assert "ready" in auth_client.post(f"/api/providers/{c['id']}/test").json()["message"]


# ---- images ------------------------------------------------------------------------------------
def test_free_provider_options(auth_client, mock_http):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (32, 32)).save(buf, "PNG")
    route = mock_http.get(url__startswith="https://image.pollinations.ai/").respond(200, content=buf.getvalue(), headers={"content-type": "image/png"})
    a = auth_client.post("/api/content/image", json={"prompt": "living room", "provider": "builtin:pollinations", "model": "turbo",
                                                      "width": 1000, "height": 500, "seed": 42, "style": "cinematic",
                                                      "negative_prompt": "people"}).json()[0]
    url = str(route.calls.last.request.url)
    assert "width=992&height=496" in url and "seed=42" in url and "model=turbo" in url  # snapped to multiples of 16
    assert "cinematic" in url and "Avoid%3A%20people" in url
    assert a["params"]["width"] == 992 and a["params"]["style"] == "cinematic"
    bad = auth_client.post("/api/content/image", json={"prompt": "x room", "provider": "builtin:pollinations", "model": "sdxl"})
    assert bad.status_code == 400


def test_openai_images_b64_saved_privately(auth_client, mock_http):
    c = add(auth_client, "openai_images")
    route = mock_http.post("https://api.openai.com/v1/images/generations").respond(
        json={"data": [{"b64_json": base64.b64encode(png_bytes()).decode()}]})
    a = auth_client.post("/api/content/image", json={"prompt": "a red square", "provider": f"conn:{c['id']}", "size": "16:9"}).json()[0]
    assert json.loads(route.calls[0].request.content)["size"] == "1344x768"
    assert a["url"].startswith("/api/files/") and a["url"].endswith(".png")
    assert auth_client.get(a["url"]).headers["content-type"] == "image/png"


def test_replicate_image_polls_and_keeps_a_copy(auth_client, mock_http):
    c = add(auth_client, "replicate_image")
    mock_http.post("https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions").respond(
        json={"id": "p1", "status": "processing", "urls": {"get": "https://api.replicate.com/v1/predictions/p1"}})
    mock_http.get("https://api.replicate.com/v1/predictions/p1").respond(
        json={"id": "p1", "status": "succeeded", "output": ["https://replicate.delivery/out.png"]})
    mock_http.get("https://replicate.delivery/out.png").respond(content=png_bytes())
    a = auth_client.post("/api/content/image", json={"prompt": "a cat", "provider": f"conn:{c['id']}", "seed": 7}).json()[0]
    assert a["url"].startswith("/api/files/") and a["model"] == "black-forest-labs/flux-schnell"


def test_stability_returns_bytes(auth_client, mock_http):
    c = add(auth_client, "stability")
    mock_http.post("https://api.stability.ai/v2beta/stable-image/generate/core").respond(
        content=png_bytes(fmt="PNG"), headers={"content-type": "image/png"})
    a = auth_client.post("/api/content/image", json={"prompt": "a cat", "provider": f"conn:{c['id']}"}).json()[0]
    assert a["url"].startswith("/api/files/")


def test_provider_returning_garbage_is_refused(auth_client, mock_http):
    c = add(auth_client, "stability")
    mock_http.post("https://api.stability.ai/v2beta/stable-image/generate/core").respond(content=b"<html>error</html>")
    r = auth_client.post("/api/content/image", json={"prompt": "a cat", "provider": f"conn:{c['id']}"})
    assert r.status_code == 502 and "valid image" in r.json()["detail"]


def test_download_refuses_private_links(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "allow_private_providers", False)
    c = add(auth_client, "openai_images")
    mock_http.post("https://api.openai.com/v1/images/generations").respond(json={"data": [{"url": "http://internal.example/secret"}]})
    r = auth_client.post("/api/content/image", json={"prompt": "a cat", "provider": f"conn:{c['id']}"})
    assert r.status_code == 502 and "isn't allowed" in r.json()["detail"]


def test_reference_image_sent_to_fal(auth_client, mock_http):
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "a:b"}})
    up = auth_client.post("/api/brand/assets", files={"file": ("p.png", png_bytes(), "image/png")}, data={"kind": "image"}).json()["asset"]
    route = mock_http.post("https://fal.run/fal-ai/flux/dev/image-to-image").respond(json={"images": [{"url": "https://cdn.fal/x.png"}]})
    auth_client.post("/api/content/image", json={"prompt": "same product, beach", "provider": "builtin:fal",
                                                 "model": "fal-ai/flux/dev/image-to-image", "reference": f"brand:{up['id']}"})
    assert json.loads(route.calls[0].request.content)["image_url"].startswith("data:image/png;base64,")


def test_rate_limit_and_quota_messages(auth_client, mock_http):
    c = add(auth_client, "openai_images")
    mock_http.post("https://api.openai.com/v1/images/generations").mock(side_effect=[
        httpx.Response(429, json={"error": {"message": "slow down"}}),
        httpx.Response(400, json={"error": {"message": "You exceeded your current quota", "code": "insufficient_quota"}}),
    ])
    r1 = auth_client.post("/api/content/image", json={"prompt": "a cat", "provider": f"conn:{c['id']}"})
    r2 = auth_client.post("/api/content/image", json={"prompt": "a cat", "provider": f"conn:{c['id']}"})
    assert r1.status_code == 429 and "rate-limiting" in r1.json()["detail"]
    assert r2.status_code == 402 or "quota" in r2.json()["detail"]


# ---- video ------------------------------------------------------------------------------------
def test_any_fal_video_model_generic_path(auth_client, mock_http):
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "a:b"}})
    route = mock_http.post("https://queue.fal.run/fal-ai/veo3").respond(json={"status_url": "https://queue.fal.run/s/v", "response_url": "https://queue.fal.run/r/v"})
    mock_http.get("https://queue.fal.run/s/v").respond(json={"status": "COMPLETED"})
    mock_http.get("https://queue.fal.run/r/v").respond(json={"video": {"url": "https://cdn.fal/veo.mp4"}})
    a = auth_client.post("/api/content/video", json={"prompt": "city at night", "model": "fal-ai/veo3", "camera": "drone",
                                                     "style": "cinematic", "seed": 5, "generate_audio": True,
                                                     "negative_prompt": "blur", "add_sound": False}).json()
    sent = json.loads(route.calls[0].request.content)
    assert "aerial drone flyover" in sent["prompt"] and sent["seed"] == 5 and sent["generate_audio"] is True
    assert "job" not in a["params"]
    done = auth_client.get(f"/api/content/video/{a['id']}").json()
    assert done["status"] == "done" and done["url"] == "https://cdn.fal/veo.mp4" and done["params"]["has_audio"]


def test_replicate_video_downloaded_locally(auth_client, mock_http):
    c = add(auth_client, "replicate_video")
    mock_http.post("https://api.replicate.com/v1/models/wan-video/wan-2.2-t2v-fast/predictions").respond(
        json={"id": "v1", "status": "starting", "urls": {"get": "https://api.replicate.com/v1/predictions/v1"}})
    mock_http.get("https://api.replicate.com/v1/predictions/v1").mock(side_effect=[
        httpx.Response(200, json={"id": "v1", "status": "processing"}),
        httpx.Response(200, json={"id": "v1", "status": "succeeded", "output": "https://replicate.delivery/v.mp4"}),
    ])
    mock_http.get("https://replicate.delivery/v.mp4").respond(content=MP4)
    a = auth_client.post("/api/content/video", json={"prompt": "waves", "provider": f"conn:{c['id']}", "duration": "5s"}).json()
    assert auth_client.get(f"/api/content/video/{a['id']}").json()["status"] == "queued"
    done = auth_client.get(f"/api/content/video/{a['id']}").json()
    assert done["status"] == "done" and done["url"].endswith(".mp4") and auth_client.get(done["url"]).status_code == 200


WORKFLOW = {"3": {"class_type": "KSampler", "inputs": {"seed": "{{seed}}", "steps": 8}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}"}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative_prompt}}"}}}


def test_comfyui_workflow_validation(auth_client):
    base = {"preset": "comfyui_video", "verify": False}
    assert "API format" in auth_client.post("/api/providers", json={**base, "workflow": json.dumps({"nodes": [], "links": []})}).json()["detail"]
    no_prompt = {"6": {"class_type": "CLIPTextEncode", "inputs": {"text": "fixed"}}}
    assert "{{prompt}}" in auth_client.post("/api/providers", json={**base, "workflow": json.dumps(no_prompt)}).json()["detail"]
    assert "valid JSON" in auth_client.post("/api/providers", json={**base, "workflow": "{nope"}).json()["detail"]


def test_comfyui_video_end_to_end(auth_client, mock_http):
    c = add(auth_client, "comfyui_video", workflow=json.dumps(WORKFLOW), api_key="")
    submit = mock_http.post("http://localhost:8188/prompt").respond(json={"prompt_id": "abc", "node_errors": {}})
    mock_http.get("http://localhost:8188/history/abc").mock(side_effect=[
        httpx.Response(200, json={}),
        httpx.Response(200, json={"abc": {"status": {"status_str": "success"}, "outputs": {
            "9": {"gifs": [{"filename": "out.mp4", "subfolder": "", "type": "output"}]}}}}),
    ])
    mock_http.get(url__startswith="http://localhost:8188/view").respond(content=MP4)
    a = auth_client.post("/api/content/video", json={"prompt": 'say "hi"', "provider": f"conn:{c['id']}", "seed": 99,
                                                     "negative_prompt": "blurry"}).json()
    wf = json.loads(submit.calls[0].request.content)["prompt"]
    assert wf["6"]["inputs"]["text"] == 'say "hi"' and wf["3"]["inputs"]["seed"] == 99 and wf["7"]["inputs"]["text"] == "blurry"
    auth_client.get(f"/api/content/video/{a['id']}")
    done = auth_client.get(f"/api/content/video/{a['id']}").json()
    assert done["status"] == "done" and done["url"].startswith("/api/files/")


def test_video_provider_failure_marks_failed_with_reason(auth_client, mock_http):
    c = add(auth_client, "replicate_video")
    mock_http.post("https://api.replicate.com/v1/models/wan-video/wan-2.2-t2v-fast/predictions").respond(
        json={"id": "v2", "status": "starting", "urls": {"get": "https://api.replicate.com/v1/predictions/v2"}})
    mock_http.get("https://api.replicate.com/v1/predictions/v2").respond(json={"id": "v2", "status": "failed", "error": "NSFW content"})
    a = auth_client.post("/api/content/video", json={"prompt": "waves", "provider": f"conn:{c['id']}"}).json()
    done = auth_client.get(f"/api/content/video/{a['id']}").json()
    assert done["status"] == "failed" and "NSFW" in done["params"]["error"]


def test_wrong_kind_provider_rejected(auth_client):
    c = add(auth_client, "openai")
    r = auth_client.post("/api/content/video", json={"prompt": "waves", "provider": f"conn:{c['id']}"})
    assert r.status_code == 400 and "text provider" in r.json()["detail"]


# ---- website builder options -------------------------------------------------------------------
def test_site_options_render(auth_client):
    brief = {"business": "Skyline Homes", "use_ai": False, "look": "elegant", "theme": "dark", "font": "serif",
             "sections": ["features", "about", "testimonials", "pricing", "faq", "contact_info"],
             "about": "Family builders since 1998.", "testimonials": [{"name": "Asha", "quote": "Loved our new home"}],
             "pricing": [{"name": "2BHK", "price": "₹45L", "features": ["Metro access"], "highlight": True}],
             "faqs": [{"q": "Is parking included?", "a": "Yes, one slot."}],
             "form_fields": ["name", "phone", "city", "budget"], "thank_you": "Thanks <b>friend</b>!",
             "seo_title": "Skyline Homes Hyderabad", "meta_pixel_id": "1234567890", "ga4_id": "G-ABC123XYZ",
             "contact_email": "hi@skyline.example", "phone": "+91 99999 00000"}
    html = auth_client.post("/api/sites", json=brief).json()["html"]
    for bit in ("Playfair Display", "#0b1020", "Family builders since 1998", "Loved our new home", "₹45L",
                "Is parking included?", 'name="city"', 'name="budget"', "Skyline Homes Hyderabad",
                "fbq('init','1234567890')", "gtag/js?id=G-ABC123XYZ", "hi@skyline.example"):
        assert bit in html, bit
    assert "<b>friend</b>" not in html and "&lt;b&gt;friend" in html  # thank-you text is escaped


def test_sections_without_content_are_skipped(auth_client):
    html = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False,
                                                "sections": ["testimonials", "pricing", "faq"]}).json()["html"]
    assert "What customers say" not in html and "Pricing" not in html and "<details>" not in html


@pytest.mark.parametrize("bad", [
    {"form_fields": ["name", "message"]},
    {"meta_pixel_id": "abc'};alert(1)//"},
    {"ga4_id": "UA-123"},
    {"hero_image": "javascript:alert(1)"},
    {"gallery": ["http://insecure.example/a.png"]},
    {"look": "neon"},
])
def test_site_option_validation(auth_client, bad):
    assert auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False, **bad}).status_code == 422


def test_library_images_and_logo_are_embedded(auth_client):
    up = auth_client.post("/api/brand/assets", files={"file": ("l.png", png_bytes(), "image/png")}, data={"kind": "logo"}).json()["asset"]
    html = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False, "include_logo": True,
                                                "hero_image": f"brand:{up['id']}"}).json()["html"]
    assert html.count("data:image/") >= 2 and "/api/files/" not in html


def test_logo_option_needs_a_logo(auth_client):
    r = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False, "include_logo": True})
    assert r.status_code == 400 and "logo" in r.json()["detail"]


def test_public_form_custom_fields(auth_client, client):
    site = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False, "form_fields": ["name", "phone", "city", "budget"]}).json()
    auth_client.post(f"/api/sites/{site['id']}/deploy", json={"target": "aimva"})
    client.post(f"/api/public/sites/{site['slug']}/lead", data={"name": "Ravi", "phone": "+919999999999", "city": "Pune", "budget": "50L", "evil": "x" * 9000})
    lead = auth_client.get("/api/leads").json()[0]
    assert "City: Pune" in lead["message"] and "Budget: 50L" in lead["message"] and "evil" not in lead["message"]


def test_chosen_writer_used_for_site(auth_client, mock_http):
    c = add(auth_client, "anthropic", is_default=False)
    add(auth_client, "openai", is_default=True)
    page = '<html><body><h1>By Claude</h1><form data-aimva-lead><input name="phone"></form></body></html>'
    claude = mock_http.post("https://api.anthropic.com/v1/messages").respond(json={"content": [{"type": "text", "text": page}]})
    site = auth_client.post("/api/sites", json={"business": "Acme", "offer": "Free trial", "writer": f"conn:{c['id']}", "language": "Hindi",
                                                "sections": ["testimonials"], "testimonials": []}).json()
    assert site["generator"] == "ai" and "By Claude" in site["html"]
    prompt = json.loads(claude.calls[0].request.content)["messages"][0]["content"]
    assert "Hindi" in prompt and "Never invent testimonials" in prompt
