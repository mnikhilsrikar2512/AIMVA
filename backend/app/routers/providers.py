"""User-managed AI providers (bring any API key) and the lookup used by every generator."""
import json
import logging
from typing import Callable, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import discreet
from .. import providers as P
from ..config import settings
from ..db import get_db
from ..models import ProviderConnection, User
from ..security import current_user, decrypt_json, encrypt_json, rate_limit
from ..services import gemini_key, integration_secret, llm

router = APIRouter(prefix="/api/providers", tags=["providers"])
log = logging.getLogger("aimva.providers")
MAX_CONNECTIONS = 30
MAX_WORKFLOW_BYTES = 400_000


def owner_user(request: Request, user: User = Depends(current_user)) -> User:
    """Supplier keys and engines are managed by the platform owner only. Everyone else gets a plain 404."""
    person = getattr(request.state, "person", None) or user
    if (person.email or "").lower() not in settings.admin_emails:
        raise HTTPException(404, "Not found.")
    return user


def http_error(e: P.ProviderError) -> HTTPException:
    return HTTPException(e.status, e.message)


def conn_out(c: ProviderConnection) -> dict:
    preset = P.PRESETS.get(c.preset, {})
    return {"id": c.id, "ref": f"conn:{c.id}", "kind": c.kind, "adapter": c.adapter, "preset": c.preset, "name": c.name,
            "base_url": c.base_url, "model": c.model, "is_default": c.is_default, "has_key": bool(c.secret),
            "has_workflow": bool((c.extra or {}).get("workflow")), "models": preset.get("models", []),
            "created_at": c.created_at.isoformat()}


def _as_dict(c: ProviderConnection) -> dict:
    return {"adapter": c.adapter, "base_url": c.base_url, "name": c.name, "model": c.model,
            "api_key": decrypt_json(c.secret).get("api_key", "") if c.secret else "", "extra": c.extra or {}}


# ---- built-ins & lookup -----------------------------------------------------------------
def studio_key(db: Session, user: User) -> str:
    """The platform's studio key (app/ai_registry.py); a user's own key only when ALLOW_USER_AI_KEYS is on."""
    from .. import ai_registry
    own = integration_secret(db, user.id, "fal").get("api_key") if ai_registry.user_keys_allowed() else ""
    return own or ai_registry.key_for("image", "fal") or ai_registry.key_for("video", "fal")


def builtin_options(db: Session, user: User, kind: str) -> list:
    """AIMVA's own engines, under neutral names and ids (see app/discreet.py); suppliers stay on the server."""
    D = discreet
    pick = lambda ms: [{"id": D.out_model(m), "label": D.model_label(m)} for m in ms]
    studio = bool(studio_key(db, user))
    if kind == "image":
        return [
            {"ref": D.out_ref("builtin:pollinations"), "name": "AIMVA images (free)", "free": True, "available": True,
             "model": D.out_model("flux"), "models": [D.out_model("flux"), D.out_model("turbo")], "choices": pick(["flux", "turbo"]), "max_count": 1},
            {"ref": D.out_ref("builtin:fal"), "name": "AIMVA Studio images", "available": studio, "model": D.out_model("fal-ai/flux/schnell"),
             "models": [D.out_model(m) for m in P.PRESETS["fal_image"]["models"]], "choices": pick(P.PRESETS["fal_image"]["models"]), "max_count": 4},
        ]
    if kind == "video":
        return [{"ref": D.out_ref("builtin:fal"), "name": "AIMVA video", "available": studio, "model": D.out_model("fal-ai/ltx-2/text-to-video"),
                 "models": [D.out_model(m) for m in P.PRESETS["fal_video"]["models"]], "choices": pick(P.PRESETS["fal_video"]["models"])}]
    if kind == "text":
        return [{"ref": D.out_ref("builtin:gemini"), "name": "AIMVA writer", "available": bool(gemini_key(db, user.id)),
                 "model": D.out_model(settings.gemini_model), "models": [D.out_model(m) for m in P.PRESETS["gemini"]["models"]], "choices": pick(P.PRESETS["gemini"]["models"])}]
    return []


