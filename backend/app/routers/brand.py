"""Brand kit: the user's brand memory (logos, colours, voice, style) used across all generators."""
import re
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..brand import UPLOADS, BadImage, get_kit, save_upload, suggest_palette
from ..db import get_db
from ..models import BrandAsset, BrandKit, User
from ..security import current_user, rate_limit

router = APIRouter(tags=["brand"])
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_ASSETS = 24


def asset_out(a: BrandAsset) -> dict:
    return {"id": a.id, "kind": a.kind, "filename": a.filename, "url": f"/api/files/{a.path}",
            "width": a.width, "height": a.height, "is_primary": a.is_primary, "created_at": a.created_at.isoformat()}


def kit_out(kit: Optional[BrandKit], assets: list) -> dict:
    base = {"name": "", "tagline": "", "colors": [], "voice": "friendly", "voice_notes": "", "style": [],
            "audience": "", "avoid": ""}
    if kit:
        base = {k: getattr(kit, k) for k in base}
    logos = [a for a in assets if a.kind == "logo"]
    return {**base, "logos": [asset_out(a) for a in logos], "images": [asset_out(a) for a in assets if a.kind == "image"],
            "is_set_up": bool(kit and (kit.colors or kit.style or kit.name)) or bool(logos)}


def _assets(db: Session, user_id: int) -> list:
    return list(db.scalars(select(BrandAsset).where(BrandAsset.user_id == user_id)
                           .order_by(BrandAsset.is_primary.desc(), BrandAsset.id.desc())))


@router.get("/api/brand")
def get_brand(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return kit_out(get_kit(db, user.id), _assets(db, user.id))


class BrandIn(BaseModel):
    name: str = Field("", max_length=160)
    tagline: str = Field("", max_length=200)
    colors: List[str] = Field(default_factory=list, max_length=8)
    voice: Literal["friendly", "professional", "bold", "playful", "luxury"] = "friendly"
    voice_notes: str = Field("", max_length=1000)
    style: List[str] = Field(default_factory=list, max_length=12)
    audience: str = Field("", max_length=300)
    avoid: str = Field("", max_length=1000)

    @field_validator("colors")
    @classmethod
    def _hex(cls, v):
        bad = [c for c in v if not HEX.match(c)]
        if bad:
            raise ValueError(f"Colours must be hex like #6d5dfc (got {bad[0]!r}).")
        return list(dict.fromkeys(c.lower() for c in v))

    @field_validator("style")
    @classmethod
    def _style(cls, v):
        return [s.strip()[:40] for s in dict.fromkeys(v) if s.strip()]


@router.put("/api/brand")
def save_brand(body: BrandIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kit = get_kit(db, user.id) or BrandKit(user_id=user.id)
    for k, v in body.model_dump().items():
        setattr(kit, k, v.strip() if isinstance(v, str) else v)
    db.add(kit)
    db.commit()
    return kit_out(kit, _assets(db, user.id))


# ---- the brand book: one page every generator reads (see app/brand_book.py) -------------------------------
@router.get("/api/brand/book")
def brand_book(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .. import brand_book as bb
    book = bb.build(db, user)
    return {**book, "markdown": bb.markdown(book), "voices": list(bb.VOICES)}


@router.put("/api/brand/book")
def save_brand_book(body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .. import brand_book as bb
    if len(str(body)) > 8000:
        raise HTTPException(400, "That's too much for a brand book.")
    book = bb.save_edits(db, user, body)
    return {**book, "markdown": bb.markdown(book), "voices": list(bb.VOICES)}


@router.get("/api/brand/book.md", response_class=PlainTextResponse)
def brand_book_md(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .. import brand_book as bb
    return PlainTextResponse(bb.markdown(bb.build(db, user)), media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="brand-book.md"'})


@router.post("/api/brand/assets")
async def upload_asset(file: UploadFile = File(...), kind: Literal["logo", "image"] = Form("logo"),
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(f"brandup:{user.id}", 40, 600)
    if len(_assets(db, user.id)) >= MAX_ASSETS:
        raise HTTPException(400, f"You can keep up to {MAX_ASSETS} brand files. Delete some first.")
    data = await file.read(5 * 1024 * 1024 + 1)
    try:
        info = save_upload(user.id, data)
    except BadImage as e:
        raise HTTPException(400, str(e))
    first_logo = kind == "logo" and not db.scalar(select(BrandAsset.id).where(
        BrandAsset.user_id == user.id, BrandAsset.kind == "logo"))
    a = BrandAsset(user_id=user.id, kind=kind, filename=(file.filename or "upload")[:200], is_primary=first_logo, **info)
    db.add(a)
    db.commit()
    out = {"asset": asset_out(a)}
    if kind == "logo":
        out["suggested_colors"] = suggest_palette(data)
    return out


def _own_asset(db: Session, user: User, asset_id: int) -> BrandAsset:
    a = db.get(BrandAsset, asset_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "File not found.")
    return a


@router.post("/api/brand/assets/{asset_id}/primary")
def make_primary(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _own_asset(db, user, asset_id)
    db.execute(update(BrandAsset).where(BrandAsset.user_id == user.id, BrandAsset.kind == a.kind).values(is_primary=False))
    a.is_primary = True
    db.commit()
    return kit_out(get_kit(db, user.id), _assets(db, user.id))


@router.delete("/api/brand/assets/{asset_id}")
def delete_asset(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _own_asset(db, user, asset_id)
    (UPLOADS / a.path).unlink(missing_ok=True)
    was_primary, kind = a.is_primary, a.kind
    db.delete(a)
    db.commit()
    if was_primary:  # promote the next logo so generators always have one to use
        nxt = db.scalar(select(BrandAsset).where(BrandAsset.user_id == user.id, BrandAsset.kind == kind)
                        .order_by(BrandAsset.id.desc()))
        if nxt:
            nxt.is_primary = True
            db.commit()
    return kit_out(get_kit(db, user.id), _assets(db, user.id))


@router.get("/api/brand/assets/{asset_id}/palette")
def palette(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..brand import asset_bytes
    return {"colors": suggest_palette(asset_bytes(_own_asset(db, user, asset_id)))}


@router.get("/api/files/{path:path}")
def serve_file(path: str, user: User = Depends(current_user)):
    """Private files: only the owner can view their uploads and branded images."""
    # Resolve first, then require the real file to sit inside this account's own folder, so "6/../99/x" can't
    # step into another account's uploads.
    own = (UPLOADS / str(user.id)).resolve()
    f = (UPLOADS / path).resolve()
    if own not in f.parents or not f.is_file():
        raise HTTPException(404, "File not found.")
    return FileResponse(f, headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=86400"})
