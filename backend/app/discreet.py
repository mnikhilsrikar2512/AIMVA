"""Keep the machinery out of sight. Customers see "AIMVA images", "Studio · detailed" and "the voice service";
which company or model does the work, and every platform key, stays on the server.

- Built-in engines and models travel to the browser under neutral public ids (out_ref / out_model) and are
  translated back on the way in (in_ref / in_model). Internal ids are still accepted, so nothing old breaks.
- scrub() rewrites any text bound for the browser that names a vendor, a model or a server setting.
- neutral_error() is the generic message for an area when a provider fails; the real detail is only logged.
Things the customer owns and connects themselves (their WhatsApp number, their Twilio number, their Meta,
Google and LinkedIn ad accounts, their hosting) keep their names: those are theirs, not our suppliers.
"""
import re

# ---- built-in engines (provider refs) ----------------------------------------------------------------
_REFS = {"builtin:pollinations": "builtin:free", "builtin:fal": "builtin:studio", "builtin:gemini": "builtin:writer"}
_REFS_IN = {v: k for k, v in _REFS.items()}


def out_ref(ref: str) -> str:
    return _REFS.get(ref, ref)


def in_ref(ref: str) -> str:
    return _REFS_IN.get(ref, ref)


# ---- models: internal id -> (public id, label) --------------------------------------------------------
_MODELS = {
    # images
    "pollinations/flux": ("free-standard", "Standard (free)"),
    "pollinations/turbo": ("free-fast", "Fast (free)"),
    "flux": ("free-standard", "Standard (free)"),
    "turbo": ("free-fast", "Fast (free)"),
    "fal-ai/flux/schnell": ("studio-fast", "Studio · fast"),
    "fal-ai/flux/dev": ("studio-detail", "Studio · detailed"),
    "fal-ai/flux-pro/v1.1": ("studio-pro", "Studio · pro"),
    "fal-ai/stable-diffusion-v35-large": ("studio-art", "Studio · artistic"),
    "fal-ai/recraft-v3": ("studio-design", "Studio · design"),
    "fal-ai/ideogram/v2": ("studio-text", "Studio · text in images"),
    "fal-ai/flux/dev/image-to-image": ("studio-remix", "Studio · from a reference"),
    # video
    "fal-ai/ltx-2/text-to-video": ("video-sound", "Video with sound"),
    "fal-ai/luma-dream-machine/ray-2": ("video-cinematic", "Cinematic video"),
    "fal-ai/kling-video/v2.1/standard/text-to-video": ("video-motion", "Smooth-motion video"),
    "fal-ai/ltx-video": ("video-fast", "Fast video"),
    "fal-ai/veo3": ("video-premium", "Premium video with sound"),
    "fal-ai/wan/v2.2-a14b/text-to-video": ("video-open", "Video · open model"),
    "fal-ai/mmaudio-v2": ("sound-match", "Matching sound"),
    # writing
    "gemini-2.5-flash": ("writer-fast", "AIMVA writer · fast"),
    "gemini-2.5-pro": ("writer-pro", "AIMVA writer · thorough"),
    "gemini-flash-latest": ("writer-latest", "AIMVA writer · latest"),
}
_MODELS_IN = {}
for _internal, (_public, _) in _MODELS.items():
    _MODELS_IN.setdefault(_public, _internal)  # "flux" and "pollinations/flux" share a public id; keep the full one


def out_model(model: str) -> str:
    return _MODELS.get(model, (model, ""))[0] if model else model


def in_model(model: str) -> str:
    return _MODELS_IN.get(model, model) if model else model


def model_label(model: str, fallback: str = "") -> str:
    return _MODELS.get(model, ("", fallback or "AIMVA engine"))[1]


def is_builtin_model(model: str) -> bool:
    return model in _MODELS


# ---- text scrubbing -------------------------------------------------------------------------------
# Suppliers the customer never deals with. Customer-owned services (WhatsApp, Twilio, Meta, Google Ads,
# LinkedIn, Netlify, Vercel, Cloudflare, GitHub, Sheets, OneDrive) are deliberately not here.
VENDORS = ["sarvam", "fal.ai", "fal-ai", "fal.run", "pollinations", "openai", "anthropic", "claude", "elevenlabs", "deepgram",
           "gemini", "replicate", "groq", "stability", "ollama", "comfyui", "huggingface", "together.ai", "mistral",
           "flux", "stable diffusion", "kling", "luma", "ltx", "veo", "mmaudio", "recraft", "ideogram", "wan-video", "llama"]
_VENDOR_RE = re.compile(r"\b(" + "|".join(re.escape(v) for v in VENDORS) + r")\b|\bfal\b", re.I)
_ENV_RE = re.compile(r"\b[A-Z][A-Z0-9]*_(?:KEY|TOKEN|SECRET|API_KEY|MODEL|EMAILS|URL|ID|SID)\b|\b(?:backend/)?\.env\b")
_SECRETISH = re.compile(r"\b(?:sk|pk|rk)[-_][A-Za-z0-9_-]{16,}|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:[0-9a-f]{16,}\b")


def leaks(text: str) -> bool:
    """Would this text tell a customer which supplier, model or server setting we use?"""
    return bool(text) and bool(_VENDOR_RE.search(text) or _ENV_RE.search(text) or _SECRETISH.search(text))


AREA_MESSAGES = {
    "voice": "The voice service is busy right now. Please try again in a minute.",
    "image": "The image engine is busy right now. Please try again in a minute.",
    "video": "The video engine is busy right now. Please try again in a minute.",
    "writer": "The AI writer is busy right now. Please try again in a minute.",
    "default": "The AI service is busy right now. Please try again in a minute.",
}
NOT_SET_UP = {
    "voice": "This voice feature isn't switched on for your account yet.",
    "image": "This image feature isn't switched on for your account yet.",
    "video": "Video isn't switched on for your account yet.",
    "writer": "The AI writer isn't switched on for your account yet.",
    "default": "This feature isn't switched on for your account yet.",
}


def area_for(path: str) -> str:
    p = path or ""
    if "/voice" in p or "/calls" in p:
        return "voice"
    if "/video" in p:
        return "video"
    if "/image" in p or "/content" in p or "/brand" in p:
        return "image"
    if "/sites" in p or "/ad-copy" in p or "/enhance" in p or "/templates" in p or "/agents" in p:
        return "writer"
    return "default"


def neutral_error(path: str, detail: str = "") -> str:
    """A customer-safe message for a failure whose real text mentions a supplier or a server setting."""
    area = area_for(path)
    d = (detail or "").lower()
    if any(w in d for w in ("connect ", "settings", "no key", "api key", "api_key", "not configured", "needs ", "set ")):
        return NOT_SET_UP[area]
    return AREA_MESSAGES[area]


def scrub(text, path: str = ""):
    """Text for the browser: unchanged when clean, otherwise the neutral message for its area."""
    if isinstance(text, str):
        return neutral_error(path, text) if leaks(text) else text
    if isinstance(text, list):  # FastAPI validation errors etc.
        return [scrub(t, path) for t in text]
    if isinstance(text, dict):
        return {k: scrub(v, path) for k, v in text.items()}
    return text
