"""Google picture engine (main) and video engine (backup). Server-side only.

Owner decision (2026-11-21, replaces 2026-11-15 for pictures): Google makes pictures and whole-image edits first,
because Imagen 4 Fast (~Rs 1.8) and the Gemini image model are cheaper than fal's finished-picture models. fal stays
the main VIDEO engine, because Veo costs more per second than fal's LTX-2.

Order for pictures:  Google (Gemini Lite image model, or Imagen if configured)  ->  fal  ->  free engine
                     (free only where FREE_AI is on; off in production). Set PICTURE_ENGINE=fal to go back to fal first.
Order for edits:     whole-image sentence: Google Gemini image model -> fal Kontext. Spot edits, eraser, cutout,
                     "keep my product" and upscale stay on fal (they need masks, which Google's model doesn't take).
Order for video:     fal  ->  Google Veo

Google is not used when fal isn't set up at all: that is a setup gap, not a failure, and silently paying Google for
every picture would break the "doesn't cost more" rule.

Google image and video generation needs billing on the Google AI Studio project. A free key gets refused (quota 0
or "billed users only"); that refusal is an ordinary failure here, so the caller moves on to the next step or shows
its usual neutral message. Nothing in this module ever reaches the browser: no key, no model name, no "Google".

Settings (backend/.env):
  PICTURE_ENGINE         google (default) / fal - which engine makes pictures and whole-image edits first
  GOOGLE_PICTURE_MODEL   default gemini-3.1-flash-lite-image (pictures from words only; imagen-* also works)
  GOOGLE_MEDIA_FALLBACK  true (default) / false - switch Google off as the backup (video, and pictures when fal is first)
  GOOGLE_MEDIA_API_KEY   optional; defaults to the platform Gemini key (GEMINI_API_KEY or TEXT_/AI_ gemini key)
  GOOGLE_IMAGE_MODEL     default gemini-3.1-flash-lite-image
  GOOGLE_VIDEO_MODEL     default veo-3.1-fast-generate-preview
  GOOGLE_VIDEO_RESOLUTION default 720p (cheapest)
"""
import base64
import logging
import os
import re
from typing import Optional

import httpx

from . import providers as P

log = logging.getLogger(__name__)

API = "https://generativelanguage.googleapis.com/v1beta"
NAME = "the Google engine"  # what ProviderError messages say; they are logged, never shown to customers
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-lite-image"  # with a reference picture, and for edits
# From words only. Imagen isn't offered to every key (checked 2026-11-21: ListModels shows no imagen-* models), so the
# default is the Gemini Lite image model; set GOOGLE_PICTURE_MODEL=imagen-... to use Imagen where it is available.
DEFAULT_PICTURE_MODEL = "gemini-3.1-flash-lite-image"
IMAGEN_ASPECTS = ("1:1", "3:4", "4:3", "9:16", "16:9")
DEFAULT_VIDEO_MODEL = "veo-3.1-fast-generate-preview"
IMAGE_ASPECTS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")
_OPERATION_RE = re.compile(r"^models/[A-Za-z0-9._-]+/operations/[A-Za-z0-9._-]+$")
MAX_IMAGES = 4


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or "").strip() or default


def enabled() -> bool:
    return _env("GOOGLE_MEDIA_FALLBACK", "true").lower() not in ("false", "0", "no", "off")


def _platform_key() -> str:
    own = _env("GOOGLE_MEDIA_API_KEY")
    if own:
        return own
    from . import ai_registry
    return ai_registry.key_for("text", "gemini")


def key() -> str:
    """The platform's Google key for the backup, or '' when the backup is off or no key is set."""
    return _platform_key() if enabled() else ""


def pictures_first() -> bool:
    return _env("PICTURE_ENGINE", "google").lower() == "google"


def primary_key() -> str:
    """The Google key when Google makes pictures first (PICTURE_ENGINE=google), else ''."""
    return _platform_key() if pictures_first() else ""


def picture_model() -> str:
    return _env("GOOGLE_PICTURE_MODEL", DEFAULT_PICTURE_MODEL)


