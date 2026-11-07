import httpx

FAL_KEY = {"values": {"api_key": "fal-test"}}


def test_models_mark_fal_unavailable_without_key(auth_client):
    m = auth_client.get("/api/content/models").json()
    assert m["fal_connected"] is False
    avail = {x["id"]: x["available"] for x in m["image"]}
    assert avail["pollinations/flux"] is True and avail["fal-ai/flux/schnell"] is False
    auth_client.post("/api/integrations/fal/key", json=FAL_KEY)
    assert auth_client.get("/api/content/models").json()["fal_connected"] is True


def jpeg(size=(64, 64)):
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", size, (90, 140, 200)).save(b, "JPEG")
    return b.getvalue()


def test_free_image_generation_fetches_once_and_keeps_a_copy(auth_client, mock_http):
    route = mock_http.get(url__startswith="https://image.pollinations.ai/prompt/").respond(200, content=jpeg(), headers={"content-type": "image/jpeg"})
    r = auth_client.post("/api/content/image", json={"prompt": "red sports car", "size": "16:9", "count": 4})
    assert r.status_code == 200
    assets = r.json()
    assert len(assets) == 1 and route.call_count == 1  # free tier: one at a time
    sent = str(route.calls.last.request.url)
    assert sent.startswith("https://image.pollinations.ai/prompt/red%20sports%20car") and "width=1344&height=768" in sent
    assert assets[0]["url"].startswith("/api/files/") and assets[0]["params"]["seed"]  # stored privately, real seed kept
    assert auth_client.get(assets[0]["url"]).headers["content-type"].startswith("image/")
    assert auth_client.get("/api/content/assets?kind=image").json()[0]["id"] == assets[0]["id"]


def test_free_image_rate_limit_is_explained_not_saved(auth_client, mock_http):
    # Pollinations answers over-limit requests with a 402 and an "at its limit" picture: never save that as a result.
    mock_http.get(url__startswith="https://image.pollinations.ai/prompt/").respond(
        402, content=jpeg(), headers={"content-type": "image/jpeg", "retry-after": "19"})
    r = auth_client.post("/api/content/image", json={"prompt": "red sports car"})
    assert r.status_code == 429 and "19 seconds" in r.json()["detail"] and "fal.ai" in r.json()["detail"]
    assert auth_client.get("/api/content/assets?kind=image").json() == []
    mock_http.get(url__startswith="https://image.pollinations.ai/prompt/").respond(200, text="<html>oops</html>",
                                                                                  headers={"content-type": "text/html"})
    assert auth_client.post("/api/content/image", json={"prompt": "red sports car"}).status_code == 502


def test_image_prompt_validation(auth_client):
    assert auth_client.post("/api/content/image", json={"prompt": "hi"}).status_code == 422
    assert auth_client.post("/api/content/image", json={"prompt": "valid prompt", "count": 9}).status_code == 422


def test_fal_model_needs_key(auth_client):
    r = auth_client.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell"})
    assert r.status_code == 400 and "fal.ai" in r.json()["detail"]


def test_fal_image_generation(auth_client, mock_http):
    auth_client.post("/api/integrations/fal/key", json=FAL_KEY)
    route = mock_http.post("https://fal.run/fal-ai/flux/schnell").respond(
        json={"images": [{"url": "https://cdn.fal/1.png"}, {"url": "https://cdn.fal/2.png"}]})
    r = auth_client.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/schnell", "count": 2})
    assert [a["url"] for a in r.json()] == ["https://cdn.fal/1.png", "https://cdn.fal/2.png"]
    assert route.calls[0].request.headers["authorization"] == "Key fal-test"


def test_fal_error_surfaces_as_502(auth_client, mock_http):
    auth_client.post("/api/integrations/fal/key", json=FAL_KEY)
    mock_http.post("https://fal.run/fal-ai/flux/dev").respond(401, json={"detail": "bad key"})
    r = auth_client.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/dev"})
    assert r.status_code == 400 and "rejected your API key" in r.json()["detail"]


def test_fal_network_failure_is_handled(auth_client, mock_http):
    auth_client.post("/api/integrations/fal/key", json=FAL_KEY)
    mock_http.post("https://fal.run/fal-ai/flux/dev").mock(side_effect=httpx.ConnectTimeout("timeout"))
    r = auth_client.post("/api/content/image", json={"prompt": "a cat", "model": "fal-ai/flux/dev"})
    assert r.status_code == 502


