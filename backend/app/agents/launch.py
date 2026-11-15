"""Launch Agent: from one link, brochure or sentence to everything needed to start getting leads.

Steps (each is recorded; a step that can't run is skipped with the reason, the rest still happen):
  1. read the facts      from the website link (import), the uploaded brochure, and/or the one-line description
  2. product              a Command Center product with the monthly budget, so results roll up in one place
  3. landing page         a Showcase page (or the best layout for the facts), written by AI from those facts only
  4. page fixes           the Page Fixer cleans up anything safe before the user sees it
  5. ad drafts            Meta / Google / LinkedIn drafts with copy, the page's photo and a tracked link
  6. voice assistant      a call-back assistant for the industry, if the user doesn't have one yet
  7. lead follow-up       the Lead Concierge is switched on for the new page's leads
Nothing goes live on its own unless the user asked to publish: ads stay drafts until they press Publish.
"""
import json
import re
from typing import List, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import Job, setting
from ..config import settings
from ..models import AgentJob, Asset, BrandAsset, BrandKit, Campaign, Product, Site, User, VoiceAgent, utcnow
from ..quality import PLAYBOOKS, match_playbook

CTA = {"real_estate": "Book now", "healthcare": "Book now", "education": "Sign up", "restaurant": "Book now"}
FACT_KEYS = ("business", "industry", "audience", "offer", "headline", "subheadline", "about", "features", "faqs", "phone",
             "whatsapp", "contact_email", "address", "location_line", "price_from", "approvals", "amenities", "stats",
             "configurations", "distances")


class LaunchIn(BaseModel):
    url: str = Field("", max_length=500)  # the business's website, a project page, or a listing
    business: str = Field("", max_length=160)  # the business being launched; else read from the site, the profile or the description
    description: str = Field("", max_length=1000)  # or just one line: "3 BHK flats in Kokapet from ₹1.2 Cr, ready by 2027"
    reference_id: Optional[int] = None  # an uploaded brochure / document
    product: str = Field("", max_length=160)
    monthly_budget: float = Field(0, ge=0, le=1e8)
    platforms: List[Literal["meta", "google", "linkedin"]] = Field(default_factory=lambda: ["meta"], max_length=3)
    publish: bool = False  # put the page live straight away
    image: str = Field("", max_length=1000)  # optional hero photo (https:// or asset:/brand:/ref: id)


def _facts(db: Session, user: User, body: LaunchIn, job: Job) -> dict:
    from ..quality import visible_text
    from ..routers import sites
    from ..routers.providers import writer
    from ..routers.references import reference_text
    from .. import providers as P
    facts, write = {}, writer(db, user.id, "auto", agent="site_reader")
    if body.url:
        url = body.url.strip() if re.match(r"^https?://", body.url.strip(), re.I) else "https://" + body.url.strip()
        try:
            page = P.download(url, 3 * 1024 * 1024, "that website").decode("utf-8", errors="replace")
            facts.update(sites.extract_business(page, url))
            if write:
                facts.update({k: v for k, v in sites._ai_extract(write, visible_text(page)).items()
                              if k not in facts or k not in ("business", "phone", "whatsapp", "contact_email")})
            job.step("Read your website", detail=f"Found: {', '.join(sorted(facts)) or 'nothing usable'}")
        except P.ProviderError as e:
            job.step("Read your website", "failed", e.message)
    if body.reference_id:
        text = reference_text(db, user.id, [body.reference_id])
        got = sites._ai_extract(write, text) if (write and text) else {}
        for k, v in got.items():
            facts.setdefault(k, v)
        job.step("Read your brochure", "done" if got else "skipped", f"Found: {', '.join(sorted(got))}" if got else
                 "No AI writer was free to read it; its text still briefs the page writer.")
    if body.description:
        facts.setdefault("offer", body.description[:160])
        if len(body.description) > 160:
            facts.setdefault("about", body.description)
    if body.business.strip():
        facts["business"] = body.business.strip()
    # The description often starts with the name ("SmileCare Dental, Kondapur…"): better than failing the launch.
    facts.setdefault("business", user.company or (short_name(body.description) if body.description else ""))
    if not facts.get("industry") and user.industry:
        facts["industry"] = PLAYBOOKS[match_playbook("", user.industry)]["label"]
    return {k: v for k, v in facts.items() if k in FACT_KEYS and v}


