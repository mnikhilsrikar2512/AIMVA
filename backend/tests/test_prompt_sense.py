import os
from urllib.parse import unquote

from app.prompt_sense import comment_intent, read_prompt
from tests.test_content import jpeg

SETS = os.path.join(os.path.dirname(__file__), "..", "scripts", "prompt_sets")


def _rows(name):
    with open(os.path.join(SETS, name), encoding="utf-8") as f:
        return [l.rstrip("\n").split("\t") for l in f if l.strip() and not l.startswith("#")]


def test_every_labelled_comment_is_read_right():
    """Guards the scored sets (scripts/prompt_bench.py) from regressions; new phrasings belong in a fresh set first."""
    wrong = [(lab, t) for n in os.listdir(SETS) if n.startswith("comments_") for lab, t in _rows(n) if comment_intent(t) != lab]
    assert wrong == []


def test_every_labelled_prompt_is_read_right():
    wrong = []
    for n in (n for n in os.listdir(SETS) if n.startswith("prompts_")):
        for fmt, words, p in _rows(n):
            r = read_prompt(p)
            if (r["format"], r["words"]) != (None if fmt == "-" else fmt, None if words == "-" else words):
                wrong.append(p)
    assert wrong == []


def test_words_stay_off_the_image_model_and_are_typeset_on_quietly(auth_client, mock_http, db):
    route = mock_http.get(url__startswith="https://image.pollinations.ai/prompt/").respond(200, content=jpeg(), headers={"content-type": "image/jpeg"})
    a = auth_client.post("/api/content/image", json={"prompt": 'poster with text "Diwali Sale 50% Off", diyas', "smart_prompt": False}).json()[0]
    sent = unquote(str(route.calls.last.request.url))
    assert "Diwali Sale" not in sent and "No text or lettering" in sent and "diyas" in sent
    assert a["prompt"] == 'poster with text "Diwali Sale 50% Off", diyas' and a["params"]["words"] == "Diwali Sale 50% Off"
    # The words are already on the picture, editable later, with the plain picture kept underneath.
    from app.models import Asset
    stored = db.get(Asset, a["id"]).params
    assert a["params"]["text_layers"][0]["text"] == "Diwali Sale 50% Off" and a["url"] != stored["text_plain_url"]
    assert "text_plain_url" not in a["params"]  # file paths stay on the server
    again = auth_client.post(f"/api/content/image/{a['id']}/text", json={"layers": [{"text": "Diwali Sale 60% Off"}]})
    assert again.status_code == 200 and again.json()["params"]["text_base"] == a["id"]


def test_shape_comes_from_the_prompt_only_when_none_was_picked(auth_client, mock_http):
    route = mock_http.get(url__startswith="https://image.pollinations.ai/prompt/").respond(200, content=jpeg(), headers={"content-type": "image/jpeg"})
    a = auth_client.post("/api/content/image", json={"prompt": "insta story for a cafe", "size_auto": True, "smart_prompt": False}).json()[0]
    assert a["params"]["size"] == "9:16" and "height=1" in str(route.calls.last.request.url)
    b = auth_client.post("/api/content/image", json={"prompt": "insta story for a cafe", "size": "1:1", "smart_prompt": False}).json()[0]
    assert b["params"]["size"] == "1:1"
    assert auth_client.get("/api/content/prompt-sense?text=story").status_code in (404, 405)
