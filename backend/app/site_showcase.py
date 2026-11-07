"""Showcase: AIMVA's flagship landing-page design, built to match or beat premium project microsites.

Full-bleed photo hero with a serif headline, fact chips, an indicative-price card and a stat strip; overview,
configurations on a dark band, grouped amenities with icons, a captioned gallery, location distances, a
three-step visit process, FAQs, a detailed enquiry form, a gated brochure, a sticky mobile action bar,
WhatsApp shortcuts, approvals and disclaimers, and structured data for Google. Every fact comes from the
brief: when something isn't given, its block is left out instead of being invented.
"""
import html as H
import json
import re
import zlib
from datetime import date

from .config import settings

E = H.escape

# dark base, gold accent, light section, muted text on dark
PALETTES = {
    "emerald": ("#0b3d2e", "#c9a45c", "#f6f3ec"),
    "navy": ("#101a33", "#d4af6a", "#f5f4f0"),
    "charcoal": ("#1c1a17", "#d6b37a", "#f7f4ef"),
    "forest": ("#14301f", "#dcb56c", "#f3f5ee"),
    "plum": ("#2a1633", "#e2b46c", "#f7f3f6"),
    "slate": ("#1e293b", "#e0a95c", "#f4f6f8"),
}
HEAD_FONTS = {  # (google family, css heading font)
    "serif": ("Playfair+Display:ital,wght@0,500;0,600;0,700;1,500;1,600", "'Playfair Display'"),
    "jakarta": ("Playfair+Display:ital,wght@0,500;0,600;0,700;1,500;1,600", "'Playfair Display'"),
    "grotesk": ("Space+Grotesk:wght@500;600;700", "'Space Grotesk'"),
    "inter": ("Inter:wght@600;700;800", "Inter"),
    "rounded": ("Nunito:wght@700;800;900", "Nunito"),
}

# Minimal line icons (24px, stroke) chosen by keyword, so amenities read at a glance.
ICONS = {
    "pool|swim": '<path d="M2 18c2 1.5 4 1.5 6 0s4-1.5 6 0 4 1.5 6 0"/><path d="M2 14c2 1.5 4 1.5 6 0s4-1.5 6 0 4 1.5 6 0"/><path d="M8 12V5a2 2 0 0 1 4 0M16 12V5a2 2 0 0 0-4 0"/>',
    "gym|fitness|dumbbell": '<path d="M6 6v12M18 6v12M3 9v6M21 9v6M6 12h12"/>',
    "club|banquet|lounge|community": '<path d="M3 21h18M5 21V9l7-5 7 5v12M9 21v-6h6v6"/>',
    "park|garden|green|landscap|tree|botanic|forest|nature|view": '<path d="M12 22v-7M7 15a5 5 0 1 1 10 0Z"/><path d="M9 9a3 3 0 1 1 6 0"/>',
    "kid|child|play": '<circle cx="12" cy="5" r="2"/><path d="M12 7v6l-3 5M12 13l3 5M8 10h8"/>',
    "security|cctv|gated|guard|safe": '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6Z"/><path d="m9 12 2 2 4-4"/>',
    "jog|walk|track|cycl|running": '<circle cx="14" cy="4" r="2"/><path d="m6 20 4-6 3 2 2-5 4 3M9 11l2-3 4 1"/>',
    "yoga|meditat|wellness|spa": '<circle cx="12" cy="5" r="2"/><path d="M4 19c2-3 5-4 8-4s6 1 8 4M12 7v8M7 12l5-2 5 2"/>',
    "parking|car": '<rect x="3" y="11" width="18" height="6" rx="2"/><path d="m5 11 2-5h10l2 5M7 17v2M17 17v2"/>',
    "power|backup|electric|solar": '<path d="M13 2 4 14h7l-1 8 9-12h-7Z"/>',
    "lift|elevator": '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="m9 9 3-3 3 3M9 15l3 3 3-3"/>',
    "water|rain|stp|lake": '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11Z"/>',
    "court|cricket|badminton|tennis|basket|sport|squash|game": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
    "theatre|theater|cinema|amphi": '<rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8 21h8M12 17v4"/>',
    "cafe|restaurant|food|dining|cafeteria": '<path d="M4 8h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5Z"/><path d="M17 9h2a2 2 0 0 1 0 4h-2M7 3v2M11 3v2"/>',
    "library|business|work|office|cowork": '<path d="M4 4h6a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4ZM20 4h-6a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h6Z"/>',
    "road|avenue|street|close to|near|minutes|metro|highway|connect|orr|airport": '<path d="M5 21 9 3M19 21 15 3M12 6v2M12 11v2M12 16v2"/>',
    "vaastu|vastu|east|west|facing": '<circle cx="12" cy="12" r="9"/><path d="m15 9-2 4-4 2 2-4Z"/>',
    "wifi|internet|smart": '<path d="M5 12a10 10 0 0 1 14 0M8.5 15.5a5 5 0 0 1 7 0"/><circle cx="12" cy="19" r="1"/>',
    "senior|elder": '<circle cx="12" cy="5" r="2"/><path d="M12 7v7l-3 7M12 14l3 7M15 10l3 1v10"/>',
    "pin|map|location|address":  '<path d="M12 21s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12Z"/><circle cx="12" cy="9" r="2.5"/>',
    "guest|room|suite|bed": '<path d="M3 18v-6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v6M3 15h18M7 10V7h4v3"/>',
}
DEFAULT_ICON = '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/><circle cx="12" cy="12" r="3"/>'


