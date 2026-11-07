"""Brand kit: uploads, palette, privacy, and its use in image/video generation and ad copy."""
import io
import json

import httpx
from PIL import Image

POLL = "https://image.pollinations.ai/prompt/"


def png(color=(109, 93, 252, 255), size=(120, 60), mode="RGBA", fmt="PNG"):
    buf = io.BytesIO()
    img = Image.new(mode, size, color)
    if mode == "RGBA":  # two-tone logo on transparent background
        for x in range(size[0] // 2, size[0]):
            for y in range(size[1]):
                img.putpixel((x, y), (255, 138, 101, 255))
        for y in range(5):
            img.putpixel((0, y), (0, 0, 0, 0))
    img.save(buf, fmt)
    return buf.getvalue()


def upload(c, data, kind="logo", name="logo.png"):
    return c.post("/api/brand/assets", files={"file": (name, data, "image/png")}, data={"kind": kind})


def test_empty_kit(auth_client):
    k = auth_client.get("/api/brand").json()
    assert k["is_set_up"] is False and k["logos"] == [] and k["voice"] == "friendly"


def test_save_kit_validates(auth_client):
    good = {"name": "Skyline Homes", "tagline": "Homes near the metro", "colors": ["#6D5DFC", "#ff8a65", "#6d5dfc"],
            "voice": "luxury", "style": ["bright natural light", "minimal", " "], "audience": "young families",
            "avoid": "cartoons, clutter"}
    k = auth_client.put("/api/brand", json=good).json()
    assert k["colors"] == ["#6d5dfc", "#ff8a65"] and k["style"] == ["bright natural light", "minimal"]
    assert k["is_set_up"] is True and auth_client.get("/api/brand").json()["voice"] == "luxury"
    assert auth_client.put("/api/brand", json={**good, "colors": ["red"]}).status_code == 422
    assert auth_client.put("/api/brand", json={**good, "voice": "angry"}).status_code == 422


def test_logo_upload_suggests_palette_and_becomes_primary(auth_client):
    r = upload(auth_client, png())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["asset"]["is_primary"] and body["asset"]["width"] == 120
    assert "#6d5dfc" in body["suggested_colors"] and "#ff8a65" in body["suggested_colors"]
    second = upload(auth_client, png((0, 120, 80, 255))).json()["asset"]
    assert second["is_primary"] is False
    k = auth_client.post(f"/api/brand/assets/{second['id']}/primary").json()
    assert k["logos"][0]["id"] == second["id"] and k["logos"][0]["is_primary"]
    assert auth_client.get(f"/api/brand/assets/{second['id']}/palette").json()["colors"]


def test_rejects_non_images_and_svg(auth_client):
    assert upload(auth_client, b"<svg onload=alert(1)></svg>", name="x.svg").status_code == 400
    assert upload(auth_client, b"%PDF-1.4 not an image", name="x.pdf").status_code == 400
    gif = png(mode="RGB", fmt="GIF")
    assert upload(auth_client, gif, name="x.gif").status_code == 400
    assert upload(auth_client, png(fmt="WEBP"), name="x.webp").status_code == 200
    big = b"\x89PNG" + b"0" * (5 * 1024 * 1024 + 10)
    r = upload(auth_client, big)
    assert r.status_code == 400 and "5 MB" in r.json()["detail"]


def test_files_are_private(auth_client, other_client, client):
    a = upload(auth_client, png()).json()["asset"]
    assert auth_client.get(a["url"]).headers["content-type"] == "image/png"
    assert auth_client.get(a["url"]).headers["x-content-type-options"] == "nosniff"
    assert other_client.get(a["url"]).status_code == 404
    assert client.get(a["url"]).status_code == 401
    r = auth_client.get("/api/files/../../app/config.py")  # normalised to /app/config.py: never the source file
    assert r.status_code == 404 or "class Settings" not in r.text
    assert other_client.delete(f"/api/brand/assets/{a['id']}").status_code == 404


def test_delete_promotes_next_logo_and_removes_file(auth_client):
    first = upload(auth_client, png()).json()["asset"]
    second = upload(auth_client, png((10, 10, 10, 255))).json()["asset"]
    k = auth_client.delete(f"/api/brand/assets/{first['id']}").json()
    assert [l["id"] for l in k["logos"]] == [second["id"]] and k["logos"][0]["is_primary"]
    assert auth_client.get(first["url"]).status_code == 404


def test_image_prompt_uses_brand_kit(auth_client, mock_http):
    auth_client.put("/api/brand", json={"colors": ["#6d5dfc"], "style": ["minimal", "warm light"],
                                        "audience": "young families", "avoid": "text overlays"})
    route = mock_http.get(url__startswith=POLL).respond(200, content=png(), headers={"content-type": "image/png"})
    auth_client.post("/api/content/image", json={"prompt": "living room", "use_brand": True})
    url = str(route.calls.last.request.url)
    for bit in ("minimal", "warm%20light", "%236d5dfc", "young%20families", "avoid"):
        assert bit in url, bit
    auth_client.post("/api/content/image", json={"prompt": "living room"})
    assert "minimal" not in str(route.calls.last.request.url)


def test_add_logo_composites_onto_image(auth_client, mock_http):
    assert auth_client.post("/api/content/image", json={"prompt": "living room", "add_logo": True}).status_code == 400
    upload(auth_client, png())
    buf = io.BytesIO()
    Image.new("RGB", (400, 400), (240, 240, 240)).save(buf, "JPEG")
    mock_http.get(url__startswith=POLL).respond(200, content=buf.getvalue(), headers={"content-type": "image/jpeg"})
    asset = auth_client.post("/api/content/image", json={"prompt": "living room", "add_logo": True,
                                                         "logo_position": "bottom-right"}).json()[0]
    assert asset["url"].startswith("/api/files/") and asset["params"]["logo"] is True
    img = Image.open(io.BytesIO(auth_client.get(asset["url"]).content)).convert("RGB")
    assert img.getpixel((5, 5))[0] > 200  # background untouched top-left
    r, g, b = img.getpixel((330, 360))  # logo sits bottom-right
    assert (r, g, b) != (240, 240, 240)


def test_add_logo_handles_provider_failure(auth_client, mock_http):
    upload(auth_client, png())
    mock_http.get(url__startswith=POLL).mock(side_effect=httpx.ConnectError("down"))
    assert auth_client.post("/api/content/image", json={"prompt": "x room", "add_logo": True}).status_code == 502


def test_video_uses_brand_and_start_image(auth_client, other_client, mock_http):
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "k"}})
    auth_client.put("/api/brand", json={"style": ["cinematic"]})
    img = upload(auth_client, png(), kind="image", name="product.png").json()["asset"]
    route = mock_http.post("https://queue.fal.run/fal-ai/luma-dream-machine/ray-2/image-to-video").respond(
        json={"status_url": "s", "response_url": "r"})
    v = auth_client.post("/api/content/video", json={"prompt": "slow pan", "model": "fal-ai/luma-dream-machine/ray-2", "use_brand": True, "start_image_id": img["id"]}).json()
    sent = json.loads(route.calls[0].request.content)
    assert sent["image_url"].startswith("data:image/png;base64,") and "cinematic" in sent["prompt"]
    assert any("image-to-video" in str(c.request.url) for c in mock_http.calls)  # the start image picks the image-to-video engine
    assert "fal" not in v["model"].lower()  # the customer sees a neutral engine name
    theirs = upload(other_client, png(), kind="image").json()["asset"]
    assert auth_client.post("/api/content/video", json={"prompt": "slow pan", "model": "fal-ai/luma-dream-machine/ray-2", "start_image_id": theirs["id"]}).status_code == 404


def test_ad_copy_follows_brand_voice(auth_client):
    auth_client.put("/api/brand", json={"voice": "luxury", "tagline": "Live above the city", "audience": "executives"})
    r = auth_client.post("/api/content/ad-copy", json={"product": "Skyline Homes"}).json()
    assert "elegant" in r["tone"]
    assert "Live above the city" in r["variants"][0]["headline"] and "executives" in r["variants"][0]["headline"]


def test_files_cannot_step_into_another_account_with_dotdot(auth_client, other_client):
    """Regression: /api/files/<me>/../<them>/<file> used to pass the "starts with my id" check and return their file."""
    a = upload(auth_client, png()).json()["asset"]
    owner_id, name = a["url"].removeprefix("/api/files/").split("/", 1)
    me = other_client.get("/api/auth/me").json()["user"]["id"]
    for path in (f"{me}/../{owner_id}/{name}", f"{me}/%2e%2e/{owner_id}/{name}", f"{me}/..%2f{owner_id}/{name}"):
        assert other_client.get(f"/api/files/{path}").status_code == 404, path
    assert auth_client.get(a["url"]).status_code == 200  # the owner still gets it
