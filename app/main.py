import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database import init_db
from .routes import photos, sets

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
PHOTOS_DIR = DATA_DIR / "photos"


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    init_db(DATA_DIR / "klickbase.db")
    yield


app = FastAPI(title="KlickBase", lifespan=lifespan)

# Ensure dirs exist before StaticFiles checks them (volume may be empty on first start)
DATA_DIR.mkdir(parents=True, exist_ok=True)
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/photos", StaticFiles(directory=str(PHOTOS_DIR)), name="photos")

app.include_router(sets.router)
app.include_router(photos.router)

# Expose templates and photos dir to routes
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def condition_class(condition: str) -> str:
    mapping = {
        "Neuf": "bg-emerald-100 text-emerald-700",
        "Très bon état": "bg-blue-100 text-blue-700",
        "Bon état": "bg-teal-100 text-teal-700",
        "État moyen": "bg-amber-100 text-amber-700",
        "Mauvais état": "bg-red-100 text-red-700",
        "Sans boîte": "bg-gray-100 text-gray-600",
    }
    return mapping.get(condition or "", "bg-gray-100 text-gray-600")


# Register Jinja2 filter for use in routes
sets.templates.env.filters["condition_class"] = condition_class
photos.templates.env.filters["condition_class"] = condition_class
