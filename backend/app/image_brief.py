"""Structured image briefs: turn the user's short sentence into a full description before it reaches the image model.

Image models follow concrete scene details (subject, setting, light, lens) far better than a one-line idea. The AI
writer fills a fixed set of fields as JSON, and we write the prompt from those fields ourselves, so the result is
predictable and always starts with the user's own words. If no writer is available, or it answers with something
we can't use, the user's prompt goes through unchanged.
"""
import json
import re
from typing import Callable, Optional, Tuple

FIELDS = ("subject", "setting", "composition", "lighting", "camera", "colours", "mood")
MAX_FIELD = 220

SYSTEM = ("You write image briefs for a marketing image generator. Answer with one JSON object only, no prose, "
          "with these string fields: " + ", ".join(FIELDS) + ". "
          "Be concrete and visual: materials, surfaces, time of day, light direction, lens and angle. "
          "Keep every fact from the idea. Don't invent brand names, people's names, prices or other numbers. "
          "Never ask for text, letters, words or logos inside the image.")


def _ask(idea: str, hint: str, brand: str, for_ad: bool, product: bool) -> str:
    bits = [f"Idea: {idea.strip()}"]
    if product:
        bits.append("A real product photo will be placed in the centre afterwards, unchanged. Describe only the scene "
                    "around it: the surface it stands on, the background, props and light. In 'subject', write "
                    "'the product' and where it sits; don't describe or change the product itself.")
    if for_ad:
        bits.append("Leave clean empty space in the lower third for a headline that is added later.")
    if hint:
        bits.append(f"Style hint for this industry: {hint}")
    if brand:
        bits.append(f"Brand: {brand}")
    return "\n".join(bits)


def parse(text: Optional[str]) -> Optional[dict]:
    """The fields from the writer's answer, or None if it isn't a usable brief."""
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
    out = {}
    for f in FIELDS:
        v = data.get(f)
        if isinstance(v, str) and v.strip():
            out[f] = re.sub(r"\s+", " ", v).strip().rstrip(".")[:MAX_FIELD]
    return out if len(out) >= 3 else None  # fewer than three fields isn't worth sending


def render(idea: str, brief: dict) -> str:
    """The prompt we send: the user's words first, then the brief in a fixed order."""
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
