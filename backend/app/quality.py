"""Quality layer for generated work: industry playbooks, brief review ("ask, don't guess") and page audits.

The aim is output a user can publish without rechecking: we ask for the facts that matter before
generating, give the writer a proven structure for the industry, and audit the result for things a
careful human would catch (placeholders, invented numbers, risky claims, missing contact details).
"""
import html as H
import json
import re
from typing import Optional

# Each playbook: a proven page structure for the industry, the facts that most change the result
# (asked before generating), claim-free fallback copy and a visual hint for image prompts.
PLAYBOOKS = {
    "real_estate": {
        "label": "Real estate",
        "keywords": ["real estate", "realty", "property", "properties", "apartment", "flat", "villa", "plot", "homes", "housing",
                     "builder", "developer", "bhk"],
        "page_type": "real_estate", "cta": "Book a site visit", "form_title": "Book a free site visit",
        "form_fields": ["name", "phone", "email", "budget", "preferred_date"],
        "sections": ["features", "gallery", "pricing", "faq", "contact_info"],
        "location": True, "pricing": True,
        "safe_features": ["Site visits on your schedule", "Floor plans and price sheet on request", "Help with home-loan paperwork"],
        "guidance": "Hero: project name, location and starting price with the site-visit form beside it. Then highlights "
                    "(configurations, amenities, connectivity), gallery, a price/configuration table, FAQ (possession, loans, "
                    "approvals) and the address. Quote approval or registration numbers only if given.",
        "image_hint": "architectural photography, bright natural light, wide angle, clean sky, inviting interiors",
    },
    "healthcare": {
        "label": "Clinic / healthcare",
        "keywords": ["clinic", "dental", "dentist", "doctor", "hospital", "health", "physio", "skin", "derma", "eye", "medical",
                     "therapy", "ayurved", "homeopath", "diagnostic"],
        "page_type": "service", "cta": "Book an appointment", "form_title": "Book an appointment",
        "form_fields": ["name", "phone", "preferred_date", "message"],
        "sections": ["features", "about", "faq", "contact_info"],
        "location": True, "pricing": False,
        "safe_features": ["Appointments that suit your schedule", "Clear advice before any treatment", "Reminders by WhatsApp"],
        "guidance": "Hero: the main treatment or specialty and a calm, reassuring promise with the booking form. Then services, "
                    "the doctor/team (only names and qualifications given), FAQ (timings, cost, what to expect) and address with "
                    "timings. No cure or outcome guarantees, no before/after claims.",
        "image_hint": "bright modern clinic, soft daylight, calm and clean, friendly staff, reassuring mood",
    },
    "education": {
        "label": "Education / coaching",
        "keywords": ["coaching", "school", "academy", "course", "class", "tuition", "institute", "training", "learning", "exam",
                     "college", "education", "tutor"],
        "page_type": "lead_gen", "cta": "Book a free demo", "form_title": "Book a free demo class",
        "form_fields": ["name", "phone", "email", "message"],
        "sections": ["features", "about", "pricing", "faq", "contact_info"],
        "location": False, "pricing": True,
        "safe_features": ["Try a demo class before you join", "Batch timings that fit around school or work", "Talk to a counsellor first"],
        "guidance": "Hero: the course/exam and the outcome students want, with the demo-class form. Then what's covered, "
                    "format (online/offline, batch size, schedule), fees if given, FAQ and contact. Quote results or ranks only "
                    "if given.",
        "image_hint": "students learning in a bright classroom, focused and engaged, natural light, candid",
    },
    "saas": {
        "label": "SaaS / software",
        "keywords": ["saas", "software", "app", "platform", "tool", "crm", "erp", "ai ", "api", "cloud", "startup"],
        "page_type": "app", "cta": "Get a demo", "form_title": "See it in action",
        "form_fields": ["name", "email", "company", "message"],
        "sections": ["features", "pricing", "faq"],
        "location": False, "pricing": True,
        "safe_features": ["Set up with help from our team", "Works with the tools you already use", "Talk to a real person"],
        "guidance": "Hero: the job the product does and for whom, in one line, with the demo form. Then 3-6 benefits tied to "
                    "features, how it works in 3 steps, pricing if given, FAQ (setup, security, contracts). No invented "
                    "customer logos, user counts or uptime figures.",
        "image_hint": "clean product UI on a laptop, minimal desk, soft gradient background, modern",
    },
    "retail": {
        "label": "Retail / e-commerce",
        "keywords": ["shop", "store", "retail", "boutique", "fashion", "jewel", "furniture", "e-commerce", "ecommerce", "brand",
                     "products", "clothing", "cosmetic", "skincare"],
        "page_type": "product", "cta": "Claim my offer", "form_title": "Get the offer",
        "form_fields": ["name", "phone", "email"],
        "sections": ["features", "gallery", "faq", "contact_info"],
        "location": False, "pricing": True,
        "safe_features": ["Ask us anything before you buy", "Updates on new arrivals", "Order help on WhatsApp"],
        "guidance": "Hero: the product and the offer with clear terms, plus the form. Then product highlights, gallery, delivery "
                    "and returns (only as given), FAQ. Show prices only as given.",
        "image_hint": "studio product photography, seamless background, soft shadows, premium and minimal",
    },
    "restaurant": {
        "label": "Restaurant / café",
        "keywords": ["restaurant", "cafe", "café", "bakery", "food", "kitchen", "catering", "bar", "bistro", "cloud kitchen"],
        "page_type": "restaurant", "cta": "Reserve a table", "form_title": "Reserve a table",
        "form_fields": ["name", "phone", "preferred_date", "message"],
        "sections": ["features", "gallery", "contact_info"],
        "location": True, "pricing": False,
        "safe_features": ["Table bookings for groups", "Call ahead for special requests", "Find us easily"],
        "guidance": "Hero: cuisine and atmosphere with the reservation form. Then signature dishes (only as given), gallery, "
                    "opening hours and address.",
        "image_hint": "appetising food photography, warm ambient light, shallow depth of field, rustic table",
    },
    "services": {
        "label": "Local services",
        "keywords": ["service", "repair", "cleaning", "plumb", "electric", "salon", "spa", "interior", "agency", "consult",
                     "legal", "accountant", "ca ", "travel", "event", "wedding", "photograph", "gym", "fitness", "pest", "movers"],
        "page_type": "service", "cta": "Get a free quote", "form_title": "Get a free quote",
        "form_fields": ["name", "phone", "city", "message"],
        "sections": ["features", "about", "faq", "contact_info"],
        "location": True, "pricing": False,
        "safe_features": ["Tell us the job, we'll call you back", "Clear quote before we start", "Book a time that suits you"],
        "guidance": "Hero: the service, the area served and the main promise with the quote form. Then services list, how it "
                    "works in 3 steps, about the team, FAQ (pricing, timing, area) and contact.",
        "image_hint": "professional at work, friendly and trustworthy, natural light, real environment",
    },
    "other": {
        "label": "General business",
        "keywords": [],
        "page_type": "lead_gen", "cta": "Contact us", "form_title": "Get in touch",
        "form_fields": ["name", "phone", "email", "message"],
        "sections": ["features", "about", "faq", "contact_info"],
        "location": False, "pricing": False,
        "safe_features": ["Tell us what you need", "We'll get back to you", "No obligation"],
        "guidance": "Hero: what the business offers and the reason to enquire now, with the form. Then benefits, about, FAQ and "
                    "contact.",
        "image_hint": "professional, bright, modern, authentic",
    },
}