def resolve(db: Session, user: User, ref: str, kind: str, model: str = "") -> dict:
    """Turn a provider reference into a connection dict for the adapters. Raises HTTPException."""
    ref, model = discreet.in_ref(ref), discreet.in_model(model)
    model = P.check_model(model) if model else ""
    if ref == "builtin:fal":
        key = studio_key(db, user)
        if not key:
            raise HTTPException(400, f"{'Video' if kind == 'video' else 'Studio images'} isn't switched on for your account yet.")
        return {"adapter": "fal", "base_url": "https://fal.run", "name": "fal.ai", "api_key": key, "extra": {},
                "model": model or ("fal-ai/flux/schnell" if kind == "image" else "fal-ai/ltx-2/text-to-video")}
    if ref.startswith("conn:"):
        from .. import ai_registry
        if not (ai_registry.user_keys_allowed() or (user.email or "").lower() in settings.admin_emails):
            raise HTTPException(400, "Pick one of AIMVA's engines.")  # own engines are off for this version
        try:
            c = db.get(ProviderConnection, int(ref.split(":", 1)[1]))
        except ValueError:
            c = None
        if not c or c.user_id != user.id:
            raise HTTPException(404, "That provider isn't connected to your account.")
        if c.kind != kind:
            raise HTTPException(400, f"“{c.name}” is a {c.kind} provider, not a {kind} provider.")
        d = _as_dict(c)
        d["model"] = model or c.model
        if not d["model"] and c.adapter != "comfyui":
            raise HTTPException(400, f"Set a model for “{c.name}” first.")
        return d
    raise HTTPException(400, "Unknown provider.")


def writer(db: Session, user_id: int, ref: str = "auto", agent: str = "general") -> Optional[Callable[..., Optional[str]]]:
    """The AI writer for a task (see app/ai_engine.py): your provider, then the shared key,
    then AIMVA free AI, with answers remembered. None means the caller should use its built-in rules."""
    from ..ai_engine import agent_writer
    if ref and ref.startswith("conn:") and ref[5:].isdigit():
        c = db.get(ProviderConnection, int(ref[5:]))
        if not c or c.user_id != user_id or c.kind != "text":
            raise HTTPException(404, "That AI writer isn't connected to your account.")
    return agent_writer(db, user_id, agent, ref)


# ---- catalogue & CRUD -------------------------------------------------------------------
@router.get("/presets")
def presets(user: User = Depends(owner_user)):
    return [{"id": k, **{x: v.get(x) for x in ("kind", "adapter", "label", "base_url", "model", "models", "docs")},
             "key_optional": bool(v.get("key_optional")), "needs_workflow": bool(v.get("needs_workflow"))}
            for k, v in P.PRESETS.items()]


@router.get("")
def list_connections(user: User = Depends(owner_user), db: Session = Depends(get_db)):
    q = select(ProviderConnection).where(ProviderConnection.user_id == user.id).order_by(ProviderConnection.kind, ProviderConnection.id)
    return [conn_out(c) for c in db.scalars(q)]