def icon(text: str, size: int = 22) -> str:
    low = text.lower()
    path = next((p for k, p in ICONS.items() if re.search(k, low)), DEFAULT_ICON)
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{path}</svg>')


def palette_for(b) -> tuple:
    if getattr(b, "palette", "auto") in PALETTES:
        return PALETTES[b.palette]
    if getattr(b, "palette", "auto") == "brand":
        return (b.primary, b.accent, "#f6f5f2")
    keys = list(PALETTES)
    return PALETTES[keys[zlib.crc32(b.business.encode()) % len(keys)]]


def _accent_headline(text: str) -> str:
    """Set the last word in the accent italic, like the reference microsites ("A grander way to call *home.*")."""
    words = text.strip().split()
    if len(words) < 3:
        return E(text)
    return f'{E(" ".join(words[:-1]))} <em>{E(words[-1])}</em>'


def showcase_html(b, slug: str, media: dict, real_estate: bool, form_script: str, tracking: str, field_labels: dict,
                  copy: dict = None) -> str:
    """Render the Showcase page. `copy` (optional) holds AI-written text grounded in the brief."""
    c = copy or {}
    dark, gold, light = palette_for(b)
    gfam, hfont = HEAD_FONTS.get(b.font, HEAD_FONTS["serif"])
    if b.font == "auto" and getattr(b, "font_heading", ""):  # heading font matched to the business (body stays Inter)
        from .design_intel import fonts_query
        q = fonts_query(b.font_heading, b.font_heading)
        if q:
            gfam, hfont = q, f"'{b.font_heading}'"
    hero_img = media.get("hero") or ""
    gallery = [g for g in media.get("gallery", []) if g]
    captions = list(getattr(b, "gallery_captions", []) or [])
    wa_num = re.sub(r"[^0-9]", "", b.whatsapp or "")
    call_href = f"tel:{E(b.phone)}" if b.shows_phone else ""
    callback = b.contact_mode != "own_phone"
    wa_link = (lambda msg: f"https://wa.me/{wa_num}?text={E(msg).replace(' ', '%20')}") if wa_num else None

    headline = c.get("headline") or b.headline or (f"{b.business}: {b.offer}" if b.offer else b.business)
    sub = c.get("subheadline") or b.subheadline or b.offer or ""
    eyebrow = getattr(b, "location_line", "") or b.address or b.industry or ""
    chips = (getattr(b, "chips", []) or [f for f in b.features if len(f) <= 32][:3])[:5]
    stats = [s for s in (getattr(b, "stats", []) or []) if s.value][:5]
    configs = list(getattr(b, "configurations", []) or [])
    if not configs and b.pricing:  # pricing plans double as configurations
        configs = [type("C", (), {"name": p.name, "area": "", "details": ", ".join(p.features), "price": p.price})() for p in b.pricing]
    amenities = [a for a in (getattr(b, "amenities", []) or []) if a.strip()][:24]
    distances = [d for d in (getattr(b, "distances", []) or []) if d.place][:12]
    approvals = getattr(b, "approvals", "") or ""
    announcement = getattr(b, "announcement", "") or ""
    price_from = getattr(b, "price_from", "") or ""
    price_note = getattr(b, "price_note", "") or ""
    brochure = bool(getattr(b, "brochure", None))
    map_url = getattr(b, "map_url", "") or (f"https://www.google.com/maps/search/?api=1&query={E(b.address).replace(' ', '+')}" if b.address else "")
    cta = "Book a site visit" if real_estate and b.cta in ("", "Get a free quote") else (b.cta or "Get in touch")
    interest_opts = [x.name for x in configs] + ["Help me choose"]
    secs = set(b.sections) | {"configurations", "amenities", "location", "steps"}  # showcase blocks appear when their facts exist

    # ---- form fields ----
    def field(name, label, kind="text", required=False, opts=None):
        req = " required" if required else ""
        if opts:
            o = "".join(f'<option value="{E(x)}">{E(x)}</option>' for x in opts)
            return f'<label class="f"><span>{E(label)}</span><select name="{name}"{req}><option value="">Select</option>{o}</select></label>'
        if kind == "textarea":
            return f'<label class="f wide"><span>{E(label)}</span><textarea name="{name}" rows="3"{req}></textarea></label>'
        return f'<label class="f"><span>{E(label)}</span><input name="{name}" type="{kind}"{req} autocomplete="{ {"name": "name", "phone": "tel", "email": "email"}.get(name, "off") }"></label>'

    need_phone = "phone" in b.form_fields
    rows = [field("name", "Full name", required=True)]
    if need_phone:
        rows.append(field("phone", "Phone number", "tel", required=True))
    if "email" in b.form_fields or not need_phone:
        rows.append(field("email", "Email", "email", required=not need_phone))
    if len(interest_opts) > 1:
        rows.append(field("interest", "Interested in", opts=interest_opts))
    rows.append(field("timeline", "When are you planning?", opts=["Immediately", "Within 30 days", "Within 3 months", "Just researching"]))
    if "preferred_date" in b.form_fields or real_estate:
        rows.append(field("preferred_date", "Preferred visit date" if real_estate else "Preferred date", "date"))
    for extra in ("city", "budget", "company"):
        if extra in b.form_fields:
            rows.append(field(extra, field_labels[extra]))
    rows.append(field("best_time", "Best time to call", opts=["Any time", "9 am – 12 pm", "12 – 4 pm", "4 – 8 pm"]))
    if "message" in b.form_fields:
        rows.append(field("message", "Anything we should know?", "textarea"))
    hp = '<input class="hp" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">'
    consent = '<label class="ck"><input type="checkbox" required> I agree to be contacted about this enquiry.</label>'
    cb = ('<label class="ck"><input type="checkbox" name="callback" value="yes"> Call me now: our assistant will ring you within a minute</label>'
          if callback else "")
    main_form = (f'<form data-aimva-lead class="form" id="enquiry-form"><input type="hidden" name="action" value="enquiry">{"".join(rows)}'
                 f'{cb}{consent}{hp}<button class="btn gold block" type="submit">{E(c.get("form_button") or "Get brochure & price list")} →</button>'
                 f'<p class="fine">We reply within minutes. No spam, ever.</p></form>')
    modal_form = (f'<form data-aimva-lead class="form" data-after="brochure-ok"><input type="hidden" name="action" value="brochure">'
                  f'{field("name", "Full name", required=True)}{field("phone", "Phone number", "tel", required=True) if need_phone else ""}'
                  f'{field("email", "Email", "email", required=not need_phone)}<input type="hidden" name="interest" value="">'
                  f'{consent}{hp}<button class="btn gold block" type="submit">Send it to me</button></form>'
                  f'<div id="brochure-ok" hidden><p class="ok-t">Thank you!</p>'
                  + (f'<a class="btn gold block" href="{settings.public_url}/s/{E(slug)}/brochure" target="_blank" rel="noopener">Download the brochure ↓</a>' if brochure
                     else '<p>Our team will send you the brochure and current price sheet on WhatsApp shortly.</p>')
                  + '</div>')

    # ---- blocks ----
    nav = [("overview", "Overview")] + ([("plans", "Plans")] if configs else []) + ([("amenities", "Amenities")] if amenities else []) \
        + ([("gallery", "Gallery")] if gallery else []) + ([("location", "Location")] if (distances or b.address) else []) + ([("faq", "FAQ")] if b.faqs else [])
    nav_html = "".join(f'<a href="#{k}">{v}</a>' for k, v in nav)
    chips_html = "".join(f"<span>{E(x)}</span>" for x in chips)
    stats_html = "".join(f'<div class="stat"><b>{E(s.value)}</b><span>{E(s.label)}</span></div>' for s in stats)
    price_card = (f'<div class="price-card glass"><span class="k">{E(c.get("price_label") or "Indicative launch price")}</span>'
                  f'<b>{E(price_from)}</b>{f"<span class=n>{E(price_note)}</span>" if price_note else ""}'
                  f'<button class="lnk" data-open="price">Get current price sheet →</button></div>') if price_from else ""
    approvals_badge = f'<span class="badge">{E(approvals)}</span>' if approvals else ""

    highlights = c.get("highlights") or [{"title": f, "text": ""} for f in b.features[:3]]
    hl_html = "".join(f'<div class="hl" data-reveal><span class="ic">{icon(h["title"])}</span><h3>{E(h["title"])}</h3>'
                      + (f'<p>{E(h["text"])}</p>' if h.get("text") else "") + '</div>' for h in highlights[:3])
    overview_img = gallery[0] if gallery else hero_img
    overview_text = c.get("overview") or b.about or b.subheadline or b.offer or ""
    overview = (f'<section id="overview" class="sec light"><div class="wrap two">'
                f'<div data-reveal><p class="kick">{E(c.get("overview_kicker") or "Overview")}</p>'
                f'<h2>{_accent_headline(c.get("overview_title") or (f"Life at {b.business}" if real_estate else f"Why {b.business}"))}</h2>'
                f'{f"<p class=lead>{E(overview_text)}</p>" if overview_text else ""}<div class="hls">{hl_html}</div></div>'
                + (f'<div class="ov-img" data-reveal><img src="{E(overview_img)}" alt="{E(b.business)}" loading="lazy">'
                   f'{f"<div class=floating><b>{E(stats[0].value)}</b><span>{E(stats[0].label)}</span></div>" if stats else ""}</div>' if overview_img else "")
                + '</div></section>')

    plans = ""
    if configs and "configurations" in secs:
        cards = "".join(
            f'<div class="plan" data-reveal><p class="kick">{E(x.area) if x.area else "&nbsp;"}</p><h3>{E(x.name)}</h3>'
            f'{f"<p class=d>{E(x.details)}</p>" if x.details else ""}'
            f'<p class="pr">{E(x.price) if x.price else "Price on request"}</p>'
            f'<button class="btn ghost block" data-open="price" data-interest="{E(x.name)}">{"Get cost sheet" if x.price else "Check availability"}</button></div>'
            for x in configs[:6])
        plans = (f'<section id="plans" class="sec dark"><div class="wrap"><div class="head" data-reveal><p class="kick">{E(c.get("plans_kicker") or ("Configurations" if real_estate else "Plans"))}</p>'
                 f'<h2>{_accent_headline(c.get("plans_title") or ("Choose the space that fits your life." if real_estate else "Choose what fits you."))}</h2></div>'
                 f'<div class="plans">{cards}</div></div></section>')

    amen = ""
    if amenities and "amenities" in secs:
        items = "".join(f'<li data-reveal><span class="ic">{icon(a)}</span>{E(a)}</li>' for a in amenities)
        amen = (f'<section id="amenities" class="sec white"><div class="wrap"><div class="head" data-reveal><p class="kick">Amenities</p>'
                f'<h2>{_accent_headline(c.get("amenities_title") or "Everything your days deserve.")}</h2>'
                + (f'<p class="lead">{E(c["amenities_intro"])}</p>' if c.get("amenities_intro") else "") + '</div>'
                f'<ul class="amen">{items}</ul></div></section>')

    gal = ""
    if gallery and ("gallery" in secs or len(gallery) > 1):
        tiles = "".join(f'<figure data-reveal class="g{i % 5}"><img src="{E(g)}" alt="{E(captions[i] if i < len(captions) else b.business)}" loading="lazy">'
                        f'{f"<figcaption>{E(captions[i])}</figcaption>" if i < len(captions) and captions[i] else ""}</figure>' for i, g in enumerate(gallery[:8]))
        gal = (f'<section id="gallery" class="sec light"><div class="wrap"><div class="head" data-reveal><p class="kick">Gallery</p>'
               f'<h2>{_accent_headline(c.get("gallery_title") or f"Picture life at {b.business}.")}</h2></div><div class="gal">{tiles}</div>'
               f'<p class="fine c">Images are artist\'s impressions and indicative. The final development may vary.</p></div></section>')

    loc = ""
    if (distances or b.address) and "location" in secs:
        rows_html = "".join(f'<li><span>{E(d.place)}</span><b>{E(d.time)}</b></li>' for d in distances)
        loc = (f'<section id="location" class="sec white"><div class="wrap two"><div data-reveal><p class="kick">Location</p>'
               f'<h2>{_accent_headline(c.get("location_title") or "Well connected. Perfectly placed.")}</h2>'
               + (f'<p class="lead">{E(c["location_intro"])}</p>' if c.get("location_intro") else "")
               + f'{f"<ul class=dist>{rows_html}</ul>" if rows_html else ""}</div>'
               + f'<div class="mapcard" data-reveal><div class="pin">{icon("pin", 26)}</div>'
               f'<p class="addr">{E(b.address or eyebrow)}</p>'
               + (f'<a class="btn gold" href="{E(map_url)}" target="_blank" rel="noopener">Open in Google Maps ↗</a>' if map_url else "")
               + '</div></div></section>')

    steps = ""
    if "steps" in secs:
        st = c.get("steps") or ([["Choose your home", "Pick the configuration and budget that suit you."],
                                 ["Visit the site", "See the project with our team at a time that works for you."],
                                 ["Book with confidence", "Clear paperwork and a guided booking process."]] if real_estate else
                                [["Tell us what you need", "Share a few details in the form."],
                                 ["Get a clear plan", "We'll call you back with options and pricing."],
                                 ["Get started", "Pick a time that works and we'll take it from there."]])
        steps = ('<section class="sec light"><div class="wrap"><div class="head c" data-reveal><p class="kick">How it works</p>'
                 f'<h2>{_accent_headline(c.get("steps_title") or "Three simple steps.")}</h2></div><ol class="steps">'
                 + "".join(f'<li data-reveal><span>{i}</span><h3>{E(t)}</h3><p>{E(d)}</p></li>' for i, (t, d) in enumerate(st[:3], 1))
                 + '</ol></div></section>')

    testi = ""
    if b.testimonials:
        testi = ('<section class="sec white"><div class="wrap"><div class="head" data-reveal><p class="kick">In their words</p><h2>What our customers say</h2></div><div class="quotes">'
                 + "".join(f'<figure data-reveal><blockquote>“{E(t.quote)}”</blockquote><figcaption>— {E(t.name)}</figcaption></figure>' for t in b.testimonials)
                 + '</div></div></section>')

    faq = ""
    if b.faqs:
        faq = ('<section id="faq" class="sec white"><div class="wrap narrow"><div class="head c" data-reveal><p class="kick">FAQ</p><h2>Common questions</h2></div>'
               + "".join(f'<details data-reveal><summary>{E(q.q)}</summary><p>{E(q.a)}</p></details>' for q in b.faqs) + '</div></section>')

    receive = c.get("receive") or (["Latest availability", "Detailed cost sheet", "A guided site visit"] if real_estate
                                   else ["A quick call back", "Clear pricing", "Answers to your questions"])
    quick = "".join(x for x in (
        f'<a class="btn ghost" href="{call_href}">Call {E(b.phone)}</a>' if call_href else "",
        f'<a class="btn ghost" href="{wa_link(f"Hi, I am interested in {b.business}")}" target="_blank" rel="noopener">WhatsApp us</a>' if wa_link else "",
    ) if x)
    enquire = (f'<section id="enquire" class="sec dark"><div class="wrap two"><div data-reveal><p class="kick">Enquire</p>'
               f'<h2>{_accent_headline(c.get("enquire_title") or (b.form_title or ("Come home to possibility." if real_estate else "Talk to us.")))}</h2>'
               f'<p class="lead">You\'ll receive:</p><ul class="rcv">' + "".join(f"<li>{E(x)}</li>" for x in receive[:4]) + '</ul>'
               f'{f"<div class=row>{quick}</div>" if quick else ""}</div>'
               f'<div class="card" id="contact" data-reveal><h3>{E(cta)}</h3>{main_form}</div></div></section>')

    year = date.today().year
    footer = (f'<footer><div class="wrap"><div class="fgrid"><div><p class="wm">{E(b.business)}</p>'
              f'{f"<p class=fs>{E(b.subheadline or b.offer)}</p>" if (b.subheadline or b.offer) else ""}{approvals_badge}</div>'
              f'<div><p class="fh">Explore</p>{nav_html}</div><div><p class="fh">Contact</p>'
              + "".join(x for x in (f'<a href="{call_href}">{E(b.phone)}</a>' if call_href else "", f'<a href="mailto:{E(b.contact_email)}">{E(b.contact_email)}</a>' if b.contact_email else "",
                                     f'<p>{E(b.address)}</p>' if b.address else "") if x)
              + f'</div></div><p class="disc">Prices, plans, specifications and availability are indicative and subject to change. Images are artist\'s impressions. '
              f'{E(approvals) + ". " if approvals else ""}© {year} {E(b.business)}.</p></div></footer>')

    sticky = ('<div class="sticky" id="sticky">'
              + (f'<a href="{call_href}">Call</a>' if call_href else ('<a href="#enquire" data-callback>Call me back</a>' if callback else ""))
              + (f'<a href="{wa_link(f"Hi, I am interested in {b.business}")}" target="_blank" rel="noopener">WhatsApp</a>' if wa_link else "")
              + f'<button data-open="price">{"Get price list" if real_estate else "Get details"}</button><a class="g" href="#enquire">Enquire →</a></div>')
    float_wa = (f'<a class="wa-float" href="{wa_link(f"Hi, I am interested in {b.business}")}" target="_blank" rel="noopener" aria-label="Chat on WhatsApp">'
                '<svg width="26" height="26" viewBox="0 0 24 24" fill="#fff"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm5.3 14.2c-.2.6-1.3 1.2-1.8 1.2s-1 .3-3.4-.7a11.6 11.6 0 0 1-4.6-4.1c-.4-.6-1-1.7-1-3.1s.8-2.1 1-2.4c.3-.3.6-.4.8-.4h.6c.2 0 .4 0 .6.5l.9 2.1c.1.2.1.4 0 .6l-.4.6-.4.4c-.1.2-.3.3-.1.6a8.6 8.6 0 0 0 3.9 3.4c.3.1.5.1.6-.1l.9-1.1c.2-.3.4-.2.7-.1l2 .9c.3.2.5.2.6.4s.1.7-.1 1.3Z"/></svg></a>'
                if wa_link and b.whatsapp_button else "")
    modal = (f'<div class="modal" id="modal" hidden><div class="mbox"><button class="x" data-close aria-label="Close">×</button>'
             f'<p class="kick">{E(b.business)}</p><h3 id="mtitle">Get the brochure & price list</h3>{modal_form}</div></div>')

    schema = {"@context": "https://schema.org", "@type": "RealEstateListing" if real_estate else "LocalBusiness", "name": b.business,
              "description": b.seo_description or sub or b.offer, "url": f"/s/{slug}"}
    if b.address:
        schema["address"] = b.address
    if hero_img.startswith("https://"):
        schema["image"] = hero_img
    if price_from:
        schema["offers"] = {"@type": "Offer", "description": price_from}

    hero_bg = (f"linear-gradient(180deg,rgba(0,0,0,.25) 0%,{dark}cc 70%,{dark} 100%),url('{E(hero_img)}')" if hero_img
               else f"radial-gradient(60% 70% at 80% 10%,{gold}33,transparent 70%),linear-gradient(160deg,{dark},#000)")
    css = f"""
:root{{--dk:{dark};--gd:{gold};--lt:{light};--tx:#1f2328;--mu:#5d6470;--ln:rgba(20,20,20,.1);--hf:{hfont},Georgia,serif}}
*{{box-sizing:border-box;margin:0}}html{{scroll-behavior:smooth}}body{{font-family:Inter,system-ui,sans-serif;color:var(--tx);background:#fff;line-height:1.6;-webkit-font-smoothing:antialiased}}
img{{max-width:100%;display:block}}a{{color:inherit}}.wrap{{max-width:1180px;margin:0 auto;padding:0 22px}}.narrow{{max-width:820px}}
h1,h2,h3,.wm{{font-family:var(--hf);font-weight:600;letter-spacing:-.01em;line-height:1.08}}h1 em,h2 em{{font-style:italic;color:var(--gd)}}
.kick{{display:flex;align-items:center;gap:12px;font-size:12px;font-weight:600;letter-spacing:.22em;text-transform:uppercase;color:var(--gd);margin-bottom:14px}}
.kick:before{{content:"";width:34px;height:1px;background:currentColor}}.head.c .kick,.c .kick{{justify-content:center}}
h2{{font-size:clamp(32px,4.6vw,54px);margin-bottom:18px}}.lead{{font-size:18px;color:var(--mu);max-width:60ch}}.head{{margin-bottom:46px}}.head.c,.c{{text-align:center}}.head.c .lead{{margin:0 auto}}
.btn{{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:15px 26px;border-radius:4px;font-weight:600;font-size:15px;text-decoration:none;border:1px solid transparent;cursor:pointer;transition:transform .2s,background .2s}}
.btn:hover{{transform:translateY(-1px)}}.btn.gold{{background:var(--gd);color:#1a1a1a}}.btn.ghost{{border-color:rgba(255,255,255,.35);color:#fff;background:rgba(255,255,255,.04)}}.btn.block{{width:100%}}
.sec{{padding:110px 0;scroll-margin-top:70px}}.sec.light{{background:var(--lt)}}.sec.white{{background:#fff}}.sec.dark{{background:var(--dk);color:#f3f1ec}}.sec.dark .lead{{color:rgba(243,241,236,.75)}}
.ann{{background:var(--gd);color:#1a1a1a;font-size:13px;font-weight:500;text-align:center;padding:9px 16px}}.ann a{{font-weight:700;margin-left:8px}}
header{{position:fixed;left:0;right:0;z-index:40;transition:background .3s,box-shadow .3s;color:#fff}}header.solid{{top:0!important;background:rgba(255,255,255,.96);color:var(--tx);box-shadow:0 8px 30px -12px rgba(0,0,0,.25);backdrop-filter:blur(10px)}}
.hdr{{display:flex;align-items:center;justify-content:space-between;height:76px}}.wm{{font-size:24px}}.logo{{max-height:44px}}nav.top{{display:flex;gap:28px;font-size:14px;font-weight:500}}nav.top a{{text-decoration:none;opacity:.85}}nav.top a:hover{{opacity:1}}
.hero{{min-height:94vh;display:flex;align-items:flex-end;background:{hero_bg};background-size:cover;background-position:center;color:#fff;padding:150px 0 70px}}
.hero h1{{font-size:clamp(44px,7.4vw,96px);max-width:15ch;margin:6px 0 22px}}.hero .sub{{font-size:clamp(17px,2vw,20px);max-width:58ch;color:rgba(255,255,255,.88)}}
.chips{{display:flex;flex-wrap:wrap;gap:10px;margin:26px 0}}.chips span{{border:1px solid rgba(255,255,255,.28);border-radius:999px;padding:7px 16px;font-size:13px;background:rgba(255,255,255,.06);backdrop-filter:blur(6px)}}
.row{{display:flex;flex-wrap:wrap;gap:12px}}.hero-grid{{display:grid;grid-template-columns:1.5fr 1fr;gap:40px;align-items:end}}
.glass{{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);backdrop-filter:blur(14px);border-radius:10px}}
.price-card{{padding:22px 24px}}.price-card .k{{display:block;font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:rgba(255,255,255,.7)}}.price-card b{{display:block;font-family:var(--hf);font-style:italic;font-size:42px;font-weight:500;color:var(--gd);line-height:1.15;margin:4px 0}}
.price-card .n{{display:block;font-size:13px;color:rgba(255,255,255,.7)}}.lnk{{background:none;border:0;color:#fff;font:inherit;font-weight:600;font-size:14px;margin-top:10px;cursor:pointer;padding:0;text-decoration:underline;text-underline-offset:4px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));margin-top:46px;border-top:1px solid rgba(255,255,255,.2)}}.stat{{padding:20px 18px 0 0}}.stat b{{display:block;font-family:var(--hf);font-size:clamp(28px,3.4vw,40px);font-weight:500;letter-spacing:.02em}}.stat span{{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:rgba(255,255,255,.65)}}
.badge{{display:inline-block;margin-top:14px;border:1px solid var(--gd);color:var(--gd);border-radius:999px;padding:6px 14px;font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase}}
.two{{display:grid;grid-template-columns:1.05fr 1fr;gap:70px;align-items:center}}.hls{{display:grid;gap:18px;margin-top:34px}}.hl{{display:grid;grid-template-columns:46px 1fr;column-gap:16px;align-items:start}}
.hl .ic,.amen .ic{{display:grid;place-items:center;width:46px;height:46px;border-radius:50%;background:#fff;color:var(--dk);box-shadow:0 6px 20px -10px rgba(0,0,0,.25)}}.hl h3{{font-family:Inter,sans-serif;font-size:17px;font-weight:600;align-self:center}}.hl p{{grid-column:2;color:var(--mu);font-size:15px}}
.ov-img{{position:relative}}.ov-img img{{border-radius:8px;aspect-ratio:4/5;object-fit:cover;width:100%}}.floating{{position:absolute;left:-26px;bottom:34px;background:var(--dk);color:#fff;padding:20px 26px;border-radius:6px;box-shadow:0 20px 50px -20px rgba(0,0,0,.5)}}.floating b{{display:block;font-family:var(--hf);font-size:34px;color:var(--gd)}}.floating span{{font-size:12px;letter-spacing:.16em;text-transform:uppercase;opacity:.75}}
.plans{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px}}.plan{{border:1px solid rgba(255,255,255,.14);border-radius:8px;padding:30px;background:rgba(255,255,255,.03);display:flex;flex-direction:column;gap:6px;transition:border-color .3s,transform .3s}}.plan:hover{{border-color:var(--gd);transform:translateY(-3px)}}
.plan h3{{font-size:28px}}.plan .d{{color:rgba(243,241,236,.7);font-size:15px;flex:1}}.plan .pr{{font-family:var(--hf);font-style:italic;font-size:30px;color:var(--gd);margin:14px 0 16px}}
.amen{{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}}.amen li{{display:flex;align-items:center;gap:14px;padding:16px 18px;border:1px solid var(--ln);border-radius:8px;font-weight:500;background:#fff}}.amen .ic{{width:42px;height:42px;flex-shrink:0;background:var(--lt);box-shadow:none}}
.gal{{display:grid;grid-template-columns:repeat(6,1fr);grid-auto-rows:220px;gap:14px}}.gal figure{{position:relative;overflow:hidden;border-radius:8px;grid-column:span 2}}.gal .g0{{grid-column:span 4;grid-row:span 2}}.gal .g3{{grid-column:span 3}}.gal .g4{{grid-column:span 3}}
.gal img{{width:100%;height:100%;object-fit:cover;transition:transform .8s}}.gal figure:hover img{{transform:scale(1.05)}}.gal figcaption{{position:absolute;left:0;right:0;bottom:0;padding:30px 18px 14px;color:#fff;font-size:14px;background:linear-gradient(transparent,rgba(0,0,0,.65))}}
.fine{{font-size:12px;color:var(--mu);margin-top:16px}}.dist{{list-style:none;padding:0;margin-top:26px;border-top:1px solid var(--ln)}}.dist li{{display:flex;justify-content:space-between;gap:16px;padding:16px 0;border-bottom:1px solid var(--ln);font-size:16px}}.dist b{{color:var(--dk);font-weight:700}}
.mapcard{{position:relative;min-height:380px;border-radius:10px;padding:40px;display:flex;flex-direction:column;justify-content:flex-end;gap:16px;color:#fff;overflow:hidden;
background:radial-gradient(circle at 70% 35%,{gold}55 0 6%,transparent 7%),repeating-linear-gradient(35deg,rgba(255,255,255,.06) 0 2px,transparent 2px 46px),repeating-linear-gradient(-55deg,rgba(255,255,255,.05) 0 2px,transparent 2px 60px),var(--dk)}}
.mapcard .pin{{position:absolute;left:calc(70% - 13px);top:calc(35% - 26px);color:var(--gd)}}.mapcard .addr{{font-family:var(--hf);font-size:24px;max-width:22ch}}.mapcard .btn{{align-self:flex-start}}
.steps{{list-style:none;padding:0;display:grid;grid-template-columns:repeat(3,1fr);gap:22px;counter-reset:s}}.steps li{{background:#fff;border-radius:8px;padding:34px 28px;box-shadow:0 20px 50px -30px rgba(0,0,0,.25)}}.steps span{{display:grid;place-items:center;width:44px;height:44px;border-radius:50%;background:var(--dk);color:var(--gd);font-family:var(--hf);font-size:20px;margin-bottom:18px}}.steps h3{{font-size:23px;margin-bottom:8px}}.steps p{{color:var(--mu)}}
.quotes{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}}.quotes figure{{border-left:2px solid var(--gd);padding:8px 0 8px 22px}}blockquote{{font-family:var(--hf);font-size:21px;line-height:1.45}}figcaption{{color:var(--mu);margin-top:10px;font-size:14px}}
details{{border-bottom:1px solid var(--ln);padding:22px 0}}summary{{cursor:pointer;font-weight:600;font-size:18px;list-style:none;display:flex;justify-content:space-between;gap:20px}}summary:after{{content:"+";color:var(--gd);font-size:24px;line-height:1}}details[open] summary:after{{content:"–"}}details p{{margin-top:12px;color:var(--mu)}}
.rcv{{list-style:none;padding:0;margin:6px 0 30px;display:grid;gap:10px}}.rcv li{{display:flex;gap:12px;align-items:center;font-size:17px}}.rcv li:before{{content:"✓";display:grid;place-items:center;width:26px;height:26px;border-radius:50%;background:var(--gd);color:#1a1a1a;font-size:13px;font-weight:700}}
.card{{background:#fff;color:var(--tx);border-radius:10px;padding:34px;box-shadow:0 30px 70px -30px rgba(0,0,0,.6)}}.card h3{{font-size:28px;margin-bottom:20px}}
.form{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.f{{display:grid;gap:6px;font-size:13px;font-weight:600;color:var(--mu)}}.f.wide,.ck,.form .btn,.fine,.form .full{{grid-column:1/-1}}
.f input,.f select,.f textarea{{font:inherit;font-weight:400;font-size:15px;color:var(--tx);padding:13px 14px;border:1px solid #d7d9de;border-radius:6px;background:#fff;width:100%}}.f input:focus,.f select:focus,.f textarea:focus{{outline:2px solid var(--gd);border-color:transparent}}
.ck{{display:flex;gap:10px;align-items:flex-start;font-size:13px;color:var(--mu)}}.ck input{{margin-top:3px;accent-color:var(--dk)}}.hp{{position:absolute;left:-9999px;opacity:0;height:0;width:0}}
footer{{background:#0e0e0e;color:rgba(255,255,255,.75);padding:80px 0 120px;font-size:14px}}.fgrid{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:40px}}footer .wm{{color:#fff;font-size:28px;margin-bottom:10px}}.fh{{color:#fff;font-weight:600;margin-bottom:12px}}footer a{{display:block;text-decoration:none;margin-bottom:8px}}footer a:hover{{color:var(--gd)}}
.disc{{border-top:1px solid rgba(255,255,255,.12);margin-top:50px;padding-top:24px;font-size:12px;line-height:1.7;color:rgba(255,255,255,.5)}}
.sticky{{position:fixed;left:12px;right:12px;bottom:12px;z-index:45;display:none;gap:6px;padding:6px;border-radius:12px;background:rgba(14,14,14,.92);backdrop-filter:blur(10px);transform:translateY(130%);transition:transform .35s}}.sticky.on{{transform:none}}
.sticky a,.sticky button{{flex:1;text-align:center;padding:12px 6px;border-radius:8px;color:#fff;text-decoration:none;font:600 14px Inter,sans-serif;background:rgba(255,255,255,.08);border:0;cursor:pointer}}.sticky .g{{background:var(--gd);color:#1a1a1a}}
.wa-float{{position:fixed;right:22px;bottom:22px;z-index:44;width:58px;height:58px;border-radius:50%;background:#25d366;display:grid;place-items:center;box-shadow:0 12px 30px -8px rgba(0,0,0,.4)}}
.modal{{position:fixed;inset:0;z-index:60;background:rgba(0,0,0,.6);display:grid;place-items:center;padding:16px}}.modal[hidden]{{display:none}}.mbox{{position:relative;background:#fff;border-radius:12px;padding:34px;width:min(520px,100%);max-height:92vh;overflow:auto}}.mbox h3{{font-size:28px;margin-bottom:18px}}.x{{position:absolute;right:14px;top:10px;background:none;border:0;font-size:30px;cursor:pointer;color:var(--mu)}}.ok-t{{font-family:var(--hf);font-size:26px;margin-bottom:12px}}
.burger{{display:none;background:none;border:0;color:inherit;font-size:26px;cursor:pointer}}
[data-reveal]{{opacity:0;transform:translateY(18px);transition:opacity .8s cubic-bezier(.22,1,.36,1),transform .8s cubic-bezier(.22,1,.36,1)}}[data-reveal].in{{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){{[data-reveal]{{opacity:1;transform:none;transition:none}}html{{scroll-behavior:auto}}}}
@media(max-width:900px){{.two,.hero-grid,.fgrid{{grid-template-columns:1fr;gap:40px}}nav.top{{display:none}}nav.top.open{{display:flex;position:absolute;top:76px;left:0;right:0;flex-direction:column;gap:0;background:#fff;color:var(--tx);padding:8px 22px 18px;box-shadow:0 20px 30px -20px rgba(0,0,0,.3)}}nav.top.open a{{padding:12px 0;border-bottom:1px solid var(--ln)}}
.burger{{display:block}}.hdr .btn{{display:none}}.sec{{padding:76px 0}}.steps{{grid-template-columns:1fr}}.gal{{grid-template-columns:1fr 1fr;grid-auto-rows:170px}}.gal figure,.gal .g0,.gal .g3,.gal .g4{{grid-column:span 1;grid-row:span 1}}.gal .g0{{grid-column:span 2}}
.floating{{left:12px}}.form{{grid-template-columns:1fr}}.sticky{{display:flex}}.wa-float{{display:none}}.card{{padding:24px}}.hero{{min-height:88vh;padding-top:120px}}}}
"""
    js = """<script>
(function(){var h=document.querySelector('header'),s=document.getElementById('sticky'),hero=document.querySelector('.hero');
function onS(){var y=window.scrollY;h&&h.classList.toggle('solid',y>40);s&&s.classList.toggle('on',hero?y>hero.offsetHeight*0.6:y>300)}
window.addEventListener('scroll',onS,{passive:true});onS();
var b=document.querySelector('.burger'),n=document.querySelector('nav.top');b&&b.addEventListener('click',function(){n.classList.toggle('open')});
n&&n.addEventListener('click',function(e){if(e.target.tagName==='A')n.classList.remove('open')});
var m=document.getElementById('modal'),t=document.getElementById('mtitle');
document.addEventListener('click',function(e){var o=e.target.closest('[data-open]');if(o){e.preventDefault();var i=o.getAttribute('data-interest')||'';
 m.querySelector('[name=interest]').value=i;t.textContent=i?('Get the cost sheet for '+i):(o.getAttribute('data-open')==='price'?'Get the current price sheet':'Get the brochure & price list');
 m.querySelector('[name=action]').value=o.getAttribute('data-open')==='price'?'price':'brochure';m.hidden=false;var f=m.querySelector('input:not([type=hidden])');f&&f.focus()}
 if(e.target.closest('[data-close]')||e.target===m){m.hidden=true}
 if(e.target.closest('[data-callback]')){var c=document.querySelector('#enquiry-form [name=callback]');if(c)c.checked=true}});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&m)m.hidden=true});
if('IntersectionObserver' in window){var io=new IntersectionObserver(function(es){es.forEach(function(x){if(x.isIntersecting){x.target.classList.add('in');io.unobserve(x.target)}})},{rootMargin:'0px 0px -8% 0px'});
 document.querySelectorAll('[data-reveal]').forEach(function(el){io.observe(el)})}else{document.querySelectorAll('[data-reveal]').forEach(function(el){el.classList.add('in')})}
})();
</script>"""
    title = b.seo_title or (f"{b.business} | {eyebrow}" if eyebrow else b.business)
    desc = b.seo_description or sub or b.offer or b.business
    brand = (f'<img src="{media["logo"]}" alt="{E(b.business)}" class="logo">' if media.get("logo") else f'<span class="wm">{E(b.business)}</span>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title><meta name="description" content="{E(desc)}"><meta name="theme-color" content="{dark}">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">{f'<meta property="og:image" content="{E(hero_img)}">' if hero_img.startswith("https://") else ""}
<meta name="aimva:layout" content="showcase">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family={gfam}&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script type="application/ld+json">{json.dumps(schema).replace("<", "&lt;")}</script>{tracking}
<style>{css}</style></head><body>
{f'<div class="ann">{E(announcement)}<a href="#enquire">Enquire ↗</a></div>' if announcement else ""}
<header style="top:{'36px' if announcement else '0'}"><div class="wrap hdr">{brand}<nav class="top">{nav_html}</nav>
<a class="btn gold" href="#enquire">{E(cta)}</a><button class="burger" aria-label="Menu">≡</button></div></header>
<main>
<section class="hero" data-aimva-section="hero"><div class="wrap"><div class="hero-grid"><div>
{f'<p class="kick">{E(eyebrow)}</p>' if eyebrow else ""}{f'<span class="badge" style="margin:0 0 18px">{E(approvals)}</span>' if approvals else ""}
<h1>{_accent_headline(headline)}</h1>{f'<p class="sub">{E(sub)}</p>' if sub else ""}
{f'<div class="chips">{chips_html}</div>' if chips_html else '<div style="height:26px"></div>'}
<div class="row"><a class="btn gold" href="#enquire">{E(cta)}</a>{'<a class="btn ghost" href="#plans">Explore plans</a>' if configs else '<button class="btn ghost" data-open="brochure">Download brochure</button>'}</div>
</div>{price_card}</div>{f'<div class="stats">{stats_html}</div>' if stats_html else ""}</div></section>
{overview}{plans}{amen}{gal}{loc}{steps}{testi}{faq}{enquire}
</main>{footer}{sticky}{float_wa}{modal}{js}{form_script}</body></html>"""