def match_playbook(industry: str = "", fallback: str = "") -> str:
    """Pick a playbook from the free-text industry, else the user's onboarding industry."""
    text = f" {(industry or '').lower()} "
    if text.strip():
        for key, p in PLAYBOOKS.items():
            if key.replace("_", " ") in text or any(k in text for k in p["keywords"]):
                return key
    return fallback if fallback in PLAYBOOKS else "other"


def playbook_out(key: str) -> dict:
    p = PLAYBOOKS[key]
    return {"key": key, "label": p["label"], "page_type": p["page_type"], "cta": p["cta"], "form_title": p["form_title"],
            "form_fields": p["form_fields"], "sections": p["sections"], "guidance": p["guidance"]}


def _has(v) -> bool:
    if isinstance(v, str):
        return bool(v.strip())
    return bool(v)


def review_brief(b: dict, fallback_industry: str = "") -> dict:
    """Score how much the generator knows and list the few questions that would improve the page most."""
    key = match_playbook(b.get("industry", ""), fallback_industry)
    p = PLAYBOOKS[key]
    items = [  # (weight, ok, field, tab, question, why, importance)
        (15, _has(b.get("offer")) or _has(b.get("headline")), "offer", "content",
         "What's the offer or the reason to contact you now?", "The headline and button are built around it.", "high"),
        (10, _has(b.get("audience")), "audience", "content",
         "Who is this page for?", "Lets the copy speak to the right people.", "medium"),
        # With the AIMVA voice agent calling leads back, the business doesn't need to share a number at all.
        (15, b.get("contact_mode", "voice_agent") != "own_phone" or any(_has(b.get(k)) for k in ("phone", "whatsapp", "contact_email")),
         "phone", "content", "What phone number should leads call?", "You chose to show your own number on the page.", "high"),
        (10, len([f for f in b.get("features") or [] if _has(f)]) >= 2, "features", "content",
         "What are 2-3 real reasons to choose you?", "Without them the page falls back to generic points.", "medium"),
        (10, _has(b.get("about")) or _has(b.get("references")), "about", "sections",
         "Tell us about the business in a few lines (or attach a brochure).", "Gives the writer facts instead of guesses.", "medium"),
        (10, _has(b.get("hero_image")) or _has(b.get("gallery")), "hero_image", "design",
         "Add a real photo of your work, place or product.", "Real photos convert much better than none.", "medium"),
    ]
    if p["location"]:
        items.append((10, _has(b.get("address")), "address", "content",
                      "Where are you located (area / city)?", "People choose nearby options first.", "high"))
    if p["pricing"]:
        items.append((5, _has(b.get("pricing")), "pricing", "sections",
                      "Is there a starting price or plan you can show?", "Pages with a price get better-qualified leads.", "low"))
    items.append((5, _has(b.get("testimonials")), "testimonials", "sections",
                  "Any real customer quotes you can share?", "Real proof builds trust (we never invent reviews).", "low"))
    total = sum(w for w, *_ in items)
    got = sum(w for w, ok, *_ in items if ok)
    score = round(100 * got / total)
    order = {"high": 0, "medium": 1, "low": 2}
    missing = [{"field": f, "tab": tab, "question": q, "why": why, "importance": imp}
               for _, ok, f, tab, q, why, imp in sorted(items, key=lambda x: order[x[6]]) if not ok]
    level = "ready" if score >= 75 else "ok" if score >= 50 else "thin"
    return {"score": score, "level": level, "missing": missing[:6], "playbook": playbook_out(key)}