def image_model() -> str:
    return _env("GOOGLE_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)


def video_model() -> str:
    return _env("GOOGLE_VIDEO_MODEL", DEFAULT_VIDEO_MODEL)


def _headers(k: str) -> dict:
    # Header, never ?key=: a key in the URL ends up in access logs and httpx's request log.
    return {"x-goog-api-key": k}


def _post(path: str, k: str, body: dict, timeout: int) -> dict:
    return P._request("POST", f"{API}/{path}", NAME, headers=_headers(k), json=body, timeout=timeout).json()


def _split_data_uri(uri: str) -> tuple:
    """(mime, base64 text) from a data: URI, or fetch an http(s) image and encode it."""
    if uri.startswith("data:"):
        head, _, data = uri.partition(",")
        mime = head[5:].split(";", 1)[0] or "image/png"
        return mime, data
    from .brand import fetch_image
    raw = fetch_image(uri)
    mime = "image/png" if raw[:8] == b"\x89PNG\r\n\x1a\n" else "image/webp" if raw[8:12] == b"WEBP" else "image/jpeg"
    return mime, base64.b64encode(raw).decode()


def closest_aspect(w: int, h: int, allowed=IMAGE_ASPECTS) -> str:
    target = w / max(h, 1)
    def ratio(a):
        x, y = a.split(":")
        return float(x) / float(y)
    return min(allowed, key=lambda a: abs(ratio(a) - target))


# ---- pictures ---------------------------------------------------------------------------------------------------
def generate_images(k: str, prompt: str, width: int, height: int, count: int = 1,
                    reference: Optional[str] = None) -> list:
    """List of PNG/JPEG bytes: Imagen from words alone, the Gemini image model when there's a reference picture.
    Raises P.ProviderError on any failure, including a free key that can't make pictures."""
    if not reference:
        if picture_model().startswith("imagen"):
            return imagen_images(k, prompt, width, height, count)
        return gemini_images(k, prompt, width, height, count, model=picture_model())
    return gemini_images(k, prompt, width, height, count, reference)


def imagen_images(k: str, prompt: str, width: int, height: int, count: int = 1) -> list:
    """Imagen makes up to 4 pictures in one call."""
    model = picture_model()
    body = {"instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": max(1, min(count, MAX_IMAGES)),
                           "aspectRatio": closest_aspect(width, height, IMAGEN_ASPECTS)}}
    data = _post(f"models/{model}:predict", k, body, timeout=150)
    got = [p.get("bytesBase64Encoded") for p in (data.get("predictions") or []) if isinstance(p, dict)]
    got = [g for g in got if g]
    if not got:
        reason = next((p.get("raiFilteredReason") for p in (data.get("predictions") or []) if isinstance(p, dict)
                       and p.get("raiFilteredReason")), "")
        raise P.ProviderError(f"{NAME} returned no picture ({reason or 'empty answer'}).", 502)
    return [base64.b64decode(g) for g in got]


def edit_image(k: str, image_png: bytes, instruction: str) -> bytes:
    """A whole-image change from a sentence ("make it night"). Returns the edited picture's bytes."""
    uri = "data:image/png;base64," + base64.b64encode(image_png).decode()
    from PIL import Image
    import io
    w, h = Image.open(io.BytesIO(image_png)).size
    return gemini_images(k, instruction.strip(), w, h, 1, uri)[0]


def gemini_images(k: str, prompt: str, width: int, height: int, count: int = 1,
                  reference: Optional[str] = None, model: Optional[str] = None) -> list:
    """The Gemini image model makes one picture per call, so `count` calls (capped)."""
    model = model or image_model()
    parts = [{"text": prompt}]
    if reference:
        try:
            mime, data = _split_data_uri(reference)
        except Exception:  # noqa: BLE001 - a missing reference shouldn't stop the backup; draw from the words
            log.warning("backup image engine: couldn't load the reference image", exc_info=True)
        else:
            parts.append({"inlineData": {"mimeType": mime, "data": data}})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": closest_aspect(width, height)}}}
    out = []
    for _ in range(max(1, min(count, MAX_IMAGES))):
        data = _post(f"models/{model}:generateContent", k, body, timeout=150)
        try:
            got = [p["inlineData"]["data"] for c in data.get("candidates", []) for p in (c.get("content") or {}).get("parts", [])
                   if (p.get("inlineData") or {}).get("data")]
        except (TypeError, AttributeError):
            got = []
        if not got:
            if out:  # keep what we have rather than throw away paid pictures
                break
            reason = (data.get("promptFeedback") or {}).get("blockReason") or \
                ((data.get("candidates") or [{}])[0].get("finishReason"))
            raise P.ProviderError(f"{NAME} returned no picture ({reason or 'empty answer'}).", 502)
        out.extend(base64.b64decode(g) for g in got[:1])
    return out


