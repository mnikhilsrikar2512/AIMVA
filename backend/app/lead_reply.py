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
from .speech import SCRIPTS as _SCRIPTS

WINDOW = timedelta(hours=24)
CLOSED = {"won", "lost"}

LANGUAGES = {  # code -> name shown to the business
    "en": "English", "hi-IN": "Hindi", "hi-Latn": "Hinglish", "bn-IN": "Bengali", "ta-IN": "Tamil", "te-IN": "Telugu",
    "gu-IN": "Gujarati", "kn-IN": "Kannada", "ml-IN": "Malayalam", "mr-IN": "Marathi", "pa-IN": "Punjabi", "od-IN": "Odia",
    "ur-IN": "Urdu", "ar-SA": "Arabic", "te-Latn": "Telugu (English letters)", "ta-Latn": "Tamil (English letters)",
}
LATIN = ("en", "hi-Latn", "te-Latn", "ta-Latn")  # replies written in English letters
SCRIPT_OF = {  # languages whose reply must be in their own script
    "hi-IN": r"[ऀ-ॿ]", "mr-IN": r"[ऀ-ॿ]", "bn-IN": r"[ঀ-৿]", "pa-IN": r"[਀-੿]",
    "gu-IN": r"[઀-૿]", "od-IN": r"[଀-୿]", "ta-IN": r"[஀-௿]", "te-IN": r"[ఀ-౿]",
    "kn-IN": r"[ಀ-೿]", "ml-IN": r"[ഀ-ൿ]", "ur-IN": r"[؀-ۿ]", "ar-SA": r"[؀-ۿ]",
}
# Words Marathi uses where Hindi uses something else (Hindi: है, मुझे, कितना, कीमत, जानकारी, कल, बताइए, नहीं...).
_MARATHI = {"आहे", "आहेत", "आहात", "आहोत", "मला", "तुम्ही", "तुमचा", "तुमची", "तुमचे", "तुमच्या", "आम्ही", "आमचा", "आमचे",
            "पाहिजे", "काय", "कधी", "किती", "किंमत", "माहिती", "उद्या", "सांगा", "करा", "पाठवा", "द्या", "घ्या", "हवा",
            "हवे", "हवी", "नको", "नाही", "कुठे", "येईल", "येऊ", "लागेल", "लागतील", "शकतो", "शकता", "आणि", "पण", "बोलू",
            "बघायचे", "झाले", "झाली", "होईल", "आता", "ना", "भेटता", "रुपये"}
_MARATHI_ENDINGS = re.compile(r"(?:ायला|ायचे|ायचं|ायची|तील|ाल)$")
# Arabic-script letters that Urdu uses and Arabic doesn't (ٹ ڈ ڑ ں ے ھ پ چ ژ گ and the Urdu forms of k and y).
_URDU = re.compile(r"[ٹڈڑںےۓھپچژگکی]")
# Hindi written in English letters. These are almost never English words; "hai" as the first word is usually a
# misspelt "hi" ("Hai sir"), so it doesn't count there.
_HINGLISH = {"hai", "hain", "kya", "kitna", "kitne", "kitni", "chahiye", "chahte", "chahenge", "mujhe", "aap", "aapka",
             "aapki", "aapke", "kab", "kaise", "kahan", "kaun", "kyun", "nahi", "nahin", "nai", "haan", "han", "karna",
             "karo", "karein", "kijiye", "dijiye", "raha", "rahi", "rahe", "rahega", "mera", "meri", "mere", "maine",
             "humein", "hum", "tum", "abhi", "batao", "bata", "bataiye", "bataye", "bhejo", "bhej", "bhejiye", "milega",
             "milegi", "milenge", "milte", "sakte", "sakta", "sakti", "wala", "wali", "accha", "acha", "theek", "thik",
             "lagega", "lagegi", "lagenge", "jayega", "jayegi", "hoga", "hogi", "aaya", "aaunga", "aaungi", "aa", "kal",
             "aaj", "shaam", "subah", "jaldi", "thoda", "paise", "rupaye", "baat", "bolo", "samajh", "ghar", "yeh", "woh",
             "tha", "thi", "baar", "tak", "hoon", "bhara", "liye", "mein", "aur", "bhi", "zaroor", "kuch", "koi", "jaana",
             "dekhna", "karunga", "karungi", "jaunga", "jaungi", "aaungi", "bataunga", "bhejunga", "milunga", "dekhunga",
             "bolunga", "rakhunga", "sochunga", "karenge", "thanda", "thandi"}
