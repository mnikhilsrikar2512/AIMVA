"""Replying to a lead in the language they write in, within WhatsApp's rules.

- Language: each lead remembers what they write in (Hindi, Tamil, Hinglish...). It is picked up from their form
  message and every WhatsApp message, and the business can correct it on the lead.
- Who is waiting: a lead "needs you" when they wrote last and nobody has answered, or when they are brand new and
  nobody has contacted them yet. The Leads list puts those first.
- Drafts: the Lead Replier agent drafts a short reply in the lead's language. Without AI it uses ready-made
  replies in 12 languages, so the button always works.
- WhatsApp's 24-hour rule: a business may send free text only within 24 hours of the customer's last message.
  Outside it (always true for a new form or ad lead) only an approved template is delivered. The business names
  its approved templates on the WhatsApp connection (meta.first_message_template / follow_up_template).
"""
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Call, Lead, User, WaMessage, utcnow
from .services import get_integration
from .speech import detect_language as _script_language

WINDOW = timedelta(hours=24)
CLOSED = {"won", "lost"}

LANGUAGES = {  # code -> name shown to the business
    "en": "English", "hi-IN": "Hindi", "hi-Latn": "Hinglish", "bn-IN": "Bengali", "ta-IN": "Tamil", "te-IN": "Telugu",
    "gu-IN": "Gujarati", "kn-IN": "Kannada", "ml-IN": "Malayalam", "mr-IN": "Marathi", "pa-IN": "Punjabi", "od-IN": "Odia",
    "ar-SA": "Arabic",
}
SCRIPT_OF = {  # languages whose reply must be in their own script
    "hi-IN": r"[ऀ-ॿ]", "mr-IN": r"[ऀ-ॿ]", "bn-IN": r"[ঀ-৿]", "pa-IN": r"[਀-੿]",
    "gu-IN": r"[઀-૿]", "od-IN": r"[଀-୿]", "ta-IN": r"[஀-௿]", "te-IN": r"[ఀ-౿]",
    "kn-IN": r"[ಀ-೿]", "ml-IN": r"[ഀ-ൿ]", "ar-SA": r"[؀-ۿ]",
}
_MARATHI = {"आहे", "आहेत", "मला", "तुम्ही", "पाहिजे", "काय", "आम्ही", "कधी"}
_HINGLISH = {"hai", "hain", "kya", "kitna", "kitne", "kitni", "chahiye", "mujhe", "aap", "aapka", "aapki", "kab", "kaise",
             "nahi", "nahin", "haan", "karna", "karo", "raha", "rahi", "mera", "meri", "humein", "abhi", "batao",
             "bataiye", "bataye", "milega", "milegi", "sakte", "sakta", "wala", "wali", "accha", "acha", "theek", "thik"}


def wa_number(phone: str) -> str:
    """Digits WhatsApp can deliver to: local 10-digit numbers get the business country code."""
    d = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(d) == 11 and d.startswith("0"):
        d = d[1:]
    if len(d) == 10 and not (phone or "").strip().startswith("+"):
        d = settings.default_country_code + d
    return d


def _contacts(phone: str) -> set:
    """Every spelling a lead's number may have been stored under in the WhatsApp inbox."""
    d = "".join(ch for ch in (phone or "") if ch.isdigit())
    return {x for x in (d, wa_number(phone)) if x}


def detect(text: str) -> Optional[str]:
    """The language a message is written in, when it is clear enough to act on."""
    if not text:
        return None
    code = _script_language(text)
    if code == "hi-IN" and set(re.findall(r"[ऀ-ॿ]+", text)) & _MARATHI:
        return "mr-IN"
    if code:
        return code
    words = set(re.findall(r"[a-z]+", text.lower()))
    if len(words & _HINGLISH) >= 2:
        return "hi-Latn"
    return None


def remember_language(lead: Lead, text: str) -> None:
    code = detect(text)
    if code:
        lead.language = code


def language_of(db: Session, lead: Lead) -> str:
    if lead.language in LANGUAGES:
        return lead.language
    last = db.scalar(select(WaMessage.body).where(WaMessage.user_id == lead.user_id, WaMessage.direction == "in",
                                                  WaMessage.contact.in_(_contacts(lead.phone)))
                     .order_by(WaMessage.id.desc()).limit(1)) if lead.phone else None
    return detect(last or "") or detect(lead.message) or "en"