def playbook_ai_rules(key: str) -> str:
    p = PLAYBOOKS.get(key) or PLAYBOOKS["other"]
    return (f" Industry playbook ({p['label']}): {p['guidance']} "
            "If a fact isn't given, leave it out rather than guessing. Never output placeholder text such as "
            "[Your phone], lorem ipsum, example.com, 555 numbers or 'Your Company'. Every image needs alt text. "
            "Include <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">.")


# ---------------------------------------------------------------------------------------------- audit

PLACEHOLDER_RE = re.compile(
    r"lorem ipsum|\[(?:your|insert|company|business|name|phone|email|address|city|price)[^\]]{0,40}\]|\{\{[^}]{1,40}\}\}|"
    r"\bTODO\b|\bTBD\b|\bXXX+\b|your company|yourcompany|your@email|example\.com|\b555[- ]?\d{3,4}\b|123[- ]?456[- ]?7890|"
    r"\+?1?[- ]?\(?000\)?[- ]?000",
    re.I)
RISKY_RE = re.compile(
    r"guaranteed? (?:results?|returns?|cure|approval|income|profit|weight loss|admission|selection)|100% (?:cure|safe|guaranteed|"
    r"results?|success|natural)|risk[- ]free|no side[- ]effects|permanent(?:ly)? cure|cures? (?:diabetes|cancer|hair loss|acne)|"
    r"double your (?:money|income|sales)|lose \d+\s?(?:kg|kgs|lbs|pounds) in|\bbest (?:in|of) (?:the )?(?:city|town|india|world|"
    r"country|market)\b|\bnumber one\b|#1\b|\bno\.? ?1\b",
    re.I)
STAT_RE = re.compile(
    r"(\d[\d,.]*\s?(?:\+|%|k\+|\s?lakh\+?|\s?crore\+?)|\d(?:\.\d)?\s?(?:★|stars?|/5|out of 5)|(?:since|est\.?|established in)\s(?:19|20)\d\d"
    r"|\d[\d,]*\s(?:happy|satisfied)\s\w+|\d[\d,]*\s(?:years?|yrs?)\s(?:of )?experience|award[- ]winning)",
    re.I)


def visible_text(html: str) -> str:
    html = re.sub(r"<(script|style|noscript|template)\b[^>]*>.*?</\1\s*>", " ", html or "", flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", H.unescape(text)).strip()


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def audit_page(html: str, brief: Optional[dict] = None, reference: str = "") -> list:
    """Checks a careful editor would make before launch. level: blocker (must fix) | warning | tip."""
    brief = brief or {}
    html = html or ""
    low = html.lower()
    text = visible_text(html)
    form = re.search(r"<form[^>]*data-aimva-lead[^>]*>(.*?)</form>", html, re.I | re.S)
    has_contact = bool(form and re.search(r"name\s*=\s*[\"']?(phone|email)\b", form.group(1), re.I))
    title = re.search(r"<title>\s*([^<]+?)\s*</title>", html, re.I)
    desc = re.search(r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"']([^\"']+)", html, re.I)
    checks = []

    def add(key, ok, level, message, detail="", fix=""):
        checks.append({"key": key, "ok": bool(ok), "level": level, "message": message,
                       "detail": "" if ok else detail, "fix": "" if ok else fix})

    add("form", form, "blocker", "Has a lead form so visitors can reach you",
        "There's no lead form on the page.", "Regenerate, or add a <form data-aimva-lead> in the HTML editor.")
    add("contact", has_contact, "blocker", "The form asks for a phone number or email",
        "Leads can't be contacted without a phone or email field.", "Add a phone or email field to the form.")
    add("size", len(html) < 3_000_000, "blocker", "Page is under 3 MB", "The page is too large to publish.",
        "Use smaller images.")
    found = sorted({m.group(0).strip() for m in PLACEHOLDER_RE.finditer(text)})[:4]
    add("placeholders", not found, "blocker", "No placeholder text left on the page",
        "Found: " + ", ".join(f"“{x}”" for x in found), "Replace these with real details, then publish.")

    known = json.dumps(brief, ensure_ascii=False).lower() + " " + (reference or "").lower()
    known_nums = {n.replace(",", "").rstrip(".") for n in re.findall(r"\d[\d,.]*", known)}
    invented = []
    for m in STAT_RE.finditer(text):
        s = m.group(0).strip()
        nums = [n.replace(",", "").rstrip(".") for n in re.findall(r"\d[\d,.]*", s)]
        if (nums and any(n not in known_nums for n in nums)) or (not nums and s.lower() not in known):
            invented.append(s)
    invented = list(dict.fromkeys(invented))[:4]
    add("claims", not invented, "warning", "Every number and award on the page came from you",
        "Not in your brief: " + ", ".join(f"“{x}”" for x in invented) + ". Make sure these are true.",
        "Edit or remove them in the HTML editor, or add them to the brief and regenerate.")
    if not brief.get("testimonials"):
        fake_quotes = bool(re.search(r"<blockquote|class=[\"'][^\"']*testimonial|what (?:our )?(?:customers|clients) say", low))
        add("testimonials", not fake_quotes, "warning", "No testimonials you didn't provide",
            "The page shows customer quotes that weren't in your brief.",
            "Remove them, or add your real testimonials in the Sections tab and regenerate.")
    risky = list(dict.fromkeys(m.group(0) for m in RISKY_RE.finditer(text)))[:3]
    add("risky", not risky, "warning", "No claims likely to be rejected by ad platforms",
        "Risky wording: " + ", ".join(f"“{x}”" for x in risky),
        "Soften it (e.g. “trusted by local families” instead of “best in the city”).")

    if brief.get("phone") and brief.get("contact_mode", "own_phone") != "voice_agent":
        add("phone", _digits(brief["phone"])[-8:] in _digits(text), "warning", "Your phone number appears on the page",
            "Your phone number isn't shown anywhere.", "Turn on the Contact section or add it to the header.")
    if brief.get("cta"):
        add("cta", brief["cta"].lower() in text.lower(), "tip", f"The button says “{brief['cta']}”",
            "The writer changed your button text.", "Edit the button in the HTML editor if you prefer yours.")
    add("title", title, "warning", "Has a page title (shown in Google and browser tabs)", "No page title.",
        "Set the SEO title when you publish.")
    add("description", desc, "warning", "Has a search description", "No search description.",
        "Set it when you publish.")
    add("headline", "<h1" in low, "warning", "Has a main headline (H1)", "No main headline.", "Regenerate the page.")
    add("mobile", 'name="viewport"' in low or "name='viewport'" in low or "name=viewport" in low, "warning",
        "Set up for mobile screens", "Missing the mobile viewport tag, so phones will show it zoomed out.",
        "Regenerate, or add <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">.")
    imgs = re.findall(r"<img\b[^>]*>", html, re.I)
    no_alt = [i for i in imgs if not re.search(r"\balt\s*=", i, re.I)]
    add("alt", not no_alt, "tip", "Images have alt text", f"{len(no_alt)} image(s) without alt text.",
        "Helps accessibility and Google Images.")
    dead = len(re.findall(r"<a\b[^>]*href\s*=\s*[\"']\s*#?\s*[\"']", html, re.I))
    add("links", not dead, "tip", "No empty links", f"{dead} link(s) go nowhere.", "Point them at #contact or remove them.")
    add("weight", len(html) < 1_500_000, "tip", "Loads quickly on mobile", "The page is heavy (over 1.5 MB).",
        "Use fewer or smaller images.")
    for key, ok, level, message, detail, fix, auto in design_checks(html):
        add(key, ok, level, message, detail, fix)
        checks[-1]["autofix"] = bool(auto and not ok)
    for c in checks:
        c.setdefault("autofix", c["key"] in ("alt", "links", "title", "description", "mobile") and not c["ok"])
    return checks


# ---------------------------------------------------------------------------------------------- design checks
# From the UI/UX Pro Max guidelines (see app/design_intel): the issues a careful designer catches before launch.
CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
FIELD_RE = re.compile(r"<(input|textarea|select)\b[^>]*>", re.I)
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def _css(html: str) -> str:
    return " ".join(re.findall(r"<style\b[^>]*>(.*?)</style>", html, re.I | re.S))


def _css_vars(css: str) -> dict:
    return {k.strip(): v.strip() for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;{}]+)", css)}


def _hex(v: str, vars_: dict) -> str:
    v = (v or "").strip()
    for _ in range(3):
        m = re.match(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^)]+))?\)", v)
        if not m:
            break
        v = vars_.get(m.group(1), m.group(2) or "").strip()
    m = re.match(r"#([0-9a-f]{3}|[0-9a-f]{6})\b", v, re.I)
    if not m:
        return {"white": "#ffffff", "black": "#000000"}.get(v.lower(), "")
    h = m.group(1)
    return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h).lower()


