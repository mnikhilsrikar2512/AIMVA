"""Ad image briefs: turn the owner's short sentence into an image prompt that sells, before it reaches the model.

Owner rule (2026-11-21): no fixed structure. What matters is what makes an ad work on Instagram, Facebook, WhatsApp
or Google: what is being sold is the hero, the customer can see why they'd want it, one clear focal point that stops
the scroll on a phone. The AI writer answers in free prose, shaped by the idea, and we always put the owner's own
words first. Older writers that still answer with the field set (subject, setting, ...) keep working. If no writer is
available, or it answers with something we can't use, the owner's prompt goes through unchanged.
"""
import json
import re
from typing import Callable, Optional, Tuple

FIELDS = ("subject", "setting", "composition", "lighting", "camera", "colours", "mood")  # older writers' answer shape
MAX_FIELD = 220
MAX_PROSE = 1200
MIN_PROSE = 40  # anything shorter adds nothing to the idea

SYSTEM = ("You write the picture for a small business's ad that will run on Instagram, Facebook, WhatsApp or Google. "
          "Answer with one JSON object only, no prose around it: {\"prompt\": \"...\"}. "
          "The prompt is one natural paragraph for an image model, shaped by the idea, not by a template: "
          "say only what helps this ad sell. What matters most: what is being sold is the hero and instantly "
          "recognisable; show it the way the customer wants it (in use, the result, the moment it's enjoyed); "
          "one clear focal point that stops the scroll on a small phone screen; a look that suits the business "
          "and, when the idea is local, feels real to Indian customers without clichés. Mention light, angle or "
          "colours only where they make the ad stronger. Keep every fact from the idea. Don't invent brand names, "
          "people's names, prices, offers or other numbers. Never ask for text, letters, words or logos inside the "
          "image: those are added afterwards.")


def _ask(idea: str, hint: str, brand: str, for_ad: bool, product: bool) -> str:
    bits = [f"Idea: {idea.strip()}"]
    if product:
        bits.append("A real product photo will be placed in the picture afterwards, unchanged. Describe only the "
                    "scene around it: what it stands on, the background, props and light. Refer to it as 'the "
                    "product'; don't describe or change the product itself.")
    if for_ad:
        bits.append("Keep one calm area of the picture where a short headline can sit later.")
    if hint:
        bits.append(f"What tends to work for this kind of business (use only if it fits): {hint}")
    if brand:
        bits.append(f"Brand: {brand}")
    return "\n".join(bits)


def parse(text: Optional[str]) -> Optional[dict]:
    """The writer's brief, or None if it isn't usable: {"prompt": prose} or the older field set."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    prose = data.get("prompt")
    if isinstance(prose, str):
        prose = re.sub(r"\s+", " ", prose).strip()
        if len(prose) >= MIN_PROSE:
            return {"prompt": prose[:MAX_PROSE]}
    out = {}
    for f in FIELDS:
        v = data.get(f)
        if isinstance(v, str) and v.strip():
            out[f] = re.sub(r"\s+", " ", v).strip().rstrip(".")[:MAX_FIELD]
    return out if len(out) >= 3 else None  # fewer than three fields isn't worth sending


def render(idea: str, brief: dict) -> str:
    """The prompt we send: the owner's words first, then the writer's picture."""
    words = idea.strip().rstrip(".")
    if "prompt" in brief:
        prose = brief["prompt"].strip()
        if prose.lower().startswith(words.lower()):  # the writer already opened with the owner's words
            return prose if prose.endswith(".") else prose + "."
        return f"{words}. {prose}" + ("" if prose.endswith(".") else ".")
    labels = {"subject": "", "setting": "Setting", "composition": "Composition", "lighting": "Lighting",
              "camera": "Camera", "colours": "Colours", "mood": "Mood"}
    parts = [idea.strip().rstrip(".")]
    for f in FIELDS:
        if f in brief:
            parts.append(f"{labels[f]}: {brief[f]}" if labels[f] else brief[f])
    return ". ".join(parts) + "."


def brief_prompt(write: Optional[Callable[..., Optional[str]]], idea: str, hint: str = "", brand: str = "",
                 for_ad: bool = False, product: bool = False, limit: int = 2000) -> Tuple[str, Optional[dict]]:
    """(prompt to send, brief or None). Falls back to the idea itself whenever the writer can't help."""
    if not write:
        return idea, None
    brief = parse(write(_ask(idea, hint, brand, for_ad, product), system=SYSTEM, max_tokens=500))
    if not brief:
        return idea, None
    return render(idea, brief)[:limit], brief