# ---- who is waiting ------------------------------------------------------------------------------------
def activity(db: Session, user_id: int, leads: list) -> dict:
    """{lead_id: {last_in_at, last_out_at, waiting_since, needs_reply}} for many leads in three queries."""
    by_contact = {}
    for l in leads:
        for c in _contacts(l.phone):
            by_contact.setdefault(c, []).append(l.id)
    last_in, last_out = {}, {}
    if by_contact:
        rows = db.execute(select(WaMessage.contact, WaMessage.direction, func.max(WaMessage.created_at))
                          .where(WaMessage.user_id == user_id, WaMessage.contact.in_(list(by_contact)),
                                 WaMessage.status != "failed")
                          .group_by(WaMessage.contact, WaMessage.direction)).all()
        for contact, direction, at in rows:
            target = last_in if direction == "in" else last_out
            for lid in by_contact.get(contact, []):
                if at and (lid not in target or at > target[lid]):
                    target[lid] = at
    ids = [l.id for l in leads]
    if ids:
        for lid, at in db.execute(select(Call.lead_id, func.max(Call.created_at))
                                  .where(Call.user_id == user_id, Call.lead_id.in_(ids), Call.status != "failed")
                                  .group_by(Call.lead_id)).all():
            if at and (lid not in last_out or at > last_out[lid]):
                last_out[lid] = at
    out = {}
    for l in leads:
        i, o = last_in.get(l.id), last_out.get(l.id)
        since = None
        if l.stage not in CLOSED and not l.opted_out_at:  # replied STOP: nobody should answer them
            if i and (not o or o < i):
                since = i
            elif not i and not o and l.stage == "new":
                since = l.created_at
        out[l.id] = {"last_in_at": i.isoformat() if i else None, "last_out_at": o.isoformat() if o else None,
                     "waiting_since": since.isoformat() if since else None, "needs_reply": since is not None}
    return out


def needs_first(leads: list, act: dict) -> list:
    """Leads waiting on the business first (hottest, then longest waiting), then everyone else newest first."""
    waiting = [l for l in leads if act[l.id]["needs_reply"]]
    rest = [l for l in leads if not act[l.id]["needs_reply"]]
    waiting.sort(key=lambda l: (-l.score, act[l.id]["waiting_since"]))
    rest.sort(key=lambda l: l.created_at, reverse=True)
    return waiting + rest


def window_open(db: Session, user_id: int, phone: str, now: Optional[datetime] = None) -> bool:
    last = db.scalar(select(func.max(WaMessage.created_at)).where(
        WaMessage.user_id == user_id, WaMessage.direction == "in", WaMessage.contact.in_(_contacts(phone))))
    return bool(last and last + WINDOW >= (now or utcnow()))


# ---- approved templates ----------------------------------------------------------------------------------
def template_for(integ, kind: str, language: str) -> Optional[dict]:
    """The approved template to send when the 24-hour window is closed: {name, lang, params}, or None."""
    meta = (integ.meta or {}) if integ else {}
    name = (meta.get("follow_up_template") if kind == "follow_up" else None) or meta.get("first_message_template")
    if not name or not re.fullmatch(r"[a-z0-9_]{1,120}", str(name)):
        return None
    langs = [str(x) for x in (meta.get("template_languages") or ["en"]) if x] or ["en"]
    base = "en" if language in ("en", "hi-Latn") else language.split("-")[0]
    return {"name": name, "lang": base if base in langs else langs[0], "with_name": meta.get("template_has_name", True) is not False}


