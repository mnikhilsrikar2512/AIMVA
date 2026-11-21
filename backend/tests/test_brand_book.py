"""The brand book: assembled from what the owner gave us, editable, and read by every generator."""
from app import brand_book, lead_reply


def test_book_builds_from_kit_and_profile(auth_client):
    auth_client.put("/api/brand", json={"name": "Smile Studio", "tagline": "Gentle dental care", "colors": ["#0B6B67", "#F4A21C"],
                                        "voice": "professional", "voice_notes": "", "style": ["clean"], "audience": "families",
                                        "avoid": "needles"})
    b = auth_client.get("/api/brand/book").json()
    assert b["name"] == "Smile Studio" and [c.lower() for c in b["colors"]] == ["#0b6b67", "#f4a21c"] and b["voice"] == "professional"
    assert "# Smile Studio" in b["markdown"] and "Gentle dental care" in b["markdown"]
    assert 0 < b["complete"] <= 1


def test_edits_win_and_clear(auth_client):
    auth_client.put("/api/brand", json={"name": "Smile Studio", "tagline": "", "colors": ["#0B6B67"], "voice": "friendly",
                                        "voice_notes": "", "style": [], "audience": "", "avoid": ""})
    b = auth_client.put("/api/brand/book", json={"never_say": "cheap, best in town", "colors": ["zz", "#123abc"],
                                                 "voice": "nonsense", "font_heading": "Fraunces<script>"}).json()
    assert b["never_say"] == ["cheap", "best in town"] and b["colors"] == ["#123abc"]
    assert b["voice"] == "friendly"  # an unknown voice is ignored
    assert b["font_heading"] == "Frauncesscript"[:40] or b["font_heading"].isalnum()
    assert set(b["edited"]) >= {"never_say", "colors"}
    b = auth_client.put("/api/brand/book", json={"colors": []}).json()
    assert [c.lower() for c in b["colors"]] == ["#0b6b67"]  # cleared edit falls back to the Brand Kit


def test_markdown_download(auth_client):
    r = auth_client.get("/api/brand/book.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown") and r.text.startswith("# ")


def test_book_is_private(auth_client, other_client):
    auth_client.put("/api/brand/book", json={"tagline": "Owner's secret tagline"})
    assert "secret" not in other_client.get("/api/brand/book").json()["markdown"]


def test_copy_rules_reach_whatsapp_replies(auth_client, monkeypatch):
    auth_client.put("/api/brand/book", json={"never_say": ["cheap"], "voice": "luxury"})
    seen = {}

    def fake_write(db, user, prompt, system):
        seen["system"] = system
        return None
    monkeypatch.setattr(lead_reply, "_write", fake_write)
    r = auth_client.post("/api/leads", json={"name": "Asha Rao", "phone": "+919800000001", "message": "Price?"})
    assert r.status_code in (200, 201), r.text
    lead_id = r.json()["id"]
    assert auth_client.post(f"/api/leads/{lead_id}/reply-draft", json={}).status_code == 200
    assert "Never use these words: cheap" in seen["system"] and "refined" in seen["system"]


def test_effective_kit_none_without_brand(auth_client):
    from app.db import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        u = db.query(User).filter_by(email="owner@example.com").first()
        assert brand_book.effective_kit(db, u) is None
