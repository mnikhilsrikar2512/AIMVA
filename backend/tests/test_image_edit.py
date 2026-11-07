"""Comment-to-edit: pins become masks, engines repaint, and only the pinned areas change."""
import io
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from PIL import Image

from app import image_edit as IE
from app.config import settings

POLL = "https://image.pollinations.ai/prompt/"
FAL_FILL = f"https://fal.run/{IE.FAL_FILL}"


def png(color, size=(256, 256)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def pixel(client, url, xy):
    return Image.open(io.BytesIO(client.get(url).content)).convert("RGB").getpixel(xy)


def make_image(client, mock_http, color=(20, 40, 200)):
    mock_http.get(url__startswith=POLL).respond(200, content=png(color), headers={"content-type": "image/png"})
    r = client.post("/api/content/image", json={"prompt": "a living room with a grey sofa", "seed": 7, "size": "1:1"})
    assert r.status_code == 200, r.text
    return r.json()[0]


PIN = {"x": 0.25, "y": 0.25, "r": 0.1, "text": "make the sofa red"}


# ---- masks and blending -------------------------------------------------------------------------
def test_only_the_pinned_area_changes():
    orig, edited = Image.new("RGB", (200, 100), (0, 0, 255)), Image.new("RGB", (400, 200), (255, 0, 0))
    out = IE.blend(orig, edited, [IE.Pin(0.5, 0.5, 0.2, "x")])
    assert out.size == (200, 100)
    assert out.getpixel((100, 50)) == (255, 0, 0)  # centre of the pin: edited
    assert out.getpixel((5, 5)) == (0, 0, 255) and out.getpixel((195, 95)) == (0, 0, 255)  # elsewhere: untouched


def test_positions_are_described_in_words():
    assert IE.where(IE.Pin(0.1, 0.1, 0.1, "")) == "top left"
    assert IE.where(IE.Pin(0.5, 0.5, 0.1, "")) == "centre"
    assert IE.where(IE.Pin(0.9, 0.5, 0.1, "")) == "middle right"
    p = IE.edit_prompt("A room.", [IE.Pin(0.9, 0.9, 0.1, "add a plant.")])
    assert p == "A room. Change only these parts: in the bottom right: add a plant. Keep everything else the same."


# ---- engines --------------------------------------------------------------------------------------
def test_free_engine_redraws_with_same_seed_and_keeps_the_rest(auth_client, mock_http):
    a = make_image(auth_client, mock_http)
    route = mock_http.get(url__startswith=POLL).respond(200, content=png((250, 10, 10)), headers={"content-type": "image/png"})
    info = auth_client.get("/api/content/image/edit-engines").json()
    engines = info["engines"]
    assert [e["ref"] for e in engines] == ["builtin:free"] and engines[0]["precise"] is False
    assert info["select_objects"] is False and info["replace_background"] is False
    r = auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [PIN]})
    assert r.status_code == 200, r.text
    e = r.json()
    q = parse_qs(urlparse(str(route.calls[-1].request.url)).query)
    assert q["seed"] == ["7"] and "make the sofa red" in unquote(str(route.calls[-1].request.url))
    assert e["params"]["edited_from"] == a["id"] and e["params"]["edit_root"] == a["id"]
    assert e["params"]["edits"][0]["text"] == "make the sofa red" and e["params"]["edit_precise"] is False
    assert pixel(auth_client, e["url"], (64, 64)) == (250, 10, 10)  # under the pin
    assert pixel(auth_client, e["url"], (250, 250)) == (20, 40, 200)  # far away: the original
    assert pixel(auth_client, a["url"], (64, 64)) == (20, 40, 200)  # the original file is never changed


