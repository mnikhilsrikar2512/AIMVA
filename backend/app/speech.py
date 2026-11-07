"""Multilingual voice, server-side only. Customers just pick a language; which engine speaks it stays here.

When the multilingual engine is configured (app/ai_registry.py: TTS_PROVIDER=sarvam + TTS_API_KEY, or
SARVAM_API_KEY, or the shared AI_PROVIDER), phone calls in Indian languages are spoken with natural voices:
the audio is generated here, cached on disk and handed to the phone network through a short-lived signed URL
(<Play>). Without it, calls fall back to the phone network's built-in voice (<Say>), as before.

The REST shapes follow the supplier's published docs (POST /text-to-speech, POST /speech-to-text). They are
covered by tests with the HTTP calls mocked and have not yet been exercised against the live service.
"""
import base64
import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Optional

import httpx
import jwt

from . import ai_registry
from .config import BASE_DIR, settings

log = logging.getLogger("aimva.speech")
API = "https://api.sarvam.ai"
CACHE_DIR = BASE_DIR / "data" / "voice_cache"
URL_TTL_S = 15 * 60          # the phone network fetches the audio within seconds; links die after 15 minutes
MAX_CHARS = 2500             # per request, per the supplier's limit
DEFAULT_VOICE = "priya"      # a warm voice on the default model; TTS_VOICE overrides it


def _engine(cap: str):
    e = ai_registry.resolve(cap)
    return e if e.live and e.provider == "sarvam" else None


def multilingual() -> bool:
    return _engine("tts") is not None


def speaks(lang: str) -> bool:
    """Can the multilingual engine voice this language on a phone call?"""
    return multilingual() and (lang in ai_registry.INDIAN_VOICE_LANGUAGES or lang == "en-IN")


def synthesize(text: str, lang: str) -> Optional[bytes]:
    """Speech audio (mp3) for the text, or None (caller falls back to the built-in phone voice)."""
    e = _engine("tts")
    if not e or not text.strip():
        return None
    body = {"text": text.strip()[:MAX_CHARS], "language_code": lang, "model": e.model or "bulbul:v3",
            "speaker": (ai_registry._env("TTS_VOICE") or DEFAULT_VOICE), "output_audio_codec": "mp3"}
    try:
        r = httpx.post(f"{API}/text-to-speech", json=body, headers={"api-subscription-key": e.key}, timeout=20)
        if r.status_code >= 400:
            log.warning("Speech synthesis failed (%s): %s", r.status_code, r.text[:300])
            return None
        audios = r.json().get("audios") or []
        return base64.b64decode(audios[0]) if audios else None
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("Speech synthesis error: %r", exc)
        return None


def transcribe(audio: bytes, filename: str = "audio.wav", lang: Optional[str] = None) -> Optional[dict]:
    """{'text', 'language'} for a short recording (under 30 s), or None."""
    e = _engine("stt")
    if not e or not audio:
        return None
    try:
        r = httpx.post(f"{API}/speech-to-text", headers={"api-subscription-key": e.key}, timeout=30,
                       files={"file": (filename, audio)},
                       data={"model": e.model or "saaras:v4", "mode": "transcribe", "language_code": lang or "unknown"})
        if r.status_code >= 400:
            log.warning("Transcription failed (%s): %s", r.status_code, r.text[:300])
            return None
        d = r.json()
        return {"text": d.get("transcript", ""), "language": d.get("language_code") or lang}
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Transcription error: %r", exc)
        return None


# ---- signed, short-lived audio links for the phone network ------------------------------------------
def audio_url(text: str, lang: str) -> Optional[str]:
    """A public URL the phone network can <Play>, or None to fall back to <Say>."""
    digest = hashlib.sha256(f"{lang}|{text}".encode()).hexdigest()[:32]
    path = CACHE_DIR / f"{digest}.mp3"
    if not path.exists():
        audio = synthesize(text, lang)
        if not audio:
            return None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
    token = jwt.encode({"a": digest, "exp": int(time.time()) + URL_TTL_S, "p": "voice-audio"}, settings.secret_key, "HS256")
    return f"{settings.public_url}/api/public/voice/audio/{token}"


def audio_file(token: str) -> Optional[Path]:
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if claims.get("p") != "voice-audio" or not re.fullmatch(r"[0-9a-f]{32}", str(claims.get("a", ""))):
        return None
    path = CACHE_DIR / f"{claims['a']}.mp3"
    return path if path.exists() else None


# ---- which language to speak -------------------------------------------------------------------------
SCRIPTS = [  # Unicode blocks -> language
    (r"[ऀ-ॿ]", "hi-IN"), (r"[ঀ-৿]", "bn-IN"), (r"[਀-੿]", "pa-IN"), (r"[઀-૿]", "gu-IN"),
    (r"[଀-୿]", "od-IN"), (r"[஀-௿]", "ta-IN"), (r"[ఀ-౿]", "te-IN"), (r"[ಀ-೿]", "kn-IN"),
    (r"[ഀ-ൿ]", "ml-IN"), (r"[؀-ۿ]", "ar-SA"),
]
NAMES = {"hindi": "hi-IN", "bengali": "bn-IN", "bangla": "bn-IN", "tamil": "ta-IN", "telugu": "te-IN", "gujarati": "gu-IN",
         "kannada": "kn-IN", "malayalam": "ml-IN", "marathi": "mr-IN", "punjabi": "pa-IN", "odia": "od-IN", "oriya": "od-IN"}
_ASK = re.compile(r"\b(?:in|speak|talk|call(?:back)?(?: me)? in|prefer)\s+(" + "|".join(NAMES) + r")\b", re.I)


def detect_language(text: str) -> Optional[str]:
    """The language a lead writes or asks for: its script, or "call me in Hindi" style requests."""
    if not text:
        return None
    m = _ASK.search(text)
    if m:
        return NAMES[m.group(1).lower()]
    for pattern, code in SCRIPTS:
        if len(re.findall(pattern, text)) >= 3:
            return code
    return None


def call_language(agent_language: str, hint_text: str = "") -> str:
    """The language for a call: what the lead wrote or asked for, if the call can speak it; else the assistant's."""
    wanted = detect_language(hint_text)
    if wanted and wanted in ai_registry.voice_languages() and (wanted in ai_registry.phone_languages() or not wanted.endswith("-IN")):
        return wanted
    return agent_language
