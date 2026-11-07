"""Image & video generation.

Images: fal.ai models when a fal key is connected, otherwise the free, keyless Pollinations
(github.com/pollinations/pollinations) FLUX endpoint so the module works out of the box.
Videos: fal.ai queue API (needs a key). The key never reaches the browser.
"""
import logging
import random
import uuid
from typing import List, Literal, Optional
from urllib.parse import quote

import httpx
from PIL import Image
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import discreet
from ..config import settings
from ..db import get_db
from .. import providers as P
from ..brand import BadImage, brand_prompt, composite_logo, data_uri, fetch_image, get_kit, primary_logo, save_generated, save_media
from ..models import Asset, BrandAsset, User
from ..security import current_user, rate_limit
from ..services import integration_secret
from .providers import http_error, resolve, writer

router = APIRouter(prefix="/api/content", tags=["content"])
log = logging.getLogger(__name__)

IMAGE_MODELS = [
    {"id": "pollinations/flux", "label": "FLUX (free, no key)", "provider": "pollinations"},
    {"id": "pollinations/turbo", "label": "Turbo (free, no key)", "provider": "pollinations"},
    {"id": "fal-ai/flux/schnell", "label": "FLUX Schnell", "provider": "fal"},
    {"id": "fal-ai/flux/dev", "label": "FLUX Dev", "provider": "fal"},
    {"id": "fal-ai/flux-pro/v1.1", "label": "FLUX 1.1 Pro", "provider": "fal"},
    {"id": "fal-ai/stable-diffusion-v35-large", "label": "Stable Diffusion 3.5", "provider": "fal"},
]
# audio: whether the model renders sound itself. durations: values each fal endpoint accepts.
VIDEO_MODELS = [
    {"id": "fal-ai/ltx-2/text-to-video", "label": "LTX-2 (with audio, open weights)", "provider": "fal",
     "audio": True, "durations": ["6", "8", "10"], "aspect_ratio": False},
    {"id": "fal-ai/luma-dream-machine/ray-2", "label": "Luma Ray 2", "provider": "fal",
     "audio": False, "durations": ["5s", "9s"], "aspect_ratio": True},
    {"id": "fal-ai/kling-video/v2.1/standard/text-to-video", "label": "Kling 2.1", "provider": "fal",
     "audio": False, "durations": ["5", "10"], "aspect_ratio": True},
    {"id": "fal-ai/ltx-video", "label": "LTX Video (fast, open weights)", "provider": "fal",
     "audio": False, "durations": [], "aspect_ratio": True},
]
VIDEO_BY_ID = {m["id"]: m for m in VIDEO_MODELS}
SOUND_MODEL = "fal-ai/mmaudio-v2"  # open-source video-to-audio: adds matching sound to silent clips
SIZES = {"1:1": (1024, 1024), "4:5": (896, 1120), "9:16": (768, 1344), "16:9": (1344, 768), "1.91:1": (1200, 628)}


def _fal_key(db: Session, user: User) -> str:
    """The platform's studio key (app/ai_registry.py); a user's own key only when ALLOW_USER_AI_KEYS is on."""
    from .. import ai_registry
    own = integration_secret(db, user.id, "fal").get("api_key") if ai_registry.user_keys_allowed() else ""
    return own or ai_registry.key_for("image", "fal") or ai_registry.key_for("video", "fal") or ai_registry.key_for("image_edit", "fal")


def _fal_failed(r: httpx.Response) -> HTTPException:
    """Turn fal.ai failures into messages a user can act on."""
    if r.status_code in (401, 403):
        try:
            detail = str(r.json().get("detail", ""))
        except ValueError:
            detail = r.text
        if "balance" in detail.lower() or "locked" in detail.lower():
            return HTTPException(402, "Your fal.ai account is out of credit. Add credit at fal.ai/dashboard/billing.")
        return HTTPException(400, "fal.ai rejected your API key. Reconnect it in Settings → Integrations → fal.ai.")
    if r.status_code == 422:
        return HTTPException(400, f"fal.ai couldn't use these settings: {r.text[:200]}")
    return HTTPException(502, f"fal.ai error ({r.status_code}): {r.text[:200]}")


def _public_label(label: str, kind: str) -> str:
    """What a customer sees as the engine name: neutral, never a supplier or model name."""
    if not label:
        return label
    if discreet.is_builtin_model(label):
        return discreet.model_label(label)
    known = {m["label"]: m["id"] for m in IMAGE_MODELS + VIDEO_MODELS}
    if label in known:
        return discreet.model_label(known[label])
    if discreet.leaks(label) or label.startswith("Free "):
        return "AIMVA video" if kind == "video" else "AIMVA images"
    return label


def asset_out(a: Asset) -> dict:
    params = {k: v for k, v in (a.params or {}).items() if not k.endswith("_url") and k not in ("job", "endpoint", "model_id")}
    if "provider" in params:
        params["provider"] = discreet.out_ref(params["provider"])
    if "provider_label" in params:
        params["provider_label"] = _public_label(params["provider_label"], a.kind)
    if isinstance(params.get("model"), str):
        params["model"] = discreet.out_model(params["model"])
    return {"id": a.id, "kind": a.kind, "prompt": a.prompt, "model": _public_label(a.model, a.kind), "url": a.url,
            "status": a.status, "params": params, "created_at": a.created_at.isoformat()}


@router.get("/models")
def models(user: User = Depends(current_user), db: Session = Depends(get_db)):
    studio = bool(_fal_key(db, user))
    public = lambda ms: [{**{k: v for k, v in m.items() if k != "provider"}, "id": discreet.out_model(m["id"]),
                          "label": discreet.model_label(m["id"], m["label"]), "free": m["provider"] == "pollinations",
                          "available": m["provider"] != "fal" or studio} for m in ms]
    return {"image": public(IMAGE_MODELS), "video": public(VIDEO_MODELS), "sizes": list(SIZES), "studio_available": studio}


LogoPosition = Literal["bottom-right", "bottom-left", "top-right", "top-left"]
STYLE_PRESETS = {
    "photographic": "professional photography, natural lighting, sharp focus, high detail",
    "cinematic": "cinematic still, dramatic lighting, shallow depth of field, film grain",
    "illustration": "clean digital illustration, vibrant colours",
    "3d_render": "3D render, soft studio lighting, octane render",
    "flat": "flat vector design, simple shapes, solid colours",
    "minimal_product": "minimal product photography, seamless background, soft shadows",
    "watercolor": "watercolour painting, soft textured paper",
    "anime": "anime style, crisp line art, vivid colours",
    "neon": "neon glow, dark background, futuristic",
}
Style = Literal["photographic", "cinematic", "illustration", "3d_render", "flat", "minimal_product", "watercolor", "anime", "neon"]


class ImageIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    provider: str = Field("", max_length=40)  # builtin:pollinations | builtin:fal | conn:<id>; empty = infer from model
    model: str = Field("pollinations/flux", max_length=200)
    size: str = "1:1"
    width: Optional[int] = Field(None, ge=256, le=2048)  # custom size overrides `size`
    height: Optional[int] = Field(None, ge=256, le=2048)
    count: int = Field(1, ge=1, le=4)
    negative_prompt: str = Field("", max_length=1000)
    seed: Optional[int] = Field(None, ge=0, le=2**31 - 1)
    style: Optional[Style] = None
    reference: str = Field("", max_length=40)  # "brand:<id>", "asset:<id>" or "ref:<id>": image to guide the result
    use_brand: bool = False  # fold the saved Brand Kit (style, colours, audience, avoid) into the prompt
    add_logo: bool = False  # composite the primary brand logo onto each result
    logo_position: LogoPosition = "bottom-right"
    keep_product: bool = False  # the reference is a product photo: build a new scene around its real pixels
    smart_prompt: bool = True  # expand the idea into a structured brief (subject, setting, light, camera...) first

    _inbound = field_validator("provider", mode="before")(lambda v: discreet.in_ref(v) if isinstance(v, str) else v)
    _inbound_model = field_validator("model", mode="before")(lambda v: discreet.in_model(v) if isinstance(v, str) else v)


def _styled(prompt: str, style: Optional[str], negative: str = "", inline_negative: bool = False) -> str:
    out = prompt
    if style:
        out += f", {STYLE_PRESETS[style]}"
    if negative and inline_negative:
        out += f". Avoid: {negative}"
    return out


def _reference(db: Session, user: User, ref: str) -> Optional[str]:
    """A data URI (private files) or URL for an image the user owns, to guide generation."""
    if not ref:
        return None
    kind, _, raw = ref.partition(":")
    if not raw.isdigit():
        raise HTTPException(400, "Unknown reference image.")
    if kind == "brand":
        a = db.get(BrandAsset, int(raw))
        if not a or a.user_id != user.id:
            raise HTTPException(404, "Reference image not found.")
        return data_uri(a)
    if kind == "ref":
        from ..models import ReferenceFile
        from ..brand import UPLOADS
        import base64
        r = db.get(ReferenceFile, int(raw))
        if not r or r.user_id != user.id:
            raise HTTPException(404, "Reference file not found.")
        if r.kind != "image":
            raise HTTPException(400, "That reference is a document. Pick an image to guide visuals.")
        return f"data:{r.content_type};base64,{base64.b64encode((UPLOADS / r.path).read_bytes()).decode()}"
    if kind == "asset":
        a = db.get(Asset, int(raw))
        if not a or a.user_id != user.id or a.kind != "image" or not a.url:
            raise HTTPException(404, "Reference image not found.")
        if a.url.startswith("/api/files/"):
            from ..brand import UPLOADS
            import base64
            f = UPLOADS / a.url[len("/api/files/"):]
            mime = "image/png" if f.suffix == ".png" else "image/webp" if f.suffix == ".webp" else "image/jpeg"
            return f"data:{mime};base64,{base64.b64encode(f.read_bytes()).decode()}"
        return a.url
    raise HTTPException(400, "Unknown reference image.")


