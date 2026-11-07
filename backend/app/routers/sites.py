"""Landing-page builder + hosting.

Pages are generated from a brief (Gemini when configured, otherwise a built-in responsive template),
hosted by AIMVA at /s/<slug>, and can be deployed to Netlify or Vercel with the user's API token.
Every page's lead form posts to /api/public/sites/<slug>/lead, which creates a scored lead.
"""
import base64
import html as H
import io
import json
import re
import secrets
import zipfile
import zlib
from collections import Counter
from urllib.parse import urljoin
from typing import List, Literal, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..brand import UPLOADS, asset_bytes, primary_logo
from ..models import Asset, BrandAsset, ReferenceFile, Site, SiteVersion, User, utcnow
from .. import providers as P
from ..design_intel import fonts_query, match_design, on_color, writer_notes
from ..quality import PLAYBOOKS, audit_page, match_playbook, playbook_ai_rules, playbook_out, readiness, review_brief
from .references import reference_text
from ..security import client_ip, current_user, rate_limit
from ..services import integration_secret
from .providers import writer
from .leads import create_lead

router = APIRouter(tags=["sites"])


PageType = Literal["lead_gen", "product", "service", "event", "real_estate", "restaurant", "portfolio", "app"]
Look = Literal["modern", "minimal", "bold", "elegant", "playful", "corporate"]
Section = Literal["features", "about", "gallery", "testimonials", "pricing", "faq", "contact_info",
                  "configurations", "amenities", "location", "steps"]
Layout = Literal["auto", "showcase", "split", "centered", "immersive", "editorial", "bento"]
Decor = Literal["auto", "blobs", "grid", "dots", "plain"]
LAYOUTS = {  # also described to the AI writer so AI pages follow the chosen structure
    "showcase": "Premium project microsite: full-bleed photo hero with a serif headline, fact chips, price card and stat strip, "
                "then overview, plans, amenities, gallery, location, steps, FAQ and a detailed enquiry form.",
    "split": "Hero text on the left with the lead form beside it; sections below as card grids.",
    "centered": "Centred hero with a very large headline and a button that scrolls to the form; wide image below; the form near the end.",
    "immersive": "Full-bleed hero photo with a dark overlay and white text; the lead form floats on the right of the hero.",
    "editorial": "Magazine style: oversized headline, numbered benefits with thin dividers, and a sticky lead form in a right-hand column.",
    "bento": "Bento grid: the hero, the form and the benefits arranged as tiles of different sizes and tints.",
}
CALLBACK_RULE = ("Leads are called back by an AI voice assistant: add a 'Request a call back' button linking to #contact, give the "
                 "form card id=\"contact\", and inside the form add <label><input type=\"checkbox\" name=\"callback\" value=\"yes\"> "
                 "Call me now: our assistant will ring you within a minute</label> before the submit button. ")
LANG_CODES = {"english": "en", "hindi": "hi", "telugu": "te", "tamil": "ta", "kannada": "kn", "marathi": "mr", "spanish": "es",
              "arabic": "ar", "french": "fr", "german": "de", "bengali": "bn", "gujarati": "gu", "malayalam": "ml"}
FormField = Literal["name", "phone", "email", "message", "city", "budget", "preferred_date", "company"]
FIELD_LABELS = {"name": "Full name", "phone": "Phone", "email": "Email", "message": "How can we help?", "city": "City",
                "budget": "Budget", "preferred_date": "Preferred date", "company": "Company"}
FONTS = {  # (Google Fonts family query, CSS heading font, CSS body font)
    "jakarta": ("Plus+Jakarta+Sans:wght@400;600;800", "'Plus Jakarta Sans'", "'Plus Jakarta Sans'"),
    "inter": ("Inter:wght@400;600;800", "Inter", "Inter"),
    "serif": ("Playfair+Display:wght@600;800&family=Inter:wght@400;600", "'Playfair Display'", "Inter"),
    "rounded": ("Nunito:wght@400;700;900", "Nunito", "Nunito"),
    "grotesk": ("Space+Grotesk:wght@400;600;700&family=Inter:wght@400;600", "'Space Grotesk'", "Inter"),
}
LOOKS = {  # radius, shadow, heading weight, hero gradient on headline
    "modern": ("20px", "0 20px 50px -20px rgba(15,23,42,.25)", 800, True),
    "minimal": ("10px", "0 1px 3px rgba(15,23,42,.08)", 700, False),
    "bold": ("6px", "8px 8px 0 rgba(15,23,42,.9)", 900, False),
    "elegant": ("2px", "0 30px 60px -30px rgba(15,23,42,.35)", 600, False),
    "playful": ("28px", "0 18px 40px -18px rgba(236,72,153,.35)", 900, True),
    "corporate": ("12px", "0 10px 30px -15px rgba(15,23,42,.25)", 700, False),
}


class Testimonial(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=3, max_length=400)


class FAQ(BaseModel):
    q: str = Field(min_length=3, max_length=200)
    a: str = Field(min_length=1, max_length=800)