def short_name(text: str) -> str:
    """“Skyline Heights: 2 & 3 BHK in Kokapet…” → “Skyline Heights”; otherwise the first few words."""
    text = text.strip()
    m = re.match(r"^(.{3,60}?)\s*(?::|\s[-–—|]\s)", text)
    if m:
        return m.group(1).strip()
    text = re.split(r",|;|\.\s|\s(?:from|starting|at|for just|with)\s", text, maxsplit=1)[0].strip().rstrip(".!")
    words = text.split()
    return " ".join(words[:7]) + ("…" if len(words) > 7 else "")


def _hero(db: Session, user: User, body: LaunchIn) -> str:
    if body.image:
        return body.image
    img = db.scalar(select(BrandAsset).where(BrandAsset.user_id == user.id, BrandAsset.kind == "image").order_by(BrandAsset.id.desc()))
    if img:
        return f"brand:{img.id}"
    a = db.scalar(select(Asset).where(Asset.user_id == user.id, Asset.kind == "image", Asset.status == "done").order_by(Asset.id.desc()))
    return f"asset:{a.id}" if a else ""


def clip(text: str, limit: int) -> str:
    """Shorten at a word boundary, never mid-word, without a dangling comma or 'and'."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit + 1].rsplit(" ", 1)[0] if " " in text[:limit + 1] else text[:limit]
    cut = re.sub(r"[\s,;:–—-]+$", "", cut)
    cut = re.sub(r"\s+(and|or|with|in|at|for|from|the|a|an|&)$", "", cut, flags=re.I)
    return cut.rstrip(".,;: ")


def _headline(facts: dict, product: str = "") -> str:
    if facts.get("headline"):
        return clip(facts["headline"], 40)
    business, offer = facts.get("business", ""), facts.get("offer", "")
    if product and business and product != business and len(f"{product} at {business}") <= 40:
        return f"{product} at {business}"
    if offer and len(offer) <= 40:
        return offer.rstrip(".")
    return clip(product or short_name(offer or business).rstrip("…"), 40)


def _ad_copy(db: Session, user: User, facts: dict, playbook: str, product: str = "") -> dict:
    from ..routers.providers import writer
    offer = facts.get("offer") or facts.get("headline") or facts["business"]
    bits = [offer.rstrip(".") + "."]
    if facts.get("price_from"):
        bits.append(f"From {facts['price_from']}.")
    if facts.get("location_line") or facts.get("address"):
        bits.append(f"📍 {facts.get('location_line') or facts['address']}.")
    bits += [f"✓ {f}" for f in (facts.get("features") or [])[:3]]
    copy = {"headline": _headline(facts, product), "text": "\n".join(bits)[:500], "cta": CTA.get(playbook, "Learn more")}
    write = writer(db, user.id, agent="copywriter")
    if write:
        out = write("Write one Meta lead ad for this business as JSON {\"headline\": max 40 chars, \"text\": max 300 chars}. "
                    "Use only these facts; no invented numbers, awards or claims; no exclamation marks. Facts: "
                    + json.dumps({k: facts[k] for k in facts if k in ("business", "offer", "features", "price_from", "location_line", "audience")},
                                 ensure_ascii=False), max_tokens=400)
        m = re.search(r"\{.*\}", out or "", re.S)
        try:
            ai = json.loads(m.group(0)) if m else {}
        except ValueError:
            ai = {}
        if isinstance(ai, dict) and isinstance(ai.get("headline"), str) and isinstance(ai.get("text"), str) and ai["headline"].strip():
            copy.update(headline=clip(ai["headline"].strip(), 40), text=ai["text"].strip()[:500])
    return copy


def _voice(db: Session, user: User, playbook: str, business: str = "") -> Optional[VoiceAgent]:
    from ..template_agent import fill, user_ctx
    from ..templates_catalog import CATALOG
    if db.scalar(select(VoiceAgent.id).where(VoiceAgent.user_id == user.id)):
        return None
    voice = [t for t in CATALOG if t["module"] == "voice"]
    t = next((t for t in voice if playbook in t["industries"]), None) or next((t for t in voice if not t["industries"]), voice[0])
    p = fill(t["payload"], user_ctx(db, user))
    a = VoiceAgent(user_id=user.id, name=f"{business or user.company or 'AIMVA'} assistant"[:120], language=p.get("language", "en-US"),
                   greeting=p["greeting"], instructions=p.get("instructions", ""), questions=p["questions"])
    db.add(a)
    db.commit()
    return a


def run(db: Session, job_row: AgentJob) -> None:
    """Runs in the background after POST /api/agents/launch; progress is pushed live to the user's open tabs."""
    from ..routers import sites
    from .fixer import fix_html, remaining
    user = db.get(User, job_row.user_id)
    body = LaunchIn(**job_row.input)
    job = Job(db, user.id, "launch", job_row.title, job=job_row)
    result = {"campaign_ids": [], "next": []}
    try:
        facts = _facts(db, user, body, job)
        if not (facts.get("offer") or facts.get("about") or facts.get("headline") or facts.get("features")):
            raise HTTPException(400, "We couldn't find what you're selling. Add a one-line description and try again.")
        if not facts.get("business"):
            raise HTTPException(400, "Tell the agent the business name (or add it in Settings → Profile), then try again.")
        playbook = match_playbook(facts.get("industry", ""), user.industry)

        name = (body.product.strip() or short_name(facts.get("offer") or facts["business"]))[:160]
        product = db.scalar(select(Product).where(Product.user_id == user.id, Product.name == name))
        if not product:
            product = Product(user_id=user.id, name=name, monthly_budget=body.monthly_budget)
            db.add(product)
            db.commit()
            job.step("Created the product in Command Center", detail=f"“{name}”" + (f", budget {body.monthly_budget:,.0f}/month" if body.monthly_budget else ""))
        else:
            job.step("Using your existing product", detail=f"“{name}”")
        result["product_id"] = product.id

        kit = db.scalar(select(BrandKit).where(BrandKit.user_id == user.id))
        brief = {**{k: v for k, v in facts.items() if k in sites.Brief.model_fields}, "use_ai": True, "layout": "auto",
                 "page_type": playbook if playbook in ("real_estate", "restaurant") else "lead_gen",
                 "hero_image": _hero(db, user, body), "references": [body.reference_id] if body.reference_id else [],
                 "sections": ["features", *(["faq"] if facts.get("faqs") else []), *(["about"] if facts.get("about") else [])]}
        if not facts.get("headline") and name != facts["business"] and not name.endswith("…"):
            brief["headline"] = name  # the project / product name reads better than "Business: whole description"
        if kit and kit.colors:
            brief.update(primary=kit.colors[0], accent=(kit.colors[1] if len(kit.colors) > 1 else kit.colors[0]))
        if facts.get("phone"):
            brief["contact_mode"] = "both"
        try:
            b = sites.Brief(**brief)
        except ValidationError:  # a fact in an odd shape shouldn't stop the launch: keep the core ones
            b = sites.Brief(**{k: brief[k] for k in ("business", "offer", "use_ai", "layout", "page_type") if k in brief})
        slug = sites._slugify(b.business)
        html, source = sites._generate(db, user, b, slug)
        fixes = []
        if setting(db, user.id, "page_fixer").enabled:
            html, fixes = fix_html(html, b.model_dump())
        site = Site(user_id=user.id, name=b.business, slug=slug, brief=b.model_dump(), html=html, product_id=product.id)
        db.add(site)
        db.flush()
        sites.add_version(db, site, "Made by the Launch Agent", source)
        if body.publish and user.require_approval and settings.agency_features:
            body.publish = False  # this client signs off first: the page stays a draft until they approve it
        if body.publish:
            site.published, site.deploy_target, site.published_at = True, "aimva", utcnow()
            site.deploy_url = f"{settings.public_url}/s/{slug}"
        db.commit()
        url = f"{settings.public_url}/s/{slug}"
        result.update(site_id=site.id, site_url=url)
        job.step(f"Built the landing page ({sites.LAYOUT_LABELS.get(b.layout, b.layout)} design)", detail=("Written by AI from your facts." if source == "ai"
                 else "Built from your facts with the built-in writer.") + (" It's live." if body.publish else " It's a draft until you publish it."))
        if fixes:
            job.step("Page Fixer tidied the page", detail="; ".join(fixes))
        todo = remaining(html, b.model_dump())
        if todo:
            result["next"].append({"title": "Check the page before publishing", "detail": "; ".join(todo[:3]), "link": "/app/websites"})

        copy = _ad_copy(db, user, facts, playbook, name)
        image = b.hero_image if b.hero_image.startswith("https://") else ""
        for platform in body.platforms:
            c = Campaign(user_id=user.id, platform=platform, name=f"{name} · {platform.title() if platform != 'linkedin' else 'LinkedIn'}"[:200],
                         daily_budget=round(body.monthly_budget / 30 / len(body.platforms), 2) if body.monthly_budget else 0,
                         creative={**copy, "image_url": image}, lead_form={"fields": ["full_name", "phone_number"]}, product_id=product.id)
            db.add(c)
            db.flush()
            c.creative = {**c.creative, "link": f"{url}?aimva_c={c.id}"}
            result["campaign_ids"].append(c.id)
        db.commit()
        if body.platforms:
            job.step(f"Drafted {len(body.platforms)} ad campaign{'s' if len(body.platforms) != 1 else ''}",
                     detail=f"“{copy['headline']}”: tracked link to the page, leads land in Command Center.")
            result["next"].append({"title": "Review the ad and press Publish", "detail": "Ads never go live without you.",
                                   "link": f"/app/ads/{body.platforms[0]}"})

        agent = _voice(db, user, playbook, facts.get("business", ""))
        if agent:
            result["voice_agent_id"] = agent.id
            job.step("Set up a call-back voice assistant", detail=f"“{agent.name}” asks {len(agent.questions)} questions and books the next step.")
        else:
            job.step("Your voice assistant will call new leads back", "skipped", "You already have one, so it's used as is.")

        cs = setting(db, user.id, "concierge")
        cs.enabled = True
        db.commit()
        from ..services import get_integration
        if get_integration(db, user.id, "whatsapp"):
            job.step("Lead Concierge is on", detail="Every new lead gets a WhatsApp welcome in seconds, then follow-ups on day 2 and day 7.")
        else:
            job.step("Lead Concierge is on", "done", "Welcome and follow-up messages are drafted on each lead. Connect WhatsApp to send them automatically.")
            result["next"].append({"title": "Connect WhatsApp", "detail": "So follow-ups go out by themselves.", "link": "/app/settings?tab=integrations"})
        if not body.publish:
            result["next"].insert(0, {"title": "Publish the page", "detail": "One click from Websites.", "link": "/app/websites"})
        job.finish(result, title=f"Launch ready: {name}")
    except HTTPException as e:
        job.step("Stopped", "failed", str(e.detail))
        job.finish(result, title=f"Launch stopped: {e.detail}"[:200], status="failed", error=str(e.detail))
    except Exception as e:  # never leave a job "running" forever
        import logging
        logging.getLogger("aimva.agents").exception("Launch agent failed")
        job.finish(result, title="Launch stopped: something went wrong on our side", status="failed", error=type(e).__name__)
