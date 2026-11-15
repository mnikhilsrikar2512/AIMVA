"""Reading a new owner's idea ("Dental clinic in Kukatpally doing implants") into a business profile, without an AI model.

POST /api/start uses this to fill the profile, pick the modules (design.md 3.4 / PRD R-6) and decide which one or two
questions are still worth asking. Rules, not a model, so the reveal is predictable and testable. People write in
English, Hinglish, Hindi, Telugu, Tamil and Kannada, with or without a link.

The word lists were written against scripts/prompt_sets/ideas_dev.tsv and scored on ideas_test.tsv and the fresh sets:
run `python scripts/idea_bench.py` after any change here. Nothing here is ever shown to the owner as "what we
understood"; the app just shows the result.
"""
import re
from typing import Optional

KINDS = ("local_service", "product_seller", "personal_brand", "b2b", "idea_only", "unclear")

# Revealed modules in order; the first starts by itself (design.md 3.4). Leads, Results, Settings are always there.
REVEAL = {
    "local_service": ["page", "whatsapp", "calls", "pictures", "campaigns"],
    "product_seller": ["pictures", "page", "whatsapp", "campaigns", "videos"],
    "personal_brand": ["page", "pictures", "videos", "whatsapp"],
    "b2b": ["page", "campaigns", "calls", "pictures"],
    "idea_only": ["page", "pictures", "whatsapp"],
    "unclear": ["page", "pictures", "whatsapp"],
}
MODULES = ("page", "whatsapp", "calls", "pictures", "campaigns", "videos")

