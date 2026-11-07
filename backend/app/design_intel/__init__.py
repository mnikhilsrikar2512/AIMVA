"""Design intelligence for generated pages: colours, fonts, look and section pattern matched to the business.

Backed by the UI/UX Pro Max design data (MIT, nextlevelbuilder, v2.15.0; see LICENSE in this folder), vendored in
``uupm/`` and ``data/``. Runs offline, in about a millisecond after the first call.

Rules of use in AIMVA:
- The owner's own choices always win: Brand kit colours, colours they picked, a look or font they picked.
- Only confident matches are used. A query that lands on the generic "General" category returns None.
- Everything returned is validated here (hex colours, whitelisted Google Fonts names) before it reaches HTML.
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

DATA = Path(__file__).parent / "data"
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


# ---- colour maths (WCAG 2.x) -----------------------------------------------------------------------------
def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


DARK_TEXT = "#0f172a"


def on_color(bg: str) -> str:
    """Text colour for a button of colour ``bg``: white when it reads, else near-black (whichever is clearer)."""
    if not HEX.match(bg or ""):
        return "#ffffff"
    return "#ffffff" if contrast(bg, "#ffffff") >= 4.5 or contrast(bg, "#ffffff") >= contrast(bg, DARK_TEXT) else DARK_TEXT


def _shift(hex_color: str, amount: float) -> str:
    """Darken (amount < 0) or lighten (amount > 0) a colour by a fraction."""
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    if amount < 0:
        rgb = [round(c * (1 + amount)) for c in rgb]
    else:
        rgb = [round(c + (255 - c) * amount) for c in rgb]
    return "#" + "".join(f"{max(0, min(255, c)):02x}" for c in rgb)


def _hue_gap(a: str, b: str) -> float:
    import colorsys
    ha, sa, _ = colorsys.rgb_to_hsv(*(int(a[i:i + 2], 16) / 255 for i in (1, 3, 5)))
    hb, sb, _ = colorsys.rgb_to_hsv(*(int(b[i:i + 2], 16) / 255 for i in (1, 3, 5)))
    if min(sa, sb) < 0.15:  # greys go with anything
        return 0.0
    d = abs(ha - hb) * 360
    return min(d, 360 - d)


# ---- fonts --------------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def allowed_fonts() -> frozenset:
    """Google Fonts families the data recommends for Latin pages; anything else is refused."""
    names = set()
    with open(DATA / "typography.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for k in ("Heading Font", "Body Font"):
                n = (row.get(k) or "").strip()
                if re.fullmatch(r"[A-Za-z0-9 ]{2,40}", n) and not n.startswith("Noto S"):
                    names.add(n)
    return frozenset(names)


def fonts_query(heading: str, body: str) -> Optional[str]:
    """The family= part of a Google Fonts URL for a pairing, or None if either name isn't whitelisted."""
    ok = allowed_fonts()
    if heading not in ok or body not in ok:
        return None
    fams = [heading] if heading == body else [heading, body]
    return "&family=".join(f"{n.replace(' ', '+')}:wght@400;600;700" for n in fams)


# ---- looks ---------------------------------------------------------------------------------------------------
def _look_for(style_name: str, mood: str) -> str:
    s = f"{style_name} {mood}".lower()
    for look, words in (("bold", ("brutal", "bold statement")), ("elegant", ("luxury", "elegant", "editorial", "premium", "serif")),
                        ("playful", ("playful", "clay", "vibrant", "block", "kids", "fun")),
                        ("minimal", ("minimal", "swiss", "flat")), ("corporate", ("corporate", "trust", "enterprise", "professional"))):
        if any(w in s for w in words):
            return look
    return "modern"


# ---- the match ---------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _generator():
    from .uupm.design_system import DesignSystemGenerator
    return DesignSystemGenerator()


@lru_cache(maxsize=512)
def _match(query: str) -> Optional[dict]:
    try:
        d = _generator().generate(query)
    except Exception:  # bad data or an edge case in the vendored code must never break page generation
        return None
    category = d.get("category") or "General"
    if category == "General":
        return None
    c, t, style, pattern = d.get("colors") or {}, d.get("typography") or {}, d.get("style") or {}, d.get("pattern") or {}
    primary = (c.get("primary") or "").strip()
    accent = next((x for x in ((c.get("accent") or "").strip(), (c.get("secondary") or "").strip())
                   if HEX.match(x) and x.lower() != primary.lower()), "")
    if not HEX.match(primary):
        return None
    if not accent or _hue_gap(primary, accent) > 90:  # a clashing pair (orange + green) makes a muddy headline gradient
        accent = _shift(primary, 0.35)
    heading, body = (t.get("heading") or "").strip(), (t.get("body") or "").strip()
    return {
        "category": category,
        "primary": primary.lower(),
        "accent": accent.lower(),
        "font_heading": heading if fonts_query(heading, body) else "",
        "font_body": body if fonts_query(heading, body) else "",
        "look": _look_for(style.get("name", ""), t.get("mood", "")),
        "style": style.get("name", ""),
        "pattern": pattern.get("name", ""),
        "sections": pattern.get("sections", ""),
        "anti_patterns": d.get("anti_patterns", ""),
    }


def match_design(industry: str = "", business: str = "", offer: str = "") -> Optional[dict]:
    """Best design direction for a business, or None when nothing fits confidently.

    The industry carries most of the signal; business name and offer only help when the industry is blank.
    """
    query = " ".join(x.strip() for x in ((industry or ""), "" if industry else (business or ""), "" if industry else (offer or "")) if x and x.strip())
    query = re.sub(r"\s+", " ", query)[:120]
    if len(query) < 3:
        return None
    m = _match(query.lower())
    return dict(m) if m else None


def writer_notes(m: Optional[dict]) -> str:
    """One paragraph for the AI page writer. Facts rules elsewhere in the prompt still win."""
    if not m:
        return ""
    bits = [f" Design direction for a {m['category']} business: {m['style']} style"]
    if m.get("font_heading"):
        bits.append(f", headings in {m['font_heading']} and body text in {m['font_body']} (Google Fonts)")
    if m.get("sections"):
        bits.append(f". A proven section order for this kind of business: {m['sections']}; keep only sections you have real facts for")
    if m.get("anti_patterns"):
        bits.append(f". Avoid: {m['anti_patterns']}")
    bits.append(". Buttons need readable text (4.5:1 contrast), tap targets at least 44px tall, body text at least 16px, "
                "inputs at least 16px so phones don't zoom, and animations must respect prefers-reduced-motion.")
    return "".join(bits)
