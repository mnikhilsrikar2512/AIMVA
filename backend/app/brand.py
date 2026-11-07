"""Brand kit helpers: safe image uploads, palette extraction, prompt building, logo compositing."""
import base64
import io
import os
import uuid
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image, ImageDraw, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import BASE_DIR
from .models import BrandAsset, BrandKit

UPLOADS = Path(os.getenv("UPLOADS_DIR") or BASE_DIR / "data" / "uploads")
MAX_BYTES = 5 * 1024 * 1024
FORMATS = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"), "WEBP": ("image/webp", "webp")}
VOICE_HINT = {
    "friendly": "warm, approachable and positive",
    "professional": "clear, credible and polished",
    "bold": "confident, punchy and energetic",
    "playful": "fun, light-hearted and witty",
    "luxury": "elegant, refined and premium",
}
Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs


class BadImage(ValueError):
    pass


def read_image(data: bytes) -> Image.Image:
    """Decode and verify an upload is a real PNG/JPEG/WebP (SVG and others are refused: they can carry scripts)."""
    if len(data) > MAX_BYTES:
        raise BadImage("Images must be 5 MB or smaller.")
    try:
        Image.open(io.BytesIO(data)).verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        raise BadImage("That file isn't a supported image. Use PNG, JPG or WebP.")
    if img.format not in FORMATS:
        raise BadImage("Use a PNG, JPG or WebP image.")
    return img


def save_upload(user_id: int, data: bytes) -> dict:
    img = read_image(data)
    content_type, ext = FORMATS[img.format]
    rel = Path(str(user_id)) / f"{uuid.uuid4().hex}.{ext}"
    dest = UPLOADS / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"path": str(rel), "content_type": content_type, "width": img.width, "height": img.height}


def asset_bytes(asset: BrandAsset) -> bytes:
    return (UPLOADS / asset.path).read_bytes()


def data_uri(asset: BrandAsset) -> str:
    """Providers like fal.ai accept base64 data URIs, so private files never need a public URL."""
    return f"data:{asset.content_type};base64,{base64.b64encode(asset_bytes(asset)).decode()}"


def suggest_palette(data: bytes, n: int = 5) -> list:
    """Dominant colours of a logo, ignoring transparent and near-white/near-black background pixels."""
    img = read_image(data).convert("RGBA")
    img.thumbnail((160, 160))
    pixels = [p[:3] for p in img.getdata() if p[3] > 128]
    keep = [p for p in pixels if 24 < sum(p) / 3 < 236] or pixels
    if not keep:
        return []
    sample = Image.new("RGB", (len(keep), 1))
    sample.putdata(keep)
    quant = sample.quantize(colors=min(n + 3, 8), method=Image.Quantize.MEDIANCUT)
    pal = quant.getpalette()
    counts = sorted(quant.getcolors(), reverse=True)
    out = []
    for _, idx in counts:
        r, g, b = pal[idx * 3: idx * 3 + 3]
        hexc = f"#{r:02x}{g:02x}{b:02x}"
        if all(sum(abs(int(hexc[i:i + 2], 16) - int(o[i:i + 2], 16)) for i in (1, 3, 5)) > 60 for o in out):
            out.append(hexc)
        if len(out) == n:
            break
    return out


def get_kit(db: Session, user_id: int) -> Optional[BrandKit]:
    return db.scalar(select(BrandKit).where(BrandKit.user_id == user_id))


def primary_logo(db: Session, user_id: int) -> Optional[BrandAsset]:
    q = select(BrandAsset).where(BrandAsset.user_id == user_id, BrandAsset.kind == "logo")
    return db.scalar(q.order_by(BrandAsset.is_primary.desc(), BrandAsset.id.desc()))


def brand_prompt(prompt: str, kit: Optional[BrandKit]) -> str:
    """Fold the brand's visual identity into a generation prompt."""
    if not kit:
        return prompt
    bits = [prompt]
    if kit.style:
        bits.append("style: " + ", ".join(kit.style[:6]))
    if kit.colors:
        bits.append("brand colour palette " + ", ".join(kit.colors[:4]))
    if kit.audience:
        bits.append(f"for {kit.audience[:120]}")
    if kit.avoid:
        bits.append(f"avoid: {kit.avoid[:160]}")
    return ", ".join(bits)


def composite_logo(image_bytes: bytes, logo: BrandAsset, position: str = "bottom-right") -> bytes:
    """Place the brand's real logo on a generated image (models can't reproduce logos reliably)."""
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    mark = Image.open(io.BytesIO(asset_bytes(logo))).convert("RGBA")
    target_w = max(48, int(base.width * 0.18))
    mark.thumbnail((target_w, int(base.height * 0.18)), Image.Resampling.LANCZOS)
    pad = max(12, int(base.width * 0.035))
    inner = max(6, int(mark.height * 0.22))  # soft white backing keeps the logo legible on busy photos
    box_w, box_h = mark.width + inner * 2, mark.height + inner * 2
    x = pad if "left" in position else base.width - box_w - pad
    y = pad if "top" in position else base.height - box_h - pad
    backing = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(backing).rounded_rectangle((x, y, x + box_w, y + box_h), radius=int(box_h * 0.3), fill=(255, 255, 255, 225))
    base.alpha_composite(backing)
    base.alpha_composite(mark, (x + inner, y + inner))
    out = io.BytesIO()
    base.convert("RGB").save(out, "JPEG", quality=92)
    return out.getvalue()