# ---- places -----------------------------------------------------------------------------------------------
# city -> (spellings, including Indian scripts; the languages its customers usually write in, most likely first)
CITIES = {
    "Hyderabad": (["hyderabad", "secunderabad", "हैदराबाद", "హైదరాబాద్", "హైదరాబాదు"], ["te-IN", "hi-Latn", "en"]),
    "Bengaluru": (["bengaluru", "bangalore", "बेंगलुरु", "బెంగళూరు", "ಬೆಂಗಳೂರು", "ಬೆಂಗಳೂರಿನ"], ["kn-IN", "en", "hi-Latn"]),
    "Chennai": (["chennai", "madras", "चेन्नई", "చెన్నై", "சென்னை"], ["ta-IN", "en"]),
    "Mumbai": (["mumbai", "bombay", "thane", "navi mumbai", "मुंबई", "मुम्बई"], ["mr-IN", "hi-Latn", "en"]),
    "Pune": (["pune", "पुणे"], ["mr-IN", "hi-Latn", "en"]),
    "Nagpur": (["nagpur", "नागपुर", "नागपूर"], ["mr-IN", "hi-Latn", "en"]),
    "Delhi": (["delhi", "new delhi", "दिल्ली"], ["hi-Latn", "hi-IN", "en"]),
    "Noida": (["noida", "नोएडा"], ["hi-Latn", "hi-IN", "en"]),
    "Gurugram": (["gurugram", "gurgaon", "गुरुग्राम", "गुड़गांव"], ["hi-Latn", "en", "hi-IN"]),
    "Kolkata": (["kolkata", "calcutta", "कोलकाता", "কলকাতা"], ["bn-IN", "en", "hi-Latn"]),
    "Ahmedabad": (["ahmedabad", "अहमदाबाद", "અમદાવાદ"], ["gu-IN", "hi-Latn", "en"]),
    "Surat": (["surat", "सूरत", "સુરત"], ["gu-IN", "hi-Latn", "en"]),
    "Rajkot": (["rajkot", "राजकोट", "રાજકોટ"], ["gu-IN", "hi-Latn", "en"]),
    "Jaipur": (["jaipur", "जयपुर"], ["hi-IN", "hi-Latn", "en"]),
    "Lucknow": (["lucknow", "लखनऊ"], ["hi-IN", "hi-Latn", "ur-IN"]),
    "Kanpur": (["kanpur", "कानपुर"], ["hi-IN", "hi-Latn", "en"]),
    "Patna": (["patna", "पटना"], ["hi-IN", "hi-Latn", "en"]),
    "Indore": (["indore", "इंदौर"], ["hi-IN", "hi-Latn", "en"]),
    "Bhopal": (["bhopal", "भोपाल"], ["hi-IN", "hi-Latn", "en"]),
    "Kota": (["kota", "कोटा"], ["hi-IN", "hi-Latn", "en"]),
    "Chandigarh": (["chandigarh", "चंडीगढ़", "ਚੰਡੀਗੜ੍ਹ"], ["pa-IN", "hi-Latn", "en"]),
    "Ludhiana": (["ludhiana", "लुधियाना", "ਲੁਧਿਆਣਾ"], ["pa-IN", "hi-Latn", "en"]),
    "Amritsar": (["amritsar", "अमृतसर", "ਅੰਮ੍ਰਿਤਸਰ"], ["pa-IN", "hi-Latn", "en"]),
    "Kochi": (["kochi", "cochin", "ernakulam", "കൊച്ചി"], ["ml-IN", "en"]),
    "Thiruvananthapuram": (["thiruvananthapuram", "trivandrum", "തിരുവനന്തപുരം"], ["ml-IN", "en"]),
    "Coimbatore": (["coimbatore", "கோயம்புத்தூர்", "கோவை"], ["ta-IN", "en"]),
    "Madurai": (["madurai", "மதுரை"], ["ta-IN", "en"]),
    "Mysuru": (["mysuru", "mysore", "ಮೈಸೂರು"], ["kn-IN", "en"]),
    "Visakhapatnam": (["visakhapatnam", "vizag", "విశాఖపట్నం", "వైజాగ్"], ["te-IN", "en"]),
    "Vijayawada": (["vijayawada", "విజయవాడ"], ["te-IN", "en"]),
    "Guntur": (["guntur", "గుంటూరు"], ["te-IN", "en"]),
    "Warangal": (["warangal", "వరంగల్"], ["te-IN", "en"]),
    "Bhubaneswar": (["bhubaneswar", "ଭୁବନେଶ୍ୱର"], ["od-IN", "en"]),
    "Goa": (["goa", "panaji", "panjim"], ["en", "hi-Latn"]),
}
# Well-known areas people name instead of the city.
AREAS = {
    "Hyderabad": ["kukatpally", "gachibowli", "madhapur", "hitech city", "ameerpet", "kondapur", "banjara hills",
                  "jubilee hills", "begumpet", "dilsukhnagar", "miyapur", "kompally", "manikonda", "lb nagar", "uppal"],
    "Bengaluru": ["indiranagar", "whitefield", "koramangala", "jayanagar", "sarjapur", "hsr layout", "btm layout",
                  "electronic city", "marathahalli", "malleshwaram", "hebbal", "yelahanka", "jp nagar", "bellandur"],
    "Chennai": ["anna nagar", "t nagar", "t. nagar", "velachery", "adyar", "tambaram", "porur", "omr", "mylapore"],
    "Mumbai": ["andheri", "bandra", "powai", "borivali", "dadar", "juhu", "goregaon", "malad", "chembur", "vashi",
               "lower parel", "colaba"],
    "Pune": ["kothrud", "hinjewadi", "baner", "wakad", "viman nagar", "kharadi", "hadapsar", "aundh"],
    "Delhi": ["laxmi nagar", "hauz khas", "connaught place", "karol bagh", "dwarka", "rohini", "saket",
              "lajpat nagar", "janakpuri", "pitampura"],
    "Kolkata": ["salt lake", "new town", "park street", "behala", "howrah"],
    "Lucknow": ["gomti nagar", "hazratganj", "aliganj"],
    "Ahmedabad": ["satellite", "navrangpura", "bopal", "sg highway"],
    "Noida": ["sector 18", "sector 62"],
}
# Indian scripts and the language customers then write in.
SCRIPT_LANG = [(r"[ఀ-౿]", "te-IN"), (r"[஀-௿]", "ta-IN"), (r"[ಀ-೿]", "kn-IN"), (r"[ഀ-ൿ]", "ml-IN"), (r"[ঀ-৿]", "bn-IN"),
               (r"[઀-૿]", "gu-IN"), (r"[਀-੿]", "pa-IN"), (r"[଀-୿]", "od-IN"), (r"[ऀ-ॿ]", "hi-IN")]
