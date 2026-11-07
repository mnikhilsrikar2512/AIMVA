"""Ask AI in the website editor, and autosave merging of visual edits."""
from datetime import timedelta

from sqlalchemy import select

from app.models import SiteVersion
from app.routers import sites as S

from .test_sites_leads import make_site

IMG = "data:image/png;base64," + "A" * 5000


def fake_writer(reply, seen=None):
    def make(*a, **k):
        def write(prompt, system="", max_tokens=2048):
            if seen is not None:
                seen.append(prompt)
            return reply(prompt) if callable(reply) else reply
        return write
    return make


def test_ai_edit_needs_a_writer(auth_client):
    s = make_site(auth_client)
    r = auth_client.post(f"/api/sites/{s['id']}/ai-edit", json={"instruction": "make it darker", "section": "<section>Hi</section>"})
    assert r.status_code == 400 and "AI writer" in r.json()["detail"]


def test_section_edit_returns_sanitized_section_and_keeps_images(auth_client, monkeypatch):
    s = make_site(auth_client)
    seen = []
    monkeypatch.setattr(S, "writer", fake_writer(
        lambda p: "```html\n<section data-aimva-section><h2 onclick=\"x()\">Darker</h2><img src=\"__AIMVA_IMG_0__\"><script>bad()</script></section>\n```", seen))
    src = f'<section data-aimva-section><h2>Hi</h2><img src="{IMG}"></section><!--aimva-script-0-->'
    r = auth_client.post(f"/api/sites/{s['id']}/ai-edit", json={"instruction": "make it darker", "section": src})
    assert r.status_code == 200, r.text
    out = r.json()["section"]
    assert "Darker" in out and IMG in out and "onclick" not in out and "<script" not in out
    assert out.endswith("<!--aimva-script-0-->")  # the page's own scripts are never lost
    assert "AAAA" not in seen[0] and "__AIMVA_IMG_0__" in seen[0]  # the AI never sees the base64 blob


def test_section_edit_cannot_drop_the_lead_form(auth_client, monkeypatch):
    s = make_site(auth_client)
    monkeypatch.setattr(S, "writer", fake_writer("<section><h2>No form</h2></section>"))
    r = auth_client.post(f"/api/sites/{s['id']}/ai-edit",
                         json={"instruction": "shorter", "section": "<section><form data-aimva-lead><input name=phone></form></section>"})
    assert r.status_code == 502 and "lead form" in r.json()["detail"]


def test_section_edit_rejects_non_html(auth_client, monkeypatch):
    s = make_site(auth_client)
    monkeypatch.setattr(S, "writer", fake_writer("Sorry, I can't."))
    r = auth_client.post(f"/api/sites/{s['id']}/ai-edit", json={"instruction": "shorter", "section": "<section>x</section>"})
    assert r.status_code == 502


def test_whole_page_edit_saves_a_version_and_keeps_our_scripts(auth_client, monkeypatch):
    s = make_site(auth_client)
    monkeypatch.setattr(S, "writer", fake_writer(
        "<!doctype html><html><body><h1>New look</h1><form data-aimva-lead><input name=phone></form><script>evil()</script></body></html>"))
    r = auth_client.post(f"/api/sites/{s['id']}/ai-edit", json={"instruction": "make the whole page feel premium"})
    assert r.status_code == 200, r.text
    html = r.json()["site"]["html"]
    assert "New look" in html and "evil()" not in html
    assert f"/api/public/sites/{s['slug']}/lead" in html  # lead-form script carried over from the old page
    notes = [v["note"] for v in auth_client.get(f"/api/sites/{s['id']}/versions").json()]
    assert notes[0] == "Edited with AI"


def test_whole_page_edit_refuses_page_without_form(auth_client, monkeypatch):
    s = make_site(auth_client)
    monkeypatch.setattr(S, "writer", fake_writer("<html><body><h1>No form</h1></body></html>"))
    r = auth_client.post(f"/api/sites/{s['id']}/ai-edit", json={"instruction": "remove everything"})
    assert r.status_code == 502
    assert auth_client.get(f"/api/sites/{s['id']}").json()["html"] == s["html"]


def test_ai_edit_is_owner_only(auth_client, other_client, monkeypatch):
    s = make_site(auth_client)
    monkeypatch.setattr(S, "writer", fake_writer("<section>x</section>"))
    r = other_client.post(f"/api/sites/{s['id']}/ai-edit", json={"instruction": "change it", "section": "<section>x</section>"})
    assert r.status_code == 404


def test_autosaved_visual_edits_merge_into_one_version(auth_client, db):
    s = make_site(auth_client)
    url = f"/api/sites/{s['id']}"
    for i in range(3):
        assert auth_client.patch(url, json={"html": f"<h1>Edit {i}</h1>", "note": "Edited visually"}).status_code == 200
    versions = auth_client.get(f"{url}/versions").json()
    assert [v["note"] for v in versions] == ["Edited visually", "Generated"] and versions[0]["current"]
    # After a pause, the next edit starts a new version so there's something to go back to.
    v = db.scalar(select(SiteVersion).where(SiteVersion.site_id == s["id"]).order_by(SiteVersion.number.desc()))
    v.created_at = v.created_at - timedelta(minutes=10)
    db.commit()
    auth_client.patch(url, json={"html": "<h1>Later</h1>", "note": "Edited visually"})
    assert len(auth_client.get(f"{url}/versions").json()) == 3


def test_selected_words_can_come_back_as_plain_text(auth_client, monkeypatch):
    s = make_site(auth_client)
    monkeypatch.setattr(S, "writer", fake_writer("Book your <free> visit"))
    r = auth_client.post(f"/api/sites/{s['id']}/ai-edit", json={"instruction": "punchier", "section": "<span>Visit us sometime</span>"})
    assert r.status_code == 200 and r.json()["section"] == "<span>Book your &lt;free&gt; visit</span>"
