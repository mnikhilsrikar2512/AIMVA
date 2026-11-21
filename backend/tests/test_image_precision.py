"""Image precision: structured prompt briefs, keeping the real product, and text layers typeset by AIMVA."""
import io
import json

from PIL import Image

from app import image_brief as B
from app import image_edit as IE
from app import text_layers as TL


def png(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def upload(client, img, name="product.png"):
    r = client.post("/api/content/image/upload", files={"file": (name, png(img), "image/png")}, data={"description": "our bottle"})
    assert r.status_code == 200, r.text
    return r.json()


BRIEF = {"subject": "the product on the left third", "setting": "a marble kitchen counter",
         "composition": "eye level, plenty of space above", "lighting": "soft window light from the left",
         "camera": "50mm lens, shallow depth of field", "colours": "warm whites and sage", "mood": "fresh and calm"}


# ---- structured briefs --------------------------------------------------------------------------------------
def test_brief_keeps_the_users_words_first_and_orders_fields():
    out, brief = B.brief_prompt(lambda p, system="", max_tokens=0: "Sure!\n" + json.dumps(BRIEF), "Steel water bottle")
    assert brief and out.startswith("Steel water bottle. the product on the left third. Setting: a marble kitchen counter")
    assert out.index("Lighting:") < out.index("Camera:") < out.index("Mood:")


def test_brief_falls_back_to_the_idea_when_the_writer_cant_help():
    assert B.brief_prompt(None, "red car") == ("red car", None)
    assert B.brief_prompt(lambda *a, **k: None, "red car") == ("red car", None)
    assert B.brief_prompt(lambda *a, **k: "not json at all", "red car") == ("red car", None)
    assert B.brief_prompt(lambda *a, **k: '{"subject": "a car"}', "red car") == ("red car", None)  # too thin to use


def test_product_brief_tells_the_writer_not_to_redraw_the_product():
    asked = {}

    def write(prompt, system="", max_tokens=0):
        asked["prompt"], asked["system"] = prompt, system
        return json.dumps(BRIEF)
    B.brief_prompt(write, "bottle on a beach", product=True, for_ad=True)
    assert "don't describe or change the product" in asked["prompt"] and "headline" in asked["prompt"]
    assert "Don't invent" in asked["system"]


def test_generation_sends_the_brief_and_keeps_it(auth_client, mock_http, monkeypatch):
    from app.routers import content
    monkeypatch.setattr(content, "writer", lambda *a, **k: (lambda p, system="", max_tokens=0: json.dumps(BRIEF)))
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (90, 140, 200)).save(buf, "JPEG")
    route = mock_http.get(url__startswith="https://image.pollinations.ai/prompt/").respond(
        200, content=buf.getvalue(), headers={"content-type": "image/jpeg"})
    a = auth_client.post("/api/content/image", json={"prompt": "steel bottle"}).json()[0]
    assert "marble%20kitchen%20counter" in str(route.calls.last.request.url)
    assert a["prompt"] == "steel bottle" and a["params"]["brief"]["setting"] == "a marble kitchen counter"
    # Turned off: the idea goes as typed.
    a = auth_client.post("/api/content/image", json={"prompt": "steel bottle", "smart_prompt": False}).json()[0]
    assert "marble" not in str(route.calls.last.request.url) and a["params"]["brief"] is None


# ---- keep the real product ------------------------------------------------------------------------------------
def product_photo():
    img = Image.new("RGB", (300, 300), (255, 255, 255))
    for x in range(100, 200):
        for y in range(60, 260):
            img.putpixel((x, y), (200 + (x % 7), 30 + (y % 11), 40))  # a textured red "bottle"
    mask = Image.new("L", img.size, 0)
    mask.paste(255, (100, 60, 200, 260))
    return img, mask


def test_product_pixels_survive_the_new_scene():
    product, mask = product_photo()
    seen = {}

    def fake_fill(key, canvas, repaint, prompt):
        seen["prompt"], seen["repaint"] = prompt, repaint
        return Image.new("RGB", canvas.size, (10, 200, 10))  # the model paints everything green, product included
    out = IE.product_scene("k", product, (512, 640), "a beach at sunset", subject_mask=lambda k, img: mask, fill_fn=fake_fill)
    assert out.size == (512, 640) and "a beach at sunset" in seen["prompt"] and "No text" in seen["prompt"]
    canvas, pmask = IE.place_product(product, mask, (512, 640))
    inner = pmask.point(lambda v: 255 if v == 255 else 0).filter(__import__("PIL.ImageFilter").ImageFilter.MinFilter(11))  # a few px in from the feathered edge
    box = inner.getbbox()
    assert box
    # Inside the product, every pixel is the original; outside it is the model's scene.
    assert out.crop(box).tobytes() == canvas.crop(box).tobytes()
    assert out.getpixel((5, 5)) == (10, 200, 10)
    assert seen["repaint"].getpixel((5, 5)) == 255 and seen["repaint"].getpixel(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)) == 0


def test_product_without_a_subject_is_refused():
    import pytest
    blank = Image.new("L", (50, 50), 0)
    with pytest.raises(IE.EditFailed) as e:
        IE.place_product(Image.new("RGB", (50, 50)), blank, (100, 100))
    assert e.value.status == 422


