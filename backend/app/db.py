"""SQLite en modo WAL: alumnos (por correo), oraciones, asignaciones, anotaciones, catálogo y memoria personal."""
import secrets
import sqlite3
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,          -- correo en minúsculas (el administrador usa 'admin')
    token TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL DEFAULT 'annotator' CHECK (role IN ('annotator','admin')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sentences (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY,
    sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    seq INTEGER NOT NULL,
    UNIQUE (sentence_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_assign_user ON assignments(user_id, seq);

CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY,
    sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL CHECK (status IN ('done','doubtful','skipped')),
    note TEXT NOT NULL DEFAULT '',
    proposal TEXT,                       -- JSON con los IDs propuestos por el sistema
    from_suggestion INTEGER NOT NULL DEFAULT 0,
    accepted_unchanged INTEGER NOT NULL DEFAULT 0,
    seconds REAL NOT NULL DEFAULT 0,
    catalog_version TEXT NOT NULL,
    guide_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (sentence_id, user_id)
);

CREATE TABLE IF NOT EXISTS annotation_items (
    annotation_id INTEGER NOT NULL REFERENCES annotations(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    picto_id INTEGER NOT NULL,
    keyword TEXT NOT NULL DEFAULT '',
    token TEXT,
    PRIMARY KEY (annotation_id, position)
);

CREATE TABLE IF NOT EXISTS catalog (
    picto_id INTEGER PRIMARY KEY,
    main_keyword TEXT NOT NULL,
    keywords TEXT NOT NULL,              -- JSON: lista de palabras clave
    groups TEXT NOT NULL,                -- JSON: ids de grupos (pestañas)
    categories TEXT NOT NULL,            -- JSON: categorías ARASAAC (en inglés)
    synsets TEXT NOT NULL,               -- JSON: synsets de WordNet
    popularity INTEGER NOT NULL DEFAULT 0,
    flags INTEGER NOT NULL DEFAULT 0     -- 1 = sexo, 2 = violencia
);

CREATE TABLE IF NOT EXISTS catalog_kw (
    norm TEXT NOT NULL,
    picto_id INTEGER NOT NULL REFERENCES catalog(picto_id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    rank INTEGER NOT NULL,
    kind TEXT NOT NULL,                  -- 'kw' | 'plural'
    type INTEGER
);
CREATE INDEX IF NOT EXISTS idx_catalog_kw_norm ON catalog_kw(norm);

CREATE TABLE IF NOT EXISTS choice_memory (
    lemma TEXT NOT NULL,
    picto_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    last_used TEXT NOT NULL,
    PRIMARY KEY (lemma, picto_id, user_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path=None) -> sqlite3.Connection:
    path = path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def _migrate(con: sqlite3.Connection) -> None:
    """Pasa una base de la versión anterior (con revisores y enlaces personales) a la actual."""
    cols = {r["name"] for r in con.execute("PRAGMA table_info(users)")}
    if "name" in cols and "email" not in cols:
        con.execute("ALTER TABLE users RENAME COLUMN name TO email")
        # Cuentas de prueba antiguas (sin correo y sin anotaciones): fuera.
        stale = ("SELECT id FROM users WHERE email NOT LIKE '%@%' AND email <> 'admin' "
                 "AND id NOT IN (SELECT user_id FROM annotations)")
        con.execute(f"DELETE FROM assignments WHERE user_id IN ({stale})")
        con.execute(f"DELETE FROM choice_memory WHERE user_id IN ({stale})")
        con.execute(f"DELETE FROM users WHERE id IN ({stale})")
        # El panel de administración ahora se abre con contraseña, no con enlace personal.
        con.execute("UPDATE users SET role='annotator' WHERE role<>'annotator' AND email<>'admin'")
        con.commit()


def init_db(path=None) -> None:
    con = connect(path)
    con.executescript(SCHEMA)
    _migrate(con)
    con.commit()
    con.close()


def get_db():
    """Dependencia de FastAPI: una conexión por petición."""
    con = connect()
    try:
        yield con
    finally:
        con.close()


def get_setting(con, key, default=None):
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(con, key, value) -> None:
    con.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def new_token() -> str:
    return secrets.token_urlsafe(16)