LANG_WORDS = {"telugu": "te-IN", "tamil": "ta-IN", "kannada": "kn-IN", "malayalam": "ml-IN", "bengali": "bn-IN",
              "bangla": "bn-IN", "gujarati": "gu-IN", "punjabi": "pa-IN", "odia": "od-IN", "marathi": "mr-IN",
              "hindi": "hi-IN", "hinglish": "hi-Latn", "urdu": "ur-IN"}

# ---- kinds of business ------------------------------------------------------------------------------------
IDEA_ONLY = re.compile(
    r"\b(?:want(?:ing)? to (?:start|open|launch|begin|set up|sell)|plan(?:ning)? to|thinking (?:of|about)|"
    r"(?:would|'d) like to (?:start|open|launch)|i have an idea|idea(?=\s*:)|idea (?:for|of)|hoping to (?:start|open)|"
    r"about to (?:start|open|launch)|going to (?:start|open|launch)|not (?:started|launched) yet|planning (?:an?|my)|"
    r"shuru karna|shuru karni|kholna|kholni|start karna)\b"
    r"|खोलना चाह|शुरू करना चाह|शुरू करने|खोलने की|ప్రారంభించాల|మొదలుపెట్టాల|పెట్టాలనుకుంట|தொடங்க விரும்|ಪ್ರಾರಂಭಿಸಲು", re.I)