# Count only next to a real Hindi word: short words that are also names, places or English ("Ka Nagar", "Ho Chi Minh").
_HINGLISH_WEAK = {"bhai", "bhaiya", "ji", "sahab", "yaar", "plz", "sir", "madam", "ka", "ki", "ke", "ko", "ye", "sa", "pe",
                  "ho", "hu", "hun", "ek", "din", "aa", "h", "anna", "akka", "amma", "bro", "ma", "mam"}
# Telugu and Tamil written in English letters ("rate entha andi", "price evlo"). Words both languages share (anna,
# akka, rendu, mari) or that are English or names (sari, nan, oka) aren't here, or are only weak.
_TELUGU = {"andi", "entha", "enta", "enti", "emiti", "ela", "elaa", "ekkada", "eppudu", "enduku", "evaru", "naaku",
           "naku", "nenu", "meeru", "miru", "mee", "meeku", "meku", "memu", "manam", "maaku", "kavali", "kaavali",
           "kavala", "cheppandi", "cheppu", "cheppara", "cheyandi", "cheyali", "chestanu", "chesta", "chestaru",
           "chesaru", "chesanu", "undi", "unnaru", "unnara", "unnav", "unnanu", "unda", "undha", "undaa", "unte",
           "ledu", "leda", "ledhu", "levu", "vaddu", "vaddhu", "kaadu", "kadu", "avunu", "sare", "saare", "baagundi",
           "bagundi", "baaga", "baga", "bagunnara", "inka", "inkaa", "ippudu", "ipudu", "ivala", "ivvala", "eeroju",
           "repu", "ninna", "tarvata", "taruvata", "taravata", "pampandi", "pampu", "pampinchandi", "vastanu",
           "vasthanu", "vastaru", "vastundi", "vachi", "vacha", "vachanu", "raavali", "randi", "raa", "matladandi",
           "matladatanu", "matladali", "maatladali", "maatladandi", "dorukutunda", "dorukutundi", "telusu", "teliyadu",
           "chala", "chaala", "konchem", "koncham", "emaina", "emanna", "ekkuva", "takkuva", "dabbulu", "dabbu", "maa",
           "intlo", "intiki", "garu", "gaaru", "kosam", "gurinchi", "kuda", "kooda", "okka", "saayantram", "sayantram",
           "poddunna", "podduna", "roju", "ikkada", "akkada", "aithe", "ayithe", "kaani", "ante", "babu", "thammudu",
           "chudandi", "chusi", "chustanu", "istanu", "ivvandi", "ichi", "dhara", "vivaralu"}
_TAMIL = {"evlo", "evvalavu", "evalavu", "enna", "ennaa", "epdi", "eppadi", "enga", "engae", "eppo", "eppodhu", "yen",
          "yaaru", "enakku", "enaku", "naan", "neenga", "neengal", "unga", "ungal", "ungalukku", "ungaluku", "ungakitta",
          "venum", "venam", "vendum", "vendam", "sollunga", "sollu", "solunga", "pannunga", "pannu", "pannalama",
          "pannalaama", "panren", "panrom", "irukku", "iruku", "irukka", "iruka", "irukeenga", "irukinga", "irundha",
          "illa", "illai", "illaya", "seri", "nalla", "nallaa", "romba", "konjam", "innum", "ippo", "ippa", "inniku",
          "innaiku", "innaikku", "naalaikku", "nalaiku", "naalaiku", "netru", "nethu", "apram", "appuram", "aprm",
          "anuppunga", "anuppu", "anupunga", "varen", "varalaama", "varalama", "varuveenga", "varum", "vaanga",
          "vanga", "ponga", "pesunga", "pesuren", "pesalam", "pesalaam", "theriyum", "theriyadhu", "theriyala",
          "kidaikkuma", "kidaikuma", "kidaikum", "kidaikkum", "edhavadhu", "ethavathu", "vilai", "kaasu", "panam",
          "veedu", "kadai", "thambi", "machan", "kudunga", "kodunga", "paakalam", "paakanum", "paarunga", "ellam",
          "ellaam", "adhu", "idhu", "athu", "ithu", "oru", "moonu", "saayangalam", "saayankalam", "kaalaila",
          "kalaila", "maalai", "mattum", "thaan", "dhaan", "sollalaam", "mudiyuma", "mudiyum", "aagum", "aaguma",
          "eppavum", "yenna", "inga", "anga"}
