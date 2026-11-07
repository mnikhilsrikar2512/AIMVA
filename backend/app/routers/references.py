"""Reference uploads in many formats.

Images (PNG/JPG/WebP/GIF) guide image & video generation or go into page galleries.
Documents (PDF, Word .docx, .txt/.md/.csv) are read to text and given to the AI writer as background.
Everything else (executables, archives, HTML, SVG...) is refused.
"""
import io
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..brand import UPLOADS
from ..db import get_db
from ..models import ReferenceFile, User
from ..security import current_user, rate_limit

router = APIRouter(prefix="/api/references", tags=["references"])
MAX_BYTES = 15 * 1024 * 1024
MAX_TEXT = 20_000
MAX_FILES = 60
IMAGE_FORMATS = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"), "WEBP": ("image/webp", "webp"), "GIF": ("image/gif", "gif")}
TEXT_EXT = {".txt", ".md", ".csv"}


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise HTTPException(400, "That PDF is password-protected. Remove the password and upload it again.")
        out = []
        for page in reader.pages[:40]:  # long brochures: the first 40 pages are plenty of context
            out.append(page.extract_text() or "")
            if sum(map(len, out)) > MAX_TEXT:
                break
        return "\n".join(out)
    except HTTPException:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError):
        raise HTTPException(400, "That PDF couldn't be read. It may be damaged or scanned without text.")


def _docx_text(data: bytes) -> str:
    import docx
    try:
        d = docx.Document(io.BytesIO(data))
    except Exception:
        raise HTTPException(400, "That Word file couldn't be read. Save it as .docx and try again.")
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)


def classify(filename: str, data: bytes) -> dict:
    """Detect the real type from content (not just the extension) and extract what we need."""
    ext = Path(filename or "").suffix.lower()
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
        if img.format in IMAGE_FORMATS:
            ctype, real_ext = IMAGE_FORMATS[img.format]
            return {"kind": "image", "content_type": ctype, "ext": real_ext, "width": img.width, "height": img.height, "text": ""}
        raise HTTPException(400, f"{img.format} images aren't supported. Use PNG, JPG, WebP or GIF.")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        pass
    if data[:5] == b"%PDF-":
        return {"kind": "document", "content_type": "application/pdf", "ext": "pdf", "text": _pdf_text(data)}
    if data[:2] == b"PK" and ext == ".docx":
        return {"kind": "document", "ext": "docx", "text": _docx_text(data),
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if ext in TEXT_EXT:
        if b"\x00" in data[:4096]:
            raise HTTPException(400, "That text file looks binary. Upload plain text, Markdown or CSV.")
        return {"kind": "document", "content_type": "text/plain", "ext": ext[1:], "text": data.decode("utf-8", errors="replace")}
    if ext in (".heic", ".heif"):
        raise HTTPException(400, "HEIC photos aren't supported yet. Export as JPG from Photos and upload again.")
    if ext == ".doc":
        raise HTTPException(400, "Old .doc files aren't supported. Save as .docx and upload again.")
    raise HTTPException(400, "Unsupported file. Upload an image (PNG, JPG, WebP, GIF), a PDF, a Word .docx or a .txt/.md/.csv file.")


def ref_out(r: ReferenceFile) -> dict:
    return {"id": r.id, "ref": f"ref:{r.id}", "kind": r.kind, "filename": r.filename, "size": r.size,
            "url": f"/api/files/{r.path}", "width": r.width, "height": r.height,
            "excerpt": r.text[:280], "chars": len(r.text), "created_at": r.created_at.isoformat()}


@router.get("")
def list_refs(kind: Optional[str] = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(ReferenceFile).where(ReferenceFile.user_id == user.id).order_by(ReferenceFile.id.desc())
    if kind in ("image", "document"):
        q = q.where(ReferenceFile.kind == kind)
    return [ref_out(r) for r in db.scalars(q)]


@router.post("")
async def upload_ref(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(f"refup:{user.id}", 60, 600)
    if db.query(ReferenceFile).filter(ReferenceFile.user_id == user.id).count() >= MAX_FILES:
        raise HTTPException(400, f"You can keep up to {MAX_FILES} reference files. Delete some first.")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "Files must be 15 MB or smaller.")
    if not data:
        raise HTTPException(400, "That file is empty.")
    info = classify(file.filename or "upload", data)
    text = " ".join(info["text"].split())[:MAX_TEXT]  # collapse whitespace, cap length
    if info["kind"] == "document" and len(text) < 20:
        raise HTTPException(400, "We couldn't find readable text in that document.")
    rel = Path(str(user.id)) / "refs" / f"{uuid.uuid4().hex}.{info['ext']}"
    (UPLOADS / rel).parent.mkdir(parents=True, exist_ok=True)
    (UPLOADS / rel).write_bytes(data)
    r = ReferenceFile(user_id=user.id, kind=info["kind"], filename=(file.filename or "upload")[:200],
                      content_type=info["content_type"], path=str(rel), size=len(data), text=text,
                      width=info.get("width", 0), height=info.get("height", 0))
    db.add(r)
    db.commit()
    return ref_out(r)


@router.delete("/{rid}")
def delete_ref(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(ReferenceFile, rid)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "Reference not found.")
    (UPLOADS / r.path).unlink(missing_ok=True)
    db.delete(r)
    db.commit()
    return {"ok": True}


def reference_text(db: Session, user_id: int, ids: list, limit: int = 6000) -> str:
    """Concatenated document text for the AI writer, owner-checked and capped."""
    out, used = [], 0
    for rid in ids:
        r = db.get(ReferenceFile, rid)
        if not r or r.user_id != user_id:
            raise HTTPException(404, "One of the reference files wasn't found.")
        if r.kind != "document":
            continue
        chunk = r.text[: max(0, limit - used)]
        if chunk:
            out.append(f"[{r.filename}]\n{chunk}")
            used += len(chunk)
    return "\n\n".join(out)
