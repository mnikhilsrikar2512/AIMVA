"""Image editing: comment-to-edit, object selection, extend to other sizes, background swap and upscale.

Comment-to-edit. The user drops pins on an image ("make this sofa blue", "remove the lamp") and only those places change:
1. Each pin becomes a mask. "area" pins are circles (centre and radius are fractions of the image). "object" pins ask a
   segmentation model (SAM 2 on fal.ai) for the exact outline of whatever was clicked, and fall back to the circle
   if that fails or isn't available.
2. An engine repaints the masked areas following the comments:
   - fal.ai FLUX Fill: true inpainting, one pass per pin so each comment gets its own area.
   - OpenAI-compatible /images/edits (gpt-image-1, DALL-E 2): one pass with all areas masked.
   - Free (no key): FLUX redraws the picture with the same seed and the comments in the prompt. It can't repaint a
     region by itself, so this is labelled "approximate".
3. Only the masked pixels are blended back onto the original. Nothing you didn't comment on changes.
"""
import base64
import io
import os
import random
import re
from dataclasses import dataclass
from typing import Callable, List, Optional
from urllib.parse import quote

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from . import providers as P

# Default fal.ai model for each editing task. Swap any of them without touching code: set EDIT_MODEL_<TASK> in
# backend/.env (e.g. EDIT_MODEL_REMOVE=fal-ai/some-better-eraser). A replacement must accept the same inputs:
#   fill / remove: image_url + mask_url (+ prompt)   instruct: image_url + prompt   segment: image_url + prompts[{x,y,label}]
#   cutout / upscale: image_url                       and return images[0].url or image.url.
FAL_FILL = "fal-ai/flux-pro/v1/fill"
FAL_REMOVE = "fal-ai/bria/eraser"
FAL_INSTRUCT = "fal-ai/flux-pro/kontext"
FAL_SEGMENT = "fal-ai/sam2/image"
FAL_CUTOUT = "fal-ai/birefnet"
FAL_UPSCALE = "fal-ai/clarity-upscaler"
DEFAULT_MODELS = {"fill": FAL_FILL, "remove": FAL_REMOVE, "instruct": FAL_INSTRUCT, "segment": FAL_SEGMENT,
                  "cutout": FAL_CUTOUT, "upscale": FAL_UPSCALE}
TASK_LABELS = {"fill": "Change or add in a spot", "remove": "Remove objects", "instruct": "Whole-image changes",
               "segment": "Select the clicked object", "cutout": "Find the main subject", "upscale": "Upscale"}


def model(task: str) -> str:
    """The model for an editing task: EDIT_MODEL_<TASK> from the environment, else the default above."""
    value = (os.getenv(f"EDIT_MODEL_{task.upper()}") or "").strip()
    return value if value and not value.startswith("#") else DEFAULT_MODELS[task]


def models() -> list:
    return [{"task": t, "label": TASK_LABELS[t], "model": model(t), "default": model(t) == DEFAULT_MODELS[t]} for t in DEFAULT_MODELS]


# A comment that only takes something away goes to the eraser; anything that also puts something there
# (change, add, replace, "remove X and add Y") goes to fill.
REMOVE_WORDS = re.compile(r"\b(remove|delete|erase|get rid of|take (out|away)|eliminate|hide|lose|clear (away|out))\b", re.I)
ADD_WORDS = re.compile(r"\b(add|put|place|replace|swap|instead|insert|with a|with an|turn (it )?into)\b", re.I)


def intent(text: str) -> str:
    text = text or ""
    return "remove" if REMOVE_WORDS.search(text) and not ADD_WORDS.search(text) else "change"
MAX_SIDE = 2048
MAX_UPSCALED_SIDE = 4096


@dataclass
class Pin:
    x: float  # 0..1 from the left
    y: float  # 0..1 from the top
    r: float  # radius as a fraction of the shorter side
    text: str
    mode: str = "area"  # area (circle) | object (select what was clicked)
    action: str = "auto"  # auto (decide from the text) | change | remove

    @property
    def does(self) -> str:
        return self.action if self.action in ("change", "remove") else intent(self.text)


