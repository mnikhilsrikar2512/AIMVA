"""Text layers: headlines, prices and buttons typeset by AIMVA on top of an image, never drawn by the image model.

Image models garble lettering, especially prices and Indian scripts. Here the words are real font glyphs, so they're
always spelled right. Each layer is stored with the version it made (params.text_layers) together with the image it
was drawn on (params.text_base), so the user can reopen the text and change it without stacking copies.

Fonts: Inter for Latin text (app/fonts/Inter.ttf) and Noto Sans for Indian scripts (app/fonts/noto/, SIL OFL).
The font is picked per word, so "₹499 ऑफ़र" mixes Inter and Noto Sans Devanagari on one line. Indian scripts need
Pillow's complex text layout (libraqm), which the standard Pillow wheels include.
"""
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont, features

log = logging.getLogger("aimva.text")

FONTS = Path(__file__).parent / "fonts"
LATIN = FONTS / "Inter.ttf"
# Unicode block -> Noto Sans font for that script.
SCRIPTS = [
    ((0x0900, 0x097F), "Devanagari"),  # Hindi, Marathi
    ((0x0980, 0x09FF), "Bengali"),
    ((0x0A00, 0x0A7F), "Gurmukhi"),    # Punjabi
    ((0x0A80, 0x0AFF), "Gujarati"),
    ((0x0B00, 0x0B7F), "Oriya"),       # Odia
    ((0x0B80, 0x0BFF), "Tamil"),
    ((0x0C00, 0x0C7F), "Telugu"),
    ((0x0C80, 0x0CFF), "Kannada"),
    ((0x0D00, 0x0D7F), "Malayalam"),
]
COLOURS = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_LAYERS = 8


def script_of(word: str) -> Optional[str]:
    for ch in word:
        cp = ord(ch)
        for (lo, hi), name in SCRIPTS:
            if lo <= cp <= hi:
                return name
    return None


def needs_complex_layout(text: str) -> bool:
    return any(script_of(w) for w in text.split())


@lru_cache(maxsize=128)
def font(script: Optional[str], size: int, weight: str) -> ImageFont.FreeTypeFont:
    path = FONTS / "noto" / f"NotoSans{script}.ttf" if script else LATIN
    try:
        f = ImageFont.truetype(str(path), size)
    except OSError:
        log.warning("Font missing: %s", path)
        return ImageFont.load_default(size=size)
    try:
        f.set_variation_by_name(weight)
    except (OSError, ValueError):
        pass
    return f


def _hex(c: str, fallback=(255, 255, 255)) -> tuple:
    if not isinstance(c, str) or not COLOURS.match(c):
        return fallback
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _contrast(rgb: tuple) -> tuple:
    """Black or white, whichever reads better on this colour."""
    r, g, b = rgb
    return (20, 20, 20) if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else (255, 255, 255)


def _words(text: str, size: int, weight: str):
    return [(w, font(script_of(w), size, weight)) for w in text.split()]


def _width(draw, words, space: float) -> float:
    return sum(draw.textlength(w, font=f) for w, f in words) + space * max(0, len(words) - 1)


def _lines(draw, text: str, size: int, weight: str, max_w: float) -> list:
    """Wrap by words; each line is a list of (word, font). Typed line breaks are kept."""
    out = []
    space = draw.textlength(" ", font=font(None, size, weight))
    for para in text.splitlines() or [""]:
        cur = []
        for item in _words(para, size, weight):
            trial = cur + [item]
            if cur and _width(draw, trial, space) > max_w:
                out.append(cur)
                cur = [item]
            else:
                cur = trial
        out.append(cur)
    return [line for line in out if line] or [[]]


def render(img: Image.Image, layers: List[dict]) -> Image.Image:
    """Draw each layer on a copy of the image. Positions are fractions of the image (x, y = centre of the block);
    size is the letter height as a fraction of the image width."""
    if any(needs_complex_layout(l.get("text", "")) for l in layers) and not features.check("raqm"):
        log.warning("Pillow has no raqm: Indian-script text will render without proper shaping.")
    base = img.convert("RGBA")
    W, H = base.size
    for layer in layers[:MAX_LAYERS]:
        text = (layer.get("text") or "").strip()
        if not text:
            continue
        size = max(10, int(W * min(0.2, max(0.02, float(layer.get("size", 0.06))))))
        weight = "Bold" if layer.get("weight") == "bold" else "Regular"
        colour = _hex(layer.get("color", "#ffffff"))
        bg = layer.get("bg", "none")
        over = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(over)
        space = draw.textlength(" ", font=font(None, size, weight))
        lines = _lines(draw, text, size, weight, W * 0.88)
        line_h = int(size * 1.25)
        widths = [_width(draw, line, space) for line in lines]
        block_w, block_h = max(widths or [0]), line_h * len(lines)
        cx, cy = float(layer.get("x", 0.5)) * W, float(layer.get("y", 0.5)) * H
        top = max(0, min(H - block_h, cy - block_h / 2))
        pad = int(size * 0.45)
        if bg == "band":  # full-width soft band behind the text
            draw.rectangle((0, top - pad, W, top + block_h + pad), fill=(0, 0, 0, 140))
        elif bg == "pill":  # a button: filled with the colour, text in black or white
            left = max(0, cx - block_w / 2)
            draw.rounded_rectangle((left - pad * 1.4, top - pad * 0.7, left + block_w + pad * 1.4, top + block_h + pad * 0.5),
                                   radius=int((block_h + pad) / 2), fill=colour + (255,))
            colour = _contrast(colour)
        shadow = bg == "none"
        for i, (line, lw) in enumerate(zip(lines, widths)):
            x = max(0, min(W - lw, cx - lw / 2))
            y = top + i * line_h
            for word, f in line:
                if shadow:
                    draw.text((x + max(1, size // 28), y + max(1, size // 28)), word, font=f, fill=(0, 0, 0, 110))
                draw.text((x, y), word, font=f, fill=colour + (255,))
                x += draw.textlength(word, font=f) + space
        base = Image.alpha_composite(base, over)
    return base.convert("RGB")