def button_contrast(html: str) -> list:
    """[(selector, background, text colour, ratio)] for button styles whose text is hard to read (under 4.5:1)."""
    from .design_intel import contrast
    css = _css(html)
    vars_ = _css_vars(css)
    seen = {}  # selector -> {"bg": (value, important), "fg": ...}: later rules win, !important beats normal
    for sel, decl in CSS_RULE.findall(css):
        for one in sel.split(","):
            one = one.strip()
            if not re.search(r"btn|button|cta", one, re.I) or re.search(r":hover|::?before|::?after|:disabled|@", one, re.I):
                continue
            cur = seen.setdefault(one, {})
            for prop, val in re.findall(r"(?:^|;)\s*(background-color|background|color)\s*:\s*([^;]+)", decl, re.I):
                k = "fg" if prop.lower() == "color" else "bg"
                imp = "!important" in val
                if imp or not cur.get(k, ("", False))[1]:
                    cur[k] = (val.replace("!important", "").strip(), imp)
    bad = []
    for one, cur in seen.items():
        if "bg" not in cur or "fg" not in cur:
            continue
        b, f = _hex(cur["bg"][0], vars_), _hex(cur["fg"][0], vars_)
        if b and f and contrast(b, f) < 4.5:
            bad.append((one[-80:], b, f, round(contrast(b, f), 1)))
    return bad