def test_fal_fill_paints_each_pin_in_turn(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "fal_key", "server-fal")
    a = make_image(auth_client, mock_http)
    fill = mock_http.post(FAL_FILL).respond(json={"images": [{"url": "https://fal.media/out.png"}]})
    mock_http.get("https://fal.media/out.png").respond(200, content=png((0, 200, 0)), headers={"content-type": "image/png"})
    mock_http.post(f"https://fal.run/{IE.FAL_SEGMENT}").respond(500)  # area pins never ask for a selection
    pins = [PIN, {"x": 0.8, "y": 0.8, "r": 0.08, "text": "add a plant"}]
    r = auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": pins})
    assert r.status_code == 200, r.text
    assert fill.call_count == 2  # one pass per comment
    import json
    sent = json.loads(fill.calls[0].request.content)
    assert sent["mask_url"].startswith("data:image/png;base64,") and sent["prompt"].startswith("make the sofa red")
    assert fill.calls[0].request.headers["authorization"] == "Key server-fal"
    e = r.json()
    assert e["params"]["edit_precise"] is True and e["params"]["edit_engine"].startswith("FLUX Fill")
    assert pixel(auth_client, e["url"], (64, 64)) == (0, 200, 0) and pixel(auth_client, e["url"], (205, 205)) == (0, 200, 0)
    assert pixel(auth_client, e["url"], (128, 20)) == (20, 40, 200)


def test_openai_edits_send_a_transparent_mask(auth_client, mock_http):
    a = make_image(auth_client, mock_http)
    c = auth_client.post("/api/providers", json={"preset": "openai_images", "api_key": "sk-x", "model": "gpt-image-1", "verify": False}).json()
    import base64
    route = mock_http.post("https://api.openai.com/v1/images/edits").respond(
        json={"data": [{"b64_json": base64.b64encode(png((255, 255, 0))).decode()}]})
    r = auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [PIN], "engine": f"conn:{c['id']}"})
    assert r.status_code == 200, r.text
    body = route.calls[0].request.content
    assert b'name="mask"' in body and b"gpt-image-1" in body and b"top left: make the sofa red" in body
    assert pixel(auth_client, r.json()["url"], (64, 64)) == (255, 255, 0)


def test_edits_chain_back_to_the_first_image(auth_client, mock_http):
    a = make_image(auth_client, mock_http)
    mock_http.get(url__startswith=POLL).respond(200, content=png((1, 2, 3)), headers={"content-type": "image/png"})
    first = auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [PIN]}).json()
    second = auth_client.post(f"/api/content/image/{first['id']}/edit", json={"pins": [PIN]}).json()
    assert second["params"]["edited_from"] == first["id"] and second["params"]["edit_root"] == a["id"]


# ---- guardrails -----------------------------------------------------------------------------------
def test_edit_is_private_and_validated(auth_client, other_client, mock_http):
    a = make_image(auth_client, mock_http)
    assert other_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [PIN]}).status_code == 404
    assert auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": []}).status_code == 400  # nothing to do
    assert auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [{**PIN, "x": 1.5}]}).status_code == 422
    assert auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [PIN] * 9}).status_code == 422
    assert auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [PIN], "engine": "builtin:fal"}).status_code == 400


def test_provider_failure_gives_a_clear_message(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "fal_key", "server-fal")
    a = make_image(auth_client, mock_http)
    mock_http.post(FAL_FILL).respond(401, json={"detail": "bad key"})
    r = auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [PIN]})
    assert r.status_code in (400, 401, 502) and r.json()["detail"]


# ---- object selection ----------------------------------------------------------------------------
def object_mask_png(box, size=(256, 256)):
    m = Image.new("L", size, 0)
    from PIL import ImageDraw
    ImageDraw.Draw(m).rectangle(box, fill=255)
    buf = io.BytesIO()
    m.save(buf, "PNG")
    return buf.getvalue()


def test_object_pins_edit_exactly_the_selected_shape(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "fal_key", "server-fal")
    a = make_image(auth_client, mock_http)
    seg = mock_http.post(f"https://fal.run/{IE.FAL_SEGMENT}").respond(json={"image": {"url": "https://fal.media/mask.png"}})
    mock_http.get("https://fal.media/mask.png").respond(200, content=object_mask_png([20, 100, 230, 140]), headers={"content-type": "image/png"})
    mock_http.post(FAL_FILL).respond(json={"images": [{"url": "https://fal.media/out.png"}]})
    mock_http.get("https://fal.media/out.png").respond(200, content=png((0, 200, 0)), headers={"content-type": "image/png"})
    r = auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [{**PIN, "x": 0.5, "y": 0.47, "r": 0.05, "mode": "object"}]})
    assert r.status_code == 200, r.text
    import json
    sent = json.loads(seg.calls[0].request.content)
    assert sent["prompts"] == [{"x": 128, "y": 120, "label": 1}]
    e = r.json()
    assert e["params"]["edits"][0]["selected"] is True
    assert pixel(auth_client, e["url"], (30, 120)) == (0, 200, 0)  # inside the object, far outside the tiny circle
    assert pixel(auth_client, e["url"], (128, 30)) == (20, 40, 200)  # outside the object