class Plan(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    price: str = Field(min_length=1, max_length=40)
    features: List[str] = Field(default_factory=list, max_length=8)
    highlight: bool = False


class Stat(BaseModel):
    value: str = Field(min_length=1, max_length=20)  # "12 acres", "3 & 4 BHK"
    label: str = Field("", max_length=40)


class Configuration(BaseModel):
    name: str = Field(min_length=1, max_length=60)  # "3 BHK", "Villa type A", "Pro plan"
    area: str = Field("", max_length=60)
    details: str = Field("", max_length=240)
    price: str = Field("", max_length=40)


class Distance(BaseModel):
    place: str = Field(min_length=1, max_length=80)
    time: str = Field("", max_length=30)  # "10 min", "4 km"


class Brief(BaseModel):
    business: str = Field(min_length=2, max_length=120)
    headline: str = Field("", max_length=200)
    subheadline: str = Field("", max_length=300)
    industry: str = Field("", max_length=80)
    audience: str = Field("", max_length=160)
    offer: str = Field("", max_length=160)
    cta: str = Field("Get a free quote", max_length=60)
    features: List[str] = Field(default_factory=list, max_length=8)
    # How leads reach the business: the AIMVA voice agent calls them back (no business number needed),
    # the business's own phone number is shown, or both.
    contact_mode: Literal["voice_agent", "own_phone", "both"] = "voice_agent"
    phone: str = Field("", max_length=30)
    whatsapp: str = Field("", max_length=30)
    primary: str = Field("#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field("#22d3ee", pattern=r"^#[0-9a-fA-F]{6}$")
    hero_image: str = Field("", max_length=1000)  # https URL, or "asset:<id>" / "brand:<id>" from your library
    use_ai: bool = True
    # ---- extra options ----
    writer: str = Field("auto", max_length=40)  # auto | builtin:gemini | conn:<id>
    page_type: PageType = "lead_gen"
    voice_agent_id: Optional[int] = None  # which agent calls leads back (default: the first one)
    country_code: str = Field("+91", pattern=r"^\+\d{1,4}$")  # for visitors who type local numbers
    layout: Layout = "auto"  # auto: a layout this user hasn't used much, so every page looks different
    decor: Decor = "auto"
    look: Look = "modern"
    theme: Literal["light", "dark"] = "light"
    font: Literal["auto", "jakarta", "inter", "serif", "rounded", "grotesk"] = "jakarta"  # auto: matched to the business
    # Design matched to the business (UI/UX Pro Max data). Off unless asked for, so the owner's own colours always win.
    match_colors: bool = False
    font_heading: str = Field("", max_length=40, pattern=r"^[A-Za-z0-9 ]*$")  # filled in by the server when font is "auto"
    font_body: str = Field("", max_length=40, pattern=r"^[A-Za-z0-9 ]*$")
    design_match: str = Field("", max_length=80)  # the kind of business the design was matched to, shown to the owner
    language: str = Field("English", max_length=40)
    sections: List[Section] = Field(default_factory=lambda: ["features"], max_length=7)
    about: str = Field("", max_length=2000)
    testimonials: List[Testimonial] = Field(default_factory=list, max_length=6)
    faqs: List[FAQ] = Field(default_factory=list, max_length=10)
    pricing: List[Plan] = Field(default_factory=list, max_length=4)
    gallery: List[str] = Field(default_factory=list, max_length=8)
    form_fields: List[FormField] = Field(default_factory=lambda: ["name", "phone", "email", "message"], max_length=8)
    form_title: str = Field("", max_length=80)
    thank_you: str = Field("Thanks! We'll be in touch shortly.", max_length=200)
    whatsapp_button: bool = True
    include_logo: bool = False
    contact_email: str = Field("", max_length=120)
    address: str = Field("", max_length=200)
    seo_title: str = Field("", max_length=70)
    seo_description: str = Field("", max_length=170)
    references: List[int] = Field(default_factory=list, max_length=10)  # uploaded documents that brief the AI writer
    # ---- project facts (Showcase design). Blocks without facts are left out, never invented. ----
    location_line: str = Field("", max_length=80)  # eyebrow above the headline, e.g. "Kollur, West Hyderabad"
    palette: Literal["auto", "brand", "emerald", "navy", "charcoal", "forest", "plum", "slate"] = "auto"
    chips: List[str] = Field(default_factory=list, max_length=5)
    stats: List[Stat] = Field(default_factory=list, max_length=5)
    price_from: str = Field("", max_length=40)
    price_note: str = Field("", max_length=80)
    configurations: List[Configuration] = Field(default_factory=list, max_length=6)
    amenities: List[str] = Field(default_factory=list, max_length=24)
    distances: List[Distance] = Field(default_factory=list, max_length=12)
    approvals: str = Field("", max_length=80)  # "RERA: P02400001234", "ISO 9001"
    announcement: str = Field("", max_length=140)
    map_url: str = Field("", max_length=500)
    brochure: Optional[int] = None  # an uploaded reference PDF that visitors get after leaving their details
    gallery_captions: List[str] = Field(default_factory=list, max_length=8)
    meta_pixel_id: str = Field("", pattern=r"^(\d{6,20})?$")
    ga4_id: str = Field("", pattern=r"^(G-[A-Z0-9]{4,15})?$")

    @field_validator("form_fields")
    @classmethod
    def _needs_contact(cls, v):
        v = list(dict.fromkeys(v))
        if "phone" not in v and "email" not in v:
            raise ValueError("The form needs a phone or email field so you can reach your leads.")
        return v

    @model_validator(mode="after")
    def _contact(self):
        if self.contact_mode == "own_phone" and not (self.phone or self.whatsapp or self.contact_email):
            raise ValueError("Add your phone number (or WhatsApp / email), or let the AIMVA voice agent call leads back.")
        if self.contact_mode != "own_phone" and "phone" not in self.form_fields:
            self.form_fields = ["phone", *self.form_fields][:8]  # the agent needs the visitor's number to call back
        return self

    @property
    def shows_phone(self) -> bool:
        return self.contact_mode != "voice_agent" and bool(self.phone)

    @field_validator("hero_image")
    @classmethod
    def _image_ref(cls, v):
        v = v.strip()
        if v and not re.match(r"^(https://\S+|(asset|brand|ref):\d+)$", v):
            raise ValueError("Use an https:// image link or pick one from your library.")
        return v

    @field_validator("map_url")
    @classmethod
    def _map(cls, v):
        v = v.strip()
        if v and not v.startswith("https://"):
            raise ValueError("The map link must start with https://")
        return v

    @field_validator("chips", "amenities", "gallery_captions")
    @classmethod
    def _short(cls, v):
        return [x.strip()[:80] for x in v if x.strip()]

    @field_validator("gallery")
    @classmethod
    def _gallery(cls, v):
        for x in v:
            if not re.match(r"^(https://\S+|(asset|brand|ref):\d+)$", x.strip()):
                raise ValueError("Gallery images must be https:// links or images from your library.")
        return [x.strip() for x in v]


def _slugify(s: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "site") + "-" + secrets.token_hex(2)


def _lead_url(slug: str) -> str:
    return f"{settings.public_url}/api/public/sites/{slug}/lead"


def _form_script(slug: str, thank_you: str = "Thanks! We'll be in touch shortly.") -> str:
    msg = json.dumps(H.escape(thank_you))  # escaped for HTML, quoted for JS
    return f"""<script>
document.querySelectorAll('form[data-aimva-lead]').forEach(function(f){{
  f.addEventListener('submit',function(e){{e.preventDefault();
    var d=new URLSearchParams(new FormData(f));new URLSearchParams(location.search).forEach(function(v,k){{if(k==='aimva_c'||k.indexOf('utm_')===0)d.set(k,v.slice(0,100))}});
    fetch('{_lead_url(slug)}',{{method:'POST',mode:'no-cors',body:d}})
    .finally(function(){{var a=document.getElementById(f.getAttribute('data-after')||'');
      if(a){{f.hidden=true;a.hidden=false;return}}f.innerHTML='<p style="font-size:18px;padding:24px 0">'+{msg}+'</p>';}});
  }});
}});
</script>"""


def _tracking(b: Brief) -> str:
    out = ""
    if b.meta_pixel_id:
        out += ("<script>!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};"
                "if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;"
                "s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');"
                f"fbq('init','{b.meta_pixel_id}');fbq('track','PageView');</script>")
    if b.ga4_id:
        out += (f'<script async src="https://www.googletagmanager.com/gtag/js?id={b.ga4_id}"></script>'
                f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{b.ga4_id}');</script>")
    return out


def _embed(db: Session, user_id: int, ref: str, max_side: int = 1600) -> str:
    """Images from the user's private library are embedded (compressed) so the public page can show them."""
    if not ref or ref.startswith("https://"):
        return ref
    kind, _, raw = ref.partition(":")
    data = None
    if kind == "brand":
        a = db.get(BrandAsset, int(raw))
        if a and a.user_id == user_id:
            data = asset_bytes(a)
    elif kind == "ref":
        r = db.get(ReferenceFile, int(raw))
        if r and r.user_id == user_id and r.kind == "image":
            data = (UPLOADS / r.path).read_bytes()
    elif kind == "asset":
        a = db.get(Asset, int(raw))
        if a and a.user_id == user_id and a.kind == "image" and a.url:
            if a.url.startswith("/api/files/"):
                data = (UPLOADS / a.url[len("/api/files/"):]).read_bytes()
            else:
                return a.url if a.url.startswith("https://") else ""
    if not data:
        raise HTTPException(404, "One of the chosen images wasn't found in your library.")
    img = Image.open(io.BytesIO(data))
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    if img.mode in ("RGBA", "LA", "P"):
        img.convert("RGBA").save(out, "PNG", optimize=True)
        mime = "image/png"
    else:
        img.convert("RGB").save(out, "JPEG", quality=82, optimize=True)
        mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(out.getvalue()).decode()}"


def _media(db: Session, user_id: int, b: Brief) -> dict:
    logo = ""
    if b.include_logo:
        lg = primary_logo(db, user_id)
        if not lg:
            raise HTTPException(400, "Upload a logo in Brand Kit first, or turn off “Show my logo”.")
        logo = _embed(db, user_id, f"brand:{lg.id}", 400)
    return {"hero": _embed(db, user_id, b.hero_image), "gallery": [_embed(db, user_id, g, 1000) for g in b.gallery], "logo": logo}


def _default_sub(b: Brief, headline: str) -> str:
    """A factual subheadline from what we know (no invented claims like "trusted by thousands")."""
    bits = []
    if b.offer and b.offer.lower() not in headline.lower():
        bits.append(b.offer.rstrip(".") + ".")
    if b.audience:
        bits.append(f"For {b.audience.rstrip('.')}.")
    if b.address:
        bits.append(f"📍 {b.address}")
    return " ".join(bits) or f"Tell us what you need and the {b.business} team will get back to you."


def _layout_css(layout: str, c: dict) -> str:
    """Per-layout structure. c holds the theme colours (bg, fg, muted, card, line, shadow)."""
    if layout == "centered":
        return f"""
.hero{{text-align:center;max-width:860px;margin:0 auto;padding:72px 0 56px}}.hero .sub{{margin-left:auto;margin-right:auto;max-width:640px}}
.hero .row{{justify-content:center}}.hero-img{{max-width:1040px;display:block;margin:40px auto 0}}
.form-sec{{max-width:560px;margin:0 auto;padding-bottom:80px}}
.feats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:28px;text-align:center}}
.feats .f{{background:none;border:0;padding:8px}}.tick{{width:44px;height:44px;border-radius:50%;margin:0 auto 12px;display:grid;place-items:center;
background:color-mix(in srgb,var(--p) 14%,transparent);color:var(--p);font-weight:800}}"""
    if layout == "immersive":
        return f"""
.top{{background:linear-gradient(100deg,rgba(6,9,20,.86),rgba(6,9,20,.45)),var(--hero-img,linear-gradient(135deg,var(--p),var(--a)));
background-size:cover;background-position:center;color:#fff;border-radius:0 0 calc(var(--r)*1.5) calc(var(--r)*1.5);margin:0 -20px 64px;padding:0 20px}}
.top nav b,.top nav a{{color:#fff}}.top .ghost{{border-color:rgba(255,255,255,.4)}}.top .sub{{color:rgba(255,255,255,.85)}}
.hero{{display:grid;grid-template-columns:1.25fr .9fr;gap:48px;align-items:center;padding:56px 0 88px;min-height:560px}}
.top h1 span{{background:none;-webkit-background-clip:initial;color:#fff}}.top .card{{color:{c['fg']}}}
.feats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}}
.num{{font-size:13px;font-weight:800;color:var(--p);letter-spacing:.08em;margin-bottom:10px}}"""
    if layout == "editorial":
        return f"""
.hero{{padding:64px 0 40px;border-bottom:1px solid {c['line']};margin-bottom:56px}}
.hero h1{{font-size:clamp(42px,7vw,88px);line-height:1;letter-spacing:-.035em;max-width:16ch}}
.hero .sub{{font-size:21px;max-width:56ch}}.cols{{display:grid;grid-template-columns:1fr 380px;gap:56px;align-items:start}}
.cols aside{{position:sticky;top:24px}}.feats{{counter-reset:n;display:grid;gap:0}}
.feats .f{{background:none;border:0;border-top:1px solid {c['line']};border-radius:0;padding:22px 0;display:flex;gap:20px;align-items:baseline}}
.feats .f::before{{counter-increment:n;content:counter(n,decimal-leading-zero);font-weight:800;color:var(--p);font-size:15px}}
.feats .f h3{{font-size:22px}}.hero-img{{margin-top:0;margin-bottom:56px}}"""
    if layout == "bento":
        return f"""
.bento{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;padding:40px 0 72px}}
.bento>*{{background:{c['card']};border-radius:var(--r);padding:28px;border:1px solid {c['line']}}}
.bento .t-hero{{grid-column:span 2;grid-row:span 2;display:flex;flex-direction:column;justify-content:center}}
.bento .t-form{{grid-column:span 2;grid-row:span 2;box-shadow:{c['shadow']}}}.bento .t-form .card{{box-shadow:none;padding:0;background:none}}
.bento .t-feat{{display:flex;flex-direction:column;justify-content:space-between;min-height:150px}}
.bento .t-feat:nth-child(3n){{background:color-mix(in srgb,var(--p) 10%,{c['card']})}}
.bento .t-feat:nth-child(4n){{background:color-mix(in srgb,var(--a) 14%,{c['card']})}}
.bento .t-img{{grid-column:span 2;padding:0;overflow:hidden}}.bento .t-img img{{width:100%;height:100%;object-fit:cover;display:block}}
.dot{{margin-bottom:0}}
@media(max-width:820px){{.bento{{grid-template-columns:1fr 1fr}}.bento .t-hero,.bento .t-form,.bento .t-img{{grid-column:span 2}}}}"""
    return """
.hero{display:grid;grid-template-columns:1.2fr 1fr;gap:48px;align-items:center;padding:56px 0 72px}
.feats{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}"""


DECOR_CSS = {  # painted on a layer behind the hero, so masks/fades never touch the text
    "blobs": ".top::before{background-image:radial-gradient(40% 55% at 12% 8%,color-mix(in srgb,var(--p) 16%,transparent),transparent 70%),"
             "radial-gradient(35% 50% at 92% 0%,color-mix(in srgb,var(--a) 18%,transparent),transparent 70%)}",
    "grid": ".top::before{background-image:linear-gradient(var(--ln) 1px,transparent 1px),linear-gradient(90deg,var(--ln) 1px,transparent 1px);"
            "background-size:44px 44px;-webkit-mask-image:linear-gradient(#000 55%,transparent);mask-image:linear-gradient(#000 55%,transparent)}",
    "dots": ".top::before{background-image:radial-gradient(var(--ln) 1.4px,transparent 1.4px);background-size:22px 22px}",
    "plain": "",
}


ICON_PHONE = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
              'stroke-linejoin="round" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6 '
              '19.8 19.8 0 0 1-3.1-8.7A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 '
              '2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/></svg>')
ICON_CHAT = ('<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
             'stroke-linejoin="round" aria-hidden="true"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/></svg>')


def apply_design_match(b: Brief) -> Optional[dict]:
    """Colours and fonts matched to the kind of business, only where the owner asked for that (match_colors, font "auto")."""
    if not (b.match_colors or b.font == "auto"):
        return None
    m = match_design(b.industry, b.business, b.offer)
    b.design_match = m["category"] if m else ""
    if b.font == "auto":
        b.font_heading, b.font_body = (m["font_heading"], m["font_body"]) if m else ("", "")
    if m and b.match_colors:
        b.primary, b.accent = m["primary"], m["accent"]
    return m


def page_fonts(b: Brief) -> tuple:
    """(Google Fonts family query, CSS heading font, CSS body font). Matched fonts only when whitelisted, else Jakarta."""
    if b.font == "auto":
        q = fonts_query(b.font_heading, b.font_body)
        if q:
            return q, f"'{b.font_heading}'", f"'{b.font_body}'"
    return FONTS.get(b.font, FONTS["jakarta"])


def _design_notes(b: Brief) -> str:
    if not (b.match_colors or b.font == "auto"):
        return ""
    m = match_design(b.industry, b.business, b.offer)
    if m and b.font != "auto":  # the owner picked the fonts: don't suggest others
        m = {**m, "font_heading": "", "font_body": ""}
    return writer_notes(m)


def template_html(b: Brief, slug: str, media: Optional[dict] = None, playbook: str = "other", copy: Optional[dict] = None) -> str:
    e = H.escape
    media = media or {"hero": b.hero_image if b.hero_image.startswith("https://") else "", "gallery": [], "logo": ""}
    layout = b.layout if b.layout != "auto" else "split"
    if layout == "showcase":
        from ..site_showcase import showcase_html
        return showcase_html(b, slug, media, playbook == "real_estate" or b.page_type == "real_estate",
                             _form_script(slug, b.thank_you), _tracking(b), FIELD_LABELS, copy)
    decor = b.decor if b.decor != "auto" else "blobs"
    radius, shadow, weight, grad = LOOKS[b.look]
    fq, hfont, bfont = page_fonts(b)
    on_p = on_color(b.primary)
    dark = b.theme == "dark"
    bg, fg, muted, card, line = (("#0b1020", "#e8ecf8", "#9aa3c0", "#121a33", "#1f2a4a") if dark
                                 else ("#f8fafc", "#0f172a", "#475569", "#ffffff", "#e2e8f0"))
    colours = {"bg": bg, "fg": fg, "muted": muted, "card": card, "line": line, "shadow": shadow}
    raw_headline = b.headline or (f"{b.business}: {b.offer}" if b.offer else b.business)
    headline = e(raw_headline)
    sub = e(b.subheadline or _default_sub(b, raw_headline))
    wa_num = re.sub(r"[^0-9]", "", b.whatsapp)
    wa = f'<a class="wa" href="https://wa.me/{wa_num}" target="_blank" rel="noopener">WhatsApp us</a>' if wa_num else ""
    callback = b.contact_mode != "own_phone"
    tel = (f'<a class="ghost" href="tel:{e(b.phone)}">{ICON_PHONE}Call {e(b.phone)}</a>' if b.shows_phone
           else f'<a class="ghost" href="#contact">{ICON_PHONE}Request a call back</a>' if callback else "")
    jump = f'<a class="btn-inline" href="#contact">{e(b.cta)}</a>'
    brand = (f'<img src="{media["logo"]}" alt="{e(b.business)}" class="logo">' if media["logo"] else f"<b>{e(b.business)}</b>")
    hero_img = f'<img class="hero-img" src="{e(media["hero"])}" alt="{e(b.business)}">' if media["hero"] else ""
    fields = []
    for f in b.form_fields:
        req = " required" if f in ("name", "phone", "email") and (f != "email" or "phone" not in b.form_fields) else ""
        if f == "message":
            fields.append(f'<textarea name="message" rows="3" placeholder="{FIELD_LABELS[f]}" aria-label="{FIELD_LABELS[f]}"></textarea>')
        else:
            typ = {"phone": "tel", "email": "email", "preferred_date": "date"}.get(f, "text")
            fields.append(f'<input name="{f}" type="{typ}" placeholder="{FIELD_LABELS[f]}" aria-label="{FIELD_LABELS[f]}"{req}>')
    if callback:  # the AIMVA voice agent rings the visitor back within a minute
        fields.append('<label class="cb"><input type="checkbox" name="callback" value="yes"> '
                      'Call me now: our assistant will ring you within a minute</label>')
    form_card = (f'<div class="card" id="contact"><h2>{e(b.form_title or b.cta)}</h2><form data-aimva-lead>{"".join(fields)}'
                 f'<button class="btn" type="submit">{e(b.cta)}</button></form></div>')
    feats = [f for f in b.features if f.strip()] or PLAYBOOKS.get(playbook, PLAYBOOKS["other"])["safe_features"]

    def feature_item(i: int, x: str) -> str:
        if layout == "centered":
            return f'<div class="f"><div class="tick">✓</div><h3>{e(x)}</h3></div>'
        if layout == "immersive":
            return f'<div class="f"><div class="num">{i:02d}</div><h3>{e(x)}</h3></div>'
        if layout == "editorial":
            return f'<div class="f"><h3>{e(x)}</h3></div>'
        return f'<div class="f"><div class="dot"></div><h3>{e(x)}</h3></div>'

    blocks = []
    for sec in b.sections:
        if sec == "features" and layout != "bento":
            blocks.append('<section class="block" data-aimva-section="features"><div class="feats">'
                          + "".join(feature_item(i, x) for i, x in enumerate(feats[:8], 1)) + "</div></section>")
        elif sec == "about" and b.about:
            blocks.append(f'<section class="block" data-aimva-section="about"><h2>About {e(b.business)}</h2><p>{e(b.about)}</p></section>')
        elif sec == "gallery" and media["gallery"]:
            blocks.append('<section class="block" data-aimva-section="gallery"><h2>Gallery</h2><div class="gallery">'
                          + "".join(f'<img src="{e(g)}" alt="{e(b.business)} photo" loading="lazy">' for g in media["gallery"] if g) + "</div></section>")
        elif sec == "testimonials" and b.testimonials:  # only real, user-provided quotes
            blocks.append('<section class="block" data-aimva-section="testimonials"><h2>What customers say</h2><div class="grid">'
                          + "".join(f'<figure class="f"><blockquote>“{e(t.quote)}”</blockquote><figcaption>— {e(t.name)}</figcaption></figure>'
                                    for t in b.testimonials) + "</div></section>")
        elif sec == "pricing" and b.pricing:
            blocks.append('<section class="block" data-aimva-section="pricing"><h2>Pricing</h2><div class="grid">' + "".join(
                f'<div class="f{" hl" if p.highlight else ""}"><h3>{e(p.name)}</h3><p class="price">{e(p.price)}</p><ul>'
                + "".join(f"<li>{e(x)}</li>" for x in p.features) + "</ul></div>" for p in b.pricing) + "</div></section>")
        elif sec == "faq" and b.faqs:
            blocks.append('<section class="block" data-aimva-section="faq"><h2>Questions</h2>'
                          + "".join(f"<details><summary>{e(q.q)}</summary><p>{e(q.a)}</p></details>" for q in b.faqs) + "</section>")
        elif sec == "contact_info" and (b.shows_phone or b.contact_email or b.address):
            bits = [x for x in (e(b.phone) if b.shows_phone else "", e(b.contact_email), e(b.address)) if x]
            blocks.append(f'<section class="block" data-aimva-section="contact_info"><h2>Contact</h2><p>{" · ".join(bits)}</p></section>')
    nav = f"<nav>{brand}{tel}</nav>"
    intro = f'<h1><span>{headline}</span></h1><p class="sub">{sub}</p>'
    if layout == "centered":
        body = (f'<div class="top">{nav}<section class="hero" data-aimva-section="hero">{intro}<div class="row">{jump}{wa}</div>{hero_img}</section></div>'
                + "".join(blocks) + f'<section class="form-sec" data-aimva-section="form">{form_card}</section>')
    elif layout == "immersive":
        style = f' style="--hero-img:url(&quot;{e(media["hero"])}&quot;)"' if media["hero"] else ""
        body = (f'<div class="top"{style}>{nav}<section class="hero" data-aimva-section="hero"><div>{intro}<div class="row">{wa}</div></div>'
                f"{form_card}</section></div>" + "".join(blocks))
    elif layout == "editorial":
        body = (f'<div class="top">{nav}<section class="hero" data-aimva-section="hero">{intro}<div class="row">{jump}{wa}</div></section></div>'
                f'{hero_img}<div class="cols"><div>{"".join(blocks)}</div><aside>{form_card}</aside></div>')
    elif layout == "bento":
        tiles = "".join(f'<div class="t-feat"><div class="dot"></div><h3>{e(x)}</h3></div>' for x in feats[:6]) if "features" in b.sections else ""
        img_tile = f'<div class="t-img">{hero_img.replace("hero-img", "")}</div>' if hero_img else ""
        body = (f'<div class="top">{nav}</div><section class="bento" data-aimva-section="hero"><div class="t-hero">{intro}<div class="row">{wa}</div></div>'
                f'<div class="t-form">{form_card}</div>{tiles}{img_tile}</section>' + "".join(blocks))
    else:
        body = (f'<div class="top">{nav}<section class="hero" data-aimva-section="hero"><div>{intro}<div class="row">{wa}</div>{hero_img}</div>'
                f"{form_card}</section></div>" + "".join(blocks))
    float_wa = (f'<a class="wa-float" href="https://wa.me/{wa_num}" target="_blank" rel="noopener" aria-label="Chat on WhatsApp">{ICON_CHAT}</a>'
                if wa_num and b.whatsapp_button else "")
    return f"""<!doctype html><html lang="{e(LANG_CODES.get(b.language.lower(), 'en'))}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(b.seo_title or b.business)}</title>
<meta name="description" content="{e(b.seo_description or (b.subheadline or b.offer or b.business))}">
<meta property="og:title" content="{e(b.seo_title or b.business)}"><meta property="og:description" content="{e(b.seo_description or b.offer)}">
<meta name="aimva:layout" content="{layout}">
<link href="https://fonts.googleapis.com/css2?family={fq}&display=swap" rel="stylesheet">{_tracking(b)}
<style>
:root{{--p:{b.primary};--a:{b.accent};--on-p:{on_p};--r:{radius};--ln:{line}}}*{{box-sizing:border-box;margin:0}}
body{{font-family:{bfont},system-ui,sans-serif;color:{fg};background:{bg};line-height:1.6}}
h1,h2,h3{{font-family:{hfont},system-ui,sans-serif;font-weight:{weight}}}
.wrap{{max-width:1120px;margin:0 auto;padding:0 20px}}
nav{{display:flex;justify-content:space-between;align-items:center;padding:20px 0}}nav b{{font-size:20px}}.logo{{max-height:44px}}
.btn,.wa,.ghost,.btn-inline{{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:48px;padding:12px 22px;border-radius:var(--r);font-weight:600;text-decoration:none}}
.ghost svg,.wa-float svg{{flex:none}}
.btn{{background:var(--p);color:var(--on-p);border:0;cursor:pointer;font-size:16px;width:100%}}.btn-inline{{background:var(--p);color:var(--on-p)}}
.wa{{background:#25d366;color:#fff}}.ghost{{border:1.5px solid {line};color:{fg}}}
h1{{font-size:clamp(34px,5vw,56px);line-height:1.1;letter-spacing:-.02em}}
{"h1 span{background:linear-gradient(90deg,var(--p),var(--a));-webkit-background-clip:text;color:transparent}" if grad else "h1 span{color:var(--p)}"}
.sub{{font-size:19px;color:{muted};margin:20px 0 28px}}.row{{display:flex;gap:12px;flex-wrap:wrap}}
.card{{background:{card};border-radius:var(--r);padding:28px;box-shadow:{shadow}}}
.card h2{{font-size:22px;margin-bottom:16px}}
input,textarea{{width:100%;font-size:16px;padding:13px 14px;border:1.5px solid {line};border-radius:calc(var(--r)/2);font:inherit;margin-bottom:12px;background:{bg};color:{fg}}}
input:focus,textarea:focus{{outline:2px solid var(--p);border-color:transparent}}
a:focus-visible,button:focus-visible,summary:focus-visible{{outline:3px solid var(--p);outline-offset:3px}}
.cb{{display:flex;gap:10px;align-items:center;font-size:14px;color:{muted};margin:2px 0 14px;cursor:pointer}}.cb input{{width:18px;height:18px;margin:0;accent-color:var(--p)}}
.hero-img{{width:100%;border-radius:var(--r);margin-top:28px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}}
.block{{padding-bottom:72px}}.block h2{{font-size:30px;margin-bottom:20px}}
.f{{background:{card};border-radius:var(--r);padding:24px;border:1px solid {line}}}.f h3{{font-size:17px}}.f.hl{{border:2px solid var(--p)}}
.dot{{width:36px;height:36px;border-radius:calc(var(--r)/2);background:linear-gradient(135deg,var(--p),var(--a));margin-bottom:14px}}
.price{{font-size:28px;font-weight:800;margin:8px 0}}.f ul{{padding-left:18px;color:{muted}}}
blockquote{{font-size:16px}}figcaption{{margin-top:10px;color:{muted};font-size:14px}}
.gallery{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}}.gallery img{{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:var(--r)}}
details{{border-bottom:1px solid {line};padding:14px 0}}summary{{font-weight:600;cursor:pointer}}details p{{margin-top:8px;color:{muted}}}
.wa-float{{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;background:#25d366;display:grid;place-items:center;color:#fff;text-decoration:none;box-shadow:0 10px 30px rgba(0,0,0,.25)}}
footer{{padding:32px 0;color:{muted};font-size:14px;border-top:1px solid {line}}}
.top{{margin:0 -20px;padding:0 20px;position:relative;isolation:isolate}}.top::before{{content:"";position:absolute;inset:0;z-index:-1;pointer-events:none}}
{DECOR_CSS[decor] if layout != "immersive" else ""}
{_layout_css(layout, colours)}
@media(prefers-reduced-motion:reduce){{*,*::before,*::after{{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}}}
@media(max-width:820px){{.hero{{grid-template-columns:1fr!important;padding-top:24px;min-height:0}}.cols{{grid-template-columns:1fr!important}}.cols aside{{position:static}}}}
</style></head><body><div class="wrap">
{body}
<footer data-aimva-section="footer">© {e(b.business)}{(" · " + e(b.address)) if b.address else ""}</footer></div>{float_wa}{_form_script(slug, b.thank_you)}</body></html>"""


def _ai_brief(b: Brief, reference: str = "", playbook: str = "other") -> str:
    sections = []
    for sec in b.sections:
        if sec == "testimonials" and b.testimonials:
            sections.append("testimonials (use EXACTLY these, do not invent others): "
                            + json.dumps([t.model_dump() for t in b.testimonials], ensure_ascii=False))
        elif sec == "pricing" and b.pricing:
            sections.append("pricing (use EXACTLY these plans and prices): " + json.dumps([p.model_dump() for p in b.pricing], ensure_ascii=False))
        elif sec == "faq" and b.faqs:
            sections.append("FAQ (use these): " + json.dumps([f.model_dump() for f in b.faqs], ensure_ascii=False))
        elif sec == "about" and b.about:
            sections.append(f"about: {b.about}")
        elif sec in ("features", "contact_info", "gallery"):
            sections.append(sec)
    return (f"Create a complete, responsive single-file HTML landing page (inline CSS only, no JS frameworks, no external JS "
            f"except fonts). Write all visible text in {b.language}. Page type: {b.page_type}. Visual look: {b.look}, {b.theme} theme. "
            f"{('Layout: ' + LAYOUTS[b.layout] + ' ') if b.layout in LAYOUTS else ''}"
            f"Business: {b.business}. Industry: {b.industry}. Audience: {b.audience}. Offer: {b.offer}. "
            f"Headline idea: {b.headline}. Subheadline idea: {b.subheadline}. Features: {', '.join(b.features)}. "
            f"Colours: primary {b.primary}, accent {b.accent}; button text {on_color(b.primary)}. {('Phone: ' + b.phone + '. ') if b.shows_phone else 'Do not show any business phone number. '}WhatsApp: {b.whatsapp}. Email: {b.contact_email}. "
            f"{CALLBACK_RULE if b.contact_mode != 'own_phone' else ''}"
            f"Address: {b.address}. Sections after the hero, in order: {'; '.join(sections) or 'features'}. "
            f"Never invent testimonials, reviews, ratings, prices, awards or statistics that aren't given above. "
            f"Use the image placeholder src values __HERO__ for the hero image and __GALLERY_1__.. for gallery images if relevant. "
            f"Include exactly one lead form with the attribute data-aimva-lead containing inputs named: {', '.join(b.form_fields)}, "
            f"and a submit button labelled '{b.cta}'." + playbook_ai_rules(playbook) + _design_notes(b) + " Return ONLY the HTML document."
            + (f"\n\nBackground material from the business (use facts from it, don't copy it wholesale):\n{reference}" if reference else ""))


def sanitize_html(html: str) -> str:
    """Strip active content from AI-written pages: scripts, frames, inline handlers, javascript: links, form targets.
    (Published pages are also served in a CSP sandbox, so this is defence in depth.)"""
    flags = re.I | re.S
    html = re.sub(r"<(script|iframe|object|embed|frame|frameset|applet|noscript)\b[^>]*>.*?</\1\s*>", "", html, flags=flags)
    html = re.sub(r"<(script|iframe|object|embed|frame|frameset|applet|base|link\s+[^>]*rel=[\"']?(?:import|preload)[^>]*)\b[^>]*/?>", "", html, flags=flags)
    html = re.sub(r"<meta[^>]+http-equiv\s*=\s*[\"']?refresh[^>]*>", "", html, flags=flags)

    def clean_tag(m):
        tag = m.group(0)
        tag = re.sub(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", tag, flags=re.I)
        tag = re.sub(r"\s+(form)?action\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", tag, flags=re.I)
        tag = re.sub(r"((?:href|src|xlink:href)\s*=\s*[\"']?)\s*(?:javascript|vbscript|data:text/html)[^\"'\s>]*", r"\1#", tag, flags=re.I)
        return tag
    return re.sub(r"<[a-zA-Z][^>]*>", clean_tag, html)


COPY_KEYS = {"headline": 90, "subheadline": 220, "overview_title": 70, "overview": 600, "plans_title": 70, "amenities_title": 70,
             "amenities_intro": 220, "gallery_title": 70, "location_title": 70, "location_intro": 220, "enquire_title": 70,
             "form_button": 34, "price_label": 34}


def showcase_copy(b: Brief, write, reference: str = "", playbook: str = "other") -> dict:
    """For the Showcase design the layout is fixed and the AI writes only the words, grounded in the brief.
    Anything malformed is dropped, so the page falls back to the built-in wording instead of failing."""
    facts = {k: v for k, v in b.model_dump(include={"business", "industry", "audience", "offer", "headline", "subheadline", "features",
                                                    "about", "address", "location_line", "price_from", "amenities", "approvals"}).items() if v}
    facts["configurations"] = [c.name for c in b.configurations]
    prompt = (f"Write the copy for a premium {b.page_type.replace('_', ' ')} landing page in {b.language}. Facts: {json.dumps(facts, ensure_ascii=False)}. "
              "Return ONLY a JSON object with these keys (short, specific, confident; no exclamation marks; never invent numbers, prices, "
              "awards, reviews or facts not given): " + ", ".join(f"{k} (max {n} chars)" for k, n in COPY_KEYS.items())
              + ', highlights (3 objects {"title": max 40 chars, "text": max 140 chars}), steps (3 pairs [title, text]).'
              " The headline's last word is shown in italics, so end on a strong word." + playbook_ai_rules(playbook)
              + (f"\n\nBackground from the business:\n{reference[:6000]}" if reference else ""))
    out = write(prompt, max_tokens=1600)
    m = re.search(r"\{.*\}", out or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    copy = {k: str(data[k]).strip()[:n] for k, n in COPY_KEYS.items() if isinstance(data.get(k), str) and data[k].strip()}
    hl = [h for h in data.get("highlights") or [] if isinstance(h, dict) and isinstance(h.get("title"), str) and h["title"].strip()]
    if len(hl) >= 2:
        copy["highlights"] = [{"title": h["title"][:40], "text": str(h.get("text") or "")[:140]} for h in hl[:3]]
    st = [x for x in data.get("steps") or [] if isinstance(x, list) and len(x) == 2 and all(isinstance(y, str) for y in x)]
    if len(st) == 3:
        copy["steps"] = [[t[:40], d[:160]] for t, d in st]
    return copy


def build_html(b: Brief, slug: str, write=None, media: Optional[dict] = None, reference: str = "",
               playbook: str = "other") -> tuple:
    media = media or {"hero": "", "gallery": [], "logo": ""}
    if b.layout == "showcase":
        copy = showcase_copy(b, write, reference, playbook) if (b.use_ai and write) else {}
        return template_html(b, slug, media, playbook, copy), ("ai" if copy else "template")
    if b.use_ai and write:
        out = write(_ai_brief(b, reference, playbook), max_tokens=8000)
        if out:
            out = re.sub(r"^```(?:html)?\s*|\s*```$", "", out.strip())
            if "<html" in out.lower() and "data-aimva-lead" in out:
                out = sanitize_html(out)
                out = out.replace("__HERO__", media["hero"] or "")
                for i, g in enumerate(media["gallery"], 1):
                    out = out.replace(f"__GALLERY_{i}__", g)
                head_extra = _tracking(b)
                if head_extra and "</head>" in out:
                    out = out.replace("</head>", head_extra + "</head>", 1)
                return out.replace("</body>", _form_script(slug, b.thank_you) + "</body>"), "ai"
    return template_html(b, slug, media, playbook), "template"


def site_out(s: Site, with_html: bool = False) -> dict:
    d = {"id": s.id, "name": s.name, "slug": s.slug, "brief": s.brief, "published": s.published,
         "custom_domain": s.custom_domain, "domain_verified": bool(s.custom_domain and s.domain_verified_at),
         "deploy_target": s.deploy_target, "deploy_url": s.deploy_url,
         "visits": s.visits, "url": f"{settings.public_url}/s/{s.slug}",
         "published_at": s.published_at.isoformat() if s.published_at else None,
         "created_at": s.created_at.isoformat(), "updated_at": s.updated_at.isoformat(),
         "pages": [{"slug": p["slug"], "title": p["title"], **({"html": p["html"]} if with_html else {})} for p in (s.pages or [])]}
    if with_html:
        d["html"] = s.html
    return d


def _own(db: Session, user: User, site_id: int) -> Site:
    s = db.get(Site, site_id)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Site not found.")
    return s


@router.get("/api/sites")
def list_sites(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [site_out(s) for s in db.scalars(select(Site).where(Site.user_id == user.id).order_by(Site.updated_at.desc()))]


MAX_VERSIONS = 30


def add_version(db: Session, site: Site, note: str, generator: str = "") -> SiteVersion:
    last = db.scalar(select(SiteVersion.number).where(SiteVersion.site_id == site.id).order_by(SiteVersion.number.desc()))
    v = SiteVersion(site_id=site.id, number=(last or 0) + 1, html=site.html, brief=site.brief or {}, note=note, generator=generator)
    db.add(v)
    db.flush()
    old = list(db.scalars(select(SiteVersion).where(SiteVersion.site_id == site.id).order_by(SiteVersion.number.desc()).offset(MAX_VERSIONS)))
    for o in old:
        db.delete(o)
    return v


LAYOUT_PREFS = {  # which structures suit each industry best, in order
    "real_estate": ["showcase", "immersive", "split", "editorial", "bento"],
    "healthcare": ["centered", "split", "editorial", "immersive", "bento"],
    "education": ["bento", "split", "centered", "editorial", "immersive"],
    "saas": ["bento", "centered", "editorial", "split", "immersive"],
    "retail": ["immersive", "showcase", "bento", "centered", "split"],
    "restaurant": ["showcase", "immersive", "editorial", "centered", "bento"],
    "services": ["split", "showcase", "centered", "immersive", "bento"],
    "other": ["showcase", "split", "centered", "bento", "editorial"],
}
DECORS = ["blobs", "grid", "dots", "plain"]
STYLE_SETS = [  # look + font + background + theme pairings that read as clearly different designs
    {"look": "modern", "font": "jakarta", "decor": "blobs", "theme": "light"},
    {"look": "elegant", "font": "serif", "decor": "plain", "theme": "light"},
    {"look": "bold", "font": "grotesk", "decor": "grid", "theme": "light"},
    {"look": "playful", "font": "rounded", "decor": "dots", "theme": "light"},
    {"look": "corporate", "font": "inter", "decor": "plain", "theme": "light"},
    {"look": "minimal", "font": "inter", "decor": "grid", "theme": "dark"},
]  # ordered so any three in a row have different backgrounds
LAYOUT_LABELS = {"showcase": "Showcase", "split": "Split", "centered": "Centred", "immersive": "Full-bleed photo", "editorial": "Editorial", "bento": "Bento grid"}


def ranked_layouts(db: Session, user: User, b: Brief, playbook: str) -> list:
    """Layouts in the order we'd suggest them: least used by this user first, then best fit for the industry."""
    used = Counter((x or {}).get("layout") for x in db.scalars(select(Site.brief).where(Site.user_id == user.id)))
    prefs = list(LAYOUT_PREFS.get(playbook, LAYOUT_PREFS["other"]))
    if not (b.hero_image or b.gallery):
        photo = ("immersive", "showcase")  # a full-bleed hero needs a real photo
        prefs = [p for p in prefs if p not in photo] + [p for p in prefs if p in photo]
    return sorted(prefs, key=lambda l: (used[l], prefs.index(l)))


def resolve_design(db: Session, user: User, b: Brief, playbook: str) -> None:
    """Fill in "auto" choices so each new page gets its own structure and background (saved in the brief)."""
    apply_design_match(b)
    if b.layout == "auto":
        b.layout = ranked_layouts(db, user, b, playbook)[0]
    if b.decor == "auto":
        b.decor = DECORS[zlib.crc32(f"{b.business}|{b.layout}".encode()) % len(DECORS)]


def _generate(db: Session, user: User, b: Brief, slug: str) -> tuple:
    if b.use_ai and not (b.offer or b.headline or b.features or b.about or b.references or b.industry or b.audience):
        raise HTTPException(400, "Add at least one detail (offer, headline, industry, audience, features, about text or a "
                                 "reference file) so the AI doesn't have to make things up.")
    ref_text = reference_text(db, user.id, b.references) if b.references else ""
    playbook = match_playbook(b.industry, user.industry)
    if b.brochure:
        r = db.get(ReferenceFile, b.brochure)
        if not r or r.user_id != user.id or r.kind != "document":
            raise HTTPException(404, "The brochure wasn't found in your reference files. Upload it as a PDF first.")
    resolve_design(db, user, b, playbook)
    return build_html(b, slug, writer(db, user.id, b.writer, agent="page_writer"), _media(db, user.id, b), ref_text, playbook)


@router.post("/api/sites/directions")
def directions(b: Brief, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Three clearly different designs for the same brief, rendered instantly (no AI cost) so the user can pick one."""
    rate_limit(f"directions:{user.id}", 30, 600)
    playbook = match_playbook(b.industry, user.industry)
    media = _media(db, user.id, b)
    b = b.model_copy()
    m = apply_design_match(b)
    start = zlib.crc32(b.business.encode()) % len(STYLE_SETS)
    styles = [STYLE_SETS[(start + i) % len(STYLE_SETS)] for i in range(len(STYLE_SETS))]
    if m:  # first option: the look and fonts proven for this kind of business, then two clearly different ones
        styles = [{"look": m["look"], "font": "auto" if m["font_heading"] else "jakarta",
                   "decor": "blobs" if m["look"] in ("modern", "playful") else "plain", "theme": "light"}] + \
                 [x for x in styles if x["look"] != m["look"]]
    out = []
    for i, layout in enumerate(ranked_layouts(db, user, b, playbook)[:3]):
        style = styles[i]
        option = b.model_copy(update={"layout": layout, **style})
        matched = bool(m) and i == 0
        out.append({"layout": layout, **style, "label": LAYOUT_LABELS[layout], "description": LAYOUTS[layout],
                    "matched": m["category"] if matched else "", "html": template_html(option, "preview", media, playbook)})
    return out


class MatchIn(BaseModel):
    industry: str = Field("", max_length=80)
    business: str = Field("", max_length=120)
    offer: str = Field("", max_length=160)


@router.post("/api/sites/design-match")
def design_match(body: MatchIn, user: User = Depends(current_user)):
    """The design the data suggests for this kind of business (instant, offline), or null when nothing fits well."""
    m = match_design(body.industry, body.business, body.offer)
    if not m:
        return None
    return {k: m[k] for k in ("category", "primary", "accent", "font_heading", "font_body", "look", "style", "pattern")}


@router.post("/api/sites")
def create_site(b: Brief, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(f"site:{user.id}", 20, 600)
    slug = _slugify(b.business)
    html, source = _generate(db, user, b, slug)
    html, fixed = _auto_fix(db, user, html, b)
    s = Site(user_id=user.id, name=b.business, slug=slug, brief=b.model_dump(), html=html)
    db.add(s)
    db.flush()
    add_version(db, s, "Generated", source)
    db.commit()
    if fixed:
        from ..agents import record
        record(db, user.id, "page_fixer", f"Tidied “{s.name}” before you saw it", {"site_id": s.id, "fixed": fixed},
               [{"label": f, "status": "done", "detail": ""} for f in fixed])
    return {**site_out(s, True), "generator": source, "auto_fixed": fixed}


def _auto_fix(db: Session, user: User, html: str, b: Brief) -> tuple:
    """The Page Fixer agent cleans up safe launch issues on every new page (unless the user turned it off)."""
    from ..agents import enabled
    from ..agents.fixer import fix_html
    if not enabled(db, user.id, "page_fixer"):
        return html, []
    return fix_html(html, b.model_dump())


@router.get("/api/sites/playbooks")
def playbooks(user: User = Depends(current_user)):
    return [playbook_out(k) for k in PLAYBOOKS]


@router.get("/api/sites/{site_id}")
def get_site(site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return site_out(_own(db, user, site_id), True)


@router.get("/api/sites/{site_id}/preview", response_class=HTMLResponse)
def preview_site(site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Owner-only render for thumbnails: works for drafts and doesn't count as a visit."""
    s = _own(db, user, site_id)
    return HTMLResponse(s.html or "", headers={"Content-Security-Policy": SITE_CSP, "X-Content-Type-Options": "nosniff",
                                               "Cache-Control": "no-store"})


class SitePatch(BaseModel):
    html: Optional[str] = None
    name: Optional[str] = None
    custom_domain: Optional[str] = None
    published: Optional[bool] = None
    note: Literal["Edited HTML", "Edited visually", "Edited with AI"] = "Edited HTML"  # how the version history labels this change


MERGE_WINDOW = 180  # seconds: autosaved visual edits within this window update one version instead of piling up new ones


def _merge_or_add_version(db: Session, s: Site, note: str) -> None:
    last = db.scalar(select(SiteVersion).where(SiteVersion.site_id == s.id).order_by(SiteVersion.number.desc()))
    if note == "Edited visually" and last is not None and last.note == note and last.created_at is not None:
        age = (utcnow() - last.created_at.replace(tzinfo=None)).total_seconds()
        if age < MERGE_WINDOW:
            last.html = s.html
            return
    add_version(db, s, note, "ai" if note == "Edited with AI" else "manual")


@router.patch("/api/sites/{site_id}")
def update_site(site_id: int, body: SitePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _own(db, user, site_id)
    changes = body.model_dump(exclude_none=True, exclude={"note"})
    if "html" in changes and len(changes["html"]) > 3_000_000:
        raise HTTPException(400, "The page is too large (over 3 MB). Remove embedded images or video.")
    html_changed = "html" in changes and changes["html"] != s.html
    if changes.get("published") and not s.published:
        from ..workspaces import require_approved
        require_approved(db, user, "site", s.id)
    if "custom_domain" in changes:
        from ..domains import set_domain
        set_domain(db, s, changes.pop("custom_domain"))
    for k, v in changes.items():
        setattr(s, k, v)
    if html_changed:
        _merge_or_add_version(db, s, body.note)
    db.commit()
    return site_out(s, True)


# ---- Ask AI: change one section (or the whole page) from a plain-language instruction ------------
class AiEditIn(BaseModel):
    instruction: str = Field(min_length=3, max_length=600)
    section: Optional[str] = Field(None, max_length=400_000)  # the clicked section's HTML; omit to change the whole page
    page: Optional[str] = Field(None, max_length=60)  # an extra page's slug, for whole-page changes on it


_DATA_URI = re.compile(r"data:[a-z]+/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]+", re.I)
_MARKER = re.compile(r"<!--aimva-script-\d+-->")


def _shrink(html: str) -> tuple:
    """Swap embedded images for short tokens so the AI sees the structure, not megabytes of base64."""
    blobs: list = []
    out = _DATA_URI.sub(lambda m: f"__AIMVA_IMG_{blobs.append(m.group(0)) or len(blobs) - 1}__", html)
    return out, blobs


def _unshrink(html: str, blobs: list) -> str:
    return re.sub(r"__AIMVA_IMG_(\d+)__", lambda m: blobs[int(m.group(1))] if int(m.group(1)) < len(blobs) else "", html)


def _strip_fence(out: str) -> str:
    return re.sub(r"^```(?:html)?\s*|\s*```$", "", (out or "").strip())


AI_EDIT_RULES = ("Keep the same language, the existing CSS classes and CSS variables (var(--p), var(--a)) so it still matches the page. "
                 "Never invent prices, numbers, reviews, awards or contact details that aren't already there. "
                 "Keep every placeholder that looks like __AIMVA_IMG_0__ and every HTML comment exactly as they are. "
                 "No <script> tags, no inline event handlers.")


@router.post("/api/sites/{site_id}/ai-edit")
def ai_edit(site_id: int, body: AiEditIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Change part of the page in plain words ("make this darker", "add three FAQs"). With a section, the rewritten
    section comes back for the editor to drop in (and autosave). Without one, the whole page is rewritten and saved."""
    rate_limit(f"site-ai-edit:{user.id}", 40, 600)
    s = _own(db, user, site_id)
    write = writer(db, user.id, (s.brief or {}).get("writer") or "auto", agent="page_writer")
    if not write:
        raise HTTPException(400, "Ask AI needs an AI writer. Add one in Settings → AI providers, or edit the page by clicking on it.")
    instruction = body.instruction.strip()
    if body.section is not None:
        src = body.section.strip()
        if not re.match(r"^<[a-zA-Z]", src):
            raise HTTPException(400, "Click a section of the page first.")
        small, blobs = _shrink(src)
        out = write("You are editing ONE part of a landing page (a section, or just a few selected words). Here is its HTML:\n\n" + small
                    + f"\n\nChange it as the owner asks: \"{instruction}\". " + AI_EDIT_RULES
                    + " Keep the outer element's tag and its data-aimva-section attribute if it has one."
                    + " If the section contains the lead form (form data-aimva-lead), keep that form and all its fields working."
                    + " Return ONLY the new HTML for this section, nothing else.", max_tokens=6000)
        new = _strip_fence(out or "")
        if src.startswith("<span") and new and not new.startswith("<") and len(new) < 2000:
            new = f"<span>{H.escape(new)}</span>"  # selected words often come back as plain text
        if not re.match(r"^<[a-zA-Z]", new):
            raise HTTPException(502, "The AI didn't return a usable section. Try saying it another way.")
        if "data-aimva-lead" in src and "data-aimva-lead" not in new:
            raise HTTPException(502, "The AI removed your lead form, so the change was not applied. Try again.")
        new = _unshrink(sanitize_html(new), blobs)
        missing = [m for m in _MARKER.findall(src) if m not in new]
        return {"section": new + "".join(missing)}
    page = _page(s, body.page) if body.page else None
    current = page["html"] if page else (s.html or "")
    small, blobs = _shrink(current)
    if len(small) > 120_000:
        raise HTTPException(400, "This page is too big to change all at once. Click a section first, then ask.")
    out = write("Here is a complete landing page:\n\n" + small + f"\n\nChange it as the owner asks: \"{instruction}\". "
                + AI_EDIT_RULES + " Keep the lead form (form data-aimva-lead) and all its fields. "
                "Return ONLY the full HTML document.", max_tokens=12000)
    new = _strip_fence(out or "")
    if "<html" not in new.lower() or "data-aimva-lead" not in new:
        raise HTTPException(502, "The AI didn't return a usable page, so nothing was changed. Try saying it another way.")
    # The lead-form script and tracking tags are ours, not the AI's: carry them over from the current page.
    scripts = re.findall(r"<script\b[\s\S]*?</script\s*>", current, re.I)
    new = _unshrink(sanitize_html(new), blobs)
    if scripts:
        new = new.replace("</body>", "".join(scripts) + "</body>", 1) if "</body>" in new else new + "".join(scripts)
    if page:
        s.pages = [{**p, "html": new} if p["slug"] == page["slug"] else p for p in s.pages]
    else:
        s.html = new
        add_version(db, s, "Edited with AI", "ai")
    db.commit()
    return {"site": site_out(s, True)}


# ---- extra pages (About, Pricing, Contact…): same design, shared menu, one address ----------------
MAX_PAGES = 10
RESERVED_PAGES = {"brochure", "lead", "index", "api", "s"}


def _page(s: Site, slug: str) -> dict:
    p = next((p for p in (s.pages or []) if p["slug"] == slug), None)
    if not p:
        raise HTTPException(404, "Page not found.")
    return p


def _page_slug(title: str, taken: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "page"
    if base in RESERVED_PAGES:
        base += "-page"
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    return slug


def nav_html(s: Site, current: str = "", base: str = "") -> str:
    """The shared menu, added when the page is served (so it always lists every page). base="" → AIMVA hosting links."""
    if not s.pages:
        return ""
    home = base or f"/s/{s.slug}"
    link = (lambda slug: f"{base}{slug}/") if base else (lambda slug: f"/s/{s.slug}/{slug}")
    items = [("", "Home", home)] + [(p["slug"], p["title"], link(p["slug"])) for p in s.pages]
    a = "".join(f'<a href="{H.escape(u)}" style="color:inherit;text-decoration:none;padding:6px 2px;'
                f'{"border-bottom:2px solid var(--p,var(--gd,#6366f1));" if k == current else "opacity:.75;"}">{H.escape(t)}</a>'
                for k, t, u in items)
    return ('<nav data-aimva-nav aria-label="Site" style="position:sticky;top:0;z-index:40;display:flex;flex-wrap:wrap;gap:6px 22px;'
            'justify-content:center;padding:10px 16px;background:rgba(255,255,255,.94);backdrop-filter:blur(8px);color:#111827;'
            f'border-bottom:1px solid rgba(0,0,0,.08);font:600 14px/1.4 system-ui,sans-serif">{a}</nav>')


_CALLBACK_LABEL = re.compile(r'<label[^>]*>\s*<input[^>]*name="callback"[^>]*>[^<]*</label>', re.I)


def can_call_back(user_id: int) -> bool:
    """Whether the owner has a phone line, so the "Call me now" promise on their page can be kept."""
    from ..db import SessionLocal
    from ..services import get_integration
    if settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number:
        return True
    with SessionLocal() as db:
        return get_integration(db, user_id, "twilio") is not None


def with_nav(html: str, s: Site, current: str = "", base: str = "") -> str:
    html = html.replace('href="#aimva-home"', f'href="{H.escape(base or f"/s/{s.slug}")}"')
    if 'name="callback"' in html and not can_call_back(s.user_id):
        html = _CALLBACK_LABEL.sub("", html)  # no phone line yet: don't promise a call within a minute
    nav = nav_html(s, current, base)
    if not nav:
        return html
    out, n = re.subn(r"<body[^>]*>", lambda m: m.group(0) + nav, html, count=1, flags=re.I)
    return out if n else nav + html


def _page_html(s: Site, title: str, sections: str) -> str:
    """A new page that reuses the home page's styles and footer, with its own sections in the middle."""
    home = s.html or ""
    head = re.search(r"<head[^>]*>[\s\S]*?</head>", home, re.I)
    head = head.group(0) if head else '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
    head = re.sub(r"<script\b[\s\S]*?</script\s*>", "", head, flags=re.I)
    t = f"<title>{H.escape(title)} · {H.escape(s.name)}</title>"
    head = re.sub(r"<title>[\s\S]*?</title>", t, head, count=1, flags=re.I) if re.search(r"<title>", head, re.I) else head.replace("</head>", t + "</head>")
    footer = re.search(r"<footer\b[\s\S]*?</footer>", home, re.I)
    thanks = (s.brief or {}).get("thank_you") or "Thanks! We'll be in touch shortly."
    return (f'<!doctype html><html lang="en">{head}<body>{sections}{footer.group(0) if footer else ""}'
            f"{_form_script(s.slug, thanks)}</body></html>")


class PageIn(BaseModel):
    title: str = Field(min_length=2, max_length=60)
    about: str = Field("", max_length=600)  # what should be on it, in the owner's words


class PagePatch(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=60)
    html: Optional[str] = Field(None, max_length=3_000_000)


@router.post("/api/sites/{site_id}/pages")
def add_page(site_id: int, body: PageIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(f"site-page:{user.id}", 20, 600)
    s = _own(db, user, site_id)
    if len(s.pages or []) >= MAX_PAGES:
        raise HTTPException(400, f"A site can have up to {MAX_PAGES} extra pages.")
    title = body.title.strip()
    slug = _page_slug(title, {p["slug"] for p in s.pages or []})
    e = H.escape
    sections = ""
    write = writer(db, user.id, (s.brief or {}).get("writer") or "auto", agent="page_writer")
    if write:
        small, blobs = _shrink((s.html or "")[:60_000])
        facts = json.dumps({k: v for k, v in (s.brief or {}).items() if k in ("business", "industry", "audience", "offer", "features",
                                                                              "about", "address", "phone", "contact_email") and v}, ensure_ascii=False)
        out = write(f"Here is the home page of a website:\n\n{small}\n\nWrite the main content for a new “{title}” page of the same site"
                    + (f" (the owner says: {body.about.strip()})" if body.about.strip() else "")
                    + f". Facts about the business: {facts}. Use the same CSS classes and CSS variables so it matches. "
                    "Write in the same language as the home page. Return ONLY 2 to 4 <section data-aimva-section> elements, no <html>, "
                    "<head>, header, footer or nav. " + AI_EDIT_RULES, max_tokens=6000)
        out = _strip_fence(out or "")
        if out.startswith("<section"):
            sections = _unshrink(sanitize_html(out), blobs)
    if not sections:
        intro = e(body.about.strip()) or f"Tell visitors about {e(title.lower())} here. Click this text to write it, or ask AI to draft it."
        btn = ("display:inline-block;padding:14px 22px;border-radius:12px;background:var(--p,var(--dk,#111827));color:#fff;"
               "text-decoration:none;font-weight:600")
        sections = (f'<section class="block" data-aimva-section="intro" style="padding:64px 0 40px"><h1>{e(title)}</h1>'
                    f'<p style="font-size:18px;margin-top:16px;max-width:65ch">{intro}</p></section>'
                    f'<section class="block" data-aimva-section="cta" style="text-align:center;padding:40px 0 72px"><h2>Want to talk?</h2>'
                    f'<p style="margin-top:16px"><a href="#aimva-home" style="{btn}">{e((s.brief or {}).get("cta") or "Get in touch")}</a></p></section>')
        sections = f'<div style="max-width:1120px;margin:0 auto;padding:0 20px">{sections}</div>'  # the home page's width, whatever the design
    s.pages = [*(s.pages or []), {"slug": slug, "title": title, "html": _page_html(s, title, sections)}]
    db.commit()
    return site_out(s, True)


@router.patch("/api/sites/{site_id}/pages/{page}")
def update_page(site_id: int, page: str, body: PagePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _own(db, user, site_id)
    _page(s, page)
    s.pages = [{**p, **body.model_dump(exclude_none=True)} if p["slug"] == page else p for p in s.pages]
    db.commit()
    return site_out(s, True)


@router.delete("/api/sites/{site_id}/pages/{page}")
def delete_page(site_id: int, page: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _own(db, user, site_id)
    _page(s, page)
    s.pages = [p for p in s.pages if p["slug"] != page]
    db.commit()
    return site_out(s, True)


@router.post("/api/sites/{site_id}/regenerate")
def regenerate(site_id: int, b: Brief, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(f"site:{user.id}", 20, 600)
    s = _own(db, user, site_id)
    html, source = _generate(db, user, b, s.slug)
    s.html = _auto_fix(db, user, html, b)[0]
    s.brief, s.name = b.model_dump(), b.business
    add_version(db, s, "Regenerated", source)
    db.commit()
    return {**site_out(s, True), "generator": source}


@router.get("/api/sites/{site_id}/versions")
def list_versions(site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _own(db, user, site_id)
    q = select(SiteVersion).where(SiteVersion.site_id == s.id).order_by(SiteVersion.number.desc())
    return [{"id": v.id, "number": v.number, "note": v.note, "generator": v.generator, "created_at": v.created_at.isoformat(),
             "current": v.html == s.html} for v in db.scalars(q)]


def _version(db: Session, s: Site, vid: int) -> SiteVersion:
    v = db.get(SiteVersion, vid)
    if not v or v.site_id != s.id:
        raise HTTPException(404, "Version not found.")
    return v


@router.get("/api/sites/{site_id}/versions/{vid}")
def get_version(site_id: int, vid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    v = _version(db, _own(db, user, site_id), vid)
    return {"id": v.id, "number": v.number, "note": v.note, "html": v.html, "brief": v.brief}


@router.post("/api/sites/{site_id}/versions/{vid}/restore")
def restore_version(site_id: int, vid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _own(db, user, site_id)
    v = _version(db, s, vid)
    s.html, s.brief = v.html, v.brief or s.brief
    add_version(db, s, f"Restored version {v.number}", v.generator)
    db.commit()
    return site_out(s, True)


def site_checks(s: Site, db: Optional[Session] = None) -> list:
    """The pre-launch audit: blockers, warnings (e.g. numbers the user never gave us) and tips."""
    brief = s.brief or {}
    ref = ""
    if db is not None and brief.get("references"):
        ref = reference_text(db, s.user_id, [int(x) for x in brief["references"] if str(x).isdigit()])
    return audit_page(s.html, brief, ref)


@router.get("/api/sites/{site_id}/checks")
def checks(site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return site_checks(_own(db, user, site_id), db)


@router.get("/api/sites/{site_id}/audit")
def audit(site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = site_checks(_own(db, user, site_id), db)
    return {"checks": c, "readiness": readiness(c)}


@router.post("/api/sites/{site_id}/autofix")
def autofix(site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """One tap: the Page Fixer applies every fix that has one right answer, as a new version (so it can be undone)."""
    from .agents import fix_site
    s = _own(db, user, site_id)
    out = fix_site(db, user, s.id)
    db.refresh(s)
    c = site_checks(s, db)
    return {"site": site_out(s, True), "fixed": out["fixed"], "checks": c, "readiness": readiness(c)}


# ---- before generating: playbooks, brief review and import ---------------------------------------
class EmbedIn(BaseModel):
    ref: str = Field(max_length=1000, pattern=r"^(https://\S+|(asset|brand|ref):\d+)$")


@router.post("/api/sites/embed-image")
def embed_image(body: EmbedIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A library image as an inline (compressed) source the visual editor can drop into a public page."""
    return {"src": _embed(db, user.id, body.ref)}


@router.post("/api/sites/review-brief")
def review(body: dict, user: User = Depends(current_user)):
    """How complete the brief is and the few questions that would improve the page most (cheap, no AI)."""
    if len(json.dumps(body, default=str)) > 60_000:
        raise HTTPException(400, "That brief is too large.")
    return review_brief(body, user.industry)


class ImportIn(BaseModel):
    url: str = Field(min_length=4, max_length=500)


def _meta(html: str, *names: str) -> str:
    for n in names:
        m = (re.search(rf"<meta[^>]+(?:name|property)=[\"']{re.escape(n)}[\"'][^>]*content=[\"']([^\"']*)", html, re.I)
             or re.search(rf"<meta[^>]+content=[\"']([^\"']*)[\"'][^>]*(?:name|property)=[\"']{re.escape(n)}[\"']", html, re.I))
        if m and m.group(1).strip():
            return H.unescape(m.group(1).strip())
    return ""


def extract_business(html: str, base_url: str = "") -> dict:
    """Facts we can read reliably from a page without AI: name, description, contacts, colour, hero image, address."""
    from ..quality import visible_text
    out = {}
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    name = _meta(html, "og:site_name") or (H.unescape(re.split(r"\s[|\-–—:]\s", title.group(1).strip())[0]) if title else "")
    if name:
        out["business"] = name[:120]
    desc = _meta(html, "description", "og:description")
    if desc:
        out["subheadline"] = desc[:300]
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if h1 and visible_text(h1.group(1)):
        out["headline"] = visible_text(h1.group(1))[:200]
    tel = re.search(r"href=[\"']tel:([+\d][\d\s().-]{6,20})", html, re.I)
    if tel:
        out["phone"] = re.sub(r"\s+", " ", tel.group(1)).strip()[:30]
    wa = re.search(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\d{8,15})", html, re.I)
    if wa:
        out["whatsapp"] = "+" + wa.group(1)
    mail = re.search(r"href=[\"']mailto:([^\"'?]+@[^\"'?]+)", html, re.I)
    if mail and len(mail.group(1)) <= 120:
        out["contact_email"] = mail.group(1).strip()
    color = _meta(html, "theme-color")
    if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        out["primary"] = color.lower()
    img = _meta(html, "og:image", "twitter:image")
    if img and base_url:
        img = urljoin(base_url, img)
    if img.startswith("https://") and len(img) <= 1000 and not re.search(r"\s", img):
        out["hero_image"] = img
    for blob in re.findall(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", html, re.I | re.S)[:5]:
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []:
            if not isinstance(item, dict):
                continue
            addr = item.get("address")
            if isinstance(addr, dict) and "address" not in out:
                parts = [addr.get(k, "") for k in ("streetAddress", "addressLocality", "addressRegion")]
                joined = ", ".join(str(x).strip() for x in parts if x and isinstance(x, str))
                if joined:
                    out["address"] = joined[:200]
            if item.get("telephone") and "phone" not in out and isinstance(item["telephone"], str):
                out["phone"] = item["telephone"][:30]
    return out


ALLOWED_IMPORT = {"business": 120, "industry": 80, "audience": 160, "offer": 160, "headline": 200, "subheadline": 300,
                  "about": 2000, "phone": 30, "whatsapp": 30, "contact_email": 120, "address": 200,
                  "location_line": 80, "price_from": 40, "approvals": 80}
LIST_IMPORT = {  # list fields and the keys (with limits) each item keeps
    "stats": ({"value": 20, "label": 40}, 5), "configurations": ({"name": 60, "area": 60, "details": 240, "price": 40}, 6),
    "distances": ({"place": 80, "time": 30}, 12),
}


def _ai_extract(write, text: str) -> dict:
    prompt = ("From this website text, extract facts for a landing-page brief as JSON with keys: business, industry, "
              "audience, offer, headline, subheadline, about (2-4 sentences), features (list of up to 6 short benefits), "
              "phone, whatsapp, contact_email, address, faqs (list of {q, a}, up to 5, only if the text answers them), "
              "location_line (area and city, short), price_from (starting price exactly as written), approvals (e.g. RERA number), "
              "amenities (list of short names), stats (list of {value, label} for headline numbers like acres or units), "
              "configurations (list of {name, area, details, price} for unit types or plans), distances (list of {place, time} for nearby places). "
              "Use ONLY facts stated in the text; use an empty string or empty list when unknown. Return only JSON.\n\n"
              + text[:7000])
    raw = write(prompt, max_tokens=1500) or ""
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}
    out = {k: str(data[k]).strip()[:n] for k, n in ALLOWED_IMPORT.items() if isinstance(data.get(k), (str, int)) and str(data[k]).strip()}
    feats = [str(f).strip()[:80] for f in data.get("features") or [] if isinstance(f, str) and f.strip()][:6]
    if feats:
        out["features"] = feats
    faqs = [{"q": str(f["q"]).strip()[:200], "a": str(f["a"]).strip()[:800]} for f in data.get("faqs") or []
            if isinstance(f, dict) and len(str(f.get("q", "")).strip()) >= 3 and str(f.get("a", "")).strip()][:5]
    if faqs:
        out["faqs"] = faqs
    amen = [str(a).strip()[:80] for a in data.get("amenities") or [] if isinstance(a, str) and a.strip()][:24]
    if amen:
        out["amenities"] = amen
    for key, (fields, cap) in LIST_IMPORT.items():
        first = next(iter(fields))
        items = [{f: str(x.get(f) or "").strip()[:n] for f, n in fields.items()} for x in data.get(key) or [] if isinstance(x, dict)]
        items = [x for x in items if x[first]][:cap]
        if items:
            out[key] = items
    return out


@router.post("/api/sites/import")
def import_site(body: ImportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Pre-fill a brief from the business's existing website (or a social/Google page that renders HTML)."""
    from ..quality import visible_text
    rate_limit(f"import:{user.id}", 10, 600)
    url = body.url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    try:
        raw = P.download(url, 3 * 1024 * 1024, "that website")
    except P.ProviderError as e:
        msg = e.message if "allowed" not in e.message else "That address can't be imported."
        raise HTTPException(400, msg.replace("the result from that website", "that website"))
    page = raw.decode("utf-8", errors="replace")
    if "<html" not in page.lower() and "<body" not in page.lower():
        raise HTTPException(400, "That link didn't return a web page.")
    found = extract_business(page, url)
    source = "basic"
    write = writer(db, user.id, "auto", agent="site_reader")
    if write:
        ai = _ai_extract(write, visible_text(page))
        if ai:
            source = "ai"
            for k, v in ai.items():
                # Exact values read from links and meta tags beat the model's reading; the rest is better from AI.
                if k in ("business", "phone", "whatsapp", "contact_email") and k in found:
                    continue
                found[k] = v
    if not found:
        raise HTTPException(422, "We couldn't find any business details on that page. Try your home or contact page.")
    return {"brief": found, "fields": sorted(found), "source": source}


SLUG_RE = r"^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$"
DOMAIN_RE = r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$"


class PublishIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=1, max_length=50, pattern=SLUG_RE)
    target: Literal["aimva", "netlify", "vercel"] = "aimva"
    custom_domain: str = Field("", max_length=253)
    seo_title: str = Field("", max_length=70)
    seo_description: str = Field("", max_length=170)

    @field_validator("custom_domain")
    @classmethod
    def _domain(cls, v):
        v = v.strip().lower().removeprefix("https://").removeprefix("http://").rstrip("/")
        if v and not re.match(DOMAIN_RE, v):
            raise ValueError("Enter a domain like offers.yourbrand.com (no https:// or paths).")
        return v


def _apply_seo(html: str, title: str, desc: str) -> str:
    """Set <title> and meta description in the page head (escaped; inserted literally, never as regex syntax)."""
    if title:
        t = f"<title>{H.escape(title)}</title>"
        html, n = re.subn(r"<title>.*?</title>", lambda _: t, html, count=1, flags=re.I | re.S)
        if not n:
            html = re.sub(r"<head[^>]*>", lambda m: m.group(0) + t, html, count=1, flags=re.I)
    if desc:
        meta = f'<meta name="description" content="{H.escape(desc)}">'
        html, n = re.subn(r"<meta[^>]+name=[\"']description[\"'][^>]*>", lambda _: meta, html, count=1, flags=re.I)
        if not n:
            html = re.sub(r"<head[^>]*>", lambda m: m.group(0) + meta, html, count=1, flags=re.I)
    return html


@router.post("/api/sites/{site_id}/publish")
def publish(site_id: int, body: PublishIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """One-step launch: name, address, SEO, pre-launch checks, then deploy."""
    from ..workspaces import require_approved
    rate_limit(f"publish:{user.id}", 20, 600)
    s = _own(db, user, site_id)
    require_approved(db, user, "site", s.id)
    if body.slug != s.slug and db.scalar(select(Site.id).where(Site.slug == body.slug, Site.id != s.id)):
        raise HTTPException(409, "That web address is taken. Try another one.")
    if body.slug != s.slug:  # the lead form and brochure links name the address: move them with it, or leads get lost
        old, new = s.slug, body.slug
        move = lambda h: h.replace(f"/api/public/sites/{old}/", f"/api/public/sites/{new}/").replace(f"/s/{old}/", f"/s/{new}/")
        s.html = move(s.html or "")
        s.pages = [{**p, "html": move(p["html"])} for p in s.pages or []]
    from ..domains import set_domain
    s.name, s.slug = body.name.strip(), body.slug
    set_domain(db, s, body.custom_domain)
    new_html = _apply_seo(s.html, body.seo_title.strip(), body.seo_description.strip())
    if new_html != s.html:
        s.html = new_html
        add_version(db, s, "SEO updated for launch", "manual")
    checks_now = site_checks(s, db)
    blockers = [c["detail"] or c["message"] for c in checks_now if c["level"] == "blocker" and not c["ok"]]
    if blockers:
        db.rollback()
        raise HTTPException(400, "Fix before publishing: " + "; ".join(blockers))
    if not s.published_at:
        s.published_at = utcnow()
    out = _deploy(site_id, DeployIn(target=body.target), user, db)
    return {**out, "checks": checks_now}





@router.delete("/api/sites/{site_id}")
def delete_site(site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own(db, user, site_id))
    db.commit()
    return {"ok": True}


class DeployIn(BaseModel):
    target: str  # aimva | netlify | vercel


@router.post("/api/sites/{site_id}/deploy")
def deploy(site_id: int, body: DeployIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..workspaces import require_approved
    require_approved(db, user, "site", _own(db, user, site_id).id)
    return _deploy(site_id, body, user, db)


def _deploy(site_id: int, body: DeployIn, user: User, db: Session):
    s = _own(db, user, site_id)
    if body.target == "aimva":
        s.published, s.deploy_target, s.deploy_url = True, "aimva", f"{settings.public_url}/s/{s.slug}"
    elif body.target == "netlify":
        token = integration_secret(db, user.id, "netlify").get("api_token")
        if not token:
            raise HTTPException(400, "Connect Netlify in Settings → Integrations first.")
        hdr = {"Authorization": f"Bearer {token}"}
        site_ref = (s.brief or {}).get("_netlify_id")
        if not site_ref:
            r = httpx.post("https://api.netlify.com/api/v1/sites", headers=hdr, json={"name": s.slug}, timeout=30)
            if r.status_code >= 400:
                raise HTTPException(502, f"Netlify error: {r.text[:200]}")
            site_ref = r.json()["id"]
            s.brief = {**s.brief, "_netlify_id": site_ref}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("index.html", with_nav(s.html, s, "", "/"))
            for p in s.pages or []:
                z.writestr(f"{p['slug']}/index.html", with_nav(p["html"], s, p["slug"], "/"))
        r = httpx.post(f"https://api.netlify.com/api/v1/sites/{site_ref}/deploys",
                       headers={**hdr, "Content-Type": "application/zip"}, content=buf.getvalue(), timeout=60)
        if r.status_code >= 400:
            raise HTTPException(502, f"Netlify error: {r.text[:200]}")
        d = r.json()
        s.deploy_target, s.deploy_url = "netlify", d.get("ssl_url") or d.get("url") or ""
    elif body.target == "vercel":
        token = integration_secret(db, user.id, "vercel").get("api_token")
        if not token:
            raise HTTPException(400, "Connect Vercel in Settings → Integrations first.")
        r = httpx.post("https://api.vercel.com/v13/deployments", headers={"Authorization": f"Bearer {token}"},
                       json={"name": s.slug, "target": "production", "projectSettings": {"framework": None},
                             "files": [{"file": "index.html", "data": with_nav(s.html, s, "", "/")}]
                             + [{"file": f"{p['slug']}/index.html", "data": with_nav(p["html"], s, p["slug"], "/")} for p in s.pages or []]},
                       timeout=60)
        if r.status_code >= 400:
            raise HTTPException(502, f"Vercel error: {r.text[:200]}")
        s.deploy_target, s.deploy_url = "vercel", "https://" + r.json().get("url", "")
    else:
        raise HTTPException(400, "Supported targets: aimva, netlify, vercel.")
    s.published = True
    from ..workspaces import keep_approved
    keep_approved(db, user, "site", s.id)
    db.commit()
    return site_out(s)


# ---- public ---------------------------------------------------------------
# Published pages run in a CSP sandbox (an opaque origin): their scripts work, but they can't read AIMVA
# cookies or call the API as a logged-in visitor, even though they're served from the same host.
SITE_CSP = "sandbox allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals"


@router.get("/s/{slug}", response_class=HTMLResponse)
def serve_site(slug: str, db: Session = Depends(get_db)):
    s = db.scalar(select(Site).where(Site.slug == slug))
    if not s or not s.published:
        return HTMLResponse("<h1 style='font-family:sans-serif;padding:40px'>Site not found</h1>", 404)
    # a Core UPDATE, so a page view doesn't count as an edit (updated_at stays put)
    db.execute(update(Site).where(Site.id == s.id).values(visits=Site.visits + 1, updated_at=Site.updated_at))
    db.commit()
    return HTMLResponse(with_nav(s.html, s), headers={"Content-Security-Policy": SITE_CSP, "X-Content-Type-Options": "nosniff",
                                                      "Referrer-Policy": "strict-origin-when-cross-origin"})


@router.get("/s/{slug}/brochure")
def site_brochure(slug: str, db: Session = Depends(get_db)):
    """The page's brochure PDF (shown to visitors after they leave their details)."""
    from fastapi.responses import FileResponse
    s = db.scalar(select(Site).where(Site.slug == slug))
    rid = (s.brief or {}).get("brochure") if s and s.published else None
    r = db.get(ReferenceFile, rid) if rid else None
    if not r or r.user_id != s.user_id or r.kind != "document" or not (UPLOADS / r.path).exists():
        raise HTTPException(404, "Brochure not found.")
    return FileResponse(UPLOADS / r.path, media_type=r.content_type, filename=r.filename,
                        headers={"X-Content-Type-Options": "nosniff", "Content-Disposition": f'inline; filename="{re.sub(r"[^A-Za-z0-9._-]", "_", r.filename)}"'})


@router.get("/s/{slug}/{page}", response_class=HTMLResponse)
def serve_page(slug: str, page: str, db: Session = Depends(get_db)):
    s = db.scalar(select(Site).where(Site.slug == slug))
    p = next((p for p in (s.pages or []) if p["slug"] == page), None) if s and s.published else None
    if not p:
        return HTMLResponse("<h1 style='font-family:sans-serif;padding:40px'>Page not found</h1>", 404)
    return HTMLResponse(with_nav(p["html"], s, page), headers={"Content-Security-Policy": SITE_CSP, "X-Content-Type-Options": "nosniff",
                                                               "Referrer-Policy": "strict-origin-when-cross-origin"})


@router.post("/api/public/sites/{slug}/lead")
async def public_lead(slug: str, request: Request, bg: BackgroundTasks, db: Session = Depends(get_db)):
    # Limits are per visitor, never per page: a page-wide cap let one script lock every real customer out.
    ip = client_ip(request)
    rate_limit(f"publead:{slug}:{ip}", 10, 600)    # one visitor on one page
    rate_limit(f"publead-ip:{ip}", 30, 3600)       # one visitor across every AIMVA page
    try:
        form = await request.form()
    except Exception:
        return {"ok": False}
    get = lambda k, n: str(form.get(k, "") or "")[:n].strip()
    if get("website", 200):  # honeypot: people never see this field, bots fill it in
        return {"ok": True}
    name, email, phone, message = get("name", 160), get("email", 255), get("phone", 40), get("message", 2000)
    # One phone number or email can't be submitted over and over, so the form can't be used to make the
    # Concierge keep messaging someone's WhatsApp.
    contact = re.sub(r"\D", "", phone)[-10:] or email.lower()
    if contact:
        rate_limit(f"publead-contact:{slug}:{contact}", 3, 3600)
    s = db.scalar(select(Site).where(Site.slug == slug))
    if not s or not (email or phone):
        return {"ok": False}
    # Optional custom fields from the page's form are kept with the message.
    labels = {**FIELD_LABELS, "interest": "Interested in", "timeline": "Planning", "best_time": "Best time to call"}
    extras = [f"{labels[k]}: {get(k, 200)}" for k in ("interest", "timeline", "budget", "preferred_date", "best_time", "city", "company") if get(k, 200)]
    action = {"brochure": "Asked for the brochure", "price": "Asked for the price sheet"}.get(get("action", 20))
    if action:
        extras.insert(0, action)
    if extras:
        message = (message + "\n" + "\n".join(extras)).strip()
    # Attribution: ads link to the page with ?aimva_c=<campaign id> (the form script passes it along).
    from ..models import Campaign
    campaign = None
    cid = get("aimva_c", 12)
    if cid.isdigit():
        campaign = db.get(Campaign, int(cid))
        if campaign and campaign.user_id != s.user_id:
            campaign = None
    utm = ", ".join(f"{k}={get(k, 100)}" for k in ("utm_source", "utm_medium", "utm_campaign") if get(k, 100))
    if utm:
        message = (message + f"\nCame from: {utm}").strip()
    lead = create_lead(db, s.user_id, bg, name=name, email=email, phone=phone, message=message[:2400],
                       source="website", source_ref=s.slug, event={"title": f"{action or 'Submitted the form'} on {s.name}"},
                       product_id=s.product_id or (campaign.product_id if campaign else None),
                       campaign_id=campaign.id if campaign else None)
    wants_call = get("callback", 10).lower() in ("yes", "on", "true", "1")
    if wants_call and phone and (s.brief or {}).get("contact_mode", "own_phone") != "own_phone":
        request_callback(db, s, lead, phone, bg)
    return {"ok": True}


def _e164(phone: str, country_code: str = "+91") -> str:
    """International format for dialling: keeps +numbers, otherwise adds the page's country code (dropping a leading 0)."""
    raw = phone.strip()
    digits = re.sub(r"\D", "", raw)
    if not raw.startswith("+"):
        digits = re.sub(r"\D", "", country_code) + digits.lstrip("0")
    return ("+" + digits) if 8 <= len(digits) <= 15 else ""


def request_callback(db: Session, site: Site, lead, phone: str, bg: BackgroundTasks) -> None:
    """A visitor asked the AIMVA voice agent to call them. Logged on the lead; dialled in the background.
    Limited per page and per number so a public form can't be used to spam calls."""
    from .leads import add_event
    number = _e164(phone, (site.brief or {}).get("country_code") or "+91")
    allowed = bool(number)
    try:
        rate_limit(f"callback-site:{site.id}", 30, 3600)
        rate_limit(f"callback-num:{number}", 1, 900)
    except HTTPException:
        allowed = False
    add_event(db, lead, "call", "Asked for a call back", "From the landing page form" if allowed else
              "Not dialled automatically (invalid number or too many requests). Call them from the lead panel.",
              source="website", ref=site.slug)
    db.commit()
    if allowed:
        bg.add_task(_dial_back, site.user_id, lead.id, number, (site.brief or {}).get("voice_agent_id"))


def _dial_back(user_id: int, lead_id: int, number: str, agent_id: Optional[int]) -> None:
    from ..db import SessionLocal
    from ..models import Lead, VoiceAgent
    from .leads import add_event
    from .voice import place_phone_call
    db = SessionLocal()
    try:
        user, lead = db.get(User, user_id), db.get(Lead, lead_id)
        q = select(VoiceAgent).where(VoiceAgent.user_id == user_id)
        agent = (db.get(VoiceAgent, agent_id) if agent_id else None) or db.scalar(q.order_by(VoiceAgent.id))
        if agent and agent.user_id != user_id:
            agent = None
        if not (user and lead):
            return
        if not agent:
            add_event(db, lead, "call", "Call back waiting", "Create a voice agent so AIMVA can call leads back automatically.")
        else:
            try:
                place_phone_call(db, user, agent, number, lead_id=lead.id)
                add_event(db, lead, "call", f"{agent.name} is calling them back")
            except HTTPException as e:
                add_event(db, lead, "call", "Call back waiting", str(e.detail))
        db.commit()
    finally:
        db.close()
