"""Template review agent: looks at how templates are used across AIMVA and proposes better ones.

Two scopes:
- user: one business. Learns from the edits they keep making, their best campaign, the page that brings the most
  leads, images they rated up or keep regenerating, and gaps for their industry.
- platform: every user (for owners). Finds fields most people change after picking a template, custom templates
  several businesses created independently, and industries with no template in a module.
Every suggestion carries the reason it was made and is validated against the module schema before it's saved.
When an AI writer is connected it drafts extra ideas, which go through the same validation.
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Asset, BrandKit, Call, Campaign, Feedback, Lead, Site, Template, TemplateUse, User, VoiceAgent
from .quality import PLAYBOOKS, match_playbook
from .templates_catalog import CATALOG, CATALOG_BY_KEY, MODULE_LABELS, MODULES, validate_payload

TOKENS = ("{business}", "{industry}", "{tagline}")
FIELD_NAMES = {"cta": "the button text", "creative.cta": "the button text", "creative.headline": "the headline", "creative.text": "the ad text",
               "daily_budget": "the daily budget", "form_title": "the form title", "form_fields": "the form fields", "body": "the message",
               "prompt": "the prompt", "negative_prompt": "what to avoid", "greeting": "the greeting", "questions": "the questions",
               "instructions": "the instructions", "page_type": "the page type", "contact_mode": "how leads reach you",
               "targeting.interests": "the interests", "targeting.locations": "the locations", "targeting.age_min": "the minimum age",
               "targeting.age_max": "the maximum age", "lead_form.fields": "the lead-form fields", "aspect_ratio": "the shape"}


def field_name(path: str) -> str:
    return FIELD_NAMES.get(path, "the " + path.split(".")[-1].replace("_", " "))


# ---- helpers ---------------------------------------------------------------------------------------------
def fill(value, ctx: dict):
    """Replace {business}/{industry}/{tagline} in every string of a payload ({name} is left for WhatsApp)."""
    if isinstance(value, str):
        for k, v in ctx.items():
            value = value.replace("{" + k + "}", v)
        return value
    if isinstance(value, list):
        return [fill(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, ctx) for k, v in value.items()}
    return value


def anonymise(value, business: str):
    """Turn a business's own name back into {business}, so a template can be shared with others."""
    if not business or len(business) < 3:
        return value
    pat = re.compile(re.escape(business), re.I)
    if isinstance(value, str):
        return pat.sub("{business}", value)
    if isinstance(value, list):
        return [anonymise(v, business) for v in value]
    if isinstance(value, dict):
        return {k: anonymise(v, business) for k, v in value.items()}
    return value