# ---- drafts -----------------------------------------------------------------------------------------------
READY = {  # ready-made replies when no AI is available. {name} = first name, {business} = business name
    "en": {"welcome": "Hi {name}, thanks for your interest in {business}! When is a good time to talk?",
           "follow_up": "Hi {name}, just following up on your enquiry. Do you have any questions I can help with?",
           "visit": "Hi {name}! Would you like to schedule a visit? Reply with a day and time that suits you.",
           "pricing": "Hi {name}, happy to share pricing options that fit your budget. When is a good time to talk?"},
    "hi-IN": {"welcome": "नमस्ते {name}, {business} में रुचि दिखाने के लिए धन्यवाद! आपसे बात करने का अच्छा समय कब रहेगा?",
              "follow_up": "नमस्ते {name}, आपकी पूछताछ के बारे में फ़ॉलो-अप कर रहे हैं। कोई सवाल हो तो बताइए, हम मदद करेंगे।",
              "visit": "नमस्ते {name}! क्या आप मिलने का समय तय करना चाहेंगे? अपनी सुविधा का दिन और समय बताइए।",
              "pricing": "नमस्ते {name}, हम आपके बजट के हिसाब से कीमतें भेज सकते हैं। बात करने का अच्छा समय कब रहेगा?"},
    "hi-Latn": {"welcome": "Namaste {name}, {business} mein interest dikhane ke liye dhanyavaad! Aapse baat karne ka sahi time kab rahega?",
                "follow_up": "Namaste {name}, aapki enquiry ke baare mein follow up kar rahe hain. Koi sawaal ho toh bataiye, hum madad karenge.",
                "visit": "Namaste {name}! Kya aap visit ka time fix karna chahenge? Apni suvidha ka din aur time bataiye.",
                "pricing": "Namaste {name}, hum aapke budget ke hisaab se prices bhej sakte hain. Baat karne ka sahi time kab rahega?"},
    "bn-IN": {"welcome": "নমস্কার {name}, {business}-এ আগ্রহ দেখানোর জন্য ধন্যবাদ! আপনার সঙ্গে কথা বলার সুবিধাজনক সময় কখন?",
              "follow_up": "নমস্কার {name}, আপনার জিজ্ঞাসার বিষয়ে খোঁজ নিচ্ছি। কোনো প্রশ্ন থাকলে জানাবেন, আমরা সাহায্য করব।",
              "visit": "নমস্কার {name}! আপনি কি দেখা করার সময় ঠিক করতে চান? আপনার সুবিধামতো দিন ও সময় জানান।",
              "pricing": "নমস্কার {name}, আপনার বাজেট অনুযায়ী দামের বিবরণ পাঠাতে পারি। কথা বলার সুবিধাজনক সময় কখন?"},
    "ta-IN": {"welcome": "வணக்கம் {name}, {business} மீது ஆர்வம் காட்டியதற்கு நன்றி! உங்களுடன் பேச வசதியான நேரம் எது?",
              "follow_up": "வணக்கம் {name}, உங்கள் விசாரணை குறித்து தொடர்பு கொள்கிறோம். ஏதேனும் கேள்விகள் இருந்தால் சொல்லுங்கள், உதவுகிறோம்.",
              "visit": "வணக்கம் {name}! சந்திப்புக்கு நேரம் முடிவு செய்ய விரும்புகிறீர்களா? உங்களுக்கு வசதியான நாள் மற்றும் நேரத்தைச் சொல்லுங்கள்.",
              "pricing": "வணக்கம் {name}, உங்கள் பட்ஜெட்டுக்கு ஏற்ற விலை விவரங்களை அனுப்பலாம். பேச வசதியான நேரம் எது?"},
    "te-IN": {"welcome": "నమస్కారం {name}, {business} పట్ల ఆసక్తి చూపినందుకు ధన్యవాదాలు! మీతో మాట్లాడటానికి అనుకూలమైన సమయం ఎప్పుడు?",
              "follow_up": "నమస్కారం {name}, మీ విచారణ గురించి మళ్ళీ సంప్రదిస్తున్నాము. ఏమైనా ప్రశ్నలు ఉంటే చెప్పండి, సహాయం చేస్తాము.",
              "visit": "నమస్కారం {name}! కలవడానికి సమయం నిర్ణయించుకోవాలనుకుంటున్నారా? మీకు అనుకూలమైన రోజు, సమయం చెప్పండి.",
              "pricing": "నమస్కారం {name}, మీ బడ్జెట్‌కు తగిన ధరల వివరాలు పంపగలము. మాట్లాడటానికి అనుకూలమైన సమయం ఎప్పుడు?"},
    "gu-IN": {"welcome": "નમસ્તે {name}, {business} માં રસ બતાવવા બદલ આભાર! તમારી સાથે વાત કરવાનો અનુકૂળ સમય ક્યારે છે?",
              "follow_up": "નમસ્તે {name}, તમારી પૂછપરછ વિશે ફરી સંપર્ક કરી રહ્યા છીએ. કોઈ પ્રશ્ન હોય તો જણાવો, અમે મદદ કરીશું.",
              "visit": "નમસ્તે {name}! શું તમે મળવાનો સમય નક્કી કરવા માંગો છો? તમારી અનુકૂળતાનો દિવસ અને સમય જણાવો.",
              "pricing": "નમસ્તે {name}, તમારા બજેટ મુજબ કિંમતોની વિગતો મોકલી શકીએ છીએ. વાત કરવાનો અનુકૂળ સમય ક્યારે છે?"},
    "kn-IN": {"welcome": "ನಮಸ್ಕಾರ {name}, {business} ಬಗ್ಗೆ ಆಸಕ್ತಿ ತೋರಿಸಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು! ನಿಮ್ಮೊಂದಿಗೆ ಮಾತನಾಡಲು ಅನುಕೂಲಕರ ಸಮಯ ಯಾವಾಗ?",
              "follow_up": "ನಮಸ್ಕಾರ {name}, ನಿಮ್ಮ ವಿಚಾರಣೆಯ ಬಗ್ಗೆ ಮತ್ತೆ ಸಂಪರ್ಕಿಸುತ್ತಿದ್ದೇವೆ. ಏನಾದರೂ ಪ್ರಶ್ನೆಗಳಿದ್ದರೆ ತಿಳಿಸಿ, ಸಹಾಯ ಮಾಡುತ್ತೇವೆ.",
              "visit": "ನಮಸ್ಕಾರ {name}! ಭೇಟಿಗೆ ಸಮಯ ನಿಗದಿಪಡಿಸಲು ಬಯಸುವಿರಾ? ನಿಮಗೆ ಅನುಕೂಲವಾದ ದಿನ ಮತ್ತು ಸಮಯ ತಿಳಿಸಿ.",
              "pricing": "ನಮಸ್ಕಾರ {name}, ನಿಮ್ಮ ಬಜೆಟ್‌ಗೆ ತಕ್ಕ ಬೆಲೆಯ ವಿವರಗಳನ್ನು ಕಳುಹಿಸಬಹುದು. ಮಾತನಾಡಲು ಅನುಕೂಲಕರ ಸಮಯ ಯಾವಾಗ?"},
    "ml-IN": {"welcome": "നമസ്കാരം {name}, {business}-ൽ താൽപ്പര്യം കാണിച്ചതിന് നന്ദി! നിങ്ങളുമായി സംസാരിക്കാൻ സൗകര്യപ്രദമായ സമയം എപ്പോഴാണ്?",
              "follow_up": "നമസ്കാരം {name}, നിങ്ങളുടെ അന്വേഷണത്തെക്കുറിച്ച് വീണ്ടും ബന്ധപ്പെടുകയാണ്. എന്തെങ്കിലും ചോദ്യങ്ങളുണ്ടെങ്കിൽ അറിയിക്കൂ, ഞങ്ങൾ സഹായിക്കാം.",
              "visit": "നമസ്കാരം {name}! കൂടിക്കാഴ്ചയ്ക്ക് സമയം നിശ്ചയിക്കാൻ ആഗ്രഹിക്കുന്നുണ്ടോ? നിങ്ങൾക്ക് സൗകര്യമുള്ള ദിവസവും സമയവും അറിയിക്കൂ.",
              "pricing": "നമസ്കാരം {name}, നിങ്ങളുടെ ബജറ്റിന് അനുയോജ്യമായ വില വിവരങ്ങൾ അയയ്ക്കാം. സംസാരിക്കാൻ സൗകര്യപ്രദമായ സമയം എപ്പോഴാണ്?"},
    "mr-IN": {"welcome": "नमस्कार {name}, {business} मध्ये रस दाखवल्याबद्दल धन्यवाद! तुमच्याशी बोलण्यासाठी सोयीची वेळ कोणती?",
              "follow_up": "नमस्कार {name}, तुमच्या चौकशीबद्दल पुन्हा संपर्क करत आहोत. काही प्रश्न असल्यास कळवा, आम्ही मदत करू.",
              "visit": "नमस्कार {name}! भेटीची वेळ ठरवायची आहे का? तुमच्या सोयीचा दिवस आणि वेळ कळवा.",
              "pricing": "नमस्कार {name}, तुमच्या बजेटनुसार किमतींची माहिती पाठवू शकतो. बोलण्यासाठी सोयीची वेळ कोणती?"},
    "pa-IN": {"welcome": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ {name}, {business} ਵਿੱਚ ਦਿਲਚਸਪੀ ਦਿਖਾਉਣ ਲਈ ਧੰਨਵਾਦ! ਤੁਹਾਡੇ ਨਾਲ ਗੱਲ ਕਰਨ ਦਾ ਸਹੀ ਸਮਾਂ ਕਦੋਂ ਹੈ?",
              "follow_up": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ {name}, ਤੁਹਾਡੀ ਪੁੱਛਗਿੱਛ ਬਾਰੇ ਦੁਬਾਰਾ ਸੰਪਰਕ ਕਰ ਰਹੇ ਹਾਂ। ਕੋਈ ਸਵਾਲ ਹੋਵੇ ਤਾਂ ਦੱਸੋ, ਅਸੀਂ ਮਦਦ ਕਰਾਂਗੇ।",
              "visit": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ {name}! ਕੀ ਤੁਸੀਂ ਮਿਲਣ ਦਾ ਸਮਾਂ ਤੈਅ ਕਰਨਾ ਚਾਹੋਗੇ? ਆਪਣੀ ਸਹੂਲਤ ਦਾ ਦਿਨ ਅਤੇ ਸਮਾਂ ਦੱਸੋ।",
              "pricing": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ {name}, ਅਸੀਂ ਤੁਹਾਡੇ ਬਜਟ ਮੁਤਾਬਕ ਕੀਮਤਾਂ ਦੀ ਜਾਣਕਾਰੀ ਭੇਜ ਸਕਦੇ ਹਾਂ। ਗੱਲ ਕਰਨ ਦਾ ਸਹੀ ਸਮਾਂ ਕਦੋਂ ਹੈ?"},
    "od-IN": {"welcome": "ନମସ୍କାର {name}, {business} ପ୍ରତି ଆଗ୍ରହ ଦେଖାଇଥିବାରୁ ଧନ୍ୟବାଦ! ଆପଣଙ୍କ ସହ କଥା ହେବା ପାଇଁ ସୁବିଧାଜନକ ସମୟ କେବେ?",
              "follow_up": "ନମସ୍କାର {name}, ଆପଣଙ୍କ ପଚରାଉଚରା ବିଷୟରେ ପୁଣି ଯୋଗାଯୋଗ କରୁଛୁ। କିଛି ପ୍ରଶ୍ନ ଥିଲେ ଜଣାନ୍ତୁ, ଆମେ ସାହାଯ୍ୟ କରିବୁ।",
              "visit": "ନମସ୍କାର {name}! ଆପଣ ଦେଖା କରିବାର ସମୟ ସ୍ଥିର କରିବାକୁ ଚାହାଁନ୍ତି କି? ଆପଣଙ୍କ ସୁବିଧାର ଦିନ ଓ ସମୟ ଜଣାନ୍ତୁ।",
              "pricing": "ନମସ୍କାର {name}, ଆପଣଙ୍କ ବଜେଟ୍ ଅନୁସାରେ ଦାମ୍‌ର ବିବରଣୀ ପଠାଇପାରିବୁ। କଥା ହେବା ପାଇଁ ସୁବିଧାଜନକ ସମୟ କେବେ?"},
}
INTENTS = {
    "welcome": "Thank them for their enquiry and ask when is a good time to talk.",
    "reply": "Answer what they last wrote as helpfully as you can from what you know, and suggest a next step.",
    "follow_up": "Politely follow up on their enquiry and ask if they have questions.",
    "visit": "Invite them to schedule a visit or appointment and ask for a day and time that suits them.",
    "pricing": "Offer to share pricing that fits their budget and ask when is a good time to talk.",
}


def first_name(lead: Lead) -> str:
    return (lead.name or "").split(" ")[0] or "there"


def ready_made(language: str, intent: str, lead: Lead, business: str) -> str:
    table = READY.get(language) or READY["en"]
    text = table.get("follow_up" if intent == "reply" else intent) or table["welcome"]
    return text.replace("{name}", first_name(lead)).replace("{business}", business or "us")


def fits_language(text: str, language: str) -> bool:
    """The AI sometimes answers in English: only accept a draft written in the script the lead uses."""
    pattern = SCRIPT_OF.get(language)
    if pattern:
        return len(re.findall(pattern, text)) >= 5
    if language in ("en", "hi-Latn"):
        return not any(re.search(p, text) for p in SCRIPT_OF.values())
    return True


def _clean(text: str) -> str:
    text = (text or "").strip().strip('"“”').strip()
    text = re.sub(r"^(message|reply)\s*:\s*", "", text, flags=re.I)
    return text[:1000]


def _write(db: Session, user: User, prompt: str, system: str) -> Optional[str]:
    from .ai_engine import agent_writer
    write = agent_writer(db, user.id, "lead_replier")
    if not write:
        return None
    try:
        return write(prompt, system, 400)
    except Exception:
        return None


def language_instruction(language: str) -> str:
    name = LANGUAGES.get(language, "English")
    if language == "hi-Latn":
        return "Hinglish: Hindi written in English letters, the way people type on WhatsApp (e.g. 'Aapka visit kab fix karein?')"
    if language in SCRIPT_OF:
        return f"{name}, in {name} script"
    return name


def translate(db: Session, user: User, text: str, language: str) -> Optional[str]:
    """A message the business wrote in English, in the lead's language, or None."""
    if language == "en":
        return text
    out = _clean(_write(db, user, f"Translate this WhatsApp message into {language_instruction(language)}. Keep names, "
                                   f"the business name, numbers and links exactly as they are.\n\n{text}",
                        "You translate short business WhatsApp messages. Reply with the translated message only."))
    return out if out and fits_language(out, language) else None


def history(db: Session, lead: Lead, limit: int = 8) -> list:
    if not lead.phone:
        return []
    rows = list(db.scalars(select(WaMessage).where(WaMessage.user_id == lead.user_id, WaMessage.contact.in_(_contacts(lead.phone)),
                                                   WaMessage.status != "failed").order_by(WaMessage.id.desc()).limit(limit)))
    return list(reversed(rows))


def auto_intent(db: Session, lead: Lead) -> str:
    act = activity(db, lead.user_id, [lead])[lead.id]
    if act["last_in_at"] and (not act["last_out_at"] or act["last_out_at"] < act["last_in_at"]):
        return "reply"
    return "follow_up" if act["last_out_at"] else "welcome"


def send_state(db: Session, user: User, lead: Lead, language: str, intent: str) -> dict:
    """Can free text reach this lead now, or only an approved template?"""
    integ = get_integration(db, user.id, "whatsapp")
    open_ = window_open(db, user.id, lead.phone) if lead.phone else False
    tpl = template_for(integ, "follow_up" if intent == "follow_up" else "first", language) if integ and not open_ else None
    note = ""
    if integ and not open_:
        note = (f"{first_name(lead)} hasn't messaged you in the last 24 hours, so WhatsApp only delivers an approved "
                "template from AIMVA. " + (f"AIMVA can send your approved template “{tpl['name']}”, or you can send this "
                                           "draft from your own WhatsApp." if tpl else
                                           "Send this draft from your own WhatsApp instead, or add your approved template "
                                           "in WhatsApp settings."))
    return {"connected": bool(integ), "window_open": open_, "needs_template": bool(integ and not open_),
            "template": tpl["name"] if tpl else "", "note": note, "wa_number": wa_number(lead.phone)}


def draft(db: Session, user: User, lead: Lead, intent: str = "auto") -> dict:
    """A short WhatsApp reply in the lead's language, plus whether WhatsApp will let it through."""
    language = language_of(db, lead)
    if intent not in INTENTS:
        intent = auto_intent(db, lead)
    business = user.company or user.name or ""
    lines = [f"{'Lead' if m.direction == 'in' else 'Business'}: {m.body[:400]}" for m in history(db, lead)
             if not m.body.startswith("[template:")]
    system = ("You write WhatsApp replies for a small business in India to a sales lead. Write only the message itself: "
              "1 to 3 short sentences, warm and plain, at most one emoji, no markdown, no sign-off. Use the lead's first "
              "name. Never invent prices, dates, addresses, discounts or promises that are not given below. "
              f"Write in {language_instruction(language)}.")
    prompt = "\n".join(filter(None, [
        f"Business: {business or 'our business'}" + (f" ({user.industry})" if getattr(user, "industry", "") else ""),
        f"Lead's first name: {first_name(lead)}",
        f"What they asked when they enquired: {lead.message[:600]}" if lead.message else "",
        "Conversation so far:\n" + "\n".join(lines) if lines else "",
        f"Task: {INTENTS[intent]}",
    ]))
    text = _clean(_write(db, user, prompt, system))
    by = "ai"
    if not text or not fits_language(text, language):
        text, by = ready_made(language, intent, lead, business), "ready_made"
    return {"text": text, "language": language, "language_name": LANGUAGES.get(language, "English"), "intent": intent,
            "by": by, **send_state(db, user, lead, language, intent)}