def test_video_needs_key(auth_client):
    assert auth_client.post("/api/content/video", json={"prompt": "drone shot"}).status_code == 400


def test_video_queue_and_polling(auth_client, mock_http):
    auth_client.post("/api/integrations/fal/key", json=FAL_KEY)
    mock_http.post("https://queue.fal.run/fal-ai/luma-dream-machine/ray-2").respond(
        json={"request_id": "r1", "status_url": "https://queue.fal.run/status/r1", "response_url": "https://queue.fal.run/res/r1"})
    mock_http.get("https://queue.fal.run/status/r1").mock(side_effect=[
        httpx.Response(200, json={"status": "IN_PROGRESS"}), httpx.Response(200, json={"status": "COMPLETED"})])
    mock_http.get("https://queue.fal.run/res/r1").respond(json={"video": {"url": "https://cdn.fal/v.mp4"}})

    a = auth_client.post("/api/content/video", json={"prompt": "drone shot over beach", "model": "fal-ai/luma-dream-machine/ray-2", "add_sound": False}).json()
    assert a["status"] == "queued"
    assert "status_url" not in a["params"]  # internal queue URLs stay server-side
    assert auth_client.get(f"/api/content/video/{a['id']}").json()["status"] == "queued"
    done = auth_client.get(f"/api/content/video/{a['id']}").json()
    assert done["status"] == "done" and done["url"] == "https://cdn.fal/v.mp4"


def test_assets_are_private(auth_client, other_client, mock_http):
    mock_http.get(url__startswith="https://image.pollinations.ai/").respond(200, content=jpeg(), headers={"content-type": "image/jpeg"})
    a = auth_client.post("/api/content/image", json={"prompt": "secret product"}).json()[0]
    assert other_client.get("/api/content/assets").json() == []
    assert other_client.get(a["url"]).status_code == 404  # the stored copy is private too
    assert other_client.get(f"/api/content/video/{a['id']}").status_code == 404
    other_client.delete(f"/api/content/assets/{a['id']}")
    assert len(auth_client.get("/api/content/assets").json()) == 1
    auth_client.delete(f"/api/content/assets/{a['id']}")
    assert auth_client.get("/api/content/assets").json() == []


def test_ad_copy_template_fallback(auth_client):
    r = auth_client.post("/api/content/ad-copy", json={"product": "Skyline Homes", "audience": "families"}).json()
    assert r["source"] == "template" and len(r["variants"]) == 3
    assert all(v["headline"] and v["text"] for v in r["variants"])



def test_fal_out_of_credit_message(auth_client, mock_http):
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "a:b"}})
    mock_http.post("https://queue.fal.run/fal-ai/luma-dream-machine/ray-2").respond(
        403, json={"detail": "User is locked. Reason: Exhausted balance."})
    r = auth_client.post("/api/content/video", json={"prompt": "drone shot", "model": "fal-ai/luma-dream-machine/ray-2"})
    assert r.status_code == 402 and "out of credit" in r.json()["detail"]



def _fal_job(mock_http, model, name, video_url):
    mock_http.post(f"https://queue.fal.run/{model}").respond(
        json={"status_url": f"https://queue.fal.run/s/{name}", "response_url": f"https://queue.fal.run/r/{name}"})
    mock_http.get(f"https://queue.fal.run/s/{name}").respond(json={"status": "COMPLETED"})
    mock_http.get(f"https://queue.fal.run/r/{name}").respond(json={"video": {"url": video_url}})


def test_models_describe_audio_and_durations(auth_client):
    vids = {m["id"]: m for m in auth_client.get("/api/content/models").json()["video"]}
    assert vids["fal-ai/ltx-2/text-to-video"]["audio"] is True
    assert vids["fal-ai/luma-dream-machine/ray-2"]["audio"] is False and vids["fal-ai/luma-dream-machine/ray-2"]["durations"] == ["5s", "9s"]


def test_ltx2_generates_with_audio_and_valid_payload(auth_client, mock_http):
    import json as _json
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "a:b"}})
    _fal_job(mock_http, "fal-ai/ltx-2/text-to-video", "ltx", "https://cdn.fal/ltx.mp4")
    a = auth_client.post("/api/content/video", json={"prompt": "beach villa at sunset", "model": "fal-ai/ltx-2/text-to-video",
                                                   "duration": "9s", "aspect_ratio": "16:9"}).json()
    sent = _json.loads(mock_http.calls[0].request.content)
    assert sent["generate_audio"] is True and sent["duration"] == "6" and "aspect_ratio" not in sent
    done = auth_client.get(f"/api/content/video/{a['id']}").json()
    assert done["status"] == "done" and done["params"]["has_audio"] is True and done["url"] == "https://cdn.fal/ltx.mp4"