@router.get("/options")
def options(kind: Literal["text", "image", "video"], request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Everything the user can pick in a generator: AIMVA's engines, plus (owner only) extra engines they connected."""
    person = getattr(request.state, "person", None) or user
    if (person.email or "").lower() not in settings.admin_emails:
        return builtin_options(db, user, kind)
    own = db.scalars(select(ProviderConnection).where(ProviderConnection.user_id == user.id, ProviderConnection.kind == kind)
                     .order_by(ProviderConnection.is_default.desc(), ProviderConnection.id))
    return builtin_options(db, user, kind) + [
        {"ref": f"conn:{c.id}", "name": c.name, "available": True, "model": c.model,
         "models": P.PRESETS.get(c.preset, {}).get("models", []), "adapter": c.adapter, "is_default": c.is_default,
         "max_count": 1 if c.adapter in ("stability", "comfyui") else 4}
        for c in own]


class ConnIn(BaseModel):
    preset: str
    name: str = Field("", max_length=80)
    base_url: str = Field("", max_length=300)
    api_key: str = Field("", max_length=500)
    model: str = Field("", max_length=200)
    workflow: Optional[str] = Field(None, max_length=MAX_WORKFLOW_BYTES)
    is_default: bool = False
    verify: bool = True


def _workflow(text: Optional[str]) -> Optional[dict]:
    if not text:
        return None
    try:
        wf = json.loads(text)
    except ValueError:
        raise HTTPException(400, "The workflow isn't valid JSON. Export it from ComfyUI with “Save (API format)”.")
    if not isinstance(wf, dict) or not wf or not all(isinstance(v, dict) and "class_type" in v for v in wf.values()):
        raise HTTPException(400, "That looks like a UI workflow. In ComfyUI use “Save (API format)” and paste that file.")
    if "{{prompt}}" not in text:
        raise HTTPException(400, "Put {{prompt}} where your prompt text goes in the workflow so AIMVA can fill it in.")
    return wf


@router.post("")
def add_connection(body: ConnIn, user: User = Depends(owner_user), db: Session = Depends(get_db)):
    rate_limit(f"provadd:{user.id}", 20, 600)
    preset = P.PRESETS.get(body.preset)
    if not preset:
        raise HTTPException(400, "Unknown provider type.")
    if db.query(ProviderConnection).filter(ProviderConnection.user_id == user.id).count() >= MAX_CONNECTIONS:
        raise HTTPException(400, f"You can add up to {MAX_CONNECTIONS} providers. Remove one first.")
    api_key = body.api_key.strip()
    if not api_key and not preset.get("key_optional"):
        raise HTTPException(400, "Paste the API key for this provider.")
    try:
        base = P.safe_url(body.base_url.strip() or preset["base_url"])
        model = P.check_model(body.model or preset["model"])
    except P.ProviderError as e:
        raise http_error(e)
    wf = _workflow(body.workflow)
    if preset.get("needs_workflow") and not wf:
        raise HTTPException(400, "Paste your ComfyUI workflow (API format) with {{prompt}} in it.")
    c = ProviderConnection(user_id=user.id, kind=preset["kind"], adapter=preset["adapter"], preset=body.preset,
                           name=(body.name.strip() or preset["label"])[:80], base_url=base, model=model,
                           secret=encrypt_json({"api_key": api_key}) if api_key else "", extra={"workflow": wf} if wf else {})
    if body.verify:
        try:
            P.verify(_as_dict(c))
        except P.ProviderError as e:
            raise http_error(e)
    first_of_kind = not db.scalar(select(ProviderConnection.id).where(ProviderConnection.user_id == user.id,
                                                                      ProviderConnection.kind == c.kind))
    db.add(c)
    db.flush()
    if body.is_default or (first_of_kind and c.kind == "text"):
        _make_default(db, user.id, c)
    db.commit()
    return conn_out(c)


def _own(db: Session, user: User, cid: int) -> ProviderConnection:
    c = db.get(ProviderConnection, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Provider not found.")
    return c


def _make_default(db: Session, user_id: int, c: ProviderConnection) -> None:
    db.execute(update(ProviderConnection).where(ProviderConnection.user_id == user_id, ProviderConnection.kind == c.kind)
               .values(is_default=False))
    c.is_default = True


class ConnPatch(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    model: Optional[str] = Field(None, max_length=200)
    api_key: Optional[str] = Field(None, max_length=500)
    workflow: Optional[str] = Field(None, max_length=MAX_WORKFLOW_BYTES)
    is_default: Optional[bool] = None


@router.patch("/{cid}")
def update_connection(cid: int, body: ConnPatch, user: User = Depends(owner_user), db: Session = Depends(get_db)):
    c = _own(db, user, cid)
    try:
        if body.model is not None:
            c.model = P.check_model(body.model)
    except P.ProviderError as e:
        raise http_error(e)
    if body.name is not None and body.name.strip():
        c.name = body.name.strip()
    if body.workflow is not None:
        c.extra = {**(c.extra or {}), "workflow": _workflow(body.workflow)}
    if body.api_key:
        c.secret = encrypt_json({"api_key": body.api_key.strip()})
        try:
            P.verify(_as_dict(c))
        except P.ProviderError as e:
            raise http_error(e)
    if body.is_default is True:
        _make_default(db, user.id, c)
    elif body.is_default is False:
        c.is_default = False
    db.commit()
    return conn_out(c)


@router.post("/{cid}/test")
def test_connection(cid: int, user: User = Depends(owner_user), db: Session = Depends(get_db)):
    rate_limit(f"provtest:{user.id}", 20, 300)
    c = _own(db, user, cid)
    try:
        P.verify(_as_dict(c))
        if c.kind == "text":
            reply = P.chat(_as_dict(c), "Reply with the single word: ready", max_tokens=10)
            return {"ok": True, "message": f"Connected. The model replied: “{reply[:60]}”"}
    except P.ProviderError as e:
        raise http_error(e)
    except (KeyError, IndexError, ValueError, TypeError):
        raise HTTPException(502, f"{c.name} answered in an unexpected format. Is it OpenAI-compatible?")
    return {"ok": True, "message": "Connected. Your key and address work."}


@router.delete("/{cid}")
def delete_connection(cid: int, user: User = Depends(owner_user), db: Session = Depends(get_db)):
    db.delete(_own(db, user, cid))
    db.commit()
    return {"ok": True}
