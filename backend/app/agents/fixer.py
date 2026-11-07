"""Page Fixer: fixes the launch issues that have one obviously right answer, so people don't have to."""
import html as H
import re

from ..quality import audit_page


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
    return html, fixed


def remaining(html: str, brief: dict) -> list:
    """Issues still open after fixing, which need a person (placeholders, invented numbers, risky claims…)."""
    return [c["message"] for c in audit_page(html, brief) if not c["ok"] and c["level"] in ("blocker", "warning")]