# (pattern, kind, industry). Earlier rows win ties; "industry" None means "keep the kind's default".
CUES = [
    # personal brands: one person selling themselves
    (r"\b(?:influencer|creator|youtuber|youtube channel|blogger|vlogger|podcaster|my (?:own |personal )?brand|"
     r"personal brand|life coach|career coach|business coach|mindfulness|motivational speaker|speaker|author|"
     r"freelance(?:r)?|independent (?:financial )?(?:advisor|consultant)|financial advisor|stand-?up|comedian|"
     r"recipe reels|followers|i'?m a (?!\w+ (?:company|firm|brand))|nutritionist|dietitian|know me|my own (?:instagram|page|channel)|"
     r"astrologer|vastu|numerologist|tarot)\b", "personal_brand", None),
    # B2B
    (r"\b(?:saas|software|crm|erp|app for|platform for|b2b|manufactur\w*|wholesale\w*|supplier|distributor|"
     r"exporter|export\w*|staffing|recruitment|logistics|warehous\w*|corporate gifting|corporates|for companies|"
     r"for (?:small )?businesses|for retailers|for restaurants|for brands|enterprise|industrial|it services|"
     r"agency for|contracts? for|contract manufacturing|bulk|"
     r"we supply|supplies to|to processors|facility management|it parks|smes?|"
     r"for (?:\w+ )?(?:factories|schools|banks|clinics|hospitals|hotels|offices|builders|developers|startups|industries))\b",
     "b2b", None),
    # product sellers
    (r"\b(?:d2c|online store|e-?commerce|shop online|sell(?:s|ing)? (?:on|online|via|through)|we sell|i sell|"
     r"selling (?!\w* ?(?:flats|plots|homes|villas|houses|property|properties))|sold online|ship(?:ping)?|deliver(?:ed|y)? "
     r"(?:to|across|pan|same|to your)|home delivery|boutique|showroom|brand of|products?|handmade|homemade|"
     r"sarees?|jewell?ery|clothes|clothing|ethnic wear|t-?shirts|hoodies|pickles?|achaar|snacks?|hampers?|"
     r"dry fruits|oils?|soaps?|skincare|candles|cakes?|bakery|accessories shop|furniture|kapde|instagram pe|"
     r"amazon|flipkart|meesho|online|our website|subscription|delivered|kits?|dealer\w*|shoes|bags|toys|ghee|chocolates?|"
     r"perfumes?|cosmetics|courier|shop|store|mart|outlet|nursery|plants|phones?|iphones?|mobiles?|laptops|electronics|"
     r"gadgets)\b"
     r"|बेचते|बेचती|बेचना|साड़ि|गहने|बेकरी|अम्मु|అమ్ముత|అమ్మే|చీరల|చీరలు|పచ్చళ్ళ|పచ్చళ్ల|విక్రయ|ಮಾರಾಟ", "product_seller", "retail"),
    # local services, by industry
    (r"\b(?:clinic|dental|dentist|hospital|physio\w*|eye|skin|hair clinic|laser|homeopath\w*|ayurveda clinic|"
     r"diagnostic|lab|doctor|dr\.?|gynaec\w*|pediatric\w*|paediatric\w*|orthopaedic|ortho|cardio\w*|ivf|"
     r"pharmacy|medical|panchakarma|wellness centre|veterinary|vet)\b"
     r"|क्लिनिक|अस्पताल|डेंटल|हॉस्पिटल|క్లినిక్|హాస్పిటల్|ఆసుపత్రి|డెంటల్|மருத்துவ|கிளினிக்|ಕ್ಲಿನಿಕ್|ಆಸ್ಪತ್ರೆ", "local_service",
     "healthcare"),
    (r"\b(?:coaching|tuition|tutor\w*|classes|institute|academy|school|play ?school|daycare|ielts|neet|jee|iit|upsc|"
     r"spoken english|course|courses|training centre|music classes|dance classes|driving school|students|preschool|"
     r"pre-school|montessori|kindergarten|teach\w*)\b"
     r"|कोचिंग|ट्यूशन|स्कूल|కోచింగ్|ట్యూషన్|స్కూల్|విద్యార్థ|பயிற்சி|ಕೋಚಿಂಗ್", "local_service", "education"),
    (r"\b(?:real estate|realtor|builder|developer|property|properties|flats?|apartments?|villas?|plots?|bhk|"
     r"residential project|resale|land|office space|commercial space|for lease|on lease|for rent|on rent|gated community)\b"
     r"|फ्लैट|प्रॉपर्टी|प्लॉट|ఫ్లాట్|ప్లాట్|రియల్ ఎస్టేట్|வீடு|மனை|ಫ್ಲಾಟ್|ನಿವೇಶನ", "local_service", "real_estate"),
    (r"\b(?:salon|parlou?r|spa|makeup|gym|fitness studio|crossfit|yoga|studio|repair|service centre|services?|"
     r"plumb\w*|electrician|pest control|cleaning|car wash|detailing|interior\w*|photograph\w*|restaurant|cafe|"
     r"caf[eé]|dhaba|catering|tiffin|cloud kitchen|kitchen|food truck|hotel|resort|travel|tours?|event\w*|wedding|"
     r"laundry|tailor\w*|grooming|pet|co-?working|movers|packers|rentals?|beauty|mehendi|mehndi|tattoo|bridal|"
     r"banquet|venue|hall|decorat\w*|nannies|maids)\b"
     r"|सैलून|पार्लर|जिम|रेस्टोरेंट|कैफे|ब्यूटी|సెలూన్|పార్లర్|జిమ్|రెస్టారెంట్|సలూన్|బ్యూటీ|ಸಲೂನ್|ಬ್ಯೂಟಿ|சலூன்|அழகு நிலைய", "local_service", "services"),
]
_CUES = [(re.compile(p, re.I), kind, ind) for p, kind, ind in CUES]
# One person's trade. Without a place or a premises it's a personal brand; "artist in Secunderabad" is a local service.
ROLE = re.compile(r"\b(?:artist|trainer|consultant|dancer|singer|musician|astrologer|coach|therapist|counsell?or|"
                  r"designer|stylist|writer|anchor|chef|instructor|advisor|adviser|psychologist|psychiatrist|reader)\b", re.I)