# ---- video ------------------------------------------------------------------------------------------------------
def _veo_seconds(duration) -> int:
    try:
        s = float(str(duration or "8").rstrip("s"))
    except ValueError:
        s = 8.0
    return 4 if s <= 4 else 6 if s <= 6 else 8


def _veo_aspect(aspect: str) -> str:
    return "9:16" if aspect in ("9:16", "3:4", "4:5") else "16:9"  # Veo makes only these two


def start_video(k: str, prompt: str, aspect_ratio: str = "16:9", duration="8", negative_prompt: str = "",
                start_image: Optional[str] = None) -> dict:
    """Queue a Veo clip (it renders its own sound). Returns the job stored on the asset."""
    model = video_model()
    instance = {"prompt": prompt}
    if start_image:
        mime, data = _split_data_uri(start_image)
        instance["image"] = {"bytesBase64Encoded": data, "mimeType": mime}
    params = {"aspectRatio": _veo_aspect(aspect_ratio), "durationSeconds": _veo_seconds(duration),
              "resolution": _env("GOOGLE_VIDEO_RESOLUTION", "720p")}
    if negative_prompt:
        params["negativePrompt"] = negative_prompt
    data = _post(f"models/{model}:predictLongRunning", k, {"instances": [instance], "parameters": params}, timeout=60)
    name = str(data.get("name") or "")
    if not _OPERATION_RE.match(name):
        raise P.ProviderError(f"{NAME} didn't queue the video.", 502)
    return {"adapter": "google", "operation": name, "model": model}


def poll_video(k: str, job: dict) -> dict:
    """{'state': 'running'|'done'|'failed', 'bytes'?: bytes, 'error'?: str}. Google's links need the key, so the
    clip is downloaded here and kept as our own copy."""
    name = str(job.get("operation") or "")
    if not _OPERATION_RE.match(name):
        return {"state": "failed", "error": "The video job is missing."}
    op = P._request("GET", f"{API}/{name}", NAME, headers=_headers(k), timeout=30).json()
    if not op.get("done"):
        return {"state": "running"}
    if op.get("error"):
        log.warning("backup video engine failed: %s", str(op["error"])[:300])
        return {"state": "failed", "error": "The video couldn't be made. Try again in a minute."}
    resp = (op.get("response") or {}).get("generateVideoResponse") or {}
    samples = resp.get("generatedSamples") or []
    uri = ((samples[0] if samples else {}).get("video") or {}).get("uri", "")
    if not uri:
        log.warning("backup video engine returned no clip: %s", str(resp.get("raiMediaFilteredReasons") or resp)[:300])
        return {"state": "failed", "error": "The video couldn't be made from this prompt. Try different words."}
    return {"state": "done", "bytes": _download(k, uri)}


def _download(k: str, uri: str) -> bytes:
    """The first hop carries the key and must be Google's API host; any redirect is fetched without the key."""
    if not uri.startswith(API.rsplit("/", 1)[0] + "/"):
        raise P.ProviderError(f"{NAME} returned a file link that isn't allowed.", 502)
    try:
        with httpx.stream("GET", uri, headers=_headers(k), timeout=180, follow_redirects=False) as r:
            if r.is_redirect and r.next_request:
                nxt = str(r.next_request.url)
            elif r.status_code >= 400:
                raise P.ProviderError(f"Couldn't download the result from {NAME} ({r.status_code}).", 502)
            else:
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > P.MAX_VIDEO_BYTES:
                        raise P.ProviderError("The generated file is too large to keep.", 502)
                return bytes(buf)
    except httpx.HTTPError:
        raise P.ProviderError(f"Couldn't download the result from {NAME}.", 502)
    return P.download(nxt, P.MAX_VIDEO_BYTES, NAME)