def fetch_image(url: str) -> bytes:
    r = httpx.get(url, timeout=120, follow_redirects=True)
    r.raise_for_status()
    if len(r.content) > 20 * 1024 * 1024:
        raise BadImage("Generated image is too large.")
    return r.content


MEDIA_EXT = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}


def save_media(user_id: int, data: bytes, kind: str = "image") -> str:
    """Store generated media privately. Images are verified with Pillow; videos must look like MP4/WebM/MOV."""
    if kind == "image":
        try:
            img = Image.open(io.BytesIO(data))
            img.verify()
            ext = MEDIA_EXT.get(img.format)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
            ext = None
        if not ext:
            raise BadImage("The provider didn't return a valid image.")
    else:
        head = data[:16]
        ext = "mp4" if b"ftyp" in head else "webm" if head.startswith(b"\x1aE\xdf\xa3") else None
        if not ext:
            raise BadImage("The provider didn't return a playable video (MP4/WebM).")
    rel = Path(str(user_id)) / "generated" / f"{uuid.uuid4().hex}.{ext}"
    (UPLOADS / rel).parent.mkdir(parents=True, exist_ok=True)
    (UPLOADS / rel).write_bytes(data)
    return str(rel)


def save_generated(user_id: int, data: bytes) -> str:
    rel = Path(str(user_id)) / "generated" / f"{uuid.uuid4().hex}.jpg"
    (UPLOADS / rel).parent.mkdir(parents=True, exist_ok=True)
    (UPLOADS / rel).write_bytes(data)
    return str(rel)


# ---- ad sets: crops for every placement + real (not AI-drawn) headline and button ----------------
from PIL import ImageFont, ImageOps  # noqa: E402


FONT_FILE = Path(__file__).parent / "fonts" / "Inter.ttf"  # Inter (SIL OFL), variable weight, includes ₹ € £


def _font(size: int, weight: str = "Regular"):
    try:
        f = ImageFont.truetype(str(FONT_FILE), size)
        f.set_variation_by_name(weight)
        return f
    except (OSError, ValueError):
        return ImageFont.load_default(size=size)


def _wrap(draw, text: str, font, max_w: float, stroke: int) -> list:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) + stroke * 2 <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _hex(c: str, fallback=(109, 93, 252)) -> tuple:
    try:
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    except (TypeError, ValueError, IndexError):
        return fallback


def render_ad(image_bytes: bytes, size: tuple, headline: str = "", subline: str = "", cta: str = "",
              position: str = "bottom", accent: str = "#6d5dfc", logo: Optional[BrandAsset] = None) -> bytes:
    """Crop to the placement size, then typeset copy on a soft scrim. Text is rendered by us, so it's always
    spelled right and stays sharp — image models still garble lettering."""
    W, H = size
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = ImageOps.fit(img, (W, H), Image.Resampling.LANCZOS, centering=(0.5, 0.42)).convert("RGBA")
    pad = int(min(W, H) * 0.07)
    if headline or subline or cta:
        draw = ImageDraw.Draw(img)
        max_w = W - pad * 2
        hsize = int(min(W, H) * (0.095 if W >= H else 0.085))
        while True:  # shrink the headline until it fits in 3 lines
            hfont = _font(hsize, "ExtraBold")
            stroke = 0
            hl = _wrap(draw, headline, hfont, max_w, stroke) if headline else []
            if len(hl) <= 3 or hsize <= 18:
                break
            hsize = int(hsize * 0.88)
        sfont = _font(max(14, int(hsize * 0.48)))
        sl = _wrap(draw, subline, sfont, max_w, 0)[:2] if subline else []
        cfont = _font(max(14, int(hsize * 0.42)), "Bold")
        lh, sh = int(hsize * 1.12), int(sfont.size * 1.35)
        btn_h = int(cfont.size * 2.3) if cta else 0
        block = len(hl) * lh + (len(sl) * sh + int(hsize * 0.3) if sl else 0) + (btn_h + int(hsize * 0.45) if cta else 0)
        top = pad if position == "top" else H - pad - block
        # scrim: transparent → dark behind the copy so it reads on any photo
        scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(scrim)
        span = block + pad * 2
        for i in range(span):
            a = int(185 * (i / span) ** 0.9)
            y = (H - span + i) if position != "top" else (span - i)
            sd.line([(0, y), (W, y)], fill=(8, 8, 18, a))
        img.alpha_composite(scrim)
        draw = ImageDraw.Draw(img)
        y = top
        for line in hl:
            draw.text((pad, y), line, font=hfont, fill="white")
            y += lh
        if sl:
            y += int(hsize * 0.3)
            for line in sl:
                draw.text((pad, y), line, font=sfont, fill=(235, 235, 245))
                y += sh
        if cta:
            y += int(hsize * 0.45)
            tw = draw.textlength(cta, font=cfont)
            bw = int(tw + cfont.size * 2.4)
            draw.rounded_rectangle((pad, y, pad + bw, y + btn_h), radius=btn_h // 2, fill=_hex(accent))
            draw.text((pad + bw / 2, y + btn_h / 2), cta, font=cfont, fill="white", anchor="mm")
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=92)
    data = out.getvalue()
    if logo:  # keep the logo clear of the copy
        data = composite_logo(data, logo, "top-right" if position != "top" else "bottom-right")
    return data
