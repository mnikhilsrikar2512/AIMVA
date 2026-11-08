"""Reading what people type, without an AI model: is a picture comment asking to remove or to change, and what a
new-picture prompt says about its shape and its words.

People write in English, Hinglish, Hindi, Telugu and Tamil, with typos, and often negate ("don't remove the logo,
make it bigger"). The word lists below were written against scripts/prompt_sets/*_dev.tsv and scored on the
held-out *_test.tsv files: run `python scripts/prompt_bench.py`.
"""
import re
from difflib import get_close_matches
from typing import Optional

# ---- picture comments: remove or change -------------------------------------------------------------------
REMOVE_EN = (r"remove|delete|erase|wipe|get rid of|(?:take|get|cut) (?:it |this |that |him |her |them )?(?:out|away|off)|eliminate|hide|"
             r"lose|clear (?:away|out)|clean(?: up)?|without|no more|bin it|(?:don'?t|do not) need|scrub|vanish|"
             r"gone|must go|has to go|should go|take (?:\w+ ){0,3}down|kill|strip|drop|not (?:needed|required|wanted)|no need for")
ADD_EN = (r"add|put|place|replace|swap|instead|insert|with an?\b|turn (?:it |this |the \w+ )?into|make|change|colou?r|paint|"
          r"bigger|smaller|brighter|darker|more|less|fix|smooth|sharpen|should (?:say|read)|reads?\b|says?\b|"
          r"(?:green|bigg|small|bright|dark|light|redd|whit|wid|tall|short|sharp|soft|warm|cool|clear|bold)er\b")
# Hinglish (Latin letters) and the Indian scripts.
REMOVE_IN = (r"hata|hatao|hatado|hata do|nikal|nikalo|nikaal|mita|mitao|saaf kar(?:o| do)|saf kar(?:o| do)|"
             r"हटा|हटाओ|हटाएं|निकाल|मिटा|"
             r"nahi chahiye|nahin chahiye|nai chahiye|zarurat nahi|"
             r"ज़रूरत नहीं|जरूरत नहीं|नहीं चाहिए|"
             r"తీసే|తొలగించ|తీసివే|అవసరం లేదు|వద్దు|"
             r"நீக்க|நீக்கு|அகற்று|வேண்டாம்|தேவையில்லை")
ADD_IN = (r"karo|kar do|banao|bana do|badlo|badal|lagao|rakho|daalo|dalo|"
          r"करो|बनाओ|बनाएं|बदलो|बदल|लगाओ|रखो|डालो|"
          r"మార్చ|చేయండి|చేయి|పెట్ట|పెంచ|"
          r"மாற்று|மாற்ற|வை\b|வைக்க|சேர்")
NO_X = r"^\s*(?:no|without)\b|\b(?:don'?t|do not) want\b|shouldn'?t be (?:here|there)|should not be (?:here|there)|\bnot needed\b"
NEGATED_REMOVE = r"\b(?:don'?t|do not|never|not)\s+(?:remove|delete|erase|touch)\b"

_REMOVE = re.compile(rf"\b(?:{REMOVE_EN})\b|{REMOVE_IN}|{NO_X}", re.I)
_ADD = re.compile(rf"\b(?:{ADD_EN})|\b(?:{ADD_IN})|(?:{ADD_IN})", re.I)
_NEG = re.compile(NEGATED_REMOVE, re.I)
_VOCAB = ["remove", "delete", "erase", "change", "add", "replace", "make", "colour", "color", "bigger", "smaller", "put"]


def _fix_typos(text: str) -> str:
    """"remvoe" -> "remove", "chnage" -> "change", "ad" -> "add", "mkae" -> "make". Only short command words."""
    out = []
    for w in re.findall(r"\S+", text):
        bare = w.lower().strip(".,!?")
        if bare == "ad":
            out.append("add")
        elif bare.isascii() and bare.isalpha() and 3 <= len(bare) <= 7 and bare not in _VOCAB:
            m = get_close_matches(bare, _VOCAB, n=1, cutoff=0.75)
            # Swapped letters always count; other near-misses only for longer words, where they're rarely real words.
            out.append(m[0] if m and (sorted(m[0]) == sorted(bare) or len(bare) >= 5) else w)
        else:
            out.append(w)
    return " ".join(out)


