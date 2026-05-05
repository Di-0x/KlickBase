import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH: Path = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_number TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    collection TEXT,
    num_pieces INTEGER,
    price_paid REAL,
    public_price REAL,
    purchase_date TEXT,
    box_condition TEXT DEFAULT 'Bon état',
    manual_present INTEGER DEFAULT 0,
    missing_pieces INTEGER DEFAULT 0,
    missing_pieces_desc TEXT,
    notes TEXT,
    official_photo_url TEXT,
    playmobil_url TEXT,
    year INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id INTEGER NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    is_primary INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS set_tags (
    set_id INTEGER NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (set_id, tag_id)
);
"""


def init_db(db_path: Path):
    global DB_PATH
    DB_PATH = db_path
    with get_db() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
