"""Page Fixer: fixes the launch issues that have one obviously right answer, so people don't have to."""
import html as H
import re

from ..quality import _eager_images, _unlabelled, audit_page, design_checks


def fix_html(html: str, brief: dict) -> tuple:
    """Return (fixed html, list of what was fixed). Never touches wording, prices or claims: those stay the user's call."""
    fixed = []
    business = brief.get("business") or "Our business"
    head = re.search(r"<head[^>]*>", html, re.I)

    def into_head(tag: str) -> None:
        nonlocal html
        html = html[:head.end()] + tag + html[head.end():] if head else tag + html

    low = html.lower()
    if head and "name=\"viewport\"" not in low and "name='viewport'" not in low and "name=viewport" not in low:
        into_head('<meta name="viewport" content="width=device-width,initial-scale=1">')
        fixed.append("Added the mobile viewport tag so phones show the page at the right size")
    head = re.search(r"<head[^>]*>", html, re.I)
    if head and not re.search(r"<title>\s*[^<\s][^<]*</title>", html, re.I):
        title = brief.get("seo_title") or (f"{business} | {brief['offer']}" if brief.get("offer") else business)
        html = re.sub(r"<title>\s*</title>", "", html, flags=re.I)
        into_head(f"<title>{H.escape(title[:70])}</title>")
        fixed.append("Added a page title for Google and browser tabs")
    head = re.search(r"<head[^>]*>", html, re.I)
    if head and not re.search(r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"'][^\"']+", html, re.I):
        desc = brief.get("seo_description") or brief.get("subheadline") or brief.get("offer") or f"Get in touch with {business}."
        into_head(f'<meta name="description" content="{H.escape(desc[:170])}">')
        fixed.append("Added a search description")

    n = 0

    def alt(m):
        nonlocal n
        tag = m.group(0)
        if re.search(r"\balt\s*=", tag, re.I):
            return tag
        n += 1
        return tag[:4] + f' alt="{H.escape(business)}"' + tag[4:]
    html = re.sub(r"<img\b[^>]*>", alt, html, flags=re.I)
    if n:
        fixed.append(f"Added alt text to {n} image{'s' if n != 1 else ''}")

    html, dead = re.subn(r"(<a\b[^>]*href\s*=\s*)([\"'])\s*#?\s*\2", r'\1"#contact"', html, flags=re.I)
    if dead:
        fixed.append(f"Pointed {dead} empty link{'s' if dead != 1 else ''} at the enquiry form")
    html, more = fix_design(html)
    return html, fixed + more


def fix_design(html: str) -> tuple:
    """Design and accessibility fixes with one right answer. Brand colours, layout and wording are left alone:
    only button *text* colour changes, to white or near-black, whichever reads on the owner's colour."""
    from ..design_intel import on_color
    from ..quality import button_contrast
    failing = {k for k, ok, *_ in design_checks(html) if not ok}
    css, fixed = [], []
    if "contrast" in failing:
        bad = button_contrast(html)
        css += [f"{sel}{{color:{on_color(bg)}!important}}" for sel, bg, _fg, _r in bad]
        fixed.append(f"Made the text on {len(bad)} button style{'s' if len(bad) != 1 else ''} readable (your button colour is unchanged)")
    if "input_size" in failing:
        css.append("@media(max-width:640px){input,select,textarea{font-size:16px!important}}")
        fixed.append("Set form text to 16px on phones so iPhones don't zoom in")
    if "motion" in failing:
        css.append("@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;"
                   "animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}")
        fixed.append("Turned animations off for visitors who asked their phone for less motion")
    if "focus" in failing:
        css.append("a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,"
                   "summary:focus-visible{outline:3px solid currentColor!important;outline-offset:2px}")
        fixed.append("Showed a focus outline for keyboard users")
    if "labels" in failing:
        todo = set(_unlabelled(html))
        n = 0

        def label(m):
            nonlocal n
            tag = m.group(0)
            if tag not in todo:
                return tag
            src = re.search(r"\bplaceholder\s*=\s*[\"']([^\"']+)", tag, re.I) or re.search(r"\bname\s*=\s*[\"']?([\w-]+)", tag, re.I)
            if not src:
                return tag
            n += 1
            text = H.unescape(src.group(1)).replace("_", " ").strip()
            text = text[:1].upper() + text[1:]
            return re.sub(r"^<(\w+)", lambda t: f'<{t.group(1)} aria-label="{H.escape(text)}"', tag)
        html = re.sub(r"<(input|textarea|select)\b[^>]*>", label, html, flags=re.I)
        if n:
            fixed.append(f"Labelled {n} form field{'s' if n != 1 else ''} for screen readers")
    if "lazy" in failing:
        todo = set(_eager_images(html))
        n = 0

        def lazy(m):
            nonlocal n
            if m.group(0) not in todo:
                return m.group(0)
            n += 1
            return m.group(0)[:4] + ' loading="lazy"' + m.group(0)[4:]
        imgs = list(re.finditer(r"<img\b[^>]*>", html, re.I))
        cut = imgs[1].end() if len(imgs) > 1 else 0  # leave the first two (above the fold) as they are
        html = html[:cut] + re.sub(r"<img\b[^>]*>", lazy, html[cut:], flags=re.I)
        if n:
            fixed.append(f"Made {n} image{'s' if n != 1 else ''} further down load as visitors scroll")
    if css:
        block = '<style data-aimva-fix="design">' + "".join(css) + "</style>"
        end = re.search(r"</head\s*>", html, re.I)
        html = html[:end.start()] + block + html[end.start():] if end else block + html
    return html, fixed


def remaining(html: str, brief: dict) -> list:
    """Issues still open after fixing, which need a person (placeholders, invented numbers, risky claims…)."""
    return [c["message"] for c in audit_page(html, brief) if not c["ok"] and c["level"] in ("blocker", "warning")]
