"""Page score: every new page is marked against one checklist, and low marks get fixed before the owner sees it.

Six parts, each out of 10: is the offer clear, can a visitor act, can they trust it, does it work on a phone, can
everyone use it, and does it look and sound like this brand. A page passes when the average is 8 or more, no part
is under 7 and nothing on it is a claim the owner never gave us. Most marks come from the launch checks in quality.py; the offer, action and brand parts add their own.

`improve` applies the safe fixes (always free), then, only while the page still fails and only for a page the writer
wrote, asks for a rewrite of exactly what is missing, up to three times. A rewrite is kept only when it scores higher.
Nothing here judges taste. These are checks a careful editor would make, so the owner sees them as plain to-dos.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from .quality import audit_page, visible_text

PARTS = {
    "offer": "Your offer is clear",
    "action": "Visitors know what to do next",
    "trust": "Nothing a visitor could doubt",
    "phone": "Works well on a phone",
    "access": "Easy for everyone to use",
    "brand": "Looks and sounds like you",
}
# Which launch check counts against which part.
CHECK_PART = {
    "form": "action", "contact": "action", "cta": "action", "links": "action",
    "placeholders": "trust", "claims": "trust", "testimonials": "trust", "risky": "trust", "phone": "trust",
    "mobile": "phone", "input_size": "phone", "small_text": "phone", "weight": "phone", "lazy": "phone", "size": "phone",
    "contrast": "access", "alt": "access", "labels": "access", "focus": "access", "motion": "access", "emoji": "access",
    "headline": "offer", "title": "offer", "description": "offer",
}
COST = {"blocker": 6, "warning": 3, "tip": 1}
PASS_AVG, PASS_MIN, ROUNDS = 8.0, 7, 3


def _words(s: str) -> list:
    return [w for w in re.findall(r"[a-z0-9ऀ-෿]+", (s or "").lower()) if len(w) > 2]


def _first_screen(html: str) -> str:
    """Roughly what shows before scrolling: the h1 and the text around it."""
    body = re.search(r"<body\b[^>]*>(.*)", html or "", re.I | re.S)
    text = visible_text(body.group(1) if body else html)
    return text[:600]


def _own_checks(html: str, brief: dict, book: dict) -> list:
    """(part, key, ok, level, message, detail) for what the launch checks don't cover."""
    out = []
    text = visible_text(html)
    low = text.lower()
    top = _first_screen(html).lower()
    h1 = re.search(r"<h1\b[^>]*>(.*?)</h1>", html or "", re.I | re.S)
    h1_text = visible_text(h1.group(1)) if h1 else ""

    offer = (brief.get("offer") or book.get("offer") or "").strip()
    if offer:
        words = _words(offer)
        hit = sum(w in top for w in words) / max(len(words), 1)
        out.append(("offer", "offer_top", hit >= 0.5, "warning", "Your offer shows on the first screen",
                    f"“{offer[:80]}” isn't near the top, so visitors may leave before they see it."))
    if h1_text:
        n = len(h1_text.split())
        out.append(("offer", "h1_length", 3 <= n <= 14, "tip", "The headline is short enough to read at a glance",
                    f"The headline is {n} words. Aim for 3 to 14."))
    cta = (brief.get("cta") or "").strip().lower()
    buttons = re.findall(r"<(?:a|button)\b[^>]*>(.*?)</(?:a|button)>", html or "", re.I | re.S)
    labels = [visible_text(b).lower() for b in buttons]
    if cta:
        out.append(("action", "cta_twice", sum(cta in l for l in labels) >= 2 or low.count(cta) >= 2, "tip",
                    "The main button appears more than once", "Your button shows only once. A second one lower down catches people who scroll."))
    out.append(("action", "cta_top", any(l and l in top for l in labels if len(l) > 2), "warning",
                "There's a button on the first screen", "Visitors have to scroll to find a button."))

    empty = len(re.findall(r"<img\b(?=[^>]*\bsrc\s*=\s*([\"'])\s*\1)[^>]*>|<img\b(?![^>]*\bsrc\s*=)[^>]*>", html or "", re.I))
    out.append(("trust", "broken_images", not empty, "warning", "No broken pictures",
                f"{empty} picture{'s' if empty != 1 else ''} on the page {'have' if empty != 1 else 'has'} nothing in {'them' if empty != 1 else 'it'} and will show as broken."))
    name = (book.get("name") or brief.get("business") or "").strip()
    if name:
        out.append(("brand", "name", name.lower() in low, "warning", "Your business name is on the page",
                    "Your business name doesn't appear on the page."))
    colors = [c.lower() for c in (book.get("colors") or []) if c] if book.get("colors_chosen", True) else []
    page_cols = [c.lower() for c in (brief.get("primary"), brief.get("accent")) if c]
    if colors and page_cols and page_cols[0] not in colors:
        colors = page_cols  # the owner picked other colours for this page: hold it to those
    if colors:
        css = (html or "").lower()
        out.append(("brand", "colors", any(c in css for c in colors[:2]), "warning", "Uses your brand colours",
                    "None of your main brand colours are used."))
    banned = [w for w in (book.get("never_say") or []) if w and re.search(rf"\b{re.escape(w.lower())}\b", low)]
    out.append(("brand", "never_say", not banned, "warning", "Avoids the words you never use",
                "Uses words you asked us never to use: " + ", ".join(f"“{w}”" for w in banned[:4]) + "."))
    for key, label in (("font_heading", "heading"), ("font_body", "body")):
        f = (book.get(key) or "").strip()
        if f:
            out.append(("brand", key, f.lower() in (html or "").lower(), "tip", f"Uses your {label} font",
                        f"The page doesn't use {f} for {label} text."))
    return out


