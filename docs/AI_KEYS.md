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
