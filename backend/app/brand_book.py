"""The project's brand book: one place that says how this business looks and sounds (owner 2026-11-21, after reading
about DESIGN.md files: "do it"). Every generator reads it, so a page, an ad, a picture and a WhatsApp reply all agree.

It is assembled from what the owner already gave us (setup answers, the Brand Kit, their latest page), and anything
they edit here wins. Edits live in `onboarding_answers["brand_book"]`, so no new table is needed. The owner sees it as
plain words; nothing in it names a provider or explains how prompts are written.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import BrandKit, Site, User

# What the owner can edit, with a length cap each. Lists are short on purpose: a brand book is a page, not a database.
FIELDS = {
    "name": 120, "tagline": 200, "what": 300, "offer": 200, "audience": 300, "area": 160, "languages": 6,
    "voice": 40, "voice_notes": 400, "colors": 5, "font_heading": 40, "font_body": 40, "style": 8,
    "say": 8, "never_say": 8, "avoid": 400, "phone": 30,
}
LISTS = {"languages", "colors", "style", "say", "never_say"}
VOICES = {
    "friendly": "warm and plain, like a helpful neighbour",
    "professional": "clear, calm and precise",
    "bold": "short, confident, energetic",
    "playful": "light and cheerful, with a little wit",
    "luxury": "refined, understated, unhurried",
}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LANG_NAMES = {"hi": "Hindi", "te": "Telugu", "ta": "Tamil", "kn": "Kannada", "ml": "Malayalam", "mr": "Marathi",
              "bn": "Bengali", "gu": "Gujarati", "pa": "Punjabi", "ur": "Urdu", "en": "English", "hinglish": "Hinglish"}


def _edits(ws: User) -> dict:
    return dict((ws.onboarding_answers or {}).get("brand_book") or {})


def _clean(key: str, value):
    """One edited value, trimmed to its shape. Returns None to mean "not set"."""
    cap = FIELDS[key]
    if key in LISTS:
        if isinstance(value, str):
            value = [v for v in re.split(r"[,\n]", value)]
        if not isinstance(value, list):
            return None
        items = [str(v).strip()[:60] for v in value if str(v).strip()]
        if key == "colors":
            items = [c if c.startswith("#") else f"#{c}" for c in items]
            items = [c for c in items if HEX.match(c)]
        return list(dict.fromkeys(items))[:cap] or None
    s = " ".join(str(value or "").split())[:cap]
    if key in ("font_heading", "font_body"):
        s = re.sub(r"[^A-Za-z0-9 ]", "", s)[:40].strip()
    if key == "voice":
        s = s.lower()
        return s if s in VOICES else None
    return s or None


def build(db: Session, ws: User) -> dict:
    """The brand book for a project: owner edits, then Brand Kit, then their latest page, then setup answers."""
    answers = ws.onboarding_answers or {}
    profile = dict(answers.get("profile") or {})
    kit = db.scalar(select(BrandKit).where(BrandKit.user_id == ws.id))
    site = db.scalar(select(Site).where(Site.user_id == ws.id).order_by(Site.id.desc()))
    brief = dict((site.brief or {}) if site else {})
    langs = profile.get("customer_languages") or []
    if isinstance(langs, str):
        langs = [langs]
    colors = list(kit.colors or []) if kit and kit.colors else [c for c in (brief.get("primary"), brief.get("accent")) if c]
    found = {
        "name": (kit.name if kit and kit.name else "") or ws.company or profile.get("name") or "",
        "tagline": (kit.tagline if kit else "") or brief.get("subheadline", ""),
        "what": answers.get("idea") or brief.get("about") or "",
        "offer": profile.get("offer") or brief.get("offer") or "",
        "audience": (kit.audience if kit else "") or profile.get("audience") or brief.get("audience") or "",
        "area": profile.get("area") or profile.get("city") or brief.get("location_line") or "",
        "languages": [LANG_NAMES.get(str(l).lower(), str(l)) for l in langs],
        "voice": (kit.voice if kit else "") or "friendly",
        "voice_notes": (kit.voice_notes if kit else "") or "",
        "colors": colors,
        "font_heading": brief.get("font_heading", ""),
        "font_body": brief.get("font_body", ""),
        "style": list(kit.style or []) if kit else [],
        "say": [],
        "never_say": [],
        "avoid": (kit.avoid if kit else "") or "",
        "phone": brief.get("phone") or profile.get("phone") or "",
    }
    book = {}
    for k in FIELDS:
        v = _clean(k, found[k]) if found[k] else None
        book[k] = v if v is not None else ([] if k in LISTS else "")
    edits = _edits(ws)
    for k, v in edits.items():
        if k in FIELDS:
            book[k] = v
    book["edited"] = sorted(k for k in edits if k in FIELDS)
    filled = sum(bool(book[k]) for k in FIELDS)
    book["complete"] = round(filled / len(FIELDS), 2)
    return book


def save_edits(db: Session, ws: User, changes: dict) -> dict:
    """Store the owner's edits. An empty value clears that edit, so the field falls back to what we found."""
    edits = _edits(ws)
    for k, v in (changes or {}).items():
        if k not in FIELDS:
            continue
        clean = _clean(k, v)
        if clean is None:
            edits.pop(k, None)
        else:
            edits[k] = clean
    ws.onboarding_answers = {**(ws.onboarding_answers or {}), "brand_book": edits}
    db.commit()
    return build(db, ws)


