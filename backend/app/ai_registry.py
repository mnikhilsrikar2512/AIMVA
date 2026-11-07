"""Which supplier and key powers each AI capability. Server-side only: nothing here ever reaches the browser.

For this version every AI feature runs on the platform's keys (backend/.env). Each capability resolves in order:

  1. its own provider and key        e.g. TTS_PROVIDER=sarvam + TTS_API_KEY=…  (or a legacy variable, below)
  2. the shared "one key" provider   AI_PROVIDER=fal + AI_API_KEY=…, if that provider can do the capability
  3. the fallback                    free/rules/built-in browser or phone voice, so the app still works

Legacy variables keep working as step 1: GEMINI_API_KEY (text), FAL_KEY (image, image_edit, video),
SARVAM_API_KEY (tts, stt). Models are pinned per capability (TEXT_MODEL, IMAGE_MODEL, VIDEO_MODEL, TTS_MODEL,
TTS_VOICE, STT_MODEL; EDIT_MODEL_* still pins each image-editing task, see app/image_edit.py).

Customers' own keys (Settings → AI providers, per-user Gemini/fal keys) are kept in the code but ignored while
ALLOW_USER_AI_KEYS is false (the default for this version), so a later version can turn bring-your-own-key back on.
"""
import os
from dataclasses import dataclass
from typing import Optional

CAPABILITIES = ("text", "image", "image_edit", "video", "tts", "stt", "voice_call")

# What each supplier can do. A shared AI_PROVIDER is only used for the capabilities listed here.
SUPPORTS = {
    "gemini": {"text"},
    "fal": {"image", "image_edit", "video"},
    "sarvam": {"tts", "stt"},
    "openai": {"text", "image"},
    "twilio": {"voice_call"},
}
LEGACY_KEYS = {"text": ("gemini", "GEMINI_API_KEY"), "image": ("fal", "FAL_KEY"), "image_edit": ("fal", "FAL_KEY"),
               "video": ("fal", "FAL_KEY"), "tts": ("sarvam", "SARVAM_API_KEY"), "stt": ("sarvam", "SARVAM_API_KEY")}
DEFAULT_MODELS = {
    ("gemini", "text"): "gemini-2.5-flash", ("fal", "image"): "fal-ai/flux/schnell", ("fal", "video"): "fal-ai/ltx-2/text-to-video",
    ("sarvam", "tts"): "bulbul:v3", ("sarvam", "stt"): "saaras:v4",
}
FALLBACK = {"text": "free", "image": "free", "image_edit": "free", "video": "", "tts": "builtin", "stt": "builtin",
            "voice_call": "builtin"}
_ENV_PREFIX = {"image_edit": "IMAGE_EDIT", "voice_call": "VOICE_CALL"}


# Legacy variables are also read through app.config.settings (loaded from backend/.env at start-up).
_SETTINGS_ATTR = {"GEMINI_API_KEY": "gemini_api_key", "GEMINI_MODEL": "gemini_model", "FAL_KEY": "fal_key",
                  "TWILIO_ACCOUNT_SID": "twilio_account_sid", "TWILIO_AUTH_TOKEN": "twilio_auth_token"}


def _env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value and name in _SETTINGS_ATTR:
        from .config import settings
        value = str(getattr(settings, _SETTINGS_ATTR[name], "") or "").strip()
    return value


def _prefix(cap: str) -> str:
    return _ENV_PREFIX.get(cap, cap.upper())


@dataclass(frozen=True)
class Engine:
    capability: str
    provider: str          # "gemini", "fal", "sarvam", … or a fallback: "free", "builtin", ""
    key: str = ""
    model: str = ""
    source: str = ""       # "own" | "shared" | "legacy" | "fallback"

    @property
    def live(self) -> bool:
        """A real supplier with a key (not a fallback)."""
        return bool(self.key) and self.source != "fallback"