def test_object_pin_falls_back_to_the_circle(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "fal_key", "server-fal")
    a = make_image(auth_client, mock_http)
    mock_http.post(f"https://fal.run/{IE.FAL_SEGMENT}").respond(json={"image": {"url": "https://fal.media/empty.png"}})
    mock_http.get("https://fal.media/empty.png").respond(200, content=object_mask_png([0, 0, 0, 0]), headers={"content-type": "image/png"})
    mock_http.post(FAL_FILL).respond(json={"images": [{"url": "https://fal.media/out.png"}]})
    mock_http.get("https://fal.media/out.png").respond(200, content=png((0, 200, 0)), headers={"content-type": "image/png"})
    r = auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [{**PIN, "mode": "object"}]})
    assert r.status_code == 200 and r.json()["params"]["edits"][0]["selected"] is False


# ---- extend, background, upscale ---------------------------------------------------------------------
def test_extend_keeps_the_original_and_paints_the_edges(auth_client, mock_http):
    a = make_image(auth_client, mock_http)  # 256 x 256
    route = mock_http.get(url__startswith=POLL).respond(200, content=png((0, 255, 0), (456, 256)), headers={"content-type": "image/png"})
    r = auth_client.post(f"/api/content/image/{a['id']}/extend", json={"size": "16:9"})
    assert r.status_code == 200, r.text
    e = r.json()
    assert (e["params"]["width"], e["params"]["height"]) == (455, 256) and e["params"]["edit_kind"] == "extend"
    assert "width=455&height=256" in str(route.calls[-1].request.url)
    assert pixel(auth_client, e["url"], (227, 128)) == (20, 40, 200)  # the middle is the original
    assert pixel(auth_client, e["url"], (5, 128)) == (0, 255, 0)  # the new left edge is painted
    assert auth_client.post(f"/api/content/image/{a['id']}/extend", json={"size": "1:1"}).status_code == 400


def test_extend_with_fal_uses_fill_on_a_bigger_canvas(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "fal_key", "server-fal")
    a = make_image(auth_client, mock_http)
    fill = mock_http.post(FAL_FILL).respond(json={"images": [{"url": "https://fal.media/out.png"}]})
    mock_http.get("https://fal.media/out.png").respond(200, content=png((0, 255, 0), (256, 455)), headers={"content-type": "image/png"})
    r = auth_client.post(f"/api/content/image/{a['id']}/extend", json={"size": "9:16"})
    assert r.status_code == 200, r.text
    import json
    from PIL import Image as I
    sent = json.loads(fill.calls[0].request.content)
    mask = I.open(io.BytesIO(base64.b64decode(sent["mask_url"].split(",", 1)[1])))
    assert mask.size == (256, 455) and mask.getpixel((128, 5)) == 255 and mask.getpixel((128, 227)) == 0
    assert pixel(auth_client, r.json()["url"], (128, 227)) == (20, 40, 200)


import base64  # noqa: E402


def test_background_keeps_the_subject(auth_client, mock_http, monkeypatch):
    a = make_image(auth_client, mock_http)
    assert auth_client.post(f"/api/content/image/{a['id']}/background", json={"prompt": "a beach at sunset"}).status_code == 400
    monkeypatch.setattr(settings, "fal_key", "server-fal")
    cut = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    from PIL import ImageDraw
    ImageDraw.Draw(cut).rectangle([80, 80, 175, 175], fill=(255, 0, 0, 255))
    buf = io.BytesIO()
    cut.save(buf, "PNG")
    mock_http.post(f"https://fal.run/{IE.FAL_CUTOUT}").respond(json={"image": {"url": "https://fal.media/cut.png"}})
    mock_http.get("https://fal.media/cut.png").respond(200, content=buf.getvalue(), headers={"content-type": "image/png"})
    mock_http.post(FAL_FILL).respond(json={"images": [{"url": "https://fal.media/out.png"}]})
    mock_http.get("https://fal.media/out.png").respond(200, content=png((255, 160, 0)), headers={"content-type": "image/png"})
    r = auth_client.post(f"/api/content/image/{a['id']}/background", json={"prompt": "a beach at sunset"})
    assert r.status_code == 200, r.text
    e = r.json()
    assert pixel(auth_client, e["url"], (128, 128)) == (20, 40, 200)  # subject kept
    assert pixel(auth_client, e["url"], (10, 10)) == (255, 160, 0)  # background replaced