def flatten(payload: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in (payload or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        else:
            out[key] = v
    return out


def set_path(payload: dict, path: str, value) -> dict:
    p = json.loads(json.dumps(payload))
    node = p
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    return p


def diff(applied: dict, final: dict) -> dict:
    """Fields the user changed between picking a template and using it (field -> final value, kept small)."""
    a, f = flatten(applied), flatten(final)
    out = {}
    for k, v in f.items():
        if k in a and a[k] != v:
            out[k] = v if len(json.dumps(v, default=str)) <= 300 else "(long text)"
    return dict(list(out.items())[:20])


def fingerprint(module: str, payload: dict) -> str:
    return hashlib.sha256((module + json.dumps(payload, sort_keys=True, default=str)).encode()).hexdigest()[:32]


def user_ctx(db: Session, user: User) -> dict:
    from .brand_book import effective_kit
    kit = effective_kit(db, user)
    key = match_playbook("", user.industry)
    return {"business": user.company or "your business", "industry": PLAYBOOKS[key]["label"],
            "tagline": (kit.tagline if kit and kit.tagline else "")}


def suggestion(module, name, description, payload, reason, industries=(), based_on=""):
    return {"module": module, "name": name[:120], "description": description[:400], "payload": validate_payload(module, payload),
            "reason": reason[:500], "industries": list(industries), "based_on": based_on}


def resolve_ref(db: Session, ref: str) -> Optional[dict]:
    if ref.startswith("b:"):
        t = CATALOG_BY_KEY.get(ref[2:])
        return {"name": t["name"], "module": t["module"], "payload": t["payload"], "industries": t["industries"]} if t else None
    if ref.startswith("t:") and ref[2:].isdigit():
        t = db.get(Template, int(ref[2:]))
        return {"name": t.name, "module": t.module, "payload": t.payload, "industries": t.industries} if t else None
    return None


# ---- user scope ------------------------------------------------------------------------------------------
def _habitual_edits(db: Session, user: User, module: Optional[str]) -> list:
    """If someone keeps changing the same field to the same value, offer a version with that built in."""
    q = select(TemplateUse).where(TemplateUse.user_id == user.id)
    if module:
        q = q.where(TemplateUse.module == module)
    by_ref = defaultdict(list)
    for u in db.scalars(q):
        by_ref[u.ref].append(u)
    out = []
    for ref, uses in by_ref.items():
        if len(uses) < 2:
            continue
        base = resolve_ref(db, ref)
        if not base:
            continue
        values = defaultdict(Counter)
        for u in uses:
            for k, v in (u.changed or {}).items():
                if v != "(long text)":
                    values[k][json.dumps(v)] += 1
        payload, changed = base["payload"], []
        for field, counts in values.items():
            val, n = counts.most_common(1)[0]
            if n >= 2 and n / len(uses) >= 0.6:
                payload = set_path(payload, field, json.loads(val))
                changed.append(f"{field_name(field)} to “{str(json.loads(val))[:40]}” in {n} of {len(uses)} uses")
        if changed:
            try:
                out.append(suggestion(base["module"], f"{base['name']} · your version", f"{base['name']} with the changes you always make.",
                                      payload, "You changed " + "; ".join(changed) + ".", base["industries"], ref))
            except ValueError:
                pass
    return out


def _best_campaign(db: Session, user: User) -> list:
    leads = dict(db.execute(select(Lead.campaign_id, func.count()).where(Lead.user_id == user.id, Lead.campaign_id.is_not(None))
                            .group_by(Lead.campaign_id)).all())
    best = None
    for c in db.scalars(select(Campaign).where(Campaign.user_id == user.id)):
        n = leads.get(c.id, 0)
        if n >= 3 and c.spend > 0 and (c.creative or {}).get("headline"):
            cpl = c.spend / n
            if not best or cpl < best[1]:
                best = (c, cpl, n)
    if not best:
        return []
    c, cpl, n = best
    t = c.targeting or {}
    payload = {"platform": c.platform if c.platform in ("meta", "google", "linkedin") else "any", "objective": c.objective if c.objective in ("leads", "traffic") else "leads",
               "daily_budget": c.daily_budget or 500,
               "creative": {k: str((c.creative or {}).get(k, ""))[:600] for k in ("headline", "text", "cta") if (c.creative or {}).get(k)},
               "targeting": {"locations": str(t.get("locations", ""))[:200], "interests": str(t.get("interests", ""))[:300],
                             "age_min": int(t.get("age_min", 18) or 18), "age_max": int(t.get("age_max", 65) or 65)},
               "lead_form": {"fields": [f for f in (c.lead_form or {}).get("fields", []) if f in ("full_name", "email", "phone_number", "city", "company_name", "job_title")] or ["full_name", "phone_number"]}}
    try:
        return [suggestion("ads", f"Best performer: {c.name}"[:120], "Your lowest cost-per-lead campaign, ready to reuse for the next product or season.",
                           payload, f"₹{cpl:,.0f} per lead from {n} leads, your cheapest campaign so far.")]
    except ValueError:
        return []


def _best_page(db: Session, user: User) -> list:
    counts = dict(db.execute(select(Lead.source_ref, func.count()).where(Lead.user_id == user.id, Lead.source == "website")
                             .group_by(Lead.source_ref)).all())
    sites = [s for s in db.scalars(select(Site).where(Site.user_id == user.id, Site.published.is_(True))) if counts.get(s.slug, 0) >= 3]
    if not sites:
        return []
    s = max(sites, key=lambda x: counts[x.slug])
    b = s.brief or {}
    keys = ("page_type", "layout", "decor", "look", "theme", "font", "sections", "form_fields", "contact_mode", "cta", "form_title")
    payload = {k: b[k] for k in keys if k in b}
    try:
        return [suggestion("website", f"Proven layout: {s.name}"[:120], "The structure of your best-converting page, without its business details.",
                           payload, f"“{s.name}” has brought {counts[s.slug]} leads.")]
    except ValueError:
        return []


def _liked_images(db: Session, user: User) -> list:
    liked = {f.target_id for f in db.scalars(select(Feedback).where(Feedback.user_id == user.id, Feedback.target_kind == "image", Feedback.rating > 0))}
    assets = list(db.scalars(select(Asset).where(Asset.user_id == user.id, Asset.kind == "image")))
    repeated = Counter(a.prompt.strip().lower() for a in assets if not (a.params or {}).get("parent"))
    out, seen = [], set()
    for a in assets:
        p = a.prompt.strip()
        key = p.lower()
        why = "You rated an image from this prompt 👍." if a.id in liked else (f"You've used this prompt {repeated[key]} times." if repeated[key] >= 2 else "")
        if not why or key in seen or len(p) < 10:
            continue
        seen.add(key)
        params = a.params or {}
        try:
            out.append(suggestion("image", (p[:50] + "…") if len(p) > 50 else p, "From an image you liked or keep coming back to.",
                                  {"prompt": p, "style": params.get("style") or "", "size": params.get("size") if params.get("size") in ("1:1", "4:5", "9:16", "16:9", "1.91:1") else "1:1",
                                   "negative_prompt": params.get("negative_prompt") or ""}, why))
        except ValueError:
            continue
        if len(out) >= 2:
            break
    return out


def _best_agent(db: Session, user: User) -> list:
    rows = db.execute(select(Call.agent_id, func.count()).where(Call.user_id == user.id, Call.lead_id.is_not(None)).group_by(Call.agent_id)).all()
    if not rows:
        return []
    agent_id, n = max(rows, key=lambda r: r[1])
    a = db.get(VoiceAgent, agent_id)
    if not a or n < 2 or len(a.questions or []) < 2:
        return []
    try:
        return [suggestion("voice", f"{a.name} (proven script)"[:120], "The call script that has created the most leads for you.",
                           {"language": a.language, "greeting": a.greeting, "instructions": a.instructions, "questions": a.questions},
                           f"This agent's calls created {n} leads.")]
    except ValueError:
        return []


def _industry_gaps(industry: str, module: Optional[str], have: set) -> list:
    """Make sure every module has at least one template written for this business's industry."""
    key = match_playbook("", industry)
    if key == "other":
        return []
    p = PLAYBOOKS[key]
    out = []
    covered = {t["module"] for t in CATALOG if key in t["industries"]} | have
    if (module in (None, "website")) and "website" not in covered:
        out.append(suggestion("website", f"{p['label']} lead page", f"Built from the {p['label'].lower()} playbook.",
                              {"page_type": p["page_type"], "cta": p["cta"], "form_title": p["form_title"], "sections": p["sections"],
                               "form_fields": p["form_fields"]}, f"No website template was written for {p['label'].lower()} yet.", [key]))
    if (module in (None, "ads")) and "ads" not in covered:
        out.append(suggestion("ads", f"{p['label']} leads", f"A lead ad using the {p['label'].lower()} playbook's offer and button.",
                              {"platform": "meta", "objective": "leads", "creative": {"headline": p["cta"], "text": "{business}: " + p["safe_features"][0] + ". " + p["safe_features"][1] + ".", "cta": "Learn more"}},
                              f"No ad template was written for {p['label'].lower()} yet.", [key]))
    return out


def _ai_drafts(write: Callable, module: str, ctx: dict, used: list) -> list:
    """Ask the AI writer for two fresh templates in the module's exact shape; keep only ones that validate."""
    from .templates_catalog import SCHEMAS
    shape = json.dumps(SCHEMAS[module]().model_dump() if module in ("website", "ads") else
                       {k: v for k, v in SCHEMAS[module].model_json_schema().get("properties", {}).items()}, default=str)[:1500]
    prompt = (f"Suggest 2 new {MODULE_LABELS[module]} templates for a {ctx['industry']} business called {ctx['business']}. "
              f"They already use: {', '.join(used) or 'nothing yet'}; make the new ones clearly different. "
              "Use {business} where the business name goes. Never invent prices, awards or statistics. "
              f"Return only JSON: a list of objects with keys name, description, reason, payload. payload must match this shape: {shape}")
    raw = write(prompt, max_tokens=1500) or ""
    m = re.search(r"\[.*\]", raw, re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        return []
    out = []
    for it in items[:2] if isinstance(items, list) else []:
        if not isinstance(it, dict) or not isinstance(it.get("payload"), dict):
            continue
        try:
            out.append(suggestion(module, str(it.get("name") or "AI idea"), str(it.get("description") or ""), it["payload"],
                                  "AI idea: " + str(it.get("reason") or "something you haven't tried yet.")))
        except ValueError:
            continue  # invalid drafts are dropped, never shown
    return out


def suggest_for_user(db: Session, user: User, module: Optional[str] = None, write: Optional[Callable] = None) -> list:
    found = []
    found += _habitual_edits(db, user, module)
    if module in (None, "ads"):
        found += _best_campaign(db, user)
    if module in (None, "website"):
        found += _best_page(db, user)
    if module in (None, "image"):
        found += _liked_images(db, user)
    if module in (None, "voice"):
        found += _best_agent(db, user)
    mine = list(db.scalars(select(Template).where(Template.owner_id == user.id)))
    found += _industry_gaps(user.industry, module, {t.module for t in mine if t.status == "active" and match_playbook("", user.industry) in (t.industries or [])})
    if write and module:
        used = [t["name"] for t in CATALOG if t["module"] == module][:6] + [t.name for t in mine if t.module == module][:6]
        found += _ai_drafts(write, module, user_ctx(db, user), used)
    # Drop anything identical to what already exists.
    existing = {t.fingerprint for t in mine} | {fingerprint(t["module"], t["payload"]) for t in CATALOG}
    out, seen = [], set()
    for s in found:
        fp = fingerprint(s["module"], s["payload"])
        if fp in existing or fp in seen:
            continue
        seen.add(fp)
        out.append({**s, "fingerprint": fp})
    return out


# ---- platform scope ------------------------------------------------------------------------------------------
def platform_review(db: Session, write: Optional[Callable] = None) -> dict:
    users = list(db.scalars(select(User)))
    company = {u.id: u.company for u in users}
    uses = list(db.scalars(select(TemplateUse)))
    by_ref = defaultdict(list)
    for u in uses:
        by_ref[u.ref].append(u)
    usage = []
    suggestions = []
    for ref, rows in by_ref.items():
        base = resolve_ref(db, ref)
        if not base:
            continue
        edits = Counter()
        values = defaultdict(Counter)
        for r in rows:
            for k, v in (r.changed or {}).items():
                edits[k] += 1
                if v != "(long text)":
                    values[k][json.dumps(anonymise(v, company.get(r.user_id, "")))] += 1
        usage.append({"ref": ref, "name": base["name"], "module": base["module"], "uses": len(rows),
                      "users": len({r.user_id for r in rows}),
                      "most_edited": [{"field": k, "label": field_name(k).removeprefix("the "), "rate": round(100 * n / len(rows))} for k, n in edits.most_common(3)]})
        if len(rows) >= 3:
            payload, why = base["payload"], []
            for field, n in edits.items():
                if n / len(rows) < 0.5:
                    continue
                val, m = values[field].most_common(1)[0] if values[field] else (None, 0)
                if val is not None and m / len(rows) >= 0.4:
                    payload = set_path(payload, field, json.loads(val))
                    why.append(f"{m} of {len(rows)} uses change {field_name(field)} to “{str(json.loads(val))[:40]}”")
            if why:
                try:
                    suggestions.append(suggestion(base["module"], f"{base['name']} (revised)", f"An update to “{base['name']}” based on how people use it.",
                                                  payload, "; ".join(why) + ".", base["industries"], ref))
                except ValueError:
                    pass
    # Custom templates that several businesses made independently: promote one (anonymised).
    groups = defaultdict(list)
    for t in db.scalars(select(Template).where(Template.source == "user", Template.status == "active")):
        groups[(t.module, re.sub(r"[^a-z]", "", t.name.lower())[:24])].append(t)
    for (module, _), ts in groups.items():
        owners = {t.owner_id for t in ts}
        if len(owners) >= 2:
            t = ts[0]
            try:
                suggestions.append(suggestion(module, t.name, t.description or f"A {MODULE_LABELS[module].lower()} template several businesses created.",
                                              anonymise(t.payload, company.get(t.owner_id, "")),
                                              f"{len(owners)} businesses created a template like this on their own.", t.industries))
            except ValueError:
                pass
    # Industries with users but no template in a module.
    published = list(db.scalars(select(Template).where(Template.source == "platform", Template.status == "active")))
    industries = Counter(match_playbook("", u.industry) for u in users if u.industry)
    coverage = []
    for ind, n in industries.most_common():
        if ind == "other":
            continue
        for module in MODULES:
            have = sum(ind in t["industries"] for t in CATALOG if t["module"] == module) + sum(ind in (t.industries or []) for t in published if t.module == module)
            coverage.append({"industry": PLAYBOOKS[ind]["label"], "module": module, "templates": have, "users": n})
            if have == 0 and module in ("website", "ads"):
                suggestions += _industry_gaps(ind, module, set())
            if have == 0 and write and module not in ("website", "ads"):
                suggestions += _ai_drafts(write, module, {"business": "{business}", "industry": PLAYBOOKS[ind]["label"]}, [])
    existing = {t.fingerprint for t in db.scalars(select(Template).where(Template.owner_id.is_(None)))} | {fingerprint(t["module"], t["payload"]) for t in CATALOG}
    out, seen = [], set()
    for s in suggestions:
        fp = fingerprint(s["module"], s["payload"])
        if fp not in existing and fp not in seen:
            seen.add(fp)
            out.append({**s, "fingerprint": fp})
    unused = [{"ref": f"b:{t['key']}", "name": t["name"], "module": t["module"]} for t in CATALOG if f"b:{t['key']}" not in by_ref]
    return {"usage": sorted(usage, key=lambda x: -x["uses"])[:30], "unused": unused[:30],
            "coverage": [c for c in coverage if c["templates"] == 0][:30], "suggestions": out, "total_uses": len(uses)}