def test_kling_gets_its_own_duration_format(auth_client, mock_http):
    import json as _json
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "a:b"}})
    route = mock_http.post("https://queue.fal.run/fal-ai/kling-video/v2.1/standard/text-to-video").respond(json={"status_url": "s", "response_url": "r"})
    auth_client.post("/api/content/video", json={"prompt": "city timelapse", "model": "fal-ai/kling-video/v2.1/standard/text-to-video", "duration": "10"})
    assert _json.loads(route.calls[0].request.content)["duration"] == "10"


def test_silent_model_gets_sound_added_automatically(auth_client, mock_http):
    import json as _json
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "a:b"}})
    _fal_job(mock_http, "fal-ai/luma-dream-machine/ray-2", "luma", "https://cdn.fal/silent.mp4")
    _fal_job(mock_http, "fal-ai/mmaudio-v2", "audio", "https://cdn.fal/with-sound.mp4")
    a = auth_client.post("/api/content/video", json={"prompt": "waves on a beach", "model": "fal-ai/luma-dream-machine/ray-2", "duration": "9s",
                                                   "sound_prompt": "gentle waves and seagulls"}).json()
    mid = auth_client.get(f"/api/content/video/{a['id']}").json()
    assert mid["status"] == "queued" and mid["params"]["stage"] == "audio"
    sound_req = _json.loads(next(c.request.content for c in mock_http.calls if "mmaudio" in str(c.request.url)))
    assert sound_req["video_url"] == "https://cdn.fal/silent.mp4" and sound_req["prompt"] == "gentle waves and seagulls"
    assert sound_req["duration"] == 9.0
    done = auth_client.get(f"/api/content/video/{a['id']}").json()
    assert done["status"] == "done" and done["url"] == "https://cdn.fal/with-sound.mp4" and done["params"]["has_audio"]


def test_failed_sound_keeps_the_silent_video(auth_client, mock_http):
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "a:b"}})
    _fal_job(mock_http, "fal-ai/luma-dream-machine/ray-2", "luma", "https://cdn.fal/silent.mp4")
    mock_http.post("https://queue.fal.run/fal-ai/mmaudio-v2").respond(json={"status_url": "https://queue.fal.run/s/a2", "response_url": "https://queue.fal.run/r/a2"})
    mock_http.get("https://queue.fal.run/s/a2").respond(json={"status": "FAILED"})
    a = auth_client.post("/api/content/video", json={"prompt": "waves", "model": "fal-ai/luma-dream-machine/ray-2"}).json()
    auth_client.get(f"/api/content/video/{a['id']}")
    done = auth_client.get(f"/api/content/video/{a['id']}").json()
    assert done["status"] == "done" and done["url"] == "https://cdn.fal/silent.mp4" and done["params"]["audio_error"]


def test_add_sound_to_existing_video(auth_client, other_client, mock_http):
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "a:b"}})
    _fal_job(mock_http, "fal-ai/luma-dream-machine/ray-2", "luma", "https://cdn.fal/silent.mp4")
    _fal_job(mock_http, "fal-ai/mmaudio-v2", "audio", "https://cdn.fal/with-sound.mp4")
    a = auth_client.post("/api/content/video", json={"prompt": "waves", "model": "fal-ai/luma-dream-machine/ray-2", "add_sound": False}).json()
    assert auth_client.post(f"/api/content/video/{a['id']}/sound", json={}).status_code == 400  # not finished yet
    assert auth_client.get(f"/api/content/video/{a['id']}").json()["params"]["has_audio"] is False
    assert other_client.post(f"/api/content/video/{a['id']}/sound", json={}).status_code == 404
    r = auth_client.post(f"/api/content/video/{a['id']}/sound", json={"prompt": "ocean"}).json()
    assert r["status"] == "queued" and r["params"]["stage"] == "audio"
    done = auth_client.get(f"/api/content/video/{a['id']}").json()
    assert done["url"] == "https://cdn.fal/with-sound.mp4"
    assert auth_client.post(f"/api/content/video/{a['id']}/sound", json={}).status_code == 400  # already has sound