def _unlabelled(html: str) -> list:
    ids = set(re.findall(r"<label\b[^>]*\bfor\s*=\s*[\"']?([\w-]+)", html, re.I))
    out = []
    for m in FIELD_RE.finditer(html):
        tag = m.group(0)
        if re.search(r"type\s*=\s*[\"']?(hidden|submit|button|checkbox|radio|reset|image)\b", tag, re.I):
            continue
        if re.search(r"\baria-label(?:ledby)?\s*=", tag, re.I) or re.search(r"\btitle\s*=", tag, re.I):
            continue
        idm = re.search(r"\bid\s*=\s*[\"']?([\w-]+)", tag, re.I)
        if idm and idm.group(1) in ids:
            continue
        before = html[max(0, m.start() - 400):m.start()].lower()
        if before.rfind("<label") > before.rfind("</label>"):  # wrapped in a <label>
            continue
        out.append(tag)
    return out


def _eager_images(html: str) -> list:
    imgs = re.findall(r"<img\b[^>]*>", html, re.I)
    return [i for i in imgs[2:] if not re.search(r"\bloading\s*=", i, re.I)]  # the first two are usually above the fold


def design_checks(html: str) -> list:
    """(key, ok, level, message, detail, fix, autofix) for design and accessibility basics."""
    css = _css(html)
    low_css = css.lower()
    out = []
    bad = button_contrast(html)
    out.append(("contrast", not bad, "warning", "Button text is easy to read",
                (f"{len(bad)} button style(s) with faint text (e.g. {bad[0][2]} on {bad[0][1]}, {bad[0][3]}:1; needs 4.5:1)." if bad else ""),
                "Fix automatically: AIMVA switches the text to white or near-black, whichever reads. Your button colour stays.", True))
    small_inputs = [px for sel, decl in CSS_RULE.findall(css) if re.search(r"\b(input|textarea|select)\b", sel, re.I)
                    for px in re.findall(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", decl, re.I) if float(px) < 16]
    if re.search(r"(input|textarea|select)[^{}]*\{[^{}]*font-size\s*:\s*(1[6-9]|[2-9]\d)px\s*!important", css, re.I):
        small_inputs = []  # an !important 16px rule (e.g. the Page Fixer's) wins on phones
    out.append(("input_size", not small_inputs, "warning", "Form fields don't make phones zoom in",
                "Form text is smaller than 16px, so iPhones zoom in when someone taps a field.",
                "Fix automatically: form text becomes 16px on phones.", True))
    unlabelled = _unlabelled(html)
    out.append(("labels", not unlabelled, "tip", "Every form field has a label screen readers can read",
                f"{len(unlabelled)} field(s) have no label.", "Fix automatically: AIMVA labels them from their placeholder or name.", True))
    moves = bool(re.search(r"@keyframes|animation\s*:|transition\s*:", low_css))
    out.append(("motion", not moves or "prefers-reduced-motion" in low_css, "tip", "Respects people who turn off animations",
                "The page animates but ignores the phone's Reduce motion setting.",
                "Fix automatically: animations switch off for people who asked for that.", True))
    eager = _eager_images(html)
    out.append(("lazy", not eager, "tip", "Images further down load only when needed",
                f"{len(eager)} image(s) further down load straight away and slow the first view on mobile.",
                "Fix automatically: they load as the visitor scrolls.", True))
    killed = bool(re.search(r"outline\s*:\s*(none|0)\b", low_css)) and "focus-visible" not in low_css
    out.append(("focus", not killed, "tip", "Keyboard users can see where they are",
                "The page hides the focus outline, so keyboard users can't see which link or field is selected.",
                "Fix automatically: a clear outline shows on keyboard focus only.", True))
    tiny = sorted({float(px) for px in re.findall(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", css, re.I) if float(px) < 12})
    out.append(("small_text", not tiny, "tip", "No text smaller than 12px",
                f"Some text is {tiny[0]:g}px, hard to read on a phone." if tiny else "", "Make it at least 12px in the HTML editor.", False))
    emoji = [t for t in re.findall(r"<(?:a|button)\b[^>]*>(.*?)</(?:a|button)>", html, re.I | re.S) if EMOJI_RE.search(visible_text(t))]
    out.append(("emoji", not emoji, "tip", "Icons are drawn, not emoji",
                f"{len(emoji)} button(s) or link(s) use emoji as icons, which look different on every phone.",
                "Swap them for simple icons or plain words in the editor.", False))
    return out


def readiness(checks: list) -> dict:
    penalty = {"blocker": 30, "warning": 10, "tip": 3}
    failed = [c for c in checks if not c["ok"]]
    score = max(0, 100 - sum(penalty[c["level"]] for c in failed))
    blockers = sum(c["level"] == "blocker" for c in failed)
    warnings = sum(c["level"] == "warning" for c in failed)
    status = "blocked" if blockers else "review" if warnings else "ready"
    return {"score": score, "status": status, "blockers": blockers, "warnings": warnings}
