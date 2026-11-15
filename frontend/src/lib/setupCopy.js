// The words of /start in the owner's chosen language (design.md 3.1: a small picker beside the step count).
// Hindi, Telugu and Tamil are Claude translations: they need a native speaker's check before launch.
// Only setup follows the choice today; the rest of the app is still English.
const KEY = "aimva_ui_lang";

export const UI_LANGS = [["en", "English"], ["hi", "हिन्दी"], ["te", "తెలుగు"], ["ta", "தமிழ்"]];

const COPY = {
  en: {
    of: "of", skip: "Skip", cancel: "Cancel", back: "Back", continue: "Continue",
    idea: "What are you building or selling?",
    ideaHint: "Write it the way you'd tell a friend. Any language is fine.",
    ideaPlaceholder: "A dental clinic in Kukatpally. Implants and braces, mostly families nearby.",
    addLink: "Add your website or Instagram (optional)",
    settingUp: "Setting up your workspace…",
    customer_languages: "Which languages do your customers speak?",
    customer_area: "Where are your customers?",
    reply_owner: "When someone asks about you, who should reply first?",
    ads_today: "Are you running ads right now?",
    reply: { aimva: "AIMVA replies, then hands to me", me: "Only me", someone: "My team" },
    ads: { self: "Yes", none: "Not yet" },
    areas: { "All of India": "All of India", "Online only": "Online only" },
    language: "Language",
  },
  hi: {
    of: "में से", skip: "छोड़ें", cancel: "रद्द करें", back: "पीछे", continue: "आगे",
    idea: "आप क्या बना रहे हैं या बेच रहे हैं?",
    ideaHint: "जैसे किसी दोस्त को बताते हैं, वैसे लिखिए। कोई भी भाषा चलेगी।",
    ideaPlaceholder: "कुकटपल्ली में एक डेंटल क्लिनिक। इम्प्लांट और ब्रेसेस, ज़्यादातर आस-पास के परिवार।",
    addLink: "अपनी वेबसाइट या इंस्टाग्राम जोड़ें (ज़रूरी नहीं)",
    settingUp: "आपका वर्कस्पेस तैयार हो रहा है…",
    customer_languages: "आपके ग्राहक कौन-सी भाषाएँ बोलते हैं?",
    customer_area: "आपके ग्राहक कहाँ हैं?",
    reply_owner: "कोई आपके बारे में पूछे, तो सबसे पहले कौन जवाब दे?",
    ads_today: "क्या आप अभी विज्ञापन चला रहे हैं?",
    reply: { aimva: "AIMVA जवाब दे, फिर मुझे सौंपे", me: "सिर्फ़ मैं", someone: "मेरी टीम" },
    ads: { self: "हाँ", none: "अभी नहीं" },
    areas: { "All of India": "पूरा भारत", "Online only": "सिर्फ़ ऑनलाइन" },
    language: "भाषा",
  },
  te: {
    of: "లో", skip: "దాటవేయి", cancel: "రద్దు", back: "వెనక్కి", continue: "కొనసాగించు",
    idea: "మీరు ఏమి తయారు చేస్తున్నారు లేదా అమ్ముతున్నారు?",
    ideaHint: "స్నేహితుడికి చెప్పినట్టు రాయండి. ఏ భాష అయినా పర్వాలేదు.",
    ideaPlaceholder: "కూకట్‌పల్లిలో ఒక డెంటల్ క్లినిక్. ఇంప్లాంట్స్, బ్రేసెస్, ఎక్కువగా దగ్గరలోని కుటుంబాలు.",
    addLink: "మీ వెబ్‌సైట్ లేదా ఇన్‌స్టాగ్రామ్ జోడించండి (ఐచ్ఛికం)",
    settingUp: "మీ వర్క్‌స్పేస్ సిద్ధమవుతోంది…",
    customer_languages: "మీ కస్టమర్లు ఏ భాషలు మాట్లాడతారు?",
    customer_area: "మీ కస్టమర్లు ఎక్కడ ఉన్నారు?",
    reply_owner: "ఎవరైనా మీ గురించి అడిగితే, ముందుగా ఎవరు జవాబివ్వాలి?",
    ads_today: "మీరు ఇప్పుడు ప్రకటనలు నడుపుతున్నారా?",
    reply: { aimva: "AIMVA జవాబిచ్చి, తర్వాత నాకు అప్పగిస్తుంది", me: "నేను మాత్రమే", someone: "నా టీమ్" },
    ads: { self: "అవును", none: "ఇంకా లేదు" },
    areas: { "All of India": "భారతదేశం అంతా", "Online only": "ఆన్‌లైన్ మాత్రమే" },
    language: "భాష",
  },
  ta: {
    of: "இல்", skip: "தவிர்", cancel: "ரத்து", back: "பின்", continue: "தொடர்",
    idea: "நீங்கள் என்ன உருவாக்குகிறீர்கள் அல்லது விற்கிறீர்கள்?",
    ideaHint: "நண்பரிடம் சொல்வது போல எழுதுங்கள். எந்த மொழியும் சரி.",
    ideaPlaceholder: "குகட்பள்ளியில் ஒரு பல் மருத்துவமனை. இம்ப்ளாண்ட், பிரேஸஸ், பெரும்பாலும் அருகிலுள்ள குடும்பங்கள்.",
    addLink: "உங்கள் இணையதளம் அல்லது இன்ஸ்டாகிராம் சேர்க்கவும் (விருப்பம்)",
    settingUp: "உங்கள் பணியிடம் தயாராகிறது…",
    customer_languages: "உங்கள் வாடிக்கையாளர்கள் எந்த மொழிகள் பேசுகிறார்கள்?",
    customer_area: "உங்கள் வாடிக்கையாளர்கள் எங்கே இருக்கிறார்கள்?",
    reply_owner: "யாராவது உங்களைப் பற்றி கேட்டால், முதலில் யார் பதில் சொல்ல வேண்டும்?",
    ads_today: "நீங்கள் இப்போது விளம்பரங்கள் நடத்துகிறீர்களா?",
    reply: { aimva: "AIMVA பதில் சொல்லி, பிறகு என்னிடம் தரும்", me: "நான் மட்டும்", someone: "என் குழு" },
    ads: { self: "ஆம்", none: "இன்னும் இல்லை" },
    areas: { "All of India": "இந்தியா முழுவதும்", "Online only": "ஆன்லைன் மட்டும்" },
    language: "மொழி",
  },
};

export function readUiLang() {
  try { const v = localStorage.getItem(KEY); return COPY[v] ? v : "en"; } catch { return "en"; }
}

export function saveUiLang(code) {
  try { localStorage.setItem(KEY, code); } catch { /* private window: the choice lasts for this visit */ }
  document.documentElement.lang = code;
}

export const setupCopy = (code) => COPY[code] || COPY.en;
