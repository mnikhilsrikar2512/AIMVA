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


def test_words_stay_off_the_image_model_and_are_offered_as_text(auth_client, mock_http):
    route = mock_http.get(url__startswith="https://image.pollinations.ai/prompt/").respond(200, content=jpeg(), headers={"content-type": "image/jpeg"})
    a = auth_client.post("/api/content/image", json={"prompt": 'poster with text "Diwali Sale 50% Off", diyas', "smart_prompt": False}).json()[0]
    sent = unquote(str(route.calls.last.request.url))
    assert "Diwali Sale" not in sent and "No text or lettering" in sent and "diyas" in sent
    assert a["prompt"] == 'poster with text "Diwali Sale 50% Off", diyas' and a["params"]["words"] == "Diwali Sale 50% Off"
    assert auth_client.get("/api/content/prompt-sense?text=insta story for a cafe&size=1:1").json() == {"format": "9:16", "words": None}
    assert auth_client.get("/api/content/prompt-sense?text=insta story for a cafe&size=9:16").json()["format"] is None