def resolve(cap: str) -> Engine:
    """The engine for a capability right now (reads the environment each call, so tests and reloads see changes)."""
    if cap not in CAPABILITIES:
        raise ValueError(f"unknown capability {cap}")
    p = _prefix(cap)
    model_pin = _env(f"{p}_MODEL")
    # 1. its own provider + key
    own_provider, own_key = _env(f"{p}_PROVIDER").lower(), _env(f"{p}_API_KEY")
    if own_provider and own_key and cap in SUPPORTS.get(own_provider, ()):
        return Engine(cap, own_provider, own_key, model_pin or DEFAULT_MODELS.get((own_provider, cap), ""), "own")
    if cap in LEGACY_KEYS:
        lp, lvar = LEGACY_KEYS[cap]
        if _env(lvar):
            legacy_model = _env("GEMINI_MODEL") if cap == "text" else ""
            return Engine(cap, lp, _env(lvar), model_pin or legacy_model or DEFAULT_MODELS.get((lp, cap), ""), "legacy")
    if cap == "voice_call" and _env("TWILIO_ACCOUNT_SID") and _env("TWILIO_AUTH_TOKEN"):
        return Engine(cap, "twilio", _env("TWILIO_AUTH_TOKEN"), "", "legacy")
    # 2. the shared one-key provider
    shared, shared_key = _env("AI_PROVIDER").lower(), _env("AI_API_KEY")
    if shared and shared_key and cap in SUPPORTS.get(shared, ()):
        return Engine(cap, shared, shared_key, model_pin or DEFAULT_MODELS.get((shared, cap), ""), "shared")
    # 3. fallback
    fb = FALLBACK[cap]
    if fb == "free" and not _free_ai():  # dev default on; deploy sets FREE_AI=false
        fb = "" if cap != "text" else "rules"
    return Engine(cap, fb, "", "", "fallback")


def _free_ai() -> bool:
    from .config import settings
    return bool(settings.free_ai)


def key_for(cap: str, provider: str) -> str:
    """The platform key for a capability if it resolves to this provider, else ''."""
    e = resolve(cap)
    return e.key if e.provider == provider and e.live else ""


def user_keys_allowed() -> bool:
    """Bring-your-own AI keys: off for this version (ALLOW_USER_AI_KEYS=false)."""
    return _env("ALLOW_USER_AI_KEYS").lower() in ("true", "1", "yes")


# ---- what the browser may know -------------------------------------------------------------------
BASE_VOICE_LANGUAGES = {"en-IN": "English (India)", "en-US": "English (US)"}
BROWSER_VOICE_LANGUAGES = {"hi-IN": "Hindi", "te-IN": "Telugu", "ta-IN": "Tamil", "es-ES": "Spanish", "fr-FR": "French",
                           "de-DE": "German", "ar-SA": "Arabic"}
# Indian languages the multilingual voice engine speaks on real phone calls (10 Indian languages + English).
INDIAN_VOICE_LANGUAGES = {"hi-IN": "Hindi", "bn-IN": "Bengali", "ta-IN": "Tamil", "te-IN": "Telugu", "gu-IN": "Gujarati",
                          "kn-IN": "Kannada", "ml-IN": "Malayalam", "mr-IN": "Marathi", "pa-IN": "Punjabi", "od-IN": "Odia"}


def voice_languages() -> dict:
    """Languages the call assistant can be set to. Grows on its own when the multilingual voice engine is set up."""
    langs = {**BASE_VOICE_LANGUAGES, **BROWSER_VOICE_LANGUAGES}
    if resolve("tts").live:
        langs.update(INDIAN_VOICE_LANGUAGES)
    return langs


def phone_languages() -> list:
    """Languages real phone calls speak naturally today."""
    return list(BASE_VOICE_LANGUAGES) + (list(INDIAN_VOICE_LANGUAGES) if resolve("tts").live else [])


def capabilities() -> dict:
    """Booleans and language codes only: never a supplier, model or key."""
    return {
        "writer": resolve("text").provider not in ("", "rules"),
        "images": resolve("image").provider != "",
        "studio_images": resolve("image").live,
        "image_editing": resolve("image_edit").live,
        "video": resolve("video").live,
        "multilingual_voice": resolve("tts").live,
        "voice_languages": voice_languages(),
        "phone_languages": phone_languages(),
    }


def env_variables() -> list:
    """Every variable this registry reads, for docs and .env.example."""
    names = ["AI_PROVIDER", "AI_API_KEY", "ALLOW_USER_AI_KEYS", "FREE_AI"]
    for cap in CAPABILITIES:
        p = _prefix(cap)
        names += [f"{p}_PROVIDER", f"{p}_API_KEY", f"{p}_MODEL"]
    return names + ["TTS_VOICE", "GEMINI_API_KEY", "GEMINI_MODEL", "FAL_KEY", "SARVAM_API_KEY"]