_TELUGU_END = re.compile(r"(?:andi|tunda|thunda|tundi|thundi|stanu|sthanu|staru|stharu|atanu|ataru|aledu)$")
_TAMIL_END = re.compile(r"(?:unga|eenga|inga|laama|lama|kkuma|kkum|kiren|uren|aaren|aanga)$")
# Plain-English words: a message that is mostly English with one such word is English with a name in it
# ("Andi is my name, call me").
_ENGLISH = {"is", "my", "the", "a", "an", "to", "me", "you", "your", "i", "it", "can", "will", "please", "call", "name",
            "and", "of", "for", "on", "at", "this", "that", "what", "when", "where", "how", "do", "does", "are", "was",
            "be", "have", "has", "want", "need", "get", "available", "still", "come"}
# "reply in Tamil", "call me in Hindi", "speak Telugu", "Hindi me baat karo" — unless it's "I don't speak Hindi".
_LANG_NAMES = {"english": "en", "hindi": "hi-IN", "bengali": "bn-IN", "bangla": "bn-IN", "tamil": "ta-IN",
               "telugu": "te-IN", "gujarati": "gu-IN", "kannada": "kn-IN", "malayalam": "ml-IN", "marathi": "mr-IN",
               "punjabi": "pa-IN", "odia": "od-IN", "oriya": "od-IN", "urdu": "ur-IN"}
_LANG = "|".join(_LANG_NAMES)
_ASK = re.compile(rf"\b(?:reply|replies|respond|answer|write|message|text|in|speak|talk|explain|call(?:back)?(?: me)?)"
                  rf"\s+(?:to me\s+|me\s+|only\s+)?(?:in\s+)?({_LANG})\b|\b({_LANG})\s+(?:is fine|works|please|only|is ok)\b", re.I)
_NOT = re.compile(rf"\b(?:don'?t|do not|can'?t|cannot|no|not|never mind)\b[^.?!,]{{0,20}}\b({_LANG})\b", re.I)


def _asked_language(text: str) -> Optional[str]:
    """A language the lead asks for in words. A later ask wins ("Tamil? Never mind, English works")."""
    refused = {m.group(1).lower() for m in _NOT.finditer(text)}
    asks = [(m.group(1) or m.group(2)).lower() for m in _ASK.finditer(text)]
    asks = [a for a in asks if a not in refused]
    return _LANG_NAMES[asks[-1]] if asks else None


def _script(text: str) -> Optional[str]:
    """The script most of the message is written in, if at least two letters of it are there."""
    counts = {code: len(re.findall(pattern, text)) for pattern, code in _SCRIPTS}
    code, n = max(counts.items(), key=lambda kv: kv[1])
    if n < 2:
        return None
    if code == "ar-SA" and _URDU.search(text):
        return "ur-IN"
    if code == "hi-IN":
        words = re.findall(r"[ऀ-ॿ]+", text)
        if set(words) & _MARATHI or any(_MARATHI_ENDINGS.search(w) for w in words if len(w) > 4):
            return "mr-IN"
    return code


def _latin(text: str) -> Optional[str]:
    """Hindi, Telugu or Tamil typed in English letters: the language with the most of its own words, when there is
    a clear winner and enough of them (two, or one next to a short Hindi/Telugu/Tamil word, or in a short message)."""
    words = re.findall(r"[a-z]+", text.lower())
    if words[:1] == ["hai"]:
        words = words[1:]
    counts = {"hi-Latn": 0, "te-Latn": 0, "ta-Latn": 0}
    for w in words:
        if w in _HINGLISH:  # a listed word belongs to its language; endings only decide words no list has
            counts["hi-Latn"] += 1
        elif w in _TELUGU:
            counts["te-Latn"] += 1
        elif w in _TAMIL:
            counts["ta-Latn"] += 1
        elif len(w) > 5 and _TELUGU_END.search(w):
            counts["te-Latn"] += 1
        elif len(w) > 5 and _TAMIL_END.search(w):
            counts["ta-Latn"] += 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    (code, strong), (_, second) = ranked[0], ranked[1]
    if strong == 0 or strong == second:
        return None
    weak = sum(w in _HINGLISH_WEAK for w in words)
    if strong >= 2:
        return code
    if code != "hi-Latn" and sum(w in _ENGLISH for w in words) >= 4:
        return None
    return code if weak >= 1 or len(words) <= 6 else None


