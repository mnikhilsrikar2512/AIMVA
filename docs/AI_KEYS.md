# AI keys (server-side only)

For this version every AI feature runs on the platform's keys, set in `backend/.env`. Customers never see or
enter AI keys, supplier names or model names: the app shows neutral names ("AIMVA writer", "Studio · detailed",
"the voice service") and `/api/capabilities` tells the browser only what is switched on (booleans and language
codes). Errors that mention a supplier, a model or a server setting are replaced with a neutral message for the
customer and logged in full on the server (`app/main.py`, `app/discreet.py`).

## How each capability finds its key (`app/ai_registry.py`)

| Capability | Own variables | Legacy variable | Fallback |
|---|---|---|---|
| Writing (pages, ad copy, replies) | `TEXT_PROVIDER`, `TEXT_API_KEY`, `TEXT_MODEL` | `GEMINI_API_KEY`, `GEMINI_MODEL` | free writer (`FREE_AI`), else rules |
| Images | `IMAGE_PROVIDER`, `IMAGE_API_KEY`, `IMAGE_MODEL` | `FAL_KEY` | free images (`FREE_AI`) |
| Image editing | `IMAGE_EDIT_PROVIDER`, `IMAGE_EDIT_API_KEY`, `IMAGE_EDIT_MODEL`, `EDIT_MODEL_*` per task | `FAL_KEY` | approximate free edit |
| Video | `VIDEO_PROVIDER`, `VIDEO_API_KEY`, `VIDEO_MODEL` | `FAL_KEY` | off ("Video isn't switched on yet") |
| Speech (multilingual voice) | `TTS_PROVIDER`, `TTS_API_KEY`, `TTS_MODEL`, `TTS_VOICE` | `SARVAM_API_KEY` | phone network's built-in voice; browser voice in practice calls |
| Transcription | `STT_PROVIDER`, `STT_API_KEY`, `STT_MODEL` | `SARVAM_API_KEY` | phone network / browser recognition |
| Phone calls | customer's own Twilio number, else `TWILIO_*` | | |

Order: the capability's own provider and key → its legacy variable → the shared `AI_PROVIDER` + `AI_API_KEY`
(only for capabilities that provider supports: gemini = writing; fal = images, editing, video; sarvam = speech,
transcription; openai = writing, images) → the fallback.

## Pictures on Google first, video on the studio (`app/google_media.py`)

Owner decision (2026-11-21): Google makes pictures and whole-image edits first because it is cheaper there; the
studio engine (`FAL_KEY`) stays first for video because Veo costs more per second.

- Pictures from words: Google's Lite image model (`GOOGLE_PICTURE_MODEL`, default `gemini-3.1-flash-lite-image`,
  about $0.034 a picture) → studio → free images (only where `FREE_AI` is on, off in production). Set an
  `imagen-*` model there to use Imagen (about $0.02, 4 per call) on keys that offer it: on 2026-11-21 ListModels
  showed no Imagen or Veo models for our key, so check before switching.
- Pictures with a reference photo, and whole-image edits ("make it night"): Google image model
  (`GOOGLE_IMAGE_MODEL`, default `gemini-3.1-flash-lite-image`) → studio (Kontext for edits).
- Spot edits, eraser, object select, cutout, "keep my product" and upscale stay on the studio: they need masks.
- Video: studio → Google Veo (`GOOGLE_VIDEO_MODEL`, default `veo-3.1-fast-generate-preview`, 720p). A clip that
  the studio accepts and later fails is handed to Veo too.
- A customer's own connected engine is never rerouted.

`PICTURE_ENGINE=fal` puts the studio first for pictures again (Google then acts only as the backup, and only when
`GOOGLE_MEDIA_FALLBACK` is on). The key is `GOOGLE_MEDIA_API_KEY`, or the platform Gemini key when that is empty.

Google picture and video generation needs billing turned on for the Google AI Studio project. With a free key
Google refuses; pictures then come from the studio as before, the customer sees nothing different, and the server
log says Google failed and that billing is needed. Customers never see which engine ran: no supplier, model or
"backup" wording reaches the browser.

Keys go in a request header, never the URL, and httpx's request log is kept at WARNING with key-shaped query
values masked (`app/observability.py`), so keys don't end up in server logs.

## Multilingual calls

With a speech key set, the call assistant's language list grows from English to 10 Indian languages plus
English, and real phone calls in those languages use natural voices: the backend generates the audio and gives
the phone network a signed link that expires after 15 minutes (`app/speech.py`). The call speaks the language
the lead wrote in or asked for ("callback in Hindi"), or switches on their first reply. Without the key, calls
use the phone network's own voice.

## Bring your own key (later)

`ALLOW_USER_AI_KEYS=false` (default) hides the AI providers settings from everyone but the platform owner and
makes the backend ignore keys customers stored earlier (nothing is deleted). Set it to `true` in a later version
to let customers use their own keys again.

## Production

`FREE_AI=false` in production: the free fallback is shared, rate-limited and watermarked, so it's for development.