def comment_intent(text: str) -> str:
    """"remove" when the comment only takes something away (goes to the eraser), else "change" (goes to fill)."""
    t = _fix_typos(text or "")
    if _NEG.search(t):  # "don't remove the logo, make it bigger"
        return "change"
    removes = bool(_REMOVE.search(t))
    adds = bool(_ADD.search(re.sub(_REMOVE, " ", t)))
    return "remove" if removes and not adds else "change"


# ---- new-picture prompts: format and words ----------------------------------------------------------------
FORMATS = [  # first match wins, so the specific ones come first
    ("4:5", r"\b4\s*[:x]\s*5\b|portrait (?:feed )?post|feed post portrait"),
    ("9:16", r"\b9\s*[:x]\s*16\b|\bstor(?:y|ies)\b|\breels?\b|\bstatus\b|\bshorts\b|\bvertical\b|\btall\b|1080\s*x\s*1920"),
    ("16:9", r"\b16\s*[:x]\s*9\b|thumbnail|\bbanner\b|\bheader\b|\bcover\b|\bhero\b|\bwide\b|landscape|panoram|1920\s*x\s*1080"),
    ("1:1", r"\b1\s*[:x]\s*1\b|\bsquare\b|\b(?:instagram|insta|ig|facebook|fb)\s+post\b|\bpost\b|1080\s*x\s*1080"),
]
_QUOTES = r"\"([^\"]{1,80})\"|“([^”]{1,80})”|'([^']{1,80})'|‘([^’]{1,80})’"
_LEAD_IN = (r"(?:with (?:the )?(?:text|words?|title|headline)|text|words?|title|headline|saying|that says|says|"
            r"which says|reads|that reads|written|likha(?: ho)?|caption)\s*[:\-]?\s*")
_UNQUOTED = re.compile(rf"(?:add |put )?\b{_LEAD_IN}((?-i:[A-Z₹0-9])[^,.;\n]{{1,60}}?)(?=\s*(?:,|\.|;|$|\bat the\b|\bon (?:the|it)\b|\bwith\b|\btext\b))", re.I)


def read_prompt(prompt: str) -> dict:
    """{"format": "9:16" | "16:9" | "1:1" | "4:5" | None, "words": text meant to be on the picture or None,
    "scene": the prompt to send the image model, with those words taken out}.

    Image models misspell lettering (worse in Indian scripts), so words go on afterwards as real text."""
    p = (prompt or "").strip()
    fmt = next((f for f, pat in FORMATS if re.search(pat, p, re.I)), None)
    if fmt == "16:9" and re.search(r"\bcover\b", p, re.I) and re.search(r"\breels?\b", p, re.I):
        fmt = "9:16"  # a reel cover is vertical
    words, scene = None, p
    if not re.search(r"\b(?:no|without) (?:text|words|lettering)\b", p, re.I):
        m = re.search(_QUOTES, p)
        if m and re.search(r"text|word|say|read|writ|likh|title|headline|caption|poster|banner|board|flyer|story|thumbnail|"
                           r"sign|label|with|लिख|రాయ", p, re.I):
            words = next(g for g in m.groups() if g).strip()
            scene = (p[:m.start()] + p[m.end():])
        else:
            u = _UNQUOTED.search(p)
            if u:
                words = u.group(1).strip()
                scene = p[:u.start()] + p[u.end():]
    if words:
        scene = re.sub(rf"\b{_LEAD_IN}$|\b{_LEAD_IN}(?=[,.;])|\b(?:written|likha ho)\s+on it\b", " ", scene, flags=re.I)
        scene = re.sub(r"\s+(?:at the (?:top|bottom)|on (?:it|the image))\b", " ", scene, flags=re.I)
        scene = re.sub(r"\s*,\s*,", ",", re.sub(r"\s{2,}", " ", scene)).strip(" ,.;:-")
        scene = f"{scene}. No text or lettering in the image" if scene else "No text or lettering in the image"
    return {"format": fmt, "words": words, "scene": scene}


def format_hint(prompt: str, chosen: Optional[str]) -> Optional[str]:
    """The format the prompt asks for, when it differs from the one picked."""
    f = read_prompt(prompt)["format"]
    return f if f and f != chosen else None