def test_upscale_basic_without_a_key_and_ai_with_fal(auth_client, mock_http, monkeypatch):
    a = make_image(auth_client, mock_http)
    r = auth_client.post(f"/api/content/image/{a['id']}/upscale", json={"factor": 2})
    assert r.status_code == 200, r.text
    assert (r.json()["params"]["width"], r.json()["params"]["height"]) == (512, 512) and r.json()["params"]["edit_precise"] is False
    monkeypatch.setattr(settings, "fal_key", "server-fal")
    up = mock_http.post(f"https://fal.run/{IE.FAL_UPSCALE}").respond(json={"image": {"url": "https://fal.media/big.png"}})
    mock_http.get("https://fal.media/big.png").respond(200, content=png((9, 9, 9), (1024, 1024)), headers={"content-type": "image/png"})
    r = auth_client.post(f"/api/content/image/{a['id']}/upscale", json={"factor": 4})
    assert r.status_code == 200 and r.json()["params"]["width"] == 1024 and up.call_count == 1


# ---- remove vs change, whole-image instructions, swappable models, uploads ----------------------------
def test_comments_are_routed_by_what_they_ask(auth_client, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "fal_key", "server-fal")
    a = make_image(auth_client, mock_http)
    eraser = mock_http.post(f"https://fal.run/{IE.FAL_REMOVE}").respond(json={"images": [{"url": "https://fal.media/gone.png"}]})
    fill = mock_http.post(FAL_FILL).respond(json={"images": [{"url": "https://fal.media/out.png"}]})
    mock_http.get("https://fal.media/gone.png").respond(200, content=png((240, 240, 240)), headers={"content-type": "image/png"})
    mock_http.get("https://fal.media/out.png").respond(200, content=png((0, 200, 0)), headers={"content-type": "image/png"})
    pins = [{**PIN, "text": "remove the lamp"}, {"x": 0.8, "y": 0.8, "r": 0.08, "text": "replace the rug with a wooden floor"}]
    r = auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": pins})
    assert r.status_code == 200, r.text
    assert eraser.call_count == 1 and fill.call_count == 1
    e = r.json()
    assert [x["action"] for x in e["params"]["edits"]] == ["remove", "change"]
    assert pixel(auth_client, e["url"], (64, 64)) == (240, 240, 240) and pixel(auth_client, e["url"], (205, 205)) == (0, 200, 0)
    # The user can overrule the guess.
    auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [{**PIN, "text": "remove the lamp", "action": "change"}]})
    assert eraser.call_count == 1 and fill.call_count == 2


def test_intent_reading():
    for t in ("remove the lamp", "Please delete the cup", "get rid of the dog", "erase the text", "hide the logo"):
        assert IE.intent(t) == "remove", t
    for t in ("make the sofa blue", "add a plant", "replace the lamp with a plant", "remove the lamp and add a plant"):
        assert IE.intent(t) == "change", t


def test_whole_image_instruction(auth_client, mock_http, monkeypatch):
    a = make_image(auth_client, mock_http)
    assert auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [], "instruction": ""}).status_code == 400
    monkeypatch.setattr(settings, "fal_key", "server-fal")
    kontext = mock_http.post(f"https://fal.run/{IE.FAL_INSTRUCT}").respond(json={"images": [{"url": "https://fal.media/night.png"}]})
    mock_http.get("https://fal.media/night.png").respond(200, content=png((10, 10, 40), (512, 512)), headers={"content-type": "image/png"})
    r = auth_client.post(f"/api/content/image/{a['id']}/edit", json={"instruction": "make it night time"})
    assert r.status_code == 200, r.text
    import json
    assert json.loads(kontext.calls[0].request.content)["prompt"] == "make it night time"
    e = r.json()
    assert e["params"]["instruction"] == "make it night time" and (e["params"]["width"], e["params"]["height"]) == (256, 256)
    assert pixel(auth_client, e["url"], (250, 250)) == (10, 10, 40)  # the whole image may change