class EditFailed(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message, self.status = message, status


# ---- images and masks -----------------------------------------------------------------------------
def open_rgb(data: bytes, max_side: int = MAX_SIDE) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (OSError, ValueError, Image.DecompressionBombError):
        raise EditFailed("That image couldn't be opened for editing. Try regenerating it.", 400)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    img = img.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side))
    return img


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def data_uri_png(img: Image.Image) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes(img)).decode()


def circle_mask(size, p: Pin) -> Image.Image:
    w, h = size
    m = Image.new("L", size, 0)
    cx, cy, rad = p.x * w, p.y * h, max(4.0, p.r * min(w, h))
    ImageDraw.Draw(m).ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=255)
    return m


def mask_for(size, pins: List[Pin], feather: bool = True) -> Image.Image:
    """Circles only (kept for callers that don't segment). White = may change."""
    m = Image.new("L", size, 0)
    for p in pins:
        m = ImageChops.lighter(m, circle_mask(size, p))
    return soften(m) if feather else m


def soften(mask: Image.Image) -> Image.Image:
    return mask.filter(ImageFilter.GaussianBlur(max(2, min(mask.size) // 120)))


def grow(mask: Image.Image, px: int) -> Image.Image:
    """Dilate a hard mask a little so edits cover the object's edge (halo) too."""
    size = max(3, px * 2 + 1)
    return mask.filter(ImageFilter.MaxFilter(size if size % 2 else size + 1))


def as_mask(data: bytes, size) -> Optional[Image.Image]:
    """Read a mask a model returned: transparency if it has any, otherwise brightness. None if it's unusable."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (OSError, ValueError):
        return None
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        m = img.convert("RGBA").getchannel("A")
    else:
        m = img.convert("L")
    m = m.resize(size, Image.NEAREST).point(lambda v: 255 if v > 127 else 0)
    share = sum(m.histogram()[255:]) / float(size[0] * size[1])
    return m if 0.002 < share < 0.95 else None  # empty or everything: the model didn't find a sensible object


def union(masks: List[Image.Image]) -> Image.Image:
    out = masks[0]
    for m in masks[1:]:
        out = ImageChops.lighter(out, m)
    return out


def blend(original: Image.Image, edited: Image.Image, pins_or_masks) -> Image.Image:
    """Keep the original everywhere except the masked areas. Accepts pins (circles) or ready-made hard masks."""
    if edited.size != original.size:
        edited = edited.resize(original.size, Image.LANCZOS)
    items = list(pins_or_masks)
    hard = union([m if isinstance(m, Image.Image) else circle_mask(original.size, m) for m in items])
    return Image.composite(edited.convert("RGB"), original, soften(hard))


def where(p: Pin) -> str:
    """Plain-language position, so engines without masks (and the prompt log) know where the change goes."""
    v = "top" if p.y < 0.34 else "bottom" if p.y > 0.66 else "middle"
    h = "left" if p.x < 0.34 else "right" if p.x > 0.66 else "centre"
    return "centre" if (v, h) == ("middle", "centre") else f"{v} {h}" if v != "middle" else f"middle {h}"


def edit_prompt(base_prompt: str, pins: List[Pin]) -> str:
    changes = "; ".join(f"in the {where(p)}: {p.text.strip().rstrip('.')}"
                        + (" (take it out completely, show only the background there)" if p.does == "remove" else "") for p in pins)
    return f"{base_prompt.strip().rstrip('.')}. Change only these parts: {changes}. Keep everything else the same."


# ---- fal helpers ----------------------------------------------------------------------------------
def _fal(key: str, model: str, payload: dict) -> dict:
    try:
        return P._request("POST", f"https://fal.run/{model}", "fal.ai", headers={"Authorization": f"Key {key}"},
                          json=payload, timeout=180).json()
    except P.ProviderError as e:
        raise EditFailed(e.message, e.status)


def _first_image_url(data: dict) -> Optional[str]:
    if isinstance(data.get("image"), dict) and data["image"].get("url"):
        return data["image"]["url"]
    imgs = data.get("images") or []
    return imgs[0].get("url") if imgs and isinstance(imgs[0], dict) else None


def _download(url: str) -> bytes:
    try:
        return P.download(url, P.MAX_IMAGE_BYTES * 4, "fal.ai")
    except P.ProviderError as e:
        raise EditFailed(e.message, e.status)


# ---- object selection --------------------------------------------------------------------------------
def fal_segmenter(key: str) -> Callable[[Image.Image, Pin], Optional[Image.Image]]:
    """SAM 2 with one positive click. Returns a hard mask, or None so the caller falls back to the circle."""
    def segment(img: Image.Image, p: Pin) -> Optional[Image.Image]:
        try:
            data = _fal(key, model("segment"), {"image_url": data_uri_png(img), "output_format": "png",
                                            "prompts": [{"x": int(p.x * img.width), "y": int(p.y * img.height), "label": 1}]})
            url = _first_image_url(data)
            return as_mask(_download(url), img.size) if url else None
        except EditFailed:
            return None
    return segment


def resolve_masks(img: Image.Image, pins: List[Pin], segment=None) -> List[dict]:
    """One hard mask per pin. Reports which pins fell back to a circle, so the UI can say so."""
    out = []
    for p in pins:
        m = segment(img, p) if (segment and p.mode == "object") else None
        if m is not None:
            out.append({"mask": grow(m, max(2, min(img.size) // 100)), "selected": True})
        else:
            out.append({"mask": circle_mask(img.size, p), "selected": False})
    return out


# ---- comment-to-edit engines ---------------------------------------------------------------------------
def fal_fill(key: str, img: Image.Image, pins: List[Pin], base_prompt: str, masks: Optional[List[Image.Image]] = None) -> Image.Image:
    """One pass per pin, each on top of the last, so each comment changes only its own area. Removals go to the
    eraser model (it fills with background instead of inventing a new object); changes and additions to fill."""
    masks = masks or [circle_mask(img.size, p) for p in pins]
    cur = img
    for p, m in zip(pins, masks):
        if p.does == "remove":
            out = erase(key, cur, m)
        else:
            out = fill(key, cur, m, f"{p.text.strip()}. Blend in seamlessly: same lighting, perspective, texture and grain "
                                    f"as the rest of the image (photorealistic if it's a photo). Scene: {base_prompt[:300]}")
        cur = blend(cur, out, [m])
    return cur


def erase(key: str, img: Image.Image, mask: Image.Image) -> Image.Image:
    data = _fal(key, model("remove"), {"image_url": data_uri_png(img), "mask_url": data_uri_png(grow(mask, max(3, min(img.size) // 80))),
                                       "mask_type": "manual"})
    url = _first_image_url(data)
    if not url:
        raise EditFailed("fal.ai didn't return an image with the object removed.")
    return open_rgb(_download(url), max_side=max(img.size))


def instruct(key: str, img: Image.Image, instruction: str) -> Image.Image:
    """Whole-image change from a sentence ("make it night", "watercolour style"). No mask: the model decides what moves."""
    data = _fal(key, model("instruct"), {"image_url": data_uri_png(img), "prompt": instruction.strip(), "num_images": 1,
                                         "output_format": "png", "safety_tolerance": "2"})
    url = _first_image_url(data)
    if not url:
        raise EditFailed("fal.ai didn't return an edited image. Try rewording the instruction.")
    out = open_rgb(_download(url), max_side=MAX_SIDE)
    return out.resize(img.size, Image.LANCZOS) if out.size != img.size else out


def fill(key: str, img: Image.Image, mask: Image.Image, prompt: str) -> Image.Image:
    data = _fal(key, model("fill"), {"image_url": data_uri_png(img), "mask_url": data_uri_png(mask), "prompt": prompt,
                                "num_images": 1, "output_format": "png", "safety_tolerance": "2"})
    url = _first_image_url(data)
    if not url:
        raise EditFailed("fal.ai didn't return an edited image. Try rewording the comment.")
    return open_rgb(_download(url), max_side=max(img.size))


def openai_edit(conn: dict, img: Image.Image, pins: List[Pin], base_prompt: str, masks: Optional[List[Image.Image]] = None,
                prompt: Optional[str] = None) -> Image.Image:
    """OpenAI /images/edits: the mask is a PNG whose transparent pixels mark where to paint."""
    hard = union(masks or [circle_mask(img.size, p) for p in pins])
    mask = Image.new("RGBA", img.size, (0, 0, 0, 255))
    mask.putalpha(ImageOps.invert(hard))
    files = {"image": ("image.png", png_bytes(img.convert("RGBA")), "image/png"),
             "mask": ("mask.png", png_bytes(mask), "image/png")}
    data = {"prompt": (prompt or edit_prompt(base_prompt, pins))[:4000], "n": "1"}
    if conn.get("model"):
        data["model"] = conn["model"]
    if (conn.get("model") or "").startswith("dall-e"):
        data["response_format"] = "b64_json"
    try:
        r = P._request("POST", f"{conn['base_url']}/images/edits", conn["name"], headers=P._auth(conn),
                       data=data, files=files, timeout=180).json()
        item = (r.get("data") or [{}])[0]
        if item.get("b64_json"):
            raw = base64.b64decode(item["b64_json"])
        elif item.get("url"):
            raw = P.download(item["url"], P.MAX_IMAGE_BYTES, conn["name"])
        else:
            raise EditFailed(f"{conn['name']} didn't return an edited image.")
    except P.ProviderError as e:
        raise EditFailed(e.message, e.status)
    return blend(img, open_rgb(raw, max_side=max(img.size)), [hard])


def free_url(prompt: str, w: int, h: int, seed: Optional[int], model: str = "flux") -> str:
    s = seed if seed is not None else random.randint(1, 10**9)
    return (f"https://image.pollinations.ai/prompt/{quote(prompt)}?width={w}&height={h}&seed={s}"
            f"&model={model if model in ('flux', 'turbo') else 'flux'}&nologo=true")


def free_redraw(fetch: Callable[[str], bytes], img: Image.Image, pins: List[Pin], base_prompt: str,
                seed: Optional[int], model: str = "flux", masks: Optional[List[Image.Image]] = None) -> Image.Image:
    """No inpainting on the free tier: redraw with the same seed and the comments, then keep only the masked areas."""
    out = open_rgb(fetch(free_url(edit_prompt(base_prompt, pins), img.width, img.height, seed, model)))
    return blend(img, out, masks or pins)


# ---- extend to another size (outpainting) ------------------------------------------------------------------
def extend_canvas(img: Image.Image, ratio: float):
    """Place the image on a bigger canvas with the target ratio. Returns (canvas, hard mask of the new area, box)."""
    w, h = img.size
    if ratio >= w / h:
        H, W = h, round(h * ratio)
    else:
        W, H = w, round(w / ratio)
    scale = min(1.0, MAX_SIDE / max(W, H))
    if scale < 1:
        W, H, img = round(W * scale), round(H * scale), img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        w, h = img.size
    W, H = max(W, w), max(H, h)
    x, y = (W - w) // 2, (H - h) // 2
    canvas = Image.new("RGB", (W, H), (127, 127, 127))
    canvas.paste(img, (x, y))
    keep = Image.new("L", (W, H), 255)
    edge = max(2, min(w, h) // 60)  # let the model blend a few pixels into the original edge, so there's no seam
    ImageDraw.Draw(keep).rectangle([x + edge, y + edge, x + w - edge - 1, y + h - edge - 1], fill=0)
    return canvas, keep, (x, y, w, h)


def finish_extend(canvas: Image.Image, generated: Image.Image, new_area: Image.Image) -> Image.Image:
    """The original stays pixel-for-pixel; only the new edges come from the model."""
    if generated.size != canvas.size:
        generated = generated.resize(canvas.size, Image.LANCZOS)
    return Image.composite(generated.convert("RGB"), canvas, soften(new_area))


EXTEND_PROMPT = "Extend the scene naturally beyond the frame, same lighting, perspective and style, no borders, no text: {}"


# ---- background and upscale --------------------------------------------------------------------------------
def fal_subject_mask(key: str, img: Image.Image) -> Image.Image:
    data = _fal(key, model("cutout"), {"image_url": data_uri_png(img), "output_format": "png"})
    url = _first_image_url(data)
    m = as_mask(_download(url), img.size) if url else None
    if m is None:
        raise EditFailed("Couldn't find a clear main subject to keep. Try comment-to-edit on the background instead.", 422)
    return m


# ---- keep the real product: new scene around the user's own product pixels ---------------------------------
PRODUCT_SCENE_PROMPT = ("{scene}. A real product photo is already placed in the frame: build the surface, background, props, "
                        "a natural contact shadow and soft reflections around it, matching its light and perspective. "
                        "No text, no logos, no second copy of the product.")


def place_product(product: Image.Image, mask: Image.Image, size, scale: float = 0.6, centre_y: float = 0.56):
    """Cut the product out and set it on a canvas of the target size. Returns (canvas, product mask)."""
    mask = mask.convert("L").point(lambda v: 255 if v >= 128 else 0)
    box = mask.getbbox()
    if not box:
        raise EditFailed("Couldn't find the product in that photo. Use a photo where the product is clearly visible.", 422)
    item, cut = product.convert("RGB").crop(box), mask.crop(box)
    W, H = size
    f = min(W * scale / item.width, H * scale / item.height)
    nw, nh = max(1, round(item.width * f)), max(1, round(item.height * f))
    item, cut = item.resize((nw, nh), Image.LANCZOS), cut.resize((nw, nh), Image.LANCZOS)
    x = (W - nw) // 2
    y = max(0, min(H - nh, round(H * centre_y - nh / 2)))
    canvas, pmask = Image.new("RGB", size, (200, 198, 194)), Image.new("L", size, 0)
    canvas.paste(item, (x, y), cut)
    pmask.paste(cut, (x, y))
    return canvas, pmask


def keep_product(canvas: Image.Image, generated: Image.Image, pmask: Image.Image) -> Image.Image:
    """Put the original product pixels back over the model's scene. The edge is pulled in a pixel and feathered,
    so the model's shadow meets the product without a halo, and the product itself is never redrawn."""
    if generated.size != canvas.size:
        generated = generated.resize(canvas.size, Image.LANCZOS)
    keep = pmask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    return Image.composite(canvas, generated.convert("RGB"), keep)


def product_scene(key: str, product: Image.Image, size, scene: str, subject_mask=None, fill_fn=None) -> Image.Image:
    """Find the product, place it, let the fill model paint everything around it, then restore the product."""
    subject_mask, fill_fn = subject_mask or fal_subject_mask, fill_fn or fill
    canvas, pmask = place_product(product, subject_mask(key, product), size)
    repaint = ImageOps.invert(pmask.point(lambda v: 255 if v >= 128 else 0))
    generated = fill_fn(key, canvas, repaint, PRODUCT_SCENE_PROMPT.format(scene=scene.strip().rstrip(".")))
    return keep_product(canvas, generated, pmask)


def basic_upscale(img: Image.Image, factor: int) -> Image.Image:
    w, h = img.size
    f = min(factor, MAX_UPSCALED_SIDE / max(w, h))
    if f <= 1:
        raise EditFailed("This image is already as large as AIMVA keeps.", 400)
    out = img.resize((round(w * f), round(h * f)), Image.LANCZOS)
    return out.filter(ImageFilter.UnsharpMask(radius=1.6, percent=70, threshold=2))


def fal_upscale(key: str, img: Image.Image, factor: int) -> Image.Image:
    if max(img.size) * factor > MAX_UPSCALED_SIDE:
        factor = max(1, MAX_UPSCALED_SIDE // max(img.size))
    if factor < 2:
        raise EditFailed("This image is already as large as AIMVA keeps.", 400)
    data = _fal(key, model("upscale"), {"image_url": data_uri_png(img), "upscale_factor": factor, "prompt": "masterpiece, best quality, highres"})
    url = _first_image_url(data)
    if not url:
        raise EditFailed("fal.ai didn't return an upscaled image.")
    return open_rgb(_download(url), max_side=MAX_UPSCALED_SIDE)