def score(html: str, brief: Optional[dict] = None, book: Optional[dict] = None, checks: Optional[list] = None) -> dict:
    """Marks out of 10 per part, the average, whether it passes, and the open to-dos (worst first)."""
    brief, book = brief or {}, book or {}
    checks = checks if checks is not None else audit_page(html, brief)
    lost = {p: 0 for p in PARTS}
    todo = []
    for c in checks:
        part = CHECK_PART.get(c["key"])
        if part and not c["ok"]:
            lost[part] += COST[c["level"]]
            todo.append({"part": part, "key": c["key"], "level": c["level"], "message": c["message"], "detail": c.get("detail", "")})
    for part, key, ok, level, message, detail in _own_checks(html, brief, book):
        if not ok:
            lost[part] += COST[level]
            todo.append({"part": part, "key": key, "level": level, "message": message, "detail": detail})
    parts = [{"key": p, "label": PARTS[p], "score": max(0, 10 - lost[p])} for p in PARTS]
    avg = round(sum(x["score"] for x in parts) / len(parts), 1)
    low = min(x["score"] for x in parts)
    order = {"blocker": 0, "warning": 1, "tip": 2}
    todo.sort(key=lambda t: (order[t["level"]], t["part"]))
    # Something a visitor could doubt (a number or quote the owner never gave us) fails the page however high the rest is.
    doubt = any(t["part"] == "trust" and t["level"] != "tip" for t in todo)
    # So does breaking a rule the owner set: their chosen colours, or a word they never use.
    doubt = doubt or any(t["key"] in ("colors", "never_say") for t in todo)
    return {"parts": parts, "average": avg, "lowest": low, "passes": avg >= PASS_AVG and low >= PASS_MIN and not doubt, "todo": todo}


def notes_for_writer(result: dict, book: Optional[dict] = None) -> str:
    """What a rewrite must fix, in the words of the checks. Only content problems a writer can solve."""
    keep = [t for t in result["todo"] if t["part"] in ("offer", "action", "trust", "brand") and t["level"] != "tip"]
    def line(t):
        if t["key"] in ("claims", "testimonials"):  # the owner never gave these: the writer must take them out
            return "- Remove these, the owner never gave them (do not replace them with other numbers or quotes): " + (t["detail"] or t["message"])
        if t["key"] == "colors" and book and book.get("colors"):
            c = book["colors"]
            return f"- Use the brand colours: {c[0]} as the main colour (buttons, links, highlights)" + (f" and {c[1]} as the second colour" if len(c) > 1 else "") + ". Replace the other accent colours with these."
        return f"- {t['detail'] or t['message']}"
    lines = [line(t) for t in keep[:8]]
    if book and book.get("never_say"):
        lines.append("- Never use these words: " + ", ".join(book["never_say"]) + ".")
    return "\n".join(lines)


def improve(html: str, brief: dict, book: Optional[dict] = None, fix: Optional[Callable] = None,
            rewrite: Optional[Callable] = None, rounds: int = ROUNDS) -> tuple:
    """Score, fix, score again. Returns (html, score, what changed). `fix(html) -> (html, [notes])` applies the safe
    fixes; `rewrite(html, notes) -> html | None` asks the writer for a better version. Either may be None."""
    book = book or {}
    changed = []
    if fix:  # the safe fixes always run, as they did before scoring existed
        html, notes = fix(html)
        changed += notes
    best = score(html, brief, book)
    for _ in range(max(1, rounds)):
        if best["passes"] or not rewrite:
            break
        notes = notes_for_writer(best, book)
        new = rewrite(html, notes) if notes else None
        if not new:
            break
        if fix:
            new = fix(new)[0]
        s = score(new, brief, book)
        if s["average"] <= best["average"] or _lost_blocker(best, s):
            break
        html, best = new, s
        changed.append("Rewrote parts of the page so it scores better on the checklist")
    return html, best, list(dict.fromkeys(changed))


def _lost_blocker(before: dict, after: dict) -> bool:
    """A rewrite that adds a must-fix problem is never kept, however much else it improves."""
    was = {t["key"] for t in before["todo"] if t["level"] == "blocker"}
    return any(t["level"] == "blocker" and t["key"] not in was for t in after["todo"])
