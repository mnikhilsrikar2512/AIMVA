"""Templates for every module: built-in, platform (published by owners), the user's own, and agent suggestions.

Refs: "b:<key>" for built-in templates (app/templates_catalog.py) and "t:<id>" for stored ones.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import staff
from ..db import get_db
from ..models import Template, TemplateUse, User
from ..quality import match_playbook
from ..security import current_user, rate_limit
from ..template_agent import diff, fill, fingerprint, platform_review, suggest_for_user, user_ctx
from ..templates_catalog import CATALOG, MODULE_LABELS, Module, validate_payload
from .feedback import require_admin
from .providers import writer

router = APIRouter(tags=["templates"])
MAX_OWN = 200
MAX_PENDING = 12


def _out(t, ctx: dict, industry: str, source: str, uses: int = 0) -> dict:
    if isinstance(t, dict):  # built-in
        ref, name, desc, inds, tags, payload, reason = f"b:{t['key']}", t["name"], t["description"], t["industries"], t["tags"], t["payload"], ""
        tid = None
    else:
        ref, name, desc, inds, tags, payload, reason, tid = f"t:{t.id}", t.name, t.description, t.industries or [], [], t.payload, t.reason, t.id
    return {"ref": ref, "id": tid, "module": t["module"] if isinstance(t, dict) else t.module, "name": name, "description": desc,
            "industries": inds, "tags": tags, "payload": fill(payload, ctx), "source": source, "reason": reason,
            "recommended": industry in inds, "uses": uses}


def _accessible(db: Session, user: User, ref: str) -> Optional[dict]:
    if ref.startswith("b:"):
        t = next((x for x in CATALOG if x["key"] == ref[2:]), None)
        return {"module": t["module"], "payload": t["payload"]} if t else None
    if ref.startswith("t:") and ref[2:].isdigit():
        t = db.get(Template, int(ref[2:]))
        if t and (t.owner_id == user.id or (t.owner_id is None and t.source == "platform" and t.status == "active")):
            return {"module": t.module, "payload": t.payload}
    return None


@router.get("/api/templates")
def list_templates(module: Module, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = user_ctx(db, user)
    industry = match_playbook("", user.industry)
    counts = {}
    for u in db.scalars(select(TemplateUse).where(TemplateUse.module == module)):
        counts[u.ref] = counts.get(u.ref, 0) + 1
    out = [_out(t, ctx, industry, "builtin", counts.get(f"b:{t['key']}", 0)) for t in CATALOG if t["module"] == module]
    out += [_out(t, ctx, industry, "platform", counts.get(f"t:{t.id}", 0)) for t in db.scalars(
        select(Template).where(Template.module == module, Template.owner_id.is_(None), Template.source == "platform", Template.status == "active"))]
    for t in db.scalars(select(Template).where(Template.module == module, Template.owner_id == user.id).order_by(Template.created_at.desc())):
        if t.source == "user" and t.status == "active":
            out.append(_out(t, ctx, industry, "mine", counts.get(f"t:{t.id}", 0)))
        elif t.source == "suggested" and t.status == "pending":
            out.append(_out(t, ctx, industry, "suggested"))
    # Your industry first, then templates for any business, then other industries; within those, yours and the most used.
    order = {"suggested": 0, "mine": 1, "platform": 2, "builtin": 3}
    out.sort(key=lambda x: (not x["recommended"], bool(x["industries"]), order[x["source"]], -x["uses"]))
    return {"module": module, "label": MODULE_LABELS[module], "industry": ctx["industry"], "templates": out}


class TemplateIn(BaseModel):
    module: Module
    name: str = Field(min_length=2, max_length=120)
    description: str = Field("", max_length=400)
    payload: dict
    industries: list = Field(default_factory=list, max_length=8)


def _clean(module: str, payload: dict) -> dict:
    try:
        return validate_payload(module, payload)
    except ValueError as e:
        raise HTTPException(400, f"This template can't be saved: {e}")


@router.post("/api/templates")
def save_template(body: TemplateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(f"tpl-save:{user.id}", 30, 600)
    if db.query(Template).filter(Template.owner_id == user.id, Template.source == "user").count() >= MAX_OWN:
        raise HTTPException(400, f"You can keep up to {MAX_OWN} templates. Delete some first.")
    payload = _clean(body.module, body.payload)
    key = match_playbook("", user.industry)
    t = Template(owner_id=user.id, module=body.module, name=body.name.strip(), description=body.description.strip(), payload=payload,
                 industries=[i for i in body.industries if isinstance(i, str)][:8] or ([key] if key != "other" else []),
                 source="user", status="active", fingerprint=fingerprint(body.module, payload))
    db.add(t)
    db.commit()
    return _out(t, user_ctx(db, user), key, "mine")


def _own(db: Session, user: User, tid: int) -> Template:
    t = db.get(Template, tid)
    if not t or t.owner_id != user.id:
        raise HTTPException(404, "Template not found.")
    return t


class TemplatePatch(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=400)
    payload: Optional[dict] = None


@router.patch("/api/templates/{tid}")
def update_template(tid: int, body: TemplatePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _own(db, user, tid)
    if body.name is not None:
        t.name = body.name.strip()
    if body.description is not None:
        t.description = body.description.strip()
    if body.payload is not None:
        t.payload = _clean(t.module, body.payload)
        t.fingerprint = fingerprint(t.module, t.payload)
    db.commit()
    return _out(t, user_ctx(db, user), match_playbook("", user.industry), "mine" if t.source == "user" else "suggested")


@router.delete("/api/templates/{tid}")
def delete_template(tid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own(db, user, tid))
    db.commit()
    return {"ok": True}


class UseIn(BaseModel):
    ref: str = Field(max_length=60)
    module: Module
    applied: dict = Field(default_factory=dict)  # the template as it was filled in
    final: dict = Field(default_factory=dict)  # what the user actually used


@router.post("/api/templates/use")
def record_use(body: UseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Called when something is created from a template, so the agent can learn which fields people change."""
    rate_limit(f"tpl-use:{user.id}", 120, 600)
    t = _accessible(db, user, body.ref)
    if not t or t["module"] != body.module:
        raise HTTPException(404, "Template not found.")
    changed = diff(body.applied, body.final)
    db.add(TemplateUse(user_id=user.id, module=body.module, ref=body.ref, changed=changed))
    db.commit()
    return {"ok": True, "changed": sorted(changed)}


