import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..database import get_db

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
PHOTOS_DIR = DATA_DIR / "photos"

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE = 10 * 1024 * 1024  # 10 MB


def _render_gallery(request: Request, set_id: int):
    with get_db() as db:
        set_row = db.execute("SELECT * FROM sets WHERE id = ?", (set_id,)).fetchone()
        photos = [
            dict(p) for p in db.execute(
                "SELECT * FROM photos WHERE set_id = ? ORDER BY is_primary DESC, created_at ASC",
                (set_id,),
            ).fetchall()
        ]
    if not set_row:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("partials/photo_gallery.html", {
        "request": request,
        "set": dict(set_row),
        "photos": photos,
    })


@router.post("/sets/{set_id}/photos", response_class=HTMLResponse)
async def upload_photo(request: Request, set_id: int, file: UploadFile = File(...)):
    with get_db() as db:
        if not db.execute("SELECT id FROM sets WHERE id = ?", (set_id,)).fetchone():
            raise HTTPException(status_code=404)

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Format non supporté (JPEG, PNG, WebP, GIF)")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 10 Mo)")

    ext = Path(file.filename or "photo.jpg").suffix.lower() or ".jpg"
    filename = f"{set_id}_{uuid.uuid4().hex}{ext}"
    (PHOTOS_DIR / filename).write_bytes(content)

    with get_db() as db:
        existing = db.execute(
            "SELECT COUNT(*) FROM photos WHERE set_id = ?", (set_id,)
        ).fetchone()[0]
        db.execute(
            "INSERT INTO photos (set_id, filename, is_primary) VALUES (?, ?, ?)",
            (set_id, filename, 1 if existing == 0 else 0),
        )

    return _render_gallery(request, set_id)


@router.post("/sets/{set_id}/photos/{photo_id}/primary", response_class=HTMLResponse)
async def set_primary_photo(request: Request, set_id: int, photo_id: int):
    with get_db() as db:
        if not db.execute(
            "SELECT id FROM photos WHERE id = ? AND set_id = ?", (photo_id, set_id)
        ).fetchone():
            raise HTTPException(status_code=404)
        db.execute("UPDATE photos SET is_primary = 0 WHERE set_id = ?", (set_id,))
        db.execute("UPDATE photos SET is_primary = 1 WHERE id = ?", (photo_id,))

    return _render_gallery(request, set_id)


@router.delete("/sets/{set_id}/photos/{photo_id}", response_class=HTMLResponse)
async def delete_photo(request: Request, set_id: int, photo_id: int):
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM photos WHERE id = ? AND set_id = ?", (photo_id, set_id)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404)
        photo = dict(row)
        db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))

        # If deleted photo was primary, promote next one
        if photo["is_primary"]:
            next_photo = db.execute(
                "SELECT id FROM photos WHERE set_id = ? ORDER BY created_at LIMIT 1", (set_id,)
            ).fetchone()
            if next_photo:
                db.execute("UPDATE photos SET is_primary = 1 WHERE id = ?", (next_photo[0],))

    try:
        (PHOTOS_DIR / photo["filename"]).unlink(missing_ok=True)
    except OSError:
        pass

    return _render_gallery(request, set_id)