def test_keep_product_endpoint(auth_client, monkeypatch):
    from app.routers import content
    product, mask = product_photo()
    up = upload(auth_client, product)
    body = {"prompt": "bottle on a beach", "keep_product": True, "size": "1:1", "model": "studio-fast"}
    r = auth_client.post("/api/content/image", json=body)
    assert r.status_code == 400 and "reference" in r.json()["detail"]
    body["reference"] = f"asset:{up['id']}"
    r = auth_client.post("/api/content/image", json=body)
    assert r.status_code == 400 and "switched on" in r.json()["detail"]
    monkeypatch.setattr(content, "_fal_key", lambda db, user: "k")
    monkeypatch.setattr(IE, "fal_subject_mask", lambda key, img: mask.resize(img.size))
    monkeypatch.setattr(IE, "fill", lambda key, canvas, repaint, prompt: Image.new("RGB", canvas.size, (0, 0, 255)))
    r = auth_client.post("/api/content/image", json={**body, "count": 2})
    assert r.status_code == 200, r.text
    assets = r.json()
    assert len(assets) == 2 and assets[0]["params"]["kept_product"] is True
    assert assets[0]["params"]["provider_label"] == "Your product, new scene"
    from app.discreet import leaks
    assert not leaks(str(assets))


# ---- text layers ------------------------------------------------------------------------------------------------
def test_script_detection_picks_noto_for_indian_scripts():
    assert TL.script_of("ऑफ़र") == "Devanagari" and TL.script_of("ఆఫర్") == "Telugu" and TL.script_of("சலுகை") == "Tamil"
    assert TL.script_of("₹499") is None and TL.script_of("Sale") is None
    for _, name in TL.SCRIPTS:
        assert (TL.FONTS / "noto" / f"NotoSans{name}.ttf").is_file()


def test_render_draws_text_and_keeps_the_rest():
    img = Image.new("RGB", (400, 300), (40, 60, 90))
    out = TL.render(img, [{"text": "₹499 ऑफ़र", "x": 0.5, "y": 0.2, "size": 0.08, "color": "#ffffff", "weight": "bold"},
                          {"text": "Book now", "x": 0.5, "y": 0.8, "size": 0.05, "color": "#ffcc00", "bg": "pill"}])
    assert out.size == img.size
    top = out.crop((0, 20, 400, 100))
    assert max(p[0] for p in top.getdata()) > 200  # white glyphs drawn
    assert out.getpixel((5, 150)) == (40, 60, 90)  # untouched away from the text
    assert (255, 204, 0) in set(out.crop((0, 200, 400, 300)).getdata())  # the button


def test_text_versions_replace_old_text_instead_of_stacking(auth_client):
    up = upload(auth_client, Image.new("RGB", (400, 400), (40, 60, 90)))
    layer = {"text": "Diwali sale ₹999", "x": 0.5, "y": 0.15, "size": 0.07, "color": "#ffffff", "weight": "bold", "bg": "band"}
    v1 = auth_client.post(f"/api/content/image/{up['id']}/text", json={"layers": [layer]})
    assert v1.status_code == 200, v1.text
    v1 = v1.json()
    assert v1["params"]["text_base"] == up["id"] and v1["params"]["text_layers"][0]["text"] == "Diwali sale ₹999"
    assert v1["params"]["edited_from"] == up["id"]
    # Editing the text again draws on the original, not on the old text.
    v2 = auth_client.post(f"/api/content/image/{v1['id']}/text", json={"layers": []}).json()
    assert v2["params"]["text_base"] == up["id"] and v2["params"]["text_layers"] == []
    plain = Image.open(io.BytesIO(auth_client.get(up["url"]).content)).convert("RGB")
    cleared = Image.open(io.BytesIO(auth_client.get(v2["url"]).content)).convert("RGB")
    assert cleared.getpixel((200, 60)) == plain.getpixel((200, 60))
    bad = {**layer, "color": "red"}
    assert auth_client.post(f"/api/content/image/{up['id']}/text", json={"layers": [bad]}).status_code == 422
    assert auth_client.post("/api/content/image/999999/text", json={"layers": [layer]}).status_code == 404


# ---- ad briefs without a fixed structure (owner rule 2026-11-21) ------------------------------------------------
def test_free_prose_brief_is_used_as_written_after_the_owners_words():
    prose = ("A steaming cup of filter coffee in a steel dabara on a sunlit Chennai doorstep, morning steam catching "
             "the light, the cup filling most of the frame")
    out, brief = B.brief_prompt(lambda *a, **k: json.dumps({"prompt": prose}), "Filter coffee for my cafe")
    assert brief == {"prompt": prose}
    assert out == f"Filter coffee for my cafe. {prose}."
    assert "Setting:" not in out and "Camera:" not in out  # no forced sections


def test_prose_that_already_opens_with_the_idea_isnt_repeated():
    prose = "Filter coffee for my cafe, served in a steel tumbler on a banana leaf, close up so it fills a phone screen."
    out, _ = B.brief_prompt(lambda *a, **k: json.dumps({"prompt": prose}), "Filter coffee for my cafe")
    assert out == prose


def test_too_short_prose_falls_back_to_the_idea():
    assert B.brief_prompt(lambda *a, **k: '{"prompt": "coffee"}', "Filter coffee") == ("Filter coffee", None)


def test_writer_is_asked_for_what_sells_not_a_template():
    asked = {}

    def write(prompt, system="", max_tokens=0):
        asked["prompt"], asked["system"] = prompt, system
        return json.dumps({"prompt": "x" * 60})
    B.brief_prompt(write, "Diwali sweets box", hint="warm festive colours", for_ad=True)
    sys = asked["system"]
    assert "not by a template" in sys and "hero" in sys and "stops the scroll" in sys
    assert "subject" not in sys and "lower third" not in asked["prompt"]
    assert "use only if it fits" in asked["prompt"]