class SuggestIn(BaseModel):
    module: Optional[Module] = None


def _store(db: Session, items: list, owner_id: Optional[int]) -> list:
    q = select(Template.fingerprint).where(Template.owner_id == owner_id) if owner_id else select(Template.fingerprint).where(Template.owner_id.is_(None))
    taken = set(db.scalars(q))  # includes dismissed ones, so they don't come back
    saved = []
    for s in items:
        if s["fingerprint"] in taken:
            continue
        t = Template(owner_id=owner_id, module=s["module"], name=s["name"], description=s["description"], payload=s["payload"],
                     industries=s["industries"], source="suggested", status="pending", reason=s["reason"], based_on=s["based_on"],
                     fingerprint=s["fingerprint"])
        db.add(t)
        saved.append(t)
        taken.add(s["fingerprint"])
    db.commit()
    return saved


@router.post("/api/templates/suggest")
def suggest(body: SuggestIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Run the template agent for this business: personal versions, proven winners and industry gaps."""
    rate_limit(f"tpl-suggest:{user.id}", 10, 600)
    pending = db.query(Template).filter(Template.owner_id == user.id, Template.source == "suggested", Template.status == "pending")
    if body.module:
        pending = pending.filter(Template.module == body.module)
    room = MAX_PENDING - pending.count()
    found = suggest_for_user(db, user, body.module, writer(db, user.id, agent="template_curator")) if room > 0 else []
    saved = _store(db, found[:max(0, room)], user.id)
    ctx, ind = user_ctx(db, user), match_playbook("", user.industry)
    return {"new": [_out(t, ctx, ind, "suggested") for t in saved], "pending": pending.count(),
            "message": (f"{len(saved)} new suggestion{'s' if len(saved) != 1 else ''}." if saved else
                        "No new suggestions right now. Use a few templates and AIMVA will learn what you change.")}


@router.post("/api/templates/{tid}/accept")
def accept(tid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _own(db, user, tid)
    if t.source != "suggested":
        raise HTTPException(400, "Only suggestions can be accepted.")
    t.source, t.status = "user", "active"
    db.commit()
    return _out(t, user_ctx(db, user), match_playbook("", user.industry), "mine")


@router.post("/api/templates/{tid}/dismiss")
def dismiss(tid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _own(db, user, tid)
    t.status = "dismissed"
    db.commit()
    return {"ok": True}


# ---- owners: review templates across the whole platform -------------------------------------------------------
def _pending_platform(db: Session) -> list:
    return [{"id": t.id, "module": t.module, "label": MODULE_LABELS[t.module], "name": t.name, "description": t.description,
             "reason": t.reason, "industries": t.industries, "payload": t.payload, "based_on": t.based_on}
            for t in db.scalars(select(Template).where(Template.owner_id.is_(None), Template.source == "suggested", Template.status == "pending")
                                .order_by(Template.created_at.desc()))]


@router.get("/api/admin/templates")
def admin_templates(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    review = platform_review(db)  # read-only analysis; nothing is stored until "Review now"
    published = [{"id": t.id, "module": t.module, "name": t.name} for t in db.scalars(
        select(Template).where(Template.owner_id.is_(None), Template.source == "platform", Template.status == "active"))]
    return {**{k: review[k] for k in ("usage", "unused", "coverage", "total_uses")}, "pending": _pending_platform(db),
            "published": published, "builtin": len(CATALOG)}


@router.post("/api/admin/templates/review")
def admin_review(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    rate_limit(f"tpl-review:{user.id}", 6, 600)
    review = platform_review(db, writer(db, user.id, agent="template_curator"))
    saved = _store(db, review["suggestions"], None)
    return {"new": len(saved), "pending": _pending_platform(db)}


@router.post("/api/admin/templates/{tid}/{action}")
def admin_decide(tid: int, action: Literal["publish", "dismiss"], user: User = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(Template, tid)
    if not t or t.owner_id is not None:
        raise HTTPException(404, "Template not found.")
    if action == "publish":
        t.source, t.status = "platform", "active"
    else:
        t.status = "dismissed"
    staff.record(db, user, f"template.{action}", None, "", {"template_id": t.id, "name": t.name}, role="owner")
    db.commit()
    return {"ok": True}