def _hinglish(text: str) -> bool:
    return _latin(text) == "hi-Latn"


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
    """The language a message is written in, or asks for, when it is clear enough to act on. Scored on
    scripts/prompt_sets/leads_*.tsv: run `python scripts/lead_language_bench.py` after any change here."""
    if not text:
        return None
    asked = _asked_language(text)
    if asked:
        return asked
    code = _script(text)
    if code:
        return code
    return _latin(text)


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
    base = "en" if language in LATIN else language.split("-")[0]
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
    # Telugu and Tamil the way people type them on WhatsApp. Written by Claude, not yet checked by a native speaker.
    "te-Latn": {"welcome": "Namaskaram {name}, {business} meeda aasakti chupinchinanduku dhanyavaadalu! Meetho maatladataniki ye time baguntundi?",
                "follow_up": "Namaskaram {name}, mee enquiry gurinchi follow up chestunnam. Emaina questions unte cheppandi, help chestam.",
                "visit": "Namaskaram {name}! Visit ki time fix cheddama? Meeku veelaina roju, time cheppandi.",
                "pricing": "Namaskaram {name}, mee budget ki taggattu prices pampagalam. Maatladataniki ye time baguntundi?"},
    "ta-Latn": {"welcome": "Vanakkam {name}, {business} mela interest kaattinadhukku nandri! Ungakitta pesa endha neram vasathiya irukkum?",
                "follow_up": "Vanakkam {name}, unga enquiry pathi follow up panrom. Edhavadhu kelvi irundha sollunga, help panrom.",
                "visit": "Vanakkam {name}! Visit ku neram fix pannalaama? Ungalukku vasathiyana naal, neram sollunga.",
                "pricing": "Vanakkam {name}, unga budget ku yetha prices anuppalaam. Pesa endha neram vasathiya irukkum?"},
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
    "ur-IN": {"welcome": "السلام علیکم {name}، {business} میں دلچسپی کا شکریہ! آپ سے بات کرنے کا مناسب وقت کب ہوگا؟",
              "follow_up": "السلام علیکم {name}، آپ کی پوچھ گچھ کے بارے میں دوبارہ رابطہ کر رہے ہیں۔ کوئی سوال ہو تو بتائیں، ہم مدد کریں گے۔",
              "visit": "السلام علیکم {name}! کیا آپ ملاقات کا وقت طے کرنا چاہیں گے؟ اپنی سہولت کا دن اور وقت بتائیں۔",
              "pricing": "السلام علیکم {name}، ہم آپ کے بجٹ کے مطابق قیمتوں کی تفصیل بھیج سکتے ہیں۔ بات کرنے کا مناسب وقت کب ہوگا؟"},
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
    if language in LATIN:
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
    if language == "te-Latn":
        return "Telugu written in English letters, the way people type on WhatsApp (e.g. 'Mee visit eppudu fix cheddam?')"
    if language == "ta-Latn":
        return "Tamil written in English letters, the way people type on WhatsApp (e.g. 'Unga visit eppo fix pannalaam?')"
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


def owner_brief(db: Session, user: User) -> str:
    """The owner's standing instructions for WhatsApp replies (the WhatsApp module's prompt), if they saved any."""
    from .models import AgentSetting
    s = db.scalar(select(AgentSetting).where(AgentSetting.user_id == user.id, AgentSetting.kind == "concierge"))
    return str(((s.config or {}) if s else {}).get("brief") or "").strip()


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
    brief = owner_brief(db, user)
    from .brand_book import build, copy_rules
    system += " " + copy_rules(build(db, user))
    prompt = "\n".join(filter(None, [
        f"Business: {business or 'our business'}" + (f" ({user.industry})" if getattr(user, "industry", "") else ""),
        f"The business owner's instructions for replies (follow them; facts here may be used): {brief}" if brief else "",
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