def markdown(book: dict) -> str:
    """The brand book as a readable page (the DESIGN.md idea), for the owner to download or share with a designer."""
    def line(label, v):
        if isinstance(v, list):
            v = ", ".join(v)
        return f"- **{label}:** {v}" if v else None
    voice = book.get("voice") or "friendly"
    parts = [
        f"# {book.get('name') or 'Our business'}",
        f"_{book['tagline']}_" if book.get("tagline") else "",
        "", "## Who we are",
        line("What we do", book.get("what")), line("Our offer", book.get("offer")),
        line("Who it's for", book.get("audience")), line("Where", book.get("area")),
        line("Our customers speak", book.get("languages")), line("Phone", book.get("phone")),
        "", "## How we sound",
        line("Voice", f"{voice}: {VOICES.get(voice, '')}"), line("Notes", book.get("voice_notes")),
        line("Words we like", book.get("say")), line("Words we never use", book.get("never_say")),
        "", "## How we look",
        line("Colours", book.get("colors")), line("Heading font", book.get("font_heading")),
        line("Body font", book.get("font_body")), line("Visual style", book.get("style")),
        line("Never show", book.get("avoid")),
    ]
    return "\n".join(p for p in parts if p is not None).replace("\n\n\n", "\n\n").strip() + "\n"


def copy_rules(book: dict) -> str:
    """How words should sound, as one short instruction for any writer (ads, captions, pages, replies)."""
    voice = book.get("voice") or "friendly"
    bits = [f"Brand voice: {VOICES.get(voice, voice)}."]
    if book.get("voice_notes"):
        bits.append(f"Voice notes: {book['voice_notes']}.")
    if book.get("audience"):
        bits.append(f"Written for: {book['audience']}.")
    if book.get("say"):
        bits.append("Words the brand likes: " + ", ".join(book["say"]) + ".")
    if book.get("never_say"):
        bits.append("Never use these words: " + ", ".join(book["never_say"]) + ".")
    return " ".join(bits)


def effective_kit(db: Session, ws: User) -> Optional[SimpleNamespace]:
    """The brand book in the Brand Kit's shape, so every generator that reads a kit reads the whole book. None when
    there is nothing brand-specific yet (generators then behave exactly as before)."""
    b = build(db, ws)
    if not any(b.get(k) for k in ("tagline", "colors", "style", "audience", "avoid", "voice_notes", "never_say")) \
            and not db.scalar(select(BrandKit.id).where(BrandKit.user_id == ws.id)):
        return None
    avoid = b.get("avoid") or ""
    if b.get("never_say"):
        avoid = (avoid + "; " if avoid else "") + "no text saying " + ", ".join(b["never_say"])
    notes = b.get("voice_notes") or ""
    rules = copy_rules(b)
    return SimpleNamespace(name=b.get("name", ""), tagline=b.get("tagline", ""), colors=b.get("colors") or [],
                           voice=b.get("voice") or "friendly", voice_notes=(notes + (" " if notes else "") + rules)[:600],
                           style=b.get("style") or [], audience=b.get("audience", ""), avoid=avoid[:400],
                           font_heading=b.get("font_heading", ""), font_body=b.get("font_body", ""), copy_rules=rules)