def test_models_can_be_swapped_from_env(auth_client, mock_http, monkeypatch):
    monkeypatch.setenv("EDIT_MODEL_REMOVE", "fal-ai/better-eraser")
    monkeypatch.setattr(settings, "fal_key", "server-fal")
    a = make_image(auth_client, mock_http)
    better = mock_http.post("https://fal.run/fal-ai/better-eraser").respond(json={"image": {"url": "https://fal.media/gone.png"}})
    mock_http.get("https://fal.media/gone.png").respond(200, content=png((240, 240, 240)), headers={"content-type": "image/png"})
    r = auth_client.post(f"/api/content/image/{a['id']}/edit", json={"pins": [{**PIN, "text": "remove the lamp"}]})
    assert r.status_code == 200 and better.call_count == 1
    info = auth_client.get("/api/content/image/edit-engines").json()
    m = {x["task"]: x for x in info["models"]}
    assert m["remove"]["default"] is False and m["fill"]["default"] is True  # the swapped model is used (call_count above)
    assert "fal" not in m["remove"]["model"].lower()  # but never named to the customer


def test_upload_your_own_photo_and_edit_it(auth_client, mock_http):
    from PIL import Image as I
    # A sideways phone photo: EXIF orientation 6 means "rotate 90° clockwise to view".
    photo = I.new("RGB", (300, 200), (30, 90, 160))
    exif = photo.getexif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    photo.save(buf, "JPEG", exif=exif.tobytes())
    r = auth_client.post("/api/content/image/upload", files={"file": ("IMG_0042.jpg", buf.getvalue(), "image/jpeg")},
                         data={"description": "our showroom"})
    assert r.status_code == 200, r.text
    up = r.json()
    assert up["model"] == "uploaded" and up["params"]["uploaded"] is True
    assert (up["params"]["width"], up["params"]["height"]) == (200, 300)  # turned upright
    mock_http.get(url__startswith=POLL).respond(200, content=png((250, 10, 10), (200, 300)), headers={"content-type": "image/png"})
    e = auth_client.post(f"/api/content/image/{up['id']}/edit", json={"pins": [PIN]})
    assert e.status_code == 200 and e.json()["params"]["edited_from"] == up["id"]
    assert auth_client.post("/api/content/image/upload", files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 400


def test_style_presets_restyle_the_whole_image(auth_client, mock_http, monkeypatch):
    import json
    styles = auth_client.get("/api/content/image/styles").json()
    ids = {s["id"] for s in styles}
    assert {"skeleton", "portrait", "anime"} <= ids and all(s["hint"] and s["group"] for s in styles)
    a = make_image(auth_client, mock_http)
    assert auth_client.post(f"/api/content/image/{a['id']}/edit", json={"style": "nope"}).status_code == 400
    monkeypatch.setattr(settings, "fal_key", "server-fal")
    kontext = mock_http.post(f"https://fal.run/{IE.FAL_INSTRUCT}").respond(json={"images": [{"url": "https://fal.media/bones.png"}]})
    mock_http.get("https://fal.media/bones.png").respond(200, content=png((200, 200, 200), (512, 512)), headers={"content-type": "image/png"})
    r = auth_client.post(f"/api/content/image/{a['id']}/edit", json={"style": "/Skeleton", "instruction": "keep the red hat"})
    assert r.status_code == 200, r.text
    sent = json.loads(kontext.calls[0].request.content)["prompt"]
    assert "skeleton" in sent and sent.endswith("Also: keep the red hat")
    p = r.json()["params"]
    assert p["restyle"] == "Skeleton" and p["edit_kind"] == "style" and p["provider_label"] == "Skeleton style"
    assert p["instruction"] == "keep the red hat"
