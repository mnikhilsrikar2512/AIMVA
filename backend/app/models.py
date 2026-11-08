from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    company: Mapped[str] = mapped_column(String(160), default="")
    industry: Mapped[str] = mapped_column(String(40), default="")
    goal: Mapped[str] = mapped_column(String(40), default="")
    onboarding_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    leads_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # for the "new leads" badge
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0)  # bump to revoke sessions
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # person = someone who signs in; workspace = a client business an agency runs (no login of its own, see workspaces.py)
    kind: Mapped[str] = mapped_column(String(20), default="person", server_default="person")
    require_approval: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # client signs off before publishing
    onboarding_answers: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")  # sign-up questions, see onboarding.py
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmailCode(Base):
    """One-time 6-digit codes for email verification and password reset (stored hashed)."""
    __tablename__ = "email_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))  # verify | reset
    code_hash: Mapped[str] = mapped_column(String(128))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Integration(Base):
    """A connected third-party account (Meta, Google, LinkedIn, WhatsApp, Netlify...)."""
    __tablename__ = "integrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    account_name: Mapped[str] = mapped_column(String(200), default="")
    secret: Mapped[str] = mapped_column(Text, default="")  # Fernet-encrypted JSON (tokens / keys)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # non-secret config (ids, numbers)
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Asset(Base):
    """Generated image / video."""
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # image | video
    prompt: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="done")  # queued | done | failed
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    brief: Mapped[dict] = mapped_column(JSON, default=dict)
    html: Mapped[str] = mapped_column(Text, default="")
    pages: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")  # extra pages: [{"slug", "title", "html"}]
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    custom_domain: Mapped[str] = mapped_column(String(255), default="")
    deploy_target: Mapped[str] = mapped_column(String(40), default="aimva")
    deploy_url: Mapped[str] = mapped_column(Text, default="")
    visits: Mapped[int] = mapped_column(Integer, default=0)
    product_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # first launch, for time-to-publish
    domain_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # custom_domain's DNS points here
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20))  # meta | google | linkedin
    name: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(String(60), default="leads")
    daily_budget: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | active | paused
    creative: Mapped[dict] = mapped_column(JSON, default=dict)
    targeting: Mapped[dict] = mapped_column(JSON, default=dict)
    lead_form: Mapped[dict] = mapped_column(JSON, default=dict)
    external_id: Mapped[str] = mapped_column(String(120), default="")
    product_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)  # what this campaign sells
    started_on: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD, if it ran before AIMVA knew it
    spend: Mapped[float] = mapped_column(Float, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(255), default="", index=True)
    phone: Mapped[str] = mapped_column(String(40), default="", index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(40), default="manual")  # website | meta | google | linkedin | whatsapp | voice
    source_ref: Mapped[str] = mapped_column(String(120), default="")
    score: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(20), default="new")  # new | contacted | qualified | won | lost
    value: Mapped[float] = mapped_column(Float, default=0)
    product_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)  # attribution
    campaign_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    synced: Mapped[dict] = mapped_column(JSON, default=dict)
    language: Mapped[str] = mapped_column(String(12), default="", server_default="")  # what the lead writes in (hi-IN, hi-Latn, ta-IN...); "" = not known yet
    opted_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # replied STOP: no messages or calls (see app/opt_out.py)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VoiceAgent(Base):
    __tablename__ = "voice_agents"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(20), default="en-US")
    greeting: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    questions: Mapped[list] = mapped_column(JSON, default=list)  # qualification questions
    handoff_number: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Call(Base):
    __tablename__ = "calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("voice_agents.id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    channel: Mapped[str] = mapped_column(String(20), default="browser")  # browser | phone
    to_number: Mapped[str] = mapped_column(String(40), default="")
    transcript: Mapped[list] = mapped_column(JSON, default=list)  # [{role, text, sentiment}]
    sentiment: Mapped[float] = mapped_column(Float, default=0)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | completed | handoff | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WaMessage(Base):
    __tablename__ = "wa_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    contact: Mapped[str] = mapped_column(String(40), index=True)  # E.164 phone
    contact_name: Mapped[str] = mapped_column(String(160), default="")
    direction: Mapped[str] = mapped_column(String(4))  # in | out
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="sent")  # queued | sent | delivered | read | failed | simulated
    wa_id: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LeadEvent(Base):
    """Timeline entries for a lead that don't live elsewhere (form fills, ad leads, stage changes, notes).

    WhatsApp messages and calls are read from their own tables when the timeline is built.
    """
    __tablename__ = "lead_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # created | form | ad | stage | value | note
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class BrandKit(Base):
    """A user's brand memory, applied to image/video generation, ad copy and landing pages."""
    __tablename__ = "brand_kits"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    tagline: Mapped[str] = mapped_column(String(200), default="")
    colors: Mapped[list] = mapped_column(JSON, default=list)  # ["#RRGGBB", ...]
    voice: Mapped[str] = mapped_column(String(40), default="friendly")  # friendly | professional | bold | playful | luxury
    voice_notes: Mapped[str] = mapped_column(Text, default="")
    style: Mapped[list] = mapped_column(JSON, default=list)  # visual keywords
    audience: Mapped[str] = mapped_column(String(300), default="")
    avoid: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class BrandAsset(Base):
    """Uploaded brand files (logos, product/reference images), stored under data/uploads/<user_id>/."""
    __tablename__ = "brand_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # logo | image
    filename: Mapped[str] = mapped_column(String(200))  # original name, display only
    path: Mapped[str] = mapped_column(String(300))  # relative to data/uploads
    content_type: Mapped[str] = mapped_column(String(40))
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProviderConnection(Base):
    """A user-added AI provider (any API key): text, image or video generation."""
    __tablename__ = "provider_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # text | image | video
    adapter: Mapped[str] = mapped_column(String(30))  # openai | anthropic | gemini | openai_images | replicate | stability | fal | comfyui
    preset: Mapped[str] = mapped_column(String(40), default="custom")
    name: Mapped[str] = mapped_column(String(80))
    base_url: Mapped[str] = mapped_column(String(300), default="")
    secret: Mapped[str] = mapped_column(Text, default="")  # Fernet-encrypted {"api_key": ...}
    model: Mapped[str] = mapped_column(String(200), default="")
    extra: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. ComfyUI workflow
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReferenceFile(Base):
    """Files a user uploads as references for generation: images guide visuals, documents brief the AI writer."""
    __tablename__ = "reference_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # image | document
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(80))
    path: Mapped[str] = mapped_column(String(300))
    size: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, default="")  # extracted text (documents), capped
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SiteVersion(Base):
    """Every generation/edit of a landing page is kept so nothing is ever overwritten."""
    __tablename__ = "site_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    html: Mapped[str] = mapped_column(Text)
    brief: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(String(120), default="")
    generator: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Feedback(Base):
    """A user's thumbs up/down on something AIMVA generated (one per user per item; latest wins)."""
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("user_id", "target_kind", "target_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_kind: Mapped[str] = mapped_column(String(20))  # site | image | video
    target_id: Mapped[int] = mapped_column(Integer)
    rating: Mapped[int] = mapped_column(Integer)  # 1 or -1
    reason: Mapped[str] = mapped_column(String(40), default="")
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Product(Base):
    """Something the business sells (a product, service or offer). Campaigns, pages and leads roll up to it."""
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20), default="product")  # product | service | offer
    price: Mapped[float] = mapped_column(Float, default=0)  # typical sale value, used when a won lead has no value
    target_cpl: Mapped[float] = mapped_column(Float, default=0)  # what a lead is worth paying for (0 = not set)
    monthly_budget: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | paused | archived
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CampaignStat(Base):
    """Cumulative campaign totals as of a day (from a platform sync or entered by hand), for period maths and trends."""
    __tablename__ = "campaign_stats"
    __table_args__ = (UniqueConstraint("campaign_id", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    day: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    spend: Mapped[float] = mapped_column(Float, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | meta


class Decision(Base):
    """What the user decided about a recommendation: accepted (and what ran), snoozed or dismissed."""
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(300))
    decision: Mapped[str] = mapped_column(String(20))  # accepted | snoozed | dismissed
    result: Mapped[str] = mapped_column(String(500), default="")
    note: Mapped[str] = mapped_column(String(500), default="")
    until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # hidden until (snooze / dismiss window)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Template(Base):
    """A saved or suggested template. Built-in templates live in app/templates_catalog.py, not here.

    owner_id set + source "user": the user's own. source "suggested": proposed by the template agent, either for
    one user (owner_id set) or for the whole platform (owner_id null) until an owner publishes it.
    source "platform": published by an owner, visible to everyone.
    """
    __tablename__ = "templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    module: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(400), default="")
    industries: Mapped[list] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(20), default="user")  # user | suggested | platform
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | pending | dismissed
    reason: Mapped[str] = mapped_column(String(500), default="")  # why the agent suggested it
    based_on: Mapped[str] = mapped_column(String(60), default="")  # template ref it improves on, if any
    fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)  # de-duplicates suggestions
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TemplateUse(Base):
    """A template was applied and then used. `changed` lists the fields the user edited before using it."""
    __tablename__ = "template_uses"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    module: Mapped[str] = mapped_column(String(20), index=True)
    ref: Mapped[str] = mapped_column(String(60), index=True)  # b:<key> built-in | t:<id> stored
    changed: Mapped[dict] = mapped_column(JSON, default=dict)  # field -> final value (for small values)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AgentRun(Base):
    """One piece of AI work done by an agent, and which engine did it (yours | platform | free | memory | rules)."""
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    agent: Mapped[str] = mapped_column(String(40), index=True)
    engine: Mapped[str] = mapped_column(String(20))
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AgentMemory(Base):
    """Answers agents already produced, so the same request never calls an API twice (per user, 7 days)."""
    __tablename__ = "agent_memory"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    agent: Mapped[str] = mapped_column(String(40))
    answer: Mapped[str] = mapped_column(Text)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AgentPref(Base):
    """How a user wants an agent to run: auto (best available), rules (never call an API) or a specific provider."""
    __tablename__ = "agent_prefs"
    __table_args__ = (UniqueConstraint("user_id", "agent"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(40))
    engine: Mapped[str] = mapped_column(String(40), default="auto")


class AgentSetting(Base):
    """Whether a work agent (launch, concierge, autopilot, weekly_report, page_fixer) runs for this user, and how."""
    __tablename__ = "agent_settings"
    __table_args__ = (UniqueConstraint("user_id", "kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    mode: Mapped[str] = mapped_column(String(20), default="suggest")  # suggest (ask first) | auto (act within guardrails)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AgentJob(Base):
    """One piece of work an agent did for the user, step by step, so they can see what was done and undo it."""
    __tablename__ = "agent_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | done | failed
    steps: Mapped[list] = mapped_column(JSON, default=list)  # [{label, status: done|skipped|failed, detail}]
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class FollowUp(Base):
    """A message the lead concierge will send later unless the lead replies, books or is closed first."""
    __tablename__ = "follow_ups"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    step: Mapped[str] = mapped_column(String(20))  # welcome (already done, status sent | drafted | failed) | day2 | day7
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | sent | skipped
    note: Mapped[str] = mapped_column(String(300), default="")


class RateHit(Base):
    """One rate-limited request. Kept in the database so the limits hold across several server processes."""
    __tablename__ = "rate_hits"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class SchedulerLease(Base):
    """Which server process currently runs the background agents. Only the lease holder ticks, so follow-ups,
    Autopilot and reports run once even with several workers; another process takes over if the holder stops renewing."""
    __tablename__ = "scheduler_leases"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    holder: Mapped[str] = mapped_column(String(120))
    expires_at: Mapped[datetime] = mapped_column(DateTime)



class LiveEvent(Base):
    """A live update too large for a Postgres NOTIFY (about 8 kB). Other server processes read it by id and deliver it;
    rows are deleted after a few minutes (see app/live.py)."""
    __tablename__ = "live_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class OptOut(Base):
    """A phone number that asked a business not to contact it (replied STOP). Checked before every message and call."""
    __tablename__ = "opt_outs"
    __table_args__ = (UniqueConstraint("user_id", "contact", name="uq_opt_outs_user_contact"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    contact: Mapped[str] = mapped_column(String(40))  # digits with country code, as WhatsApp sends them
    source: Mapped[str] = mapped_column(String(20), default="whatsapp")  # whatsapp | manual
    note: Mapped[str] = mapped_column(String(300), default="")  # what they wrote
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WaScheduled(Base):
    """A WhatsApp message to send later. The agent scheduler sends it when due (once, even with several workers)."""
    __tablename__ = "wa_scheduled"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    contact: Mapped[str] = mapped_column(String(40))
    contact_name: Mapped[str] = mapped_column(String(160), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    template: Mapped[str] = mapped_column(String(120), default="")  # approved template name, for chats outside 24 h
    template_lang: Mapped[str] = mapped_column(String(12), default="en")
    send_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # UTC
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)  # scheduled | sending | sent | failed | cancelled
    error: Mapped[str] = mapped_column(String(500), default="")
    message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # the WaMessage once sent
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Subscription(Base):
    """A user's plan. Everyone starts on a trial; a payment processor (Razorpay) or an admin moves them to a plan."""
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(30), default="trial")
    status: Mapped[str] = mapped_column(String(20), default="trialing")  # trialing | active | past_due | cancelled | expired
    period_start: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    period_end: Mapped[datetime] = mapped_column(DateTime)
    processor: Mapped[str] = mapped_column(String(20), default="")  # razorpay | manual | ""
    processor_subscription_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class UsageEvent(Base):
    """One unit of metered work (an image, a video, a call minute...). Counted per billing period."""
    __tablename__ = "usage_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    meter: Mapped[str] = mapped_column(String(30), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    ref: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class CreditGrant(Base):
    """Extra units on top of the plan (a top-up, or a goodwill grant by an admin). Usable until expires_at."""
    __tablename__ = "credit_grants"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    meter: Mapped[str] = mapped_column(String(30))
    quantity: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Membership(Base):
    """Who can work in a workspace and how. The workspace is a User row (kind=workspace, or a person's own account)."""
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "member_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # owner | admin | editor | client
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Invite(Base):
    """A pending invitation by email. Accepted automatically once that email signs in verified."""
    __tablename__ = "invites"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(20))
    invited_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Approval(Base):
    """The agency asks the client to sign off a campaign, page or image; the client approves or asks for changes."""
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # campaign | site | asset
    ref_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending | approved | changes | withdrawn
    comment: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # what was approved; edits after it need a new approval
