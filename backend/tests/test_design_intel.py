"""Business-matched design (UI/UX Pro Max data) and the design checks before launch."""
from app.agents.fixer import fix_html
from app.design_intel import allowed_fonts, contrast, fonts_query, match_design, on_color
from app.quality import audit_page

BRIEF = {"business": "Smile Dental", "industry": "dental clinic", "offer": "Free check-up", "use_ai": False,
         "features": ["Gentle care", "Evening slots"], "contact_mode": "voice_agent"}


def checks(html):
    return {c["key"]: c for c in audit_page(html, {})}


def test_match_is_confident_or_none():
    m = match_design("dental clinic")
    assert m and m["category"] and m["primary"].startswith("#") and m["font_heading"] in allowed_fonts()
    assert match_design("coaching institute") is None  # lands on "General": we don't guess
    assert match_design("") is None


def test_fonts_whitelist_blocks_injection():
    assert fonts_query("Poppins", "Open Sans")
    assert fonts_query("Evil');}body{x", "Inter") is None


def test_on_color_always_reads():
    for bg in ("#6366f1", "#fde047", "#0ea5e9", "#22c55e", "#111827", "#f97316"):
        assert contrast(bg, on_color(bg)) >= 3.0


def test_owner_colours_win_unless_matching_is_on(auth_client):
    own = auth_client.post("/api/sites", json={**BRIEF, "primary": "#123456"}).json()
    assert own["brief"]["primary"] == "#123456" and "--p:#123456" in own["html"]
    m = match_design("dental clinic")
    matched = auth_client.post("/api/sites", json={**BRIEF, "primary": "#123456", "match_colors": True, "font": "auto"}).json()
    assert matched["brief"]["primary"] == m["primary"] and matched["brief"]["design_match"] == m["category"]
    assert m["font_heading"].replace(" ", "+") in matched["html"]


def test_auto_font_without_a_match_falls_back(auth_client):
    s = auth_client.post("/api/sites", json={**BRIEF, "industry": "coaching institute", "font": "auto", "match_colors": True}).json()
    assert "Plus+Jakarta+Sans" in s["html"] and s["brief"]["primary"] == "#4f46e5"


def test_directions_lead_with_the_matched_design(auth_client):
    out = auth_client.post("/api/sites/directions", json={**BRIEF, "match_colors": True, "font": "auto"}).json()
    assert out[0]["matched"] and out[0]["font"] == "auto" and not out[1]["matched"]
    assert auth_client.post("/api/sites/design-match", json={"industry": "bakery"}).json()["category"]


def test_template_pages_pass_the_design_checks(auth_client):
    html = auth_client.post("/api/sites", json={**BRIEF, "primary": "#fde047", "whatsapp": "+919876543210"}).json()["html"]
    c = checks(html)
    for k in ("contrast", "input_size", "labels", "motion", "lazy", "focus", "emoji"):
        assert c[k]["ok"], (k, c[k])


BAD = """<!doctype html><html><head><title>x</title><style>:root{--p:#fde047}
.btn{background:var(--p);color:#fff}input{font-size:14px}a:focus{outline:none}.x{transition:all .3s;font-size:10px}</style></head>
<body><form data-aimva-lead><input name="phone" placeholder="Phone"><button class="btn">Go</button></form>
<a href="#contact">📞 Call</a><img src="a.jpg" alt="a"><img src="b.jpg" alt="b"><img src="c.jpg" alt="c"></body></html>"""


def test_audit_finds_design_issues_and_marks_what_fixes_itself():
    c = checks(BAD)
    for k in ("contrast", "input_size", "labels", "motion", "lazy", "focus", "small_text", "emoji"):
        assert not c[k]["ok"], k
    assert c["contrast"]["autofix"] and not c["small_text"]["autofix"]


def test_fixer_fixes_design_issues_but_keeps_brand_colour_and_words():
    html, fixed = fix_html(BAD, {"business": "X"})
    c = checks(html)
    for k in ("contrast", "input_size", "labels", "motion", "lazy", "focus"):
        assert c[k]["ok"], k
    assert "--p:#fde047" in html and "📞 Call" in html and fixed
    assert fix_html(html, {"business": "X"})[1] == []  # nothing left to do the second time


def test_one_tap_autofix_makes_a_new_version(auth_client):
    s = auth_client.post("/api/sites", json=BRIEF).json()
    r = auth_client.patch(f"/api/sites/{s['id']}", json={"html": BAD.replace("<form", "<h1>Hi</h1><form"), "note": "Edited HTML"})
    assert r.status_code == 200, r.text
    out = auth_client.post(f"/api/sites/{s['id']}/autofix").json()
    assert out["fixed"] and all(c["ok"] for c in out["checks"] if c["key"] in ("contrast", "labels", "input_size"))
    assert 'data-aimva-fix="design"' in out["site"]["html"]