PLACE = re.compile(r"\b(?:studio|clinic|centre|center|academy|institute|shop|salon|company|firm|agency|school|"
                   r"restaurant|hospital)\b", re.I)
SAAS = re.compile(r"\b(?:saas|software|crm|erp|app\b|platform|inventory management)\b", re.I)


def _norm(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def find_city(text: str) -> Optional[str]:
    low = (text or "").lower()
    for city, (names, _) in CITIES.items():
        for n in names:
            if (re.search(rf"(?<![a-z]){re.escape(n)}(?![a-z])", low) if n.isascii()
                    else n in text or (len(n) > 4 and n[:-1] in text)):
                return city
    for city, areas in AREAS.items():
        if any(re.search(rf"(?<![a-z]){re.escape(a)}(?![a-z])", low) for a in areas):
            return city
    return None


def find_area(text: str, city: Optional[str]) -> str:
    """The neighbourhood, when one is named ("Kukatpally"), for the reveal header."""
    low = (text or "").lower()
    for c, areas in AREAS.items():
        for a in areas:
            if re.search(rf"(?<![a-z]){re.escape(a)}(?![a-z])", low) and (city in (None, c)):
                return a.title()
    m = re.search(r"\bin ([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b", text or "")
    if m and m.group(1) != city and not find_city(m.group(1)) and m.group(1).lower() not in LANG_WORDS:
        return m.group(1)
    return ""


def customer_languages(text: str, city: Optional[str]) -> tuple:
    """(languages, sure): from a language the owner names, the script they wrote in, or their city."""
    langs = []
    for w, code in LANG_WORDS.items():
        if re.search(rf"\b(?:in|speak\w*|customers?|students?)\b[^.]{{0,25}}\b{w}\b", text or "", re.I):
            langs.append(code)
    for pattern, code in SCRIPT_LANG:
        if len(re.findall(pattern, text or "")) >= 3:
            if code == "hi-IN" and city in ("Mumbai", "Pune", "Nagpur"):
                code = "mr-IN"
            langs.append(code)
            break
    sure = bool(langs) or bool(city)
    if city:
        langs += CITIES[city][1]
    if not langs:
        langs = ["en", "hi-Latn"]
    out = []
    for code in langs + ["en"]:
        if code not in out:
            out.append(code)
    return out[:3], sure


def find_name(text: str) -> str:
    """A business name the owner typed: "Dr. Rao's Dental, implants..." or "called Spice Route"."""
    t = _norm(text)
    m = re.search(r"\b(?:called|named|name is|brand name is)\s+[\"“']?([A-Z0-9][\w&'’.\- ]{1,50}?)[\"”']?(?:[,.;]|\s+(?:in|at|for|and)\b|$)", t)
    if m:
        return m.group(1).strip()
    m = re.search(r"[\"“]([^\"”]{2,60})[\"”]", t)
    if m:
        return m.group(1).strip()
    head = re.split(r"[,–—\-:|]| in | at | for ", t, maxsplit=1)[0].strip()
    if re.search(r"\b(?:Dr\.?|[A-Z][a-z]+['’]s)\s", head) and 1 < len(head.split()) <= 6 and not head.lower().startswith(("i ", "we ")):
        return head
    return ""


def read_kind(text: str) -> tuple:
    """(kind, industry) for an idea."""
    t = _norm(text)
    words = re.findall(r"\w+", t)
    hits = [(kind, ind) for rx, kind, ind in _CUES if rx.search(t)]
    if IDEA_ONLY.search(t):
        ind = next((i for k, i in hits if i in ("healthcare", "education", "services") and k == "local_service"), None)
        if any(k == "product_seller" for k, _ in hits) and not ind:
            ind = "retail"
        if ind == "services" and re.search(r"\b(?:cafe|caf[eé]|restaurant|kitchen|food truck|tiffin|bakery|grooming|pet|co-?working)\b"
                                           r"|कैफे|रेस्टोरेंट|బేకరీ|बेकरी", t, re.I):
            ind = "other"
        if re.search(r"\bbakery\b|बेकरी", t, re.I):
            ind = "other"
        return "idea_only", ind or "other"
    if (not hits and not ROLE.search(t)) or len(words) < 2:
        return "unclear", "other"
    kinds = [k for k, _ in hits]
    role = ROLE.search(t)
    if role and not find_city(t) and not PLACE.search(t) and "b2b" not in kinds:
        kinds.insert(0, "personal_brand")
    if "personal_brand" in kinds:
        ind = ("healthcare" if re.search(r"\b(?:dr\.?|doctor|gynaec\w*|nutritionist|dietitian|physio\w*|psycholog\w*|"
                                          r"psychiatr\w*|therap\w*)\b", t, re.I) else "other")
        return "personal_brand", ind
    if "b2b" in kinds:
        return "b2b", "saas" if SAAS.search(t) else "other"
    if "product_seller" in kinds:
        # "Cake shop with home delivery" sells products; "Restaurant ... home delivery" is still a local service.
        local = [i for k, i in hits if k == "local_service"]
        if local and local[0] in ("healthcare", "education", "real_estate"):
            return "local_service", local[0]
        if local and re.search(r"\b(?:restaurant|cafe|caf[eé]|dhaba|hotel)\b", t, re.I) and not re.search(r"\b(?:cakes?|bakery)\b", t, re.I):
            return "local_service", "services"
        return "product_seller", "retail"
    return "local_service", next(i for k, i in hits if k == "local_service")


# ---- the AI reads first, the rules are the backup (owner decision 2026-11-15) -------------------------------
AI_SYSTEM = ("You sort small Indian businesses into one kind. Reply with the kind's key only, nothing else.\n"
             "local_service: customers visit or book a service nearby (clinic, salon, gym, coaching, real estate, "
             "restaurant, repairs, events).\n"
             "product_seller: sells physical products, online or from a shop (D2C brand, boutique, bakery with delivery, "
             "pickles, phones).\n"
             "personal_brand: one person selling their own name or skill (creator, coach, consultant, doctor's own brand, "
             "artist, astrologer).\n"
             "b2b: sells to other businesses (software, manufacturing, wholesale, supply, staffing, facility services).\n"
             "idea_only: the business doesn't exist yet (wants to start, planning, thinking of).\n"
             "unclear: not enough to tell.\n"
             "The idea may be in English, Hinglish, Hindi, Telugu, Tamil, Kannada or another Indian language.")
_KIND_WORD = re.compile(r"\b(" + "|".join(KINDS) + r")\b")


def ai_kind(write, idea: str) -> Optional[str]:
    """The AI writer's kind for an idea, or None. Only an answer naming exactly one kind counts."""
    try:
        answer = write(f"Business idea: {idea[:600]}\n\nKind:", AI_SYSTEM, 12)
    except Exception:
        return None
    found = set(_KIND_WORD.findall((answer or "").lower()))
    return found.pop() if len(found) == 1 else None


def industry_for(kind: str, text: str, rules_kind: str, rules_industry: str) -> str:
    """Keep the industry consistent with the kind when the AI and the rules disagree."""
    if kind == rules_kind:
        return rules_industry
    if kind == "product_seller":
        return "retail"
    if kind == "b2b":
        return "saas" if SAAS.search(text) else "other"
    if kind == "personal_brand":
        return "healthcare" if rules_industry == "healthcare" else "other"
    if kind == "local_service":
        return rules_industry if rules_industry in ("healthcare", "education", "real_estate", "services") else "services"
    if kind == "idea_only":
        return rules_industry
    return "other"


def read_idea(idea: str, link: str = "", write=None) -> dict:
    """Profile, gaps and modules for one idea. With an AI writer, its kind wins when it names a valid one; the rules
    fill everything else (city, area, languages, name) and stand in whenever the AI is missing or off-script.
    `link` is only a hint (a site usually means a running business)."""
    text = _norm(idea)
    kind, industry = read_kind(text)
    if write and text:
        ai = ai_kind(write, text)
        if ai and not (ai == "unclear" and kind != "unclear"):  # the AI shrugging never undoes a clear rules answer
            kind, industry = ai, industry_for(ai, text, kind, industry)
    city = find_city(idea or "")
    langs, langs_sure = customer_languages(idea or "", city)
    profile = {
        "name": find_name(idea or ""),
        "kind": kind,
        "industry": industry,
        "city": city or "",
        "area": find_area(idea or "", city),
        "offer": text[:200],
        "customer_languages": langs,
    }
    gaps = []
    if not langs_sure:
        gaps.append("customer_languages")  # the edge: ask first whenever it's a guess (PRD S-7)
    if not city and kind not in ("b2b", "personal_brand"):
        gaps.append("customer_area")
    gaps += ["reply_owner", "ads_today"]
    return {"profile": profile, "gaps": gaps, "modules": REVEAL[kind]}


# ---- Home prompt routing (POST /api/route) ----------------------------------------------------------------
# Which module a sentence typed on Home belongs to. Earlier rows win: "make a video ad" is a video, "make an image for
# my ad" is a picture, "run ads" is a campaign. Scored with scripts/idea_bench.py on routes_*.tsv.
ROUTES = [
    ("results", r"\bhow (?:are|is) my\b|\bhow much did i spend\b|\breports?\b|\bresults?\b|\banalytics\b|\bwhich ad brought\b|"
                r"\bperforming\b|\broi\b"),
    ("videos", r"\bvideos?\b|\breels?\b|\bshorts\b|\byoutube\b|\banimation\b|वीडियो|రీల్|వీడియో"),
    ("pictures", r"\bposters?\b|\bbanners?\b|\bflyers?\b|\blogo\b|\bphotos?\b|\bpictures?\b|\bimages?\b|\bcreatives?\b|"
                 r"\b(?:instagram|insta|facebook) post\b|\bthumbnail\b|पोस्टर|फोटो|तस्वीर|ఫోటో|పోస్టర్|போஸ்டர்|புகைப்பட"),
    ("whatsapp", r"\bwhats ?app\b|\bbroadcast\b|\bfollow[ -]?up message\b|\bmessage (?:the |my |all )?(?:leads|everyone|customers)\b|"
                 r"\breply to\b|व्हाट्सएप|వాట్సాప్"),
    ("calls", r"\bcall(?:s|ing)?\b|\bcall[ -]?back\b|\bvoice\b|\bphone\b|\bring\b"),
    ("campaigns", r"\bads?\b|\bcampaigns?\b|\bboost\b|\bpromote\b|\bbudget\b|\bgoogle ads\b|\bmeta\b|\bspend\b|विज्ञापन|ప్రకటన"),
    ("page", r"\bwebsite\b|\bweb ?page\b|\bsite\b|\blanding\b|\bpage\b|\bheadline\b|\bsection\b|\bcontact form\b|वेबसाइट|"
             r"వెబ్‌సైట్|వెబ్సైట్|இணையதள"),
    ("leads", r"\bleads?\b|\benquir(?:y|ies)\b|\binquir(?:y|ies)\b|\bcustomers\b|\bwho is waiting\b|\bwaiting for a reply\b"),
]
_ROUTES = [(m, re.compile(p, re.I)) for m, p in ROUTES]


def route(text: str, fallback: str = "page") -> str:
    t = text or ""
    # "show my leads" / "reply to leads on WhatsApp": WhatsApp beats leads, leads beats a bare "call".
    if re.search(r"^\s*(?:show|list|see|who)\b", t, re.I) and re.search(r"\bleads?\b|\benquir", t, re.I) and not re.search(r"whats ?app", t, re.I):
        return "leads"
    for module, rx in _ROUTES:
        if rx.search(t):
            return module
    return fallback
