"""Ideas to make one page better: short asks the owner can drop into the editor's change box.

They are written for this business and this page, never a fixed list. The AI writer (when there is one) reads the
page's own words and the business facts and suggests what this page is missing. Without a writer, the rules below pick
ideas for the kind of business and fill in its own offer, area, audience and languages, and skip what the page
already has. Either way the ones that fix a failing check come first, since they raise the page score.

No idea asks for reviews, numbers, awards or prices the owner never gave: the writer would have to invent them.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from .quality import match_playbook, visible_text

MAX = 5
WORDS = 16  # an idea is one short instruction


def _clip(s: str, n: int = 60) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip().strip(".")).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0]


def facts(brief: dict, book: dict) -> dict:
    langs = [l for l in (book.get("languages") or []) if l and l.lower() != "english"]
    return {
        "business": _clip(brief.get("business") or book.get("name") or "", 50),
        # Only the offer's first part: "First week free, morning batch at 6 am" reads badly inside a sentence.
        "offer": _clip(re.split(r"[,;|]| - ", brief.get("offer") or book.get("offer") or "")[0], 50),
        "audience": _clip(brief.get("audience") or book.get("audience") or "", 60),
        "area": _clip(book.get("area") or "", 40),
        "cta": _clip(brief.get("cta") or "", 40),
        "lang": langs[0] if langs else "",
    }


def fix_ideas(todo: list, f: dict) -> list:
    """What this page is missing, said with its own button and offer."""
    cta, offer = f["cta"], f["offer"]
    say = {
        "offer_top": f"Put “{offer}” in the main headline" if offer else "Say the offer in the main headline",
        "h1_length": "Make the main headline shorter, under 10 words",
        "headline": f"Rewrite the headline so it says what {f['business'] or 'we'} offer and for whom",
        "cta": f"Add one clear “{cta}” button" if cta else "Add one clear button that says what happens next",
        "cta_top": f"Put the “{cta}” button on the first screen, next to the headline" if cta else "Put the main button on the first screen",
        "cta_twice": f"Add the “{cta}” button again after the benefits" if cta else "Add the main button again lower down",
        "phone": "Add a tap-to-call button at the top",
        "contact": "Add a tap-to-call button at the top",
        "name": f"Show “{f['business']}” clearly at the top" if f["business"] else "Show the business name clearly at the top",
        "placeholders": "Replace the placeholder text with real details from my brief",
        "claims": "Remove the numbers and claims I never gave you",
        "testimonials": "Remove the customer reviews I never gave you",
        "risky": "Tone down promises that sound too good to be true",
        "small_text": "Make the small text bigger so it reads easily on phones",
    }
    out = []
    for t in todo:
        s = say.get(t.get("key"))
        if s and s not in out:
            out.append(s)
    return out


# (already on the page?, idea). {offer} {area} {audience} {business} are this owner's own words; an idea that needs one
# that's empty is skipped rather than shown half-filled.
BY_KIND = {
    "real_estate": [
        (r"floor ?plan", "Add a floor-plan section for {offer}"),
        (r"getting here|connectivity|nearby|near by", "Add a “Getting here” section: what's close to {area}"),
        (r"home ?loan", "Add a short “Help with your home loan” section"),
        (r"site visit", "Add a “Book a site visit this weekend” strip above the form"),
        (r"possession|faq|questions", "Add answers buyers ask: possession, approvals, parking"),
    ],
    "healthcare": [
        (r"first visit|what to expect", "Add “Your first visit to {business}” in 3 short steps"),
        (r"timings|opening hours|directions", "Add clinic timings and a “Get directions” button for {area}"),
        (r"does it hurt|how long|faq|questions", "Add answers patients ask: does it hurt, how long, what it costs"),
        (r"\bdr\.?\s|doctor", "Add a short line about the doctor, using only the details I gave"),
    ],
    "education": [
        (r"demo class|free class|trial class", "Add a “Free demo class” strip above the form"),
        (r"batch|timings|schedule", "Add a batch timings table for {offer}"),
        (r"week 1|syllabus|curriculum|what you.?ll learn", "Add what a student learns week by week in {offer}"),
        (r"faq|questions|fees", "Add answers parents ask: fees, batch size, study material"),
    ],
    "restaurant": [
        (r"menu|our dishes|bestseller", "Add a menu highlights section with 6 dishes from my brief"),
        (r"wa\.me|whatsapp", "Add an “Order on WhatsApp” button"),
        (r"timings|opening hours|delivery", "Add our timings and the areas we deliver to around {area}"),
        (r"reserve|book a table", "Add a “Book a table” option to the form"),
    ],
    "retail": [
        (r"bestseller|popular|top picks", "Add a bestsellers section using products from my brief"),
        (r"delivery|shipping", "Add how fast we deliver and where, around {area}"),
        (r"return|exchange|refund", "Add a short returns and exchange line"),
        (r"wa\.me|whatsapp", "Add an “Order on WhatsApp” button"),
    ],
    "saas": [
        (r"how it works|step 1|3 steps", "Add a 3-step “how it works” section for {offer}"),
        (r"demo|walkthrough", "Add a “See a 15-minute demo” button next to the form"),
        (r"faq|questions|security", "Add answers buyers ask: setup time, data safety, support"),
    ],
    "services": [
        (r"how it works|step 1|3 steps", "Add a 3-step “how it works” section for {offer}"),
        (r"areas we serve|service area|we cover", "Add the areas we serve around {area}"),
        (r"what.?s included|included", "Add what's included in {offer}, as a short list"),
        (r"faq|questions", "Add answers customers ask before they book"),
    ],
    "fitness": [
        (r"trial|first class|first session", "Add “Your first session at {business}” in 3 short steps"),
        (r"timetable|schedule|batch|timings", "Add a weekly class timetable"),
        (r"trainer|coach", "Add a short line about our trainers, using only the details I gave"),
        (r"bring|what to wear", "Add what to bring to your first session"),
        (r"faq|questions", "Add answers people ask before joining: fees, timings, beginners"),
    ],
    "beauty": [
        (r"services|menu|treatments", "Add a services list with how long each one takes"),
        (r"book|appointment|slot", "Add a “Pick a time” option to the form"),
        (r"hygiene|clean|sanit", "Add a short line on how we keep tools and rooms clean"),
        (r"timings|opening hours|directions", "Add our timings and a “Get directions” button for {area}"),
    ],
    "other": [
        (r"why choose|why us", "Add one short line on why people choose {business}"),
        (r"how it works|step 1|3 steps", "Add a 3-step “how it works” section for {offer}"),
        (r"faq|questions", "Add answers to what customers ask before they enquire"),
        (r"find us|address|directions", "Add where to find us in {area}"),
    ],
}


def rule_ideas(html: str, f: dict, industry: str = "") -> list:
    text = visible_text(html).lower()
    about = f"{industry} {f['business']} {f['offer']}".lower()
    kind = ("fitness" if re.search(r"gym|fitness|yoga|zumba|crossfit|pilates|workout", about) else
            "beauty" if re.search(r"salon|spa\b|beauty|parlou?r|makeup|nail|hair", about) else match_playbook(about))
    out = []
    if f["audience"] and f["audience"].lower()[:20] not in text:
        out.append(f"Speak to {f['audience']} in the line under the headline")
    if f["lang"] and f["lang"].lower() not in text:
        out.append(f"Add a {f['lang']} line under the headline for customers who read {f['lang']}")
    for has, idea in BY_KIND.get(kind, BY_KIND["other"]):
        if re.search(has, text, re.I):
            continue
        need = re.findall(r"\{(\w+)\}", idea)
        if any(not f.get(k) for k in need):
            continue
        out.append(idea.format(**f))
    if not re.search(r"wa\.me|whatsapp", (html or "").lower()) and not any("WhatsApp" in i for i in out):
        out.append("Add a WhatsApp chat button")
    return out


BANNED = re.compile(r"testimonial|review|rating|stars?\b|award|badge|\d[\d,]*\s?(?:\+|%|lakh|crore)|years? of experience|"
                    r"happy \w+|satisfied \w+|certif|guarantee|trusted by|discount|\boff\b|zero[- ]|no[- ]joining|"
                    r"limited[- ](?:time|period|offer)", re.I)


def ai_ideas(write: Callable[..., Optional[str]], html: str, f: dict, fixes: list) -> list:
    """Up to five ideas the writer suggests for this page. [] when it can't give usable ones."""
    page = visible_text(html)[:5000]
    known = {k: v for k, v in f.items() if v}
    prompt = (
        "You are an editor helping a small business owner improve their landing page. Business facts: "
        + json.dumps(known, ensure_ascii=False) + "\n\nThe page's words:\n" + page
        + ("\n\nAlready suggested (don't repeat): " + "; ".join(fixes) if fixes else "")
        + f"\n\nSuggest {MAX} changes that would get this page more enquiries. Each is one instruction the owner could send to "
        "an AI page editor, under " + str(WORDS) + " words, written as the owner (\"Add our…\"), specific to this business "
        "and to what this page is missing. Don't suggest anything the page already has. Never suggest reviews, "
        "testimonials, ratings, awards, statistics, prices or guarantees, and never a new offer, discount, fee or fact "
        "that isn't in the business facts or on the page. Return ONLY a JSON array of strings."
    )
    try:
        out = write(prompt, max_tokens=600) or ""
    except Exception:  # an unavailable writer just means the rules answer
        return []
    m = re.search(r"\[[\s\S]*\]", out)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        return []
    ideas = []
    for i in items if isinstance(items, list) else []:
        if not isinstance(i, str):
            continue
        i = re.sub(r"\s+", " ", i).strip().strip("\"'").rstrip(".")
        if 3 <= len(i.split()) <= WORDS + 4 and not BANNED.search(i) and "<" not in i and i not in ideas:
            ideas.append(i[:140])
    return ideas


def ideas(html: str, brief: dict, book: dict, todo: list, write: Optional[Callable[..., Optional[str]]] = None) -> dict:
    f = facts(brief or {}, book or {})
    fixes = fix_ideas(todo, f)
    more = ai_ideas(write, html, f, fixes) if write else []
    source = "ai" if more else "rules"
    if not more:
        more = rule_ideas(html, f, (brief or {}).get("industry", ""))
    seen, out = set(), []
    for text, raises in [(t, True) for t in fixes] + [(t, False) for t in more]:
        k = text.lower()
        if k not in seen:
            seen.add(k)
            out.append({"text": text, "raises_score": raises})
    return {"ideas": out[:MAX], "source": source}
