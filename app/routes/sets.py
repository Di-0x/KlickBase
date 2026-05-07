import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..database import get_db
from ..scraper import THEMES, scrape_klickypedia

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


BOX_CONDITIONS = ["Neuf", "Très bon état", "Bon état", "État moyen", "Mauvais état", "Sans boîte"]

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
PHOTOS_DIR = DATA_DIR / "photos"


def _query_sets(
    db,
    q: str = None,
    collection: str = None,
    box_condition: str = None,
    missing_pieces: str = None,
    manual_present: str = None,
    tag: str = None,
    sort: str = "set_number",
    order: str = "asc",
    min_price: str = None,
    max_price: str = None,
) -> list[dict]:
    where = ["1=1"]
    params = []

    if q:
        where.append("(s.name LIKE ? OR s.set_number LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if collection:
        where.append("s.collection = ?")
        params.append(collection)
    if box_condition:
        where.append("s.box_condition = ?")
        params.append(box_condition)
    if missing_pieces in ("0", "1"):
        where.append("s.missing_pieces = ?")
        params.append(int(missing_pieces))
    if manual_present in ("0", "1"):
        where.append("s.manual_present = ?")
        params.append(int(manual_present))
    if tag:
        where.append(
            "EXISTS (SELECT 1 FROM set_tags st JOIN tags t ON t.id = st.tag_id "
            "WHERE st.set_id = s.id AND t.name = ?)"
        )
        params.append(tag)
    if min_price:
        try:
            where.append("s.price_paid >= ?")
            params.append(float(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            where.append("s.price_paid <= ?")
            params.append(float(max_price))
        except ValueError:
            pass

    valid_sorts = {"set_number", "name", "price_paid", "purchase_date", "collection", "created_at"}
    if sort not in valid_sorts:
        sort = "set_number"
    order_sql = "DESC" if order == "desc" else "ASC"

    sql = f"""
        SELECT s.*,
               GROUP_CONCAT(DISTINCT t.name) AS tags,
               (SELECT filename FROM photos WHERE set_id = s.id AND is_primary = 1 LIMIT 1) AS primary_photo,
               (SELECT filename FROM photos WHERE set_id = s.id ORDER BY created_at LIMIT 1) AS first_photo
        FROM sets s
        LEFT JOIN set_tags st ON st.set_id = s.id
        LEFT JOIN tags t ON t.id = st.tag_id
        WHERE {' AND '.join(where)}
        GROUP BY s.id
        ORDER BY s.{sort} {order_sql} NULLS LAST
    """
    return [dict(row) for row in db.execute(sql, params).fetchall()]


def _upsert_tags(db, set_id: int, tags_raw: str):
    db.execute("DELETE FROM set_tags WHERE set_id = ?", (set_id,))
    if not tags_raw:
        return
    for name in {t.strip() for t in tags_raw.split(",") if t.strip()}:
        db.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        tag_id = db.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()[0]
        db.execute("INSERT OR IGNORE INTO set_tags (set_id, tag_id) VALUES (?, ?)", (set_id, tag_id))


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    with get_db() as db:
        sets = _query_sets(db)
        collections = [
            r[0] for r in db.execute(
                "SELECT DISTINCT collection FROM sets WHERE collection IS NOT NULL ORDER BY collection"
            ).fetchall()
        ]
        all_tags = [r[0] for r in db.execute("SELECT name FROM tags ORDER BY name").fetchall()]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "sets": sets,
        "collections": collections,
        "all_tags": all_tags,
        "BOX_CONDITIONS": BOX_CONDITIONS,
        "total": len(sets),
    })


@router.get("/sets", response_class=HTMLResponse)
async def list_sets(
    request: Request,
    q: Optional[str] = None,
    collection: Optional[str] = None,
    box_condition: Optional[str] = None,
    missing_pieces: Optional[str] = None,
    manual_present: Optional[str] = None,
    tag: Optional[str] = None,
    sort: str = "set_number",
    order: str = "asc",
    view: str = "grid",
    min_price: Optional[str] = None,
    max_price: Optional[str] = None,
):
    with get_db() as db:
        sets = _query_sets(
            db, q=q, collection=collection, box_condition=box_condition,
            missing_pieces=missing_pieces, manual_present=manual_present,
            tag=tag, sort=sort, order=order, min_price=min_price, max_price=max_price,
        )
    return templates.TemplateResponse("partials/set_list.html", {
        "request": request,
        "sets": sets,
        "view": view,
        "sort": sort,
        "order": order,
        "total": len(sets),
    })


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.get("/sets/new", response_class=HTMLResponse)
async def new_set_form(request: Request):
    with get_db() as db:
        all_tags = [r[0] for r in db.execute("SELECT name FROM tags ORDER BY name").fetchall()]
    return templates.TemplateResponse("set_form.html", {
        "request": request,
        "set": None,
        "set_tags": [],
        "THEMES": THEMES,
        "BOX_CONDITIONS": BOX_CONDITIONS,
        "all_tags": all_tags,
    })


@router.post("/sets/new")
async def create_set(
    set_number: str = Form(...),
    name: str = Form(...),
    collection: Optional[str] = Form(None),
    num_pieces: Optional[str] = Form(None),
    num_figures: Optional[str] = Form(None),
    price_paid: Optional[str] = Form(None),
    purchase_date: Optional[str] = Form(None),
    box_condition: str = Form("Bon état"),
    manual_present: Optional[str] = Form(None),
    missing_pieces: Optional[str] = Form(None),
    missing_pieces_desc: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    year: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
):
    def _int(v): return int(v) if v and v.strip().isdigit() else None
    def _float(v):
        try: return float(v.replace(",", ".")) if v and v.strip() else None
        except ValueError: return None

    with get_db() as db:
        cursor = db.execute(
            """INSERT INTO sets
               (set_number, name, collection, num_pieces, num_figures, price_paid,
                purchase_date, box_condition, manual_present, missing_pieces,
                missing_pieces_desc, notes, year)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                set_number.strip(), name.strip(),
                collection or None, _int(num_pieces), _int(num_figures), _float(price_paid),
                purchase_date or None, box_condition,
                1 if manual_present else 0,
                1 if missing_pieces else 0,
                missing_pieces_desc or None, notes or None, _int(year),
            ),
        )
        set_id = cursor.lastrowid
        _upsert_tags(db, set_id, tags or "")

    return RedirectResponse(f"/sets/{set_id}", status_code=303)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@router.get("/sets/{set_id}", response_class=HTMLResponse)
async def set_detail(request: Request, set_id: int):
    with get_db() as db:
        row = db.execute(
            """SELECT s.*, GROUP_CONCAT(DISTINCT t.name) AS tags
               FROM sets s
               LEFT JOIN set_tags st ON st.set_id = s.id
               LEFT JOIN tags t ON t.id = st.tag_id
               WHERE s.id = ? GROUP BY s.id""",
            (set_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Set non trouvé")
        photos = [
            dict(p) for p in db.execute(
                "SELECT * FROM photos WHERE set_id = ? ORDER BY is_primary DESC, created_at ASC",
                (set_id,),
            ).fetchall()
        ]

    s = dict(row)
    s["tags_list"] = s["tags"].split(",") if s["tags"] else []
    return templates.TemplateResponse("set_detail.html", {
        "request": request,
        "set": s,
        "photos": photos,
    })


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------

@router.get("/sets/{set_id}/edit", response_class=HTMLResponse)
async def edit_set_form(request: Request, set_id: int):
    with get_db() as db:
        row = db.execute(
            """SELECT s.*, GROUP_CONCAT(DISTINCT t.name) AS tags
               FROM sets s
               LEFT JOIN set_tags st ON st.set_id = s.id
               LEFT JOIN tags t ON t.id = st.tag_id
               WHERE s.id = ? GROUP BY s.id""",
            (set_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Set non trouvé")
        all_tags = [r[0] for r in db.execute("SELECT name FROM tags ORDER BY name").fetchall()]

    s = dict(row)
    s["tags_list"] = s["tags"].split(",") if s["tags"] else []
    return templates.TemplateResponse("set_form.html", {
        "request": request,
        "set": s,
        "set_tags": s["tags_list"],
        "THEMES": THEMES,
        "BOX_CONDITIONS": BOX_CONDITIONS,
        "all_tags": all_tags,
    })


@router.post("/sets/{set_id}/edit")
async def update_set(
    set_id: int,
    set_number: str = Form(...),
    name: str = Form(...),
    collection: Optional[str] = Form(None),
    num_pieces: Optional[str] = Form(None),
    num_figures: Optional[str] = Form(None),
    price_paid: Optional[str] = Form(None),
    purchase_date: Optional[str] = Form(None),
    box_condition: str = Form("Bon état"),
    manual_present: Optional[str] = Form(None),
    missing_pieces: Optional[str] = Form(None),
    missing_pieces_desc: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    year: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
):
    def _int(v): return int(v) if v and v.strip().isdigit() else None
    def _float(v):
        try: return float(v.replace(",", ".")) if v and v.strip() else None
        except ValueError: return None

    with get_db() as db:
        existing = db.execute("SELECT id FROM sets WHERE id = ?", (set_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Set non trouvé")

        db.execute(
            """UPDATE sets SET
               set_number=?, name=?, collection=?, num_pieces=?, num_figures=?, price_paid=?,
               purchase_date=?, box_condition=?, manual_present=?, missing_pieces=?,
               missing_pieces_desc=?, notes=?, year=?, updated_at=datetime('now')
               WHERE id=?""",
            (
                set_number.strip(), name.strip(),
                collection or None, _int(num_pieces), _int(num_figures), _float(price_paid),
                purchase_date or None, box_condition,
                1 if manual_present else 0,
                1 if missing_pieces else 0,
                missing_pieces_desc or None, notes or None, _int(year),
                set_id,
            ),
        )
        _upsert_tags(db, set_id, tags or "")

    return RedirectResponse(f"/sets/{set_id}", status_code=303)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete("/sets/{set_id}", response_class=HTMLResponse)
async def delete_set(set_id: int):
    with get_db() as db:
        db.execute("DELETE FROM sets WHERE id = ?", (set_id,))
    return HTMLResponse(status_code=200, headers={"HX-Redirect": "/"})


# ---------------------------------------------------------------------------
# Scrape
# ---------------------------------------------------------------------------

@router.post("/sets/{set_id}/scrape", response_class=HTMLResponse)
async def scrape_set(request: Request, set_id: int):
    with get_db() as db:
        row = db.execute("SELECT set_number FROM sets WHERE id = ?", (set_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404)
        set_number = row[0]

    scraped = scrape_klickypedia(set_number)

    if scraped:
        with get_db() as db:
            fields, params = [], []
            for key in ("name", "official_photo_url", "year", "collection", "num_pieces", "num_figures", "klickypedia_url"):
                if scraped.get(key) is not None:
                    fields.append(f"{key} = ?")
                    params.append(scraped[key])
            if fields:
                fields.append("updated_at = datetime('now')")
                params.append(set_id)
                db.execute(f"UPDATE sets SET {', '.join(fields)} WHERE id = ?", params)

    with get_db() as db:
        row = db.execute(
            """SELECT s.*, GROUP_CONCAT(DISTINCT t.name) AS tags
               FROM sets s
               LEFT JOIN set_tags st ON st.set_id = s.id
               LEFT JOIN tags t ON t.id = st.tag_id
               WHERE s.id = ? GROUP BY s.id""",
            (set_id,),
        ).fetchone()
        photos = [
            dict(p) for p in db.execute(
                "SELECT * FROM photos WHERE set_id = ? ORDER BY is_primary DESC, created_at ASC",
                (set_id,),
            ).fetchall()
        ]

    s = dict(row)
    s["tags_list"] = s["tags"].split(",") if s["tags"] else []
    return templates.TemplateResponse("set_detail.html", {
        "request": request,
        "set": s,
        "photos": photos,
        "scrape_message": "Données récupérées avec succès depuis Klickypedia." if scraped else "Aucune donnée trouvée sur Klickypedia.",
        "scrape_ok": bool(scraped),
    })
