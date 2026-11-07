"""Predefined templates for every module, and the schema each module's template must follow.

A template is a starting point: picking one fills the module's form and everything stays editable.
Text may use {business}, {industry} and {tagline}; they are filled from the user's profile and Brand Kit
when templates are listed. WhatsApp templates keep {name}, which is the person being messaged.
Industries use the playbook keys from app.quality (empty list = suits any business).
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

Module = Literal["image", "video", "website", "ads", "voice", "whatsapp"]
MODULES = ("image", "video", "website", "ads", "voice", "whatsapp")
MODULE_LABELS = {"image": "Image generation", "video": "Video generation", "website": "Website builder", "ads": "Ad campaigns",
                 "voice": "Voice agent", "whatsapp": "WhatsApp messages"}


# ---- what a template may contain, per module ------------------------------------------------------------------
class ImageT(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    style: Literal["", "photographic", "cinematic", "illustration", "3d_render", "flat", "minimal_product", "watercolor", "anime", "neon"] = ""
    size: Literal["1:1", "4:5", "9:16", "16:9", "1.91:1"] = "1:1"
    negative_prompt: str = Field("", max_length=1000)


class VideoT(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"] = "16:9"
    camera: Literal["", "static", "push_in", "pull_out", "pan_left", "pan_right", "orbit", "drone", "handheld", "tilt_up"] = ""
    style: Literal["", "photographic", "cinematic", "illustration", "3d_render", "flat", "minimal_product", "watercolor", "anime", "neon"] = ""
    negative_prompt: str = Field("", max_length=1000)


class WebsiteT(BaseModel):
    page_type: Literal["lead_gen", "product", "service", "event", "real_estate", "restaurant", "portfolio", "app"] = "lead_gen"
    layout: Literal["auto", "split", "centered", "immersive", "editorial", "bento"] = "auto"
    decor: Literal["auto", "blobs", "grid", "dots", "plain"] = "auto"
    look: Literal["modern", "minimal", "bold", "elegant", "playful", "corporate"] = "modern"
    theme: Literal["light", "dark"] = "light"
    font: Literal["jakarta", "inter", "serif", "rounded", "grotesk"] = "jakarta"
    sections: List[Literal["features", "about", "gallery", "testimonials", "pricing", "faq", "contact_info"]] = Field(default_factory=lambda: ["features"], max_length=7)
    form_fields: List[Literal["name", "phone", "email", "message", "city", "budget", "preferred_date", "company"]] = Field(
        default_factory=lambda: ["name", "phone", "email"], max_length=8)
    contact_mode: Literal["voice_agent", "own_phone", "both"] = "voice_agent"
    cta: str = Field("Get a free quote", min_length=2, max_length=60)
    form_title: str = Field("", max_length=80)
    offer: str = Field("", max_length=160)
    headline: str = Field("", max_length=200)
    subheadline: str = Field("", max_length=300)
    features: List[str] = Field(default_factory=list, max_length=8)

    @field_validator("form_fields")
    @classmethod
    def _contact(cls, v):
        if "phone" not in v and "email" not in v:
            raise ValueError("A page template's form needs a phone or email field.")
        return list(dict.fromkeys(v))


class Creative(BaseModel):
    headline: str = Field("", max_length=120)
    text: str = Field("", max_length=600)
    cta: str = Field("Learn more", max_length=30)


class Targeting(BaseModel):
    locations: str = Field("", max_length=200)
    age_min: int = Field(18, ge=13, le=65)
    age_max: int = Field(65, ge=13, le=65)
    interests: str = Field("", max_length=300)


class LeadFormT(BaseModel):
    fields: List[Literal["full_name", "email", "phone_number", "city", "company_name", "job_title"]] = Field(
        default_factory=lambda: ["full_name", "email", "phone_number"], max_length=6)


class AdsT(BaseModel):
    platform: Literal["any", "meta", "google", "linkedin"] = "any"
    objective: Literal["leads", "traffic"] = "leads"
    daily_budget: float = Field(500, ge=0, le=1e6)
    creative: Creative = Field(default_factory=Creative)
    targeting: Targeting = Field(default_factory=Targeting)
    lead_form: LeadFormT = Field(default_factory=LeadFormT)


class VoiceT(BaseModel):
    language: str = Field("en-US", max_length=20)
    greeting: str = Field(min_length=5, max_length=600)
    instructions: str = Field("", max_length=1500)
    questions: List[str] = Field(max_length=10)  # at least two, checked below with a friendlier message

    @field_validator("questions")
    @classmethod
    def _q(cls, v):
        v = [q.strip()[:300] for q in v if q and q.strip()]
        if len(v) < 2:
            raise ValueError("A voice agent template needs at least two questions.")
        return v


class WhatsAppT(BaseModel):
    body: str = Field(min_length=5, max_length=1000)


SCHEMAS = {"image": ImageT, "video": VideoT, "website": WebsiteT, "ads": AdsT, "voice": VoiceT, "whatsapp": WhatsAppT}


def validate_payload(module: str, payload: dict) -> dict:
    """Normalise a template payload for its module; raises ValueError with a readable message."""
    try:
        return SCHEMAS[module](**(payload or {})).model_dump()
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(x) for x in first.get("loc", ()) if x != "__root__")
        raise ValueError(f"{where + ': ' if where else ''}{first.get('msg', 'invalid value')}".replace("Value error, ", ""))
    except KeyError:
        raise ValueError("Unknown module.")


# ---- the catalogue -------------------------------------------------------------------------------------------
def T(key, module, name, description, payload, industries=(), tags=()):
    return {"key": key, "module": module, "name": name, "description": description, "industries": list(industries),
            "tags": list(tags), "payload": validate_payload(module, payload)}


NO_TEXT = "text, letters, watermark, logo, blurry, distorted hands, extra fingers"

CATALOG = [
    # ---------------- images ----------------
    T("img-property-hero", "image", "Property hero shot", "Bright wide-angle exterior with clean sky and space for a headline.",
      {"prompt": "Modern residential building exterior at golden hour, landscaped entrance, clear blue sky, wide angle, inviting, generous empty space at the top for a headline",
       "style": "photographic", "size": "16:9", "negative_prompt": NO_TEXT}, ["real_estate"], ["ad", "hero"]),
    T("img-interior-lifestyle", "image", "Lived-in interior", "Warm living room that helps buyers picture the home.",
      {"prompt": "Sunlit modern living room with a family relaxing, soft natural light, warm tones, real estate listing photo",
       "style": "photographic", "size": "4:5", "negative_prompt": NO_TEXT}, ["real_estate"], ["social"]),
    T("img-clinic-trust", "image", "Calm clinic welcome", "Reassuring clinic scene: friendly staff, clean space.",
      {"prompt": "Friendly doctor greeting a patient in a bright, clean modern clinic, soft daylight, calm and reassuring mood",
       "style": "photographic", "size": "1:1", "negative_prompt": NO_TEXT}, ["healthcare"], ["social"]),
    T("img-product-studio", "image", "Studio product shot", "Minimal hero image for a product on a seamless background.",
      {"prompt": "Premium product on a pastel stone pedestal, seamless background, soft shadows, minimal composition with space for text",
       "style": "minimal_product", "size": "1:1", "negative_prompt": NO_TEXT}, ["retail", "saas"], ["ad"]),
    T("img-food-closeup", "image", "Signature dish close-up", "Appetising close-up for menus and Instagram.",
      {"prompt": "Close-up of a signature dish on a rustic wooden table, steam rising, warm ambient light, shallow depth of field",
       "style": "photographic", "size": "4:5", "negative_prompt": NO_TEXT}, ["restaurant"], ["social"]),
    T("img-classroom", "image", "Engaged classroom", "Students learning together: for demo-class and admission ads.",
      {"prompt": "Students engaged in a bright modern classroom, teacher explaining at a whiteboard, natural light, candid",
       "style": "photographic", "size": "1.91:1", "negative_prompt": NO_TEXT}, ["education"], ["ad"]),
    T("img-saas-dashboard", "image", "Product on a laptop", "Your software on a laptop in a tidy workspace.",
      {"prompt": "Clean analytics dashboard on a laptop screen, minimal desk, plant, soft gradient background, modern workspace",
       "style": "3d_render", "size": "16:9", "negative_prompt": "watermark, blurry, distorted"}, ["saas"], ["ad", "hero"]),
    T("img-story-offer", "image", "Story offer background", "Vertical background with room for an offer and button.",
      {"prompt": "Soft abstract gradient background in brand colours with gentle light flares, lots of empty space in the middle for an offer",
       "style": "flat", "size": "9:16", "negative_prompt": NO_TEXT}, [], ["story", "offer"]),
    T("img-team-at-work", "image", "Team at work", "Your service in action, for trust and about sections.",
      {"prompt": "Professional technician helping a smiling customer at home, natural light, authentic and trustworthy",
       "style": "photographic", "size": "4:5", "negative_prompt": NO_TEXT}, ["services"], ["social"]),

    # ---------------- videos ----------------
    T("vid-property-flyover", "video", "Property drone flyover", "Slow aerial reveal of a project and its surroundings.",
      {"prompt": "Slow aerial drone flyover of a modern residential tower at sunset, landscaped grounds, city skyline in the background",
       "aspect_ratio": "16:9", "camera": "drone", "style": "cinematic", "negative_prompt": "text, watermark, flicker"}, ["real_estate"], ["hero"]),
    T("vid-walkthrough", "video", "Home walkthrough reel", "Vertical push-in through a bright interior for Reels.",
      {"prompt": "Smooth push-in through a bright modern apartment living room towards a balcony with a view, warm afternoon light",
       "aspect_ratio": "9:16", "camera": "push_in", "style": "cinematic", "negative_prompt": "text, watermark, warping"}, ["real_estate"], ["reel"]),
    T("vid-product-orbit", "video", "Product 360° orbit", "Slow orbit around a product on a pedestal.",
      {"prompt": "Slow orbit around a premium product on a rotating pedestal, studio lighting, soft reflections, seamless background",
       "aspect_ratio": "1:1", "camera": "orbit", "style": "minimal_product", "negative_prompt": "text, watermark"}, ["retail"], ["ad"]),
    T("vid-clinic-welcome", "video", "Clinic welcome", "Calm walk into a welcoming reception.",
      {"prompt": "Gentle handheld walk into a calm, bright clinic reception, friendly receptionist smiling, soft daylight",
       "aspect_ratio": "9:16", "camera": "handheld", "style": "photographic", "negative_prompt": "text, watermark"}, ["healthcare"], ["reel"]),
    T("vid-food-sizzle", "video", "Kitchen sizzle", "Close-up of a dish being plated, steam and sizzle.",
      {"prompt": "Close-up of a chef plating a sizzling dish, steam rising, warm kitchen light, shallow depth of field",
       "aspect_ratio": "9:16", "camera": "static", "style": "cinematic", "negative_prompt": "text, watermark"}, ["restaurant"], ["reel"]),
    T("vid-brand-reveal", "video", "Brand reveal", "Abstract gradient motion for intros and outros.",
      {"prompt": "Elegant flowing gradient shapes in soft brand colours slowly morphing, light particles, calm and premium",
       "aspect_ratio": "16:9", "camera": "pull_out", "style": "3d_render", "negative_prompt": "text, letters, watermark"}, [], ["intro"]),
    T("vid-classroom", "video", "Classroom moment", "Candid pan across an engaged class.",
      {"prompt": "Smooth pan across students raising hands in a bright classroom, teacher smiling, natural light, candid",
       "aspect_ratio": "16:9", "camera": "pan_right", "style": "photographic", "negative_prompt": "text, watermark"}, ["education"], ["ad"]),

    # ---------------- websites ----------------
    T("web-site-visit", "website", "Site-visit booking", "Photo-led page that books site visits, with price and FAQs.",
      {"page_type": "real_estate", "layout": "immersive", "look": "elegant", "font": "serif", "cta": "Book a site visit",
       "form_title": "Book a free site visit", "offer": "Free site visit this weekend",
       "sections": ["features", "gallery", "pricing", "faq", "contact_info"], "form_fields": ["name", "phone", "preferred_date", "budget"]},
      ["real_estate"]),
    T("web-appointments", "website", "Appointment booking", "Calm, trustworthy page for clinics that books appointments.",
      {"page_type": "service", "layout": "centered", "look": "minimal", "font": "inter", "cta": "Book an appointment",
       "form_title": "Book an appointment", "sections": ["features", "about", "faq", "contact_info"],
       "form_fields": ["name", "phone", "preferred_date", "message"]}, ["healthcare"]),
    T("web-demo-class", "website", "Free demo class", "Bento page for coaching centres with fees and FAQs.",
      {"page_type": "lead_gen", "layout": "bento", "look": "playful", "font": "rounded", "cta": "Book a free demo",
       "form_title": "Book a free demo class", "offer": "Free demo class", "sections": ["features", "pricing", "faq"],
       "form_fields": ["name", "phone", "email", "message"]}, ["education"]),
    T("web-saas-demo", "website", "Software demo request", "Editorial SaaS page: benefits, pricing, demo form.",
      {"page_type": "app", "layout": "editorial", "look": "corporate", "font": "grotesk", "cta": "Get a demo",
       "form_title": "See it in action", "sections": ["features", "pricing", "faq"], "form_fields": ["name", "email", "company", "message"]},
      ["saas"]),
    T("web-launch-offer", "website", "Launch offer", "Bold one-offer page with a countdown-style message.",
      {"page_type": "product", "layout": "split", "look": "bold", "font": "grotesk", "cta": "Claim my offer", "offer": "Launch offer for the first 50 customers",
       "sections": ["features", "gallery", "faq"], "form_fields": ["name", "phone", "email"]}, ["retail"]),
    T("web-table-booking", "website", "Table reservations", "Atmospheric restaurant page with gallery and timings.",
      {"page_type": "restaurant", "layout": "immersive", "look": "elegant", "theme": "dark", "font": "serif", "cta": "Reserve a table",
       "form_title": "Reserve a table", "sections": ["features", "gallery", "contact_info"], "form_fields": ["name", "phone", "preferred_date", "message"]},
      ["restaurant"]),
    T("web-free-quote", "website", "Free quote", "Straightforward local-services page that collects quote requests.",
      {"page_type": "service", "layout": "split", "look": "modern", "font": "jakarta", "cta": "Get a free quote", "offer": "Free quote in 24 hours",
       "sections": ["features", "about", "faq", "contact_info"], "form_fields": ["name", "phone", "city", "message"]}, ["services"]),
    T("web-event", "website", "Event registration", "Centred page for webinars, open houses and launches.",
      {"page_type": "event", "layout": "centered", "look": "modern", "font": "jakarta", "cta": "Register now", "form_title": "Save your seat",
       "sections": ["features", "about", "faq"], "form_fields": ["name", "email", "phone"]}, []),

    # ---------------- ads ----------------
    T("ads-site-visit-meta", "ads", "Weekend site visits (Meta)", "Lead-form ad for property site visits, 28–55 in your city.",
      {"platform": "meta", "objective": "leads", "daily_budget": 1500,
       "creative": {"headline": "Free site visit this weekend", "text": "Homes by {business}, close to metro, schools and offices. Book a free site visit and see it for yourself.", "cta": "Book now"},
       "targeting": {"locations": "", "age_min": 28, "age_max": 55, "interests": "Real estate, home buying, home loans"},
       "lead_form": {"fields": ["full_name", "phone_number", "city"]}}, ["real_estate"]),
    T("ads-search-intent", "ads", "High-intent search (Google)", "Search ad for people already looking for what you sell.",
      {"platform": "google", "objective": "leads", "daily_budget": 1000,
       "creative": {"headline": "{business} | Book a Free Consultation", "text": "Talk to an expert today. Clear pricing, quick response, trusted locally.", "cta": "Get a quote"},
       "targeting": {"locations": "", "age_min": 25, "age_max": 65, "interests": ""}, "lead_form": {"fields": ["full_name", "phone_number", "email"]}}, []),
    T("ads-clinic-appointments", "ads", "Clinic appointments (Meta)", "Local appointment ad with a calm, reassuring tone.",
      {"platform": "meta", "objective": "leads", "daily_budget": 800,
       "creative": {"headline": "Book your appointment this week", "text": "Experienced care at {business}. Same-week appointments and clear advice before any treatment.", "cta": "Book now"},
       "targeting": {"locations": "", "age_min": 25, "age_max": 65, "interests": "Health, wellness, family"}, "lead_form": {"fields": ["full_name", "phone_number"]}}, ["healthcare"]),
    T("ads-demo-class", "ads", "Free demo class (Meta)", "Parents and students, with a free-demo hook.",
      {"platform": "meta", "objective": "leads", "daily_budget": 700,
       "creative": {"headline": "Try a free demo class", "text": "Small batches, expert faculty and a plan that fits your schedule. Book a free demo at {business}.", "cta": "Sign up"},
       "targeting": {"locations": "", "age_min": 16, "age_max": 50, "interests": "Education, competitive exams, parenting"}, "lead_form": {"fields": ["full_name", "phone_number", "email"]}}, ["education"]),
    T("ads-b2b-demo", "ads", "B2B demo requests (LinkedIn)", "Decision-makers by job title, for software and services.",
      {"platform": "linkedin", "objective": "leads", "daily_budget": 2500,
       "creative": {"headline": "See how {business} saves your team hours", "text": "Book a 20-minute demo. We'll show you the workflow with your own use case.", "cta": "Request demo"},
       "targeting": {"locations": "", "age_min": 25, "age_max": 60, "interests": "Founders, Operations managers, Marketing heads"},
       "lead_form": {"fields": ["full_name", "email", "company_name", "job_title"]}}, ["saas", "services"]),
    T("ads-retail-offer", "ads", "Limited-time offer (Meta)", "Offer-led ad that drives to your shop or landing page.",
      {"platform": "meta", "objective": "traffic", "daily_budget": 600,
       "creative": {"headline": "This week only: 10% off", "text": "Fresh arrivals at {business}. Easy returns and fast delivery. Shop before the offer ends.", "cta": "Shop now"},
       "targeting": {"locations": "", "age_min": 18, "age_max": 45, "interests": "Online shopping, fashion, lifestyle"}, "lead_form": {"fields": ["full_name", "email"]}}, ["retail"]),
    T("ads-retarget", "ads", "Retarget page visitors", "Bring back people who visited but didn't enquire.",
      {"platform": "meta", "objective": "leads", "daily_budget": 400,
       "creative": {"headline": "Still thinking it over?", "text": "Have questions about {business}? Leave your number and we'll call you back in minutes.", "cta": "Get a call back"},
       "targeting": {"locations": "", "age_min": 21, "age_max": 65, "interests": "Website visitors (custom audience)"}, "lead_form": {"fields": ["full_name", "phone_number"]}}, []),

    # ---------------- voice ----------------
    T("voice-property", "voice", "Property enquiry qualifier", "Qualifies home buyers: area, size, budget, visit date.",
      {"greeting": "Hi! This is the assistant from {business}. Thanks for your interest in our homes. May I ask a few quick questions to find the right option for you?",
       "instructions": "Warm, concise and respectful. Never promise prices or availability; offer a site visit instead. Keep replies under 2 sentences.",
       "questions": ["May I have your full name?", "Which area are you looking in?", "Are you looking for a 2 BHK, 3 BHK or something else?",
                     "What budget range are you considering?", "When would you like to visit the site?"]}, ["real_estate"]),
    T("voice-clinic", "voice", "Appointment booking", "Books clinic appointments calmly; hands off anything medical.",
      {"greeting": "Hello, you've reached {business}. I can help you book an appointment.",
       "instructions": "Calm and reassuring. Never give medical advice; for symptoms or urgent issues, hand off to a person.",
       "questions": ["May I have the patient's full name?", "What would you like to see the doctor about?",
                     "Which day and time suit you best?", "Is this the best number to confirm the appointment?"]}, ["healthcare"]),
    T("voice-admissions", "voice", "Admissions counsellor", "Captures student, course and preferred demo time.",
      {"greeting": "Hi! Thanks for contacting {business}. I'll ask a few quick questions so our counsellor can help you.",
       "instructions": "Friendly and encouraging. Don't guarantee results or ranks.",
       "questions": ["May I have the student's name?", "Which course or exam are you preparing for?", "Which class or year are you in?",
                     "When would you like to attend a free demo class?"]}, ["education"]),
    T("voice-b2b", "voice", "B2B demo qualifier", "Qualifies company, team size and problem before a demo.",
      {"greeting": "Hi, thanks for your interest in {business}. Mind if I ask a couple of questions so we can tailor your demo?",
       "instructions": "Professional and brief. If they ask for pricing, explain it depends on team size and offer the demo.",
       "questions": ["May I have your name and company?", "What problem are you hoping to solve?", "How big is your team?",
                     "When would be a good time for a 20-minute demo?"]}, ["saas", "services"]),
    T("voice-service-quote", "voice", "Service quote", "Collects the job, location and timing for a quote.",
      {"greeting": "Hi! Thanks for calling {business}. I'll take a few details so we can send you a quote.",
       "instructions": "Helpful and practical. Confirm the address area, not the full address.",
       "questions": ["May I have your name?", "What service do you need?", "Which area is the job in?", "When would you like it done?"]}, ["services"]),
    T("voice-callback", "voice", "Website call-back", "Short call for people who asked for a call back on your page.",
      {"greeting": "Hi! You asked {business} for a call back. Is now a good time for two quick questions?",
       "instructions": "Very brief and polite. If it's not a good time, ask when to call back and end the call.",
       "questions": ["What are you looking for help with?", "Is there a budget or timeline you have in mind?",
                     "When is the best time for our team to follow up?"]}, []),

    # ---------------- whatsapp ----------------
    T("wa-schedule-visit", "whatsapp", "Schedule a visit", "Ask for a convenient day and time.",
      {"body": "Hi {name}! Thanks for your interest in {business}. Would you like to schedule a visit? Reply with a day and time that suits you (e.g. Sat 11am)."}, []),
    T("wa-pricing", "whatsapp", "Share pricing", "Offer to walk them through options.",
      {"body": "Hi {name}, here's a quick overview of our pricing. Happy to walk you through options that fit your budget. When is a good time to talk?"}, []),
    T("wa-follow-up", "whatsapp", "Gentle follow-up", "Nudge leads who went quiet.",
      {"body": "Hi {name}, just following up on your enquiry with {business}. Do you have any questions I can help with?"}, []),
    T("wa-visit-reminder", "whatsapp", "Visit reminder", "Day-before reminder for site visits.",
      {"body": "Hi {name}, a reminder of your site visit with {business} tomorrow. Reply YES to confirm or tell us a better time."}, ["real_estate"]),
    T("wa-appointment-confirm", "whatsapp", "Appointment confirmation", "Confirm a booked appointment.",
      {"body": "Hi {name}, your appointment at {business} is confirmed. Please arrive 10 minutes early. Reply here if you need to reschedule."}, ["healthcare"]),
    T("wa-demo-class", "whatsapp", "Demo class invite", "Invite to a free demo class.",
      {"body": "Hi {name}! Your free demo class at {business} is ready to book. Which day works best this week?"}, ["education"]),
    T("wa-thank-you", "whatsapp", "Thank you", "After a purchase or visit.",
      {"body": "Thank you {name} for choosing {business}! If you have a minute, we'd love to hear how it went."}, []),
]
CATALOG_BY_KEY = {t["key"]: t for t in CATALOG}