def _pollinations(url: str) -> bytes:
    """Fetch the free image once, now, and keep our own copy. Linking to it instead re-renders on every view,
    burns the shared free quota and can show Pollinations' "limit reached" picture in place of the result."""
    headers = {"Accept": "image/*"}
    if settings.pollinations_token:
        headers["Authorization"] = f"Bearer {settings.pollinations_token}"
    try:
        r = httpx.get(url, timeout=150, follow_redirects=True, headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(504, "The free image service took too long. Try again, or connect fal.ai in Settings for faster images.")
    except httpx.HTTPError:
        raise HTTPException(502, "Couldn't reach the free image service. Try again in a moment.")
    if r.status_code in (402, 429):
        wait = r.headers.get("retry-after", "")
        raise HTTPException(429, "The free image engine is busy (it makes about one image every 45 seconds). "
                                 f"Try again {'in ' + wait + ' seconds' if wait.isdigit() else 'in a minute'}, or use Studio images.")
    if r.status_code >= 400 or not r.headers.get("content-type", "").startswith("image/"):
        log.warning("Pollinations returned %s %s: %s", r.status_code, r.headers.get("content-type"), r.text[:200] if "image" not in r.headers.get("content-type", "") else "")
        if r.status_code >= 500:
            raise HTTPException(503, "The free image service is having trouble right now. Try again in a minute, or pick another provider.")
        raise HTTPException(502, "The free image service didn't return an image. Try again or pick another provider.")
    if len(r.content) > P.MAX_IMAGE_BYTES:
        raise HTTPException(502, "The generated image is too large to keep.")
    return r.content


def _image_prompt(db: Session, user: User, body: "ImageIn", kit, product: bool = False):
    """(prompt, brief): the user's idea expanded into a structured brief when an AI writer is available."""
    from .. import image_brief
    if not body.smart_prompt:
        return brand_prompt(body.prompt, kit), None
    from ..quality import PLAYBOOKS, match_playbook
    hint = PLAYBOOKS[match_playbook(fallback=user.industry)]["image_hint"]
    brand = brand_prompt("", kit).strip(", ") if kit else ""
    prompt, brief = image_brief.brief_prompt(writer(db, user.id, agent="prompt_artist"), body.prompt, hint, brand, product=product)
    return (prompt if brief else brand_prompt(body.prompt, kit)), brief


def _reference_bytes(ref: str) -> bytes:
    import base64
    if ref.startswith("data:"):
        return base64.b64decode(ref.split(",", 1)[1])
    try:
        return fetch_image(ref)
    except (httpx.HTTPError, BadImage):
        raise HTTPException(502, "Couldn't load that product photo. Try uploading it again.")


def _product_images(db: Session, user: User, body: "ImageIn", reference: Optional[str], kit, w: int, h: int):
    """New scenes around the user's real product: cut it out, paint the scene, put the original pixels back."""
    from .. import image_edit as IE
    if not reference:
        raise HTTPException(400, "Pick your product photo as the reference image first, then turn on “Keep my product exactly”.")
    key = _fal_key(db, user)
    if not key:
        raise HTTPException(400, "Keeping your product exactly needs Studio images, which aren't switched on yet.")
    prompt, brief = _image_prompt(db, user, body, kit, product=True)
    try:
        product = IE.open_rgb(_reference_bytes(reference))
        out = [("bytes", IE.png_bytes(IE.product_scene(key, product, (w, h), _styled(prompt, body.style))))
               for _ in range(body.count)]
    except IE.EditFailed as e:
        raise HTTPException(e.status, e.message)
    return out, prompt, brief


def _snap(v: int) -> int:
    return max(256, min(2048, int(round(v / 16) * 16)))  # most models want multiples of 16


@router.post("/image")
def generate_image(body: ImageIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(f"img:{user.id}", 30, 300)
    w, h = (_snap(body.width), _snap(body.height)) if body.width and body.height else SIZES.get(body.size, SIZES["1:1"])
    kit = get_kit(db, user.id) if body.use_brand else None
    logo = primary_logo(db, user.id) if body.add_logo else None
    if body.add_logo and not logo:
        raise HTTPException(400, "Upload a logo in Brand Kit first, or turn off “Add my logo”.")
    ref = body.provider or ("builtin:pollinations" if body.model.startswith("pollinations/") else "builtin:fal")
    reference = _reference(db, user, body.reference)
    results = []  # ("url", str) | ("bytes", bytes)
    seed = body.seed
    brief, sent = None, None
    if body.keep_product:
        results, sent, brief = _product_images(db, user, body, reference, kit, w, h)
        model_label = "product-keep"
    elif ref == "builtin:pollinations":
        variant = body.model.split("/", 1)[1] if body.model.startswith("pollinations/") else (body.model or "flux")
        if variant not in ("flux", "turbo"):
            raise HTTPException(400, "The free provider supports the “flux” and “turbo” models.")
        base, brief = _image_prompt(db, user, body, kit)
        prompt = _styled(base, body.style, body.negative_prompt, inline_negative=True)
        sent = prompt
        seed = body.seed if body.seed is not None else random.randint(1, 10**9)
        results.append(("bytes", _pollinations(f"https://image.pollinations.ai/prompt/{quote(prompt)}?width={w}&height={h}"
                                               f"&seed={seed}&model={variant}&nologo=true")))  # free tier: one at a time
        model_label = f"pollinations/{variant}"
    else:
        conn = resolve(db, user, ref, "image", "" if body.model.startswith("pollinations/") else body.model)
        base, brief = _image_prompt(db, user, body, kit)
        prompt = sent = _styled(base, body.style)
        aspect = next((k for k, v in SIZES.items() if v == (w, h)), body.size if body.size in SIZES else "1:1")
        opts = {"prompt": prompt, "negative_prompt": body.negative_prompt, "width": w, "height": h, "count": body.count,
                "seed": body.seed, "aspect_ratio": aspect, "image_data_uri": reference}
        try:
            results = P.generate_images(conn, opts)
        except P.ProviderError as e:
            raise http_error(e)
        except (KeyError, IndexError, TypeError, ValueError):
            raise HTTPException(502, f"{conn['name']} answered in an unexpected format. Check the model supports images.")
        if not results:
            raise HTTPException(502, f"{conn['name']} didn't return any images. Try a different prompt or model.")
        model_label = conn["model"]
        if conn["adapter"] in ("replicate", "openai_images"):  # their links expire: keep our own copy
            try:
                results = [r if r[0] == "bytes" else ("bytes", P.download(r[1], P.MAX_IMAGE_BYTES, conn["name"])) for r in results]
            except P.ProviderError as e:
                raise http_error(e)
    urls = []
    try:
        for kind, val in results:
            if logo:  # render the real logo onto each image and keep the branded copy privately
                data = val if kind == "bytes" else fetch_image(val)
                urls.append("/api/files/" + save_generated(user.id, composite_logo(data, logo, body.logo_position)))
            elif kind == "bytes":
                urls.append("/api/files/" + save_media(user.id, val, "image"))
            else:
                urls.append(val)
    except BadImage as e:
        raise HTTPException(502, str(e))
    except P.ProviderError as e:
        raise http_error(e)
    assets = []
    batch = uuid.uuid4().hex[:12]
    for u in urls:
        a = Asset(user_id=user.id, kind="image", prompt=body.prompt, model=model_label, url=u,
                  params={"size": body.size if not body.width else f"{w}x{h}", "width": w, "height": h, "brand": bool(kit),
                          "logo": bool(logo), "provider": ref, "style": body.style, "seed": seed,
                          "negative_prompt": body.negative_prompt, "reference": bool(reference), "batch": batch,
                          "kept_product": body.keep_product, "brief": brief, "prompt_sent": sent,
                          "provider_label": "Your product, new scene" if body.keep_product
                          else "Free FLUX" if ref == "builtin:pollinations" else model_label})
        db.add(a)
        assets.append(a)
    db.commit()
    return [asset_out(a) for a in assets]


CAMERA_PRESETS = {
    "static": "locked-off static camera", "push_in": "slow push-in camera move", "pull_out": "slow pull-out reveal",
    "pan_left": "smooth pan left", "pan_right": "smooth pan right", "orbit": "slow orbit around the subject",
    "drone": "aerial drone flyover", "handheld": "subtle handheld camera", "tilt_up": "slow tilt up",
}
Camera = Literal["static", "push_in", "pull_out", "pan_left", "pan_right", "orbit", "drone", "handheld", "tilt_up"]


class VideoIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    provider: str = Field("", max_length=40)  # builtin:fal | conn:<id>
    model: str = Field("", max_length=200)  # empty: LTX-2 on fal, or the provider's saved model
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"] = "16:9"
    duration: str = Field("5s", max_length=6)
    resolution: Optional[Literal["480p", "540p", "720p", "1080p", "1440p", "2160p"]] = None
    negative_prompt: str = Field("", max_length=1000)
    seed: Optional[int] = Field(None, ge=0, le=2**31 - 1)
    camera: Optional[Camera] = None

    _inbound = field_validator("provider", mode="before")(lambda v: discreet.in_ref(v) if isinstance(v, str) else v)
    _inbound_model = field_validator("model", mode="before")(lambda v: discreet.in_model(v) if isinstance(v, str) else v)
    style: Optional[Style] = None
    generate_audio: Optional[bool] = None  # for custom models that support it
    use_brand: bool = False
    start_image_id: Optional[int] = None  # a Brand Kit image to animate (image-to-video)
    start_asset_id: Optional[int] = None  # or one of your generated images
    start_ref: str = Field("", max_length=40)  # or any library/uploaded image: "brand:<id>" | "asset:<id>" | "ref:<id>"
    add_sound: bool = True  # silent models only: add matching audio with MMAudio once the clip is ready
    sound_prompt: str = Field("", max_length=500)


# Image-to-video endpoints for each text-to-video model, used when starting from a brand image.
IMAGE_TO_VIDEO = {
    "fal-ai/luma-dream-machine/ray-2": "fal-ai/luma-dream-machine/ray-2/image-to-video",
    "fal-ai/kling-video/v2.1/standard/text-to-video": "fal-ai/kling-video/v2.1/standard/image-to-video",
    "fal-ai/ltx-video": "fal-ai/ltx-video/image-to-video",
    "fal-ai/ltx-2/text-to-video": "fal-ai/ltx-2/image-to-video",
}


def _seconds(duration: str) -> float:
    try:
        return float(str(duration).rstrip("s"))
    except ValueError:
        return 6.0


def _fal_queue(key: str, model: str, payload: dict) -> dict:
    r = httpx.post(f"https://queue.fal.run/{model}", headers={"Authorization": f"Key {key}"}, timeout=60, json=payload)
    if r.status_code >= 400:
        raise _fal_failed(r)
    return r.json()


def _start_sound(a: Asset, key: str, prompt: str) -> None:
    """Queue MMAudio on a finished silent clip; the asset stays 'queued' until audio is ready."""
    q = _fal_queue(key, SOUND_MODEL, {
        "video_url": a.url, "duration": _seconds(a.params.get("duration") or "6"),
        "prompt": prompt or f"natural ambient sound and soft background music that fits: {a.prompt[:300]}",
        "negative_prompt": "distorted speech, noise, clipping",
    })
    a.params = {**a.params, "stage": "audio", "silent_url": a.url,
                "audio_status_url": q.get("status_url"), "audio_response_url": q.get("response_url")}
    a.status = "queued"



def _video_prompt(db: Session, user: User, body: VideoIn) -> str:
    prompt = brand_prompt(body.prompt, get_kit(db, user.id) if body.use_brand else None)
    prompt = _styled(prompt, body.style)
    if body.camera:
        prompt += f", {CAMERA_PRESETS[body.camera]}"
    return prompt


def _start_image(db: Session, user: User, body: VideoIn) -> Optional[str]:
    if sum(bool(x) for x in (body.start_image_id, body.start_asset_id, body.start_ref)) > 1:
        raise HTTPException(400, "Pick one start image.")
    if body.start_ref:
        return _reference(db, user, body.start_ref)
    if body.start_image_id:
        img = db.get(BrandAsset, body.start_image_id)
        if not img or img.user_id != user.id:
            raise HTTPException(404, "Brand image not found.")
        return data_uri(img)
    if body.start_asset_id:
        return _reference(db, user, f"asset:{body.start_asset_id}")
    return None


@router.post("/video")
def generate_video(body: VideoIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(f"vid:{user.id}", 10, 600)
    ref = body.provider or "builtin:fal"
    if ref == "builtin:fal" and not body.model:
        body.model = VIDEO_MODELS[0]["id"]
    prompt = _video_prompt(db, user, body)
    start = _start_image(db, user, body)
    spec = VIDEO_BY_ID.get(body.model) if ref == "builtin:fal" else None

    if spec:  # known fal model: tuned payload (durations, audio, image-to-video endpoint)
        key = _fal_key(db, user)
        if not key:
            raise HTTPException(400, "Video generation needs a fal.ai key. Connect it in Settings → Integrations.")
        duration = body.duration if body.duration in spec["durations"] else (spec["durations"][0] if spec["durations"] else "")
        payload = {"prompt": prompt}
        if spec["durations"]:
            payload["duration"] = duration
        if spec["aspect_ratio"]:
            payload["aspect_ratio"] = body.aspect_ratio
        if spec["audio"]:
            res = body.resolution if body.resolution in ("1080p", "1440p", "2160p") else "1080p"
            payload.update({"generate_audio": True, "resolution": res})
        if body.negative_prompt:
            payload["negative_prompt"] = body.negative_prompt
        if body.seed is not None:
            payload["seed"] = body.seed
        model = body.model
        if start:
            if model not in IMAGE_TO_VIDEO:
                raise HTTPException(400, "This model can't start from an image.")
            model, payload["image_url"] = IMAGE_TO_VIDEO[model], start
        q = _fal_queue(key, model, payload)
        a = Asset(user_id=user.id, kind="video", prompt=body.prompt, model=model, status="queued",
                  params={"aspect_ratio": body.aspect_ratio if spec["aspect_ratio"] else "", "duration": duration or "5",
                          "brand": body.use_brand, "start_image": bool(start), "stage": "video", "provider": ref,
                          "has_audio": spec["audio"], "add_sound": body.add_sound and not spec["audio"],
                          "sound_prompt": body.sound_prompt.strip(), "camera": body.camera, "style": body.style,
                          "status_url": q.get("status_url"), "response_url": q.get("response_url")})
    else:  # any model on fal, Replicate or a self-hosted ComfyUI
        conn = resolve(db, user, ref, "video", body.model)
        opts = {"prompt": prompt, "negative_prompt": body.negative_prompt, "seed": body.seed, "aspect_ratio": body.aspect_ratio,
                "duration": body.duration, "resolution": body.resolution, "image_data_uri": start,
                "generate_audio": body.generate_audio}
        try:
            job = P.start_video(conn, opts)
        except P.ProviderError as e:
            raise http_error(e)
        except (KeyError, TypeError, ValueError):
            raise HTTPException(502, f"{conn['name']} answered in an unexpected format. Check the model makes videos.")
        has_fal = bool(_fal_key(db, user))
        a = Asset(user_id=user.id, kind="video", prompt=body.prompt, model=conn["model"] or conn["name"], status="queued",
                  params={"aspect_ratio": body.aspect_ratio, "duration": body.duration, "brand": body.use_brand,
                          "start_image": bool(start), "stage": "video", "provider": ref, "job": job,
                          "has_audio": bool(body.generate_audio),
                          "add_sound": body.add_sound and not body.generate_audio and has_fal,
                          "sound_prompt": body.sound_prompt.strip(), "camera": body.camera, "style": body.style})
    db.add(a)
    db.commit()
    return asset_out(a)


def _finish_video(db: Session, user: User, a: Asset) -> None:
    """Poll a provider-agnostic job (custom fal model, Replicate, ComfyUI)."""
    try:
        conn = resolve(db, user, a.params["provider"], "video", a.model if a.params["job"].get("adapter") != "comfyui" else "")
        r = P.poll_video(conn, a.params["job"])
    except HTTPException as e:
        a.status, a.params = "failed", {**a.params, "error": e.detail}
        return
    except P.ProviderError as e:
        if e.status in (400, 401, 403, 404):  # won't fix itself by waiting
            a.status, a.params = "failed", {**a.params, "error": e.message}
        return
    if r["state"] == "running":
        return
    if r["state"] == "failed":
        a.status, a.params = "failed", {**a.params, "error": r.get("error", "The provider couldn't finish.")}
        return
    try:
        if r.get("bytes"):
            a.url = "/api/files/" + save_media(user.id, r["bytes"], "video")
        elif a.params["job"]["adapter"] == "replicate":  # expiring links: keep a copy
            a.url = "/api/files/" + save_media(user.id, P.download(r["url"], P.MAX_VIDEO_BYTES, "Replicate"), "video")
        else:
            a.url = r["url"]
    except (BadImage, P.ProviderError) as e:
        a.status, a.params = "failed", {**a.params, "error": getattr(e, "message", str(e))}
        return
    a.status = "done"
    if a.params.get("add_sound") and a.url.startswith("http"):
        try:
            _start_sound(a, _fal_key(db, user), a.params.get("sound_prompt", ""))
        except HTTPException:
            a.params = {**a.params, "audio_error": True}


@router.get("/video/{asset_id}")
def video_status(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Asset, asset_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Not found.")
    if a.status != "queued":
        return asset_out(a)
    if a.params.get("job") and a.params.get("stage") == "video":
        _finish_video(db, user, a)
        db.commit()
        return asset_out(a)
    key = _fal_key(db, user)
    headers = {"Authorization": f"Key {key}"}
    audio_stage = a.params.get("stage") == "audio"
    status_url = a.params["audio_status_url" if audio_stage else "status_url"]
    s = httpx.get(status_url, headers=headers, timeout=30).json()
    if s.get("status") == "COMPLETED":
        res = httpx.get(a.params["audio_response_url" if audio_stage else "response_url"], headers=headers, timeout=30).json()
        url = (res.get("video") or {}).get("url", "")
        if audio_stage:
            # Keep the silent clip if sound generation produced nothing.
            a.url = url or a.params.get("silent_url", a.url)
            a.params = {**a.params, "stage": "done", "has_audio": bool(url), **({} if url else {"audio_error": True})}
            a.status = "done"
        elif not url:
            a.status = "failed"
        else:
            a.url, a.status = url, "done"
            if a.params.get("add_sound") and not a.params.get("has_audio"):
                try:
                    _start_sound(a, key, a.params.get("sound_prompt", ""))
                except HTTPException:
                    a.params = {**a.params, "audio_error": True}
        db.commit()
    elif s.get("status") in ("FAILED", "ERROR"):
        if audio_stage:  # video is fine, only the sound failed
            a.url, a.status = a.params.get("silent_url", a.url), "done"
            a.params = {**a.params, "stage": "done", "audio_error": True}
        else:
            a.status = "failed"
        db.commit()
    return asset_out(a)


class SoundIn(BaseModel):
    prompt: str = Field("", max_length=500)


@router.post("/video/{asset_id}/sound")
def add_sound(asset_id: int, body: SoundIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Add matching audio (MMAudio) to an existing silent video."""
    a = db.get(Asset, asset_id)
    if not a or a.user_id != user.id or a.kind != "video":
        raise HTTPException(404, "Not found.")
    if a.status != "done" or not a.url:
        raise HTTPException(400, "Wait for the video to finish first.")
    if a.params.get("has_audio"):
        raise HTTPException(400, "This video already has sound.")
    key = _fal_key(db, user)
    if not key:
        raise HTTPException(400, "Connect fal.ai in Settings → Integrations first.")
    if not a.url.startswith("http"):
        raise HTTPException(400, "Sound can only be added to videos hosted by the provider, not self-hosted ones.")
    _start_sound(a, key, body.prompt.strip())
    db.commit()
    return asset_out(a)


@router.get("/assets")
def list_assets(kind: Optional[str] = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Asset).where(Asset.user_id == user.id).order_by(Asset.created_at.desc()).limit(100)
    if kind:
        q = q.where(Asset.kind == kind)
    return [asset_out(a) for a in db.scalars(q)]


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Asset, asset_id)
    if a and a.user_id == user.id:
        db.delete(a)
        db.commit()
    return {"ok": True}


class CopyIn(BaseModel):
    product: str = Field(min_length=2, max_length=500)
    audience: str = ""
    platform: str = "meta"
    tone: str = "confident"


@router.post("/ad-copy")
def ad_copy(body: CopyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Headline/primary text variants for ads, in the Brand Kit's voice. Gemini when configured, templates otherwise."""
    from ..brand import VOICE_HINT
    kit = get_kit(db, user.id)
    tone = VOICE_HINT.get(kit.voice, body.tone) if kit else body.tone
    if kit and kit.voice_notes:
        tone += f" ({kit.voice_notes[:200]})"
    audience = body.audience or (kit.audience if kit else "")
    write = writer(db, user.id, agent="copywriter")
    text = write and write(f"Write 3 ad variants for {body.platform} ads. Product: {body.product}. Audience: {audience}. "
               f"Tone: {tone}. Return each as 'Headline: ...' newline 'Text: ...' separated by blank lines.")
    if text:
        variants = []
        for block in text.split("\n\n"):
            lines = dict(l.split(":", 1) for l in block.splitlines() if ":" in l)
            if "Headline" in lines:
                variants.append({"headline": lines["Headline"].strip(), "text": lines.get("Text", "").strip()})
        if variants:
            return {"variants": variants[:3], "source": "ai"}
    p, a = body.product, audience or "you"
    if kit and kit.tagline:
        p = f"{p}: {kit.tagline}" if kit.tagline.lower() not in p.lower() else p
    return {"source": "template", "tone": tone, "variants": [
        {"headline": f"{p} — built for {a}", "text": f"Discover why {a} are switching to {p}. Get started today."},
        {"headline": f"Ready to try {p}?", "text": f"Limited-time offer for {a}. Book a free consultation now."},
        {"headline": f"The smarter way: {p}", "text": f"Save time and grow faster with {p}. Tap to learn more."},
    ]}


# ---- first-time-right helpers: prompt enhancer and ad sets ----------------------------------------
NEGATIVE = {
    "image": "text, letters, words, captions, watermark, signature, logo, blurry, low quality, distorted hands, extra fingers, "
             "deformed face, cluttered background",
    "video": "text, captions, watermark, flicker, warping, morphing faces, jitter, low quality",
}


class EnhanceIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    kind: Literal["image", "video"] = "image"
    use_brand: bool = False
    for_ad: bool = True  # leave clean space for a headline we add afterwards


def _rule_enhance(body: EnhanceIn, hint: str, kit) -> str:
    bits = [body.prompt.strip().rstrip(".")]
    bits.append(hint)
    if body.kind == "image":
        bits.append("clear single subject, professional composition, high detail, true-to-life colours")
        if body.for_ad:
            bits.append("generous empty space in the lower third for a headline, no text in the image")
    else:
        bits.append("smooth steady camera movement, natural motion, realistic lighting, cinematic, no on-screen text")
    return brand_prompt(", ".join(bits), kit)


@router.post("/enhance")
def enhance_prompt(body: EnhanceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Turn a short idea into a detailed, brand-aware prompt the user can read and edit before generating."""
    from ..quality import PLAYBOOKS, match_playbook
    rate_limit(f"enhance:{user.id}", 30, 300)
    kit = get_kit(db, user.id) if body.use_brand else None
    hint = PLAYBOOKS[match_playbook(fallback=user.industry)]["image_hint"]
    write = writer(db, user.id, agent="prompt_artist")
    out, source = None, "rules"
    if write:
        task = ("an image model (FLUX / Stable Diffusion)" if body.kind == "image" else "a text-to-video model (5-10 second clip)")
        brand = brand_prompt("", kit).strip(", ") if kit else ""
        text = write(
            f"Rewrite this idea as one detailed prompt for {task}. Describe subject, setting, composition, lighting, "
            f"camera/lens{', motion and camera movement' if body.kind == 'video' else ''} and mood in under 90 words. "
            f"Keep every fact from the idea; don't add brand names, people's names or numbers that aren't in it. "
            f"{'No text, letters or logos in the image. Leave clean space for a headline. ' if body.for_ad and body.kind == 'image' else 'No on-screen text. '}"
            f"Style hint for this industry: {hint}. {('Brand: ' + brand + '. ') if brand else ''}"
            f"Return only the prompt.\n\nIdea: {body.prompt}", max_tokens=400)
        if text:
            text = text.strip().strip('"').strip()
            if 10 <= len(text) <= 2000:
                out, source = text, "ai"
    if not out:
        out = _rule_enhance(body, hint, kit)[:2000]
    return {"prompt": out, "negative_prompt": NEGATIVE[body.kind], "source": source}


AD_SIZES = {"1:1": ((1080, 1080), "Feed square"), "4:5": ((1080, 1350), "Feed portrait"),
            "9:16": ((1080, 1920), "Stories & Reels"), "16:9": ((1920, 1080), "YouTube & display"),
            "1.91:1": ((1200, 628), "Link ads & Google")}


class AdSetIn(BaseModel):
    sizes: List[Literal["1:1", "4:5", "9:16", "16:9", "1.91:1"]] = Field(min_length=1, max_length=5)
    headline: str = Field("", max_length=90)
    subline: str = Field("", max_length=120)
    cta: str = Field("", max_length=30)
    position: Literal["top", "bottom"] = "bottom"
    accent: str = Field("", pattern=r"^(#[0-9a-fA-F]{6})?$")
    add_logo: bool = False


def _asset_bytes(a: Asset) -> bytes:
    if a.url.startswith("/api/files/"):
        from ..brand import UPLOADS
        f = (UPLOADS / a.url[len("/api/files/"):]).resolve()
        if UPLOADS.resolve() not in f.parents or not f.is_file():
            raise HTTPException(404, "The original image file is missing.")
        return f.read_bytes()
    try:
        return P.download(a.url, P.MAX_IMAGE_BYTES, "the image host")
    except P.ProviderError as e:
        raise http_error(e)


@router.get("/ad-sizes")
def ad_sizes(user: User = Depends(current_user)):
    return [{"key": k, "width": s[0], "height": s[1], "label": label} for k, (s, label) in AD_SIZES.items()]


@router.post("/image/{asset_id}/adset")
def make_adset(asset_id: int, body: AdSetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Every placement size from one image, with the headline and button typeset by us (always spelled right)."""
    from ..brand import render_ad
    rate_limit(f"adset:{user.id}", 20, 300)
    src = db.get(Asset, asset_id)
    if not src or src.user_id != user.id or src.kind != "image" or not src.url:
        raise HTTPException(404, "Image not found.")
    logo = primary_logo(db, user.id) if body.add_logo else None
    if body.add_logo and not logo:
        raise HTTPException(400, "Upload a logo in Brand Kit first, or turn off “Add my logo”.")
    kit = get_kit(db, user.id)
    accent = body.accent or (kit.colors[0] if kit and kit.colors else "#6d5dfc")
    data = _asset_bytes(src)
    batch = uuid.uuid4().hex[:12]
    made = []
    try:
        for key in dict.fromkeys(body.sizes):
            (w, h), label = AD_SIZES[key]
            out = render_ad(data, (w, h), body.headline.strip(), body.subline.strip(), body.cta.strip(), body.position, accent, logo)
            a = Asset(user_id=user.id, kind="image", prompt=src.prompt, model=src.model,
                      url="/api/files/" + save_generated(user.id, out),
                      params={"size": key, "width": w, "height": h, "parent": src.id, "adset": batch, "placement": label,
                              "headline": body.headline, "cta": body.cta, "batch": batch, "provider_label": "Ad set",
                              "logo": bool(logo)})
            db.add(a)
            made.append(a)
    except (OSError, ValueError, BadImage):
        raise HTTPException(400, "That image couldn't be opened to make the ad set. Try regenerating it.")
    db.commit()
    return [asset_out(a) for a in made]


# ---- image editing: comment-to-edit, object selection, extend, background, upscale -------------------
class EditPin(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    r: float = Field(0.12, ge=0.02, le=0.5)  # circle radius, as a fraction of the shorter side
    text: str = Field(min_length=2, max_length=300)
    mode: Literal["area", "object"] = "area"  # object: select what was clicked (needs fal.ai), else the circle
    action: Literal["auto", "change", "remove"] = "auto"  # auto: decided from the text ("remove the lamp" → remove)


class EditIn(BaseModel):
    pins: List[EditPin] = Field(default_factory=list, max_length=8)
    instruction: str = Field("", max_length=500)  # a change to the whole image ("make it night"), applied after the pins
    style: str = Field("", max_length=40)  # a whole-image style preset id from /image/styles ("skeleton", "portrait")
    engine: str = Field("auto", max_length=40)  # auto | builtin:studio | builtin:free | conn:<id> (public refs)

    _inbound = field_validator("engine", mode="before")(lambda v: discreet.in_ref(v) if isinstance(v, str) else v)


def _edit_engines(db: Session, user: User) -> list:
    """Engines that can edit, best first. `precise` engines repaint only the area; the free one redraws and blends."""
    from ..models import ProviderConnection
    out = []
    if _fal_key(db, user):
        out.append({"ref": "builtin:fal", "name": "FLUX Fill (fal.ai)", "precise": True})
    from .. import ai_registry
    own_conns = ai_registry.user_keys_allowed() or (user.email or "").lower() in settings.admin_emails
    for c in ([] if not own_conns else db.scalars(select(ProviderConnection).where(ProviderConnection.user_id == user.id, ProviderConnection.kind == "image",
                                                         ProviderConnection.adapter.in_(("openai_images", "fal")))
                        .order_by(ProviderConnection.is_default.desc(), ProviderConnection.id))):
        if c.adapter == "openai_images" and "together" in (c.base_url or ""):
            continue  # Together has no /images/edits
        out.append({"ref": f"conn:{c.id}", "name": f"{c.name}{' · ' + c.model if c.model else ''}", "precise": True})
    out.append({"ref": "builtin:pollinations", "name": "Free FLUX (approximate)", "precise": False})
    return out


MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.post("/image/upload")
async def upload_image(file: UploadFile = File(...), description: str = Form("", max_length=500),
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Bring your own photo (product shot, room, person, anything) into the editor. Phone photos are turned upright
    from their EXIF data. Saved as a normal image in History, so every editing tool works on it."""
    import io
    from PIL import ImageOps
    from .. import image_edit as IE
    rate_limit(f"imgup:{user.id}", 30, 600)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "That file is over 20 MB. Export a smaller JPG or PNG and try again.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        img = ImageOps.exif_transpose(img)
    except (OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(400, "That file isn't an image AIMVA can open. Use JPG, PNG or WebP (iPhone HEIC: export as JPG).")
    img = IE.open_rgb(IE.png_bytes(img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=94)
    try:
        url = "/api/files/" + save_media(user.id, buf.getvalue(), "image")
    except BadImage as e:
        raise HTTPException(400, str(e))
    a = Asset(user_id=user.id, kind="image", prompt=description.strip(), model="uploaded", url=url,
              params={"width": img.width, "height": img.height, "uploaded": True, "filename": (file.filename or "")[:120],
                      "provider_label": "Your upload"})
    db.add(a)
    db.commit()
    return asset_out(a)


@router.get("/image/styles")
def image_styles(user: User = Depends(current_user)):
    """Whole-image style presets for the editor's style menu and /slash commands."""
    from .. import image_styles as S
    return S.public()


@router.get("/image/edit-engines")
def edit_engines(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The editing engines, plus which extra tools work: object selection, background swap and AI upscaling need fal.ai."""
    from .. import image_edit as IE
    fal = bool(_fal_key(db, user))
    names = {"builtin:fal": "AIMVA Studio edit (precise)", "builtin:pollinations": "AIMVA quick edit (approximate)"}
    engines = [{**e, "ref": discreet.out_ref(e["ref"]), "name": names.get(e["ref"], e["name"])} for e in _edit_engines(db, user)]
    tasks = [{**t, "model": discreet.model_label(t["model"], "AIMVA Studio")} for t in IE.models()]
    return {"engines": engines, "select_objects": fal, "replace_background": fal, "ai_upscale": fal, "models": tasks}


def _own_image(db: Session, user: User, asset_id: int) -> Asset:
    src = db.get(Asset, asset_id)
    if not src or src.user_id != user.id or src.kind != "image" or not src.url:
        raise HTTPException(404, "Image not found.")
    return src


def _pick_engine(db: Session, user: User, choice: str) -> dict:
    engines = _edit_engines(db, user)
    ref = engines[0]["ref"] if choice == "auto" else choice
    engine = next((e for e in engines if e["ref"] == ref), None)
    if not engine:
        raise HTTPException(400, "That provider can't edit images. Pick another one, or connect fal.ai for precise edits.")
    return engine


def _free_variant(src: Asset) -> str:
    return (src.model or "").split("/", 1)[1] if (src.model or "").startswith("pollinations/") else "flux"


def _save_version(db: Session, user: User, src: Asset, img, extra: dict, label: str) -> Asset:
    from .. import image_edit as IE
    try:
        url = "/api/files/" + save_media(user.id, IE.png_bytes(img), "image")
    except BadImage as e:
        raise HTTPException(502, str(e))
    keep = {k: v for k, v in (src.params or {}).items() if k in ("size", "style", "seed", "brand", "batch")}
    a = Asset(user_id=user.id, kind="image", prompt=src.prompt, model=src.model, url=url,
              params={**keep, "width": img.size[0], "height": img.size[1], "edited_from": src.id,
                      "edit_root": (src.params or {}).get("edit_root") or src.id, "provider_label": label, **extra})
    db.add(a)
    db.commit()
    return a


def _edit_error(e) -> HTTPException:
    return HTTPException(e.status if 400 <= e.status < 600 else 502, e.message)


@router.post("/image/{asset_id}/edit")
def edit_image(asset_id: int, body: EditIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Apply pinned comments to an image. Saves a new version linked to the original; the original is never changed."""
    from .. import image_edit as IE
    rate_limit(f"imgedit:{user.id}", 20, 300)
    from .. import image_styles as S
    style = S.get(body.style) if body.style.strip() else None
    if body.style.strip() and not style:
        raise HTTPException(400, "That style doesn't exist. Pick one from the style menu.")
    typed = body.instruction.strip()
    if not body.pins and not style and len(typed) < 3:
        raise HTTPException(400, "Add a comment on the image, pick a style, or describe a change to the whole image.")
    instruction = S.instruction(style["id"], typed) if style else typed
    src = _own_image(db, user, asset_id)
    engine = _pick_engine(db, user, body.engine)
    ref = engine["ref"]
    pins = [IE.Pin(p.x, p.y, p.r, p.text, p.mode, p.action) for p in body.pins]
    base_prompt = src.prompt or "a photo"
    fal_key = _fal_key(db, user)
    try:
        img = IE.open_rgb(_asset_bytes(src))
        resolved = IE.resolve_masks(img, pins, IE.fal_segmenter(fal_key) if fal_key else None) if pins else []
        masks = [r["mask"] for r in resolved]
        conn = resolve(db, user, ref, "image") if ref.startswith("conn:") else None
        key = fal_key if ref == "builtin:fal" else (conn["api_key"] if conn and conn["adapter"] == "fal" else "")
        out = img
        if pins:
            if key:
                out = IE.fal_fill(key, img, pins, base_prompt, masks)
            elif ref == "builtin:pollinations":
                out = IE.free_redraw(_pollinations, img, pins, base_prompt, (src.params or {}).get("seed"), _free_variant(src), masks)
            else:
                out = IE.openai_edit(conn, img, pins, base_prompt, masks)
        if instruction:
            if key:
                out = IE.instruct(key, out, instruction)
            elif ref == "builtin:pollinations":
                prompt = f"{base_prompt.strip().rstrip('.')}. {instruction}"
                out = IE.open_rgb(_pollinations(IE.free_url(prompt, *out.size, (src.params or {}).get("seed"), _free_variant(src))))
                out = out.resize(img.size) if out.size != img.size else out
            else:
                whole = Image.new("L", out.size, 255)
                out = IE.openai_edit(conn, out, [], "", [whole], prompt=instruction)
    except IE.EditFailed as e:
        raise _edit_error(e)
    edits = [{**p.model_dump(), "action": pin.does, "selected": r["selected"]} for p, pin, r in zip(body.pins, pins, resolved)]
    a = _save_version(db, user, src, out, {"edits": edits, "instruction": typed, "restyle": style["name"] if style else None,
                                           "edit_engine": engine["name"],
                                           "edit_precise": engine["precise"], "edit_kind": "style" if style and not pins else "comments"},
                       f"{style['name']} style" if style and not pins else f"Edited · {engine['name']}")
    return asset_out(a)


class TextLayerIn(BaseModel):
    text: str = Field("", max_length=160)
    x: float = Field(0.5, ge=0, le=1)
    y: float = Field(0.5, ge=0, le=1)
    size: float = Field(0.06, ge=0.02, le=0.2)  # letter height as a share of the image width
    color: str = Field("#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    weight: Literal["regular", "bold"] = "bold"
    bg: Literal["none", "band", "pill"] = "none"


class TextIn(BaseModel):
    layers: List[TextLayerIn] = Field(default_factory=list, max_length=8)


@router.post("/image/{asset_id}/text")
def set_text(asset_id: int, body: TextIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Typeset headlines, prices and buttons on the image ourselves, so they're always spelled right (any Indian script
    too). Text is drawn on the image underneath the last text version, so editing it again replaces the old text."""
    from .. import image_edit as IE
    from .. import text_layers as TL
    rate_limit(f"imgedit:{user.id}", 40, 300)
    src = _own_image(db, user, asset_id)
    base_id = (src.params or {}).get("text_base")
    base = db.get(Asset, base_id) if base_id else None
    if not base or base.user_id != user.id or base.kind != "image" or not base.url:
        base = src
    layers = [l.model_dump() for l in body.layers if l.text.strip()]
    try:
        out = TL.render(IE.open_rgb(_asset_bytes(base)), layers)
    except IE.EditFailed as e:
        raise _edit_error(e)
    label = f"Text · {layers[0]['text'][:24]}" if layers else "Text removed"
    a = _save_version(db, user, src, out, {"text_layers": layers, "text_base": base.id, "text_base_url": base.url, "edit_kind": "text",
                                           "edit_engine": "AIMVA text", "edit_precise": True}, label)
    return asset_out(a)


class ExtendIn(BaseModel):
    size: Literal["1:1", "4:5", "9:16", "16:9", "1.91:1"]
    engine: str = Field("auto", max_length=40)

    _inbound = field_validator("engine", mode="before")(lambda v: discreet.in_ref(v) if isinstance(v, str) else v)


@router.post("/image/{asset_id}/extend")
def extend_image(asset_id: int, body: ExtendIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Make another placement size by painting in the missing edges instead of cropping. The original stays untouched."""
    from .. import image_edit as IE
    rate_limit(f"imgedit:{user.id}", 20, 300)
    src = _own_image(db, user, asset_id)
    engine = _pick_engine(db, user, body.engine)
    (tw, th), label = AD_SIZES[body.size]
    try:
        img = IE.open_rgb(_asset_bytes(src))
        if abs(img.width / img.height - tw / th) < 0.02:
            raise HTTPException(400, f"This image is already {body.size}.")
        canvas, new_area, _ = IE.extend_canvas(img, tw / th)
        prompt = IE.EXTEND_PROMPT.format((src.prompt or "the scene")[:500])
        if engine["ref"] == "builtin:fal":
            gen = IE.fill(_fal_key(db, user), canvas, new_area, prompt)
        elif engine["ref"] == "builtin:pollinations":
            gen = IE.open_rgb(_pollinations(IE.free_url(prompt, *canvas.size, (src.params or {}).get("seed"), _free_variant(src))))
        else:
            conn = resolve(db, user, engine["ref"], "image")
            gen = (IE.fill(conn["api_key"], canvas, new_area, prompt) if conn["adapter"] == "fal"
                   else IE.openai_edit(conn, canvas, [], "", [new_area], prompt=prompt))
        out = IE.finish_extend(canvas, gen, new_area)
    except IE.EditFailed as e:
        raise _edit_error(e)
    a = _save_version(db, user, src, out, {"size": body.size, "extended_for": label, "edit_kind": "extend",
                                           "edit_engine": engine["name"], "edit_precise": engine["precise"]},
                      f"Extended to {body.size} · {engine['name']}")
    return asset_out(a)


class BackgroundIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=500)


@router.post("/image/{asset_id}/background")
def replace_background(asset_id: int, body: BackgroundIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Keep the main subject exactly and paint a new background around it (fal.ai: cut-out + FLUX Fill)."""
    from PIL import ImageOps

    from .. import image_edit as IE
    rate_limit(f"imgedit:{user.id}", 20, 300)
    src = _own_image(db, user, asset_id)
    key = _fal_key(db, user)
    if not key:
        raise HTTPException(400, "Replacing the background needs fal.ai. Connect it in Settings → Integrations.")
    try:
        img = IE.open_rgb(_asset_bytes(src))
        subject = IE.fal_subject_mask(key, img)
        background = ImageOps.invert(subject)
        gen = IE.fill(key, img, background, f"{body.prompt.strip()}. Natural lighting that matches the subject, realistic shadows.")
        out = IE.blend(img, gen, [background])
    except IE.EditFailed as e:
        raise _edit_error(e)
    a = _save_version(db, user, src, out, {"edit_kind": "background", "background": body.prompt, "edit_engine": "fal.ai",
                                           "edit_precise": True}, "New background · fal.ai")
    return asset_out(a)


class UpscaleIn(BaseModel):
    factor: Literal[2, 4] = 2


@router.post("/image/{asset_id}/upscale")
def upscale_image(asset_id: int, body: UpscaleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Bigger, sharper copy: AI upscaling with fal.ai, or a basic high-quality resize without a key (labelled as such)."""
    from .. import image_edit as IE
    rate_limit(f"imgedit:{user.id}", 20, 300)
    src = _own_image(db, user, asset_id)
    key = _fal_key(db, user)
    try:
        img = IE.open_rgb(_asset_bytes(src), max_side=IE.MAX_UPSCALED_SIDE)
        out = IE.fal_upscale(key, img, body.factor) if key else IE.basic_upscale(img, body.factor)
    except IE.EditFailed as e:
        raise _edit_error(e)
    name = "AI upscale (fal.ai)" if key else "Basic upscale"
    a = _save_version(db, user, src, out, {"edit_kind": "upscale", "edit_engine": name, "edit_precise": bool(key)},
                      f"{out.size[0]}×{out.size[1]} · {name}")
    return asset_out(a)
