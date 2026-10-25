"""Catálogo local de ARASAAC: descarga, instantánea versionada, ingesta en SQLite e índice en memoria.

El catálogo vive en su propio archivo SQLite local (data/catalog.db), separado de la base de la
aplicación. Es de solo lectura y se reconstruye desde la copia versionada en cada arranque si falta,
así que no hace falta guardarlo en la base externa (Neon) ni en un disco persistente.
"""
import gzip
import hashlib
import json
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime, timezone

import httpx

from . import config

# Pestañas de categoría (en español). Las categorías de ARASAAC vienen en inglés y son
# 568 distintas, demasiadas para pestañas: se agrupan por etiquetas/categorías de alto nivel.
GROUPS = [
    ("basicos", "Básicos", {"core vocabulary", "core vocabulary-communication", "routine"}),
    ("acciones", "Acciones", {"verb", "usual verbs"}),
    ("personas", "Personas", {"person", "professional", "character", "family"}),
    ("emociones", "Emociones", {"psychology", "emotion", "feeling"}),
    ("comida", "Comida", {"food", "feeding", "beverage", "gastronomy"}),
    ("lugares", "Lugares", {"place", "building", "room", "facility", "geography", "country"}),
    ("casa", "Casa", {"home", "household", "appliance", "furniture"}),
    ("animales", "Animales", {"animal"}),
    ("cuerpo", "Cuerpo", {"human body", "anatomy", "physiology"}),
    ("salud", "Salud", {"health", "medicine", "hygiene", "corporal hygiene"}),
    ("ropa", "Ropa", {"clothes", "fashion"}),
    ("cualidades", "Cualidades", {"adjective", "qualifying adjective"}),
    ("tiempo", "Tiempo", {"time"}),
    ("transporte", "Transporte", {"mode of transport", "traffic", "land transport"}),
    ("escuela", "Escuela", {"education", "alphabet", "mathematics"}),
    ("ocio", "Ocio", {"leisure", "sport", "music", "outdoor activity", "physical exercise"}),
]


def norm(s: str) -> str:
    """Minúsculas, sin tildes (conserva la ñ), solo letras/dígitos separados por un espacio."""
    s = (s or "").lower().replace("ñ", "\x00")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("\x00", "ñ")
    s = re.sub(r"[^0-9a-zñ]+", " ", s)
    return s.strip()


def groups_for(p: dict) -> list[str]:
    tagset = set(p.get("tags") or []) | set(p.get("categories") or [])
    return [gid for gid, _label, tags in GROUPS if tagset & tags]


# ---------------------------------------------------------------- descarga

def download(lang: str | None = None):
    """Descarga el catálogo completo y guarda una copia comprimida. Devuelve (versión, lista, ruta)."""
    lang = lang or config.CATALOG_LANG
    r = httpx.get(f"{config.ARASAAC_API}/pictograms/all/{lang}", timeout=180, follow_redirects=True)
    r.raise_for_status()
    raw = r.content
    sha = hashlib.sha256(raw).hexdigest()[:8]
    config.CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(config.CATALOG_DIR.glob(f"arasaac-{lang}-*-{sha}.json.gz"))
    if existing:
        path = existing[0]
        version = path.name[: -len(".json.gz")]
    else:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
        version = f"arasaac-{lang}-{date}-{sha}"
        path = config.CATALOG_DIR / f"{version}.json.gz"
        path.write_bytes(gzip.compress(raw))
    return version, json.loads(raw), path


def load_snapshot(path):
    path = str(path)
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    name = path.rsplit("/", 1)[-1]
    version = re.sub(r"\.json(\.gz)?$", "", name)
    return version, data


# ---------------------------------------------------------------- base local del catálogo

SCHEMA = """
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
    picto_id INTEGER NOT NULL,
    keyword TEXT NOT NULL,
    rank INTEGER NOT NULL,
    kind TEXT NOT NULL,                  -- 'kw' | 'plural'
    type INTEGER
);
CREATE INDEX IF NOT EXISTS idx_catalog_kw_norm ON catalog_kw(norm);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def connect() -> sqlite3.Connection:
    config.CATALOG_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.CATALOG_DB, timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def _meta(con, key, default=None):
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _set_meta(con, key, value) -> None:
    con.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)))


# ---------------------------------------------------------------- ingesta

def ingest(raw: list[dict], version: str) -> int:
    """Reemplaza el catálogo local por `raw` (lista de pictogramas tal como la entrega ARASAAC)."""
    pictos, kws_rows = [], []
    for p in raw:
        kws = p.get("keywords") or []
        if not kws or p.get("_id") is None:
            continue
        flags = (1 if p.get("sex") else 0) | (2 if p.get("violence") else 0)
        pictos.append((
            p["_id"],
            kws[0]["keyword"].strip(),
            json.dumps([k["keyword"].strip() for k in kws], ensure_ascii=False),
            json.dumps(groups_for(p)),
            json.dumps(p.get("categories") or []),
            json.dumps(p.get("synsets") or []),
            int(p.get("downloads") or 0),
            flags,
        ))
        for rank, k in enumerate(kws):
            for kind, text in (("kw", k.get("keyword")), ("plural", k.get("plural"))):
                n = norm(text or "")
                if n:
                    kws_rows.append((n, p["_id"], (text or "").strip(), rank, kind, k.get("type")))
    con = connect()
    try:
        con.execute("DELETE FROM catalog_kw")
        con.execute("DELETE FROM catalog")
        con.executemany("INSERT INTO catalog(picto_id, main_keyword, keywords, groups, categories, synsets,"
                        " popularity, flags) VALUES (?,?,?,?,?,?,?,?)", pictos)
        con.executemany("INSERT INTO catalog_kw(norm, picto_id, keyword, rank, kind, type) VALUES (?,?,?,?,?,?)",
                        kws_rows)
        _set_meta(con, "version", version)
        _set_meta(con, "count", len(pictos))
        _set_meta(con, "loaded_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        con.commit()
    finally:
        con.close()
    reset_cache()
    return len(pictos)


def version() -> str | None:
    con = connect()
    try:
        return _meta(con, "version")
    finally:
        con.close()


def status() -> dict:
    con = connect()
    try:
        return {"version": _meta(con, "version"), "count": int(_meta(con, "count", "0")),
                "loaded_at": _meta(con, "loaded_at")}
    finally:
        con.close()


def ensure_loaded() -> str:
    """Deja el catálogo listo al arrancar (también tras cada reinicio en un servidor sin disco).

    Usa la copia más reciente que viaja con el código (o la que haya en la carpeta de datos) y, solo si
    no existe ninguna, la descarga de ARASAAC. Así todos los alumnos anotan con los mismos IDs.
    """
    con = connect()
    try:
        current = _meta(con, "version")
        if current and con.execute("SELECT 1 FROM catalog LIMIT 1").fetchone():
            return current
    finally:
        con.close()
    snapshots = sorted(
        [*config.CATALOG_SEED_DIR.glob("arasaac-*.json.gz"), *config.CATALOG_DIR.glob("arasaac-*.json.gz")],
        key=lambda p: p.name,
    )
    if snapshots:
        ver, raw = load_snapshot(snapshots[-1])
    else:
        ver, raw, _ = download()
    ingest(raw, ver)
    return ver


# ---------------------------------------------------------------- índice en memoria

class Index:
    def __init__(self, con):
        self.version = _meta(con, "version")
        self.pictos: dict[int, dict] = {}
        self.by_key: dict[str, list[dict]] = {}
        for r in con.execute("SELECT picto_id, main_keyword, groups, popularity, flags FROM catalog"):
            self.pictos[r["picto_id"]] = {
                "id": r["picto_id"],
                "main": r["main_keyword"],
                "groups": json.loads(r["groups"]),
                "popularity": r["popularity"],
                "flags": r["flags"],
            }
        for r in con.execute("SELECT norm, picto_id, keyword, rank, kind, type FROM catalog_kw"):
            self.by_key.setdefault(r["norm"], []).append(
                {"id": r["picto_id"], "keyword": r["keyword"], "rank": r["rank"], "kind": r["kind"], "type": r["type"]}
            )

    def lookup(self, key: str) -> list[dict]:
        """Candidatos para una clave normalizada, sin repetir pictograma (gana la mejor fila)."""
        best: dict[int, dict] = {}
        for row in self.by_key.get(key, []):
            cur = best.get(row["id"])
            if cur is None or (row["kind"] == "kw", -row["rank"]) > (cur["kind"] == "kw", -cur["rank"]):
                best[row["id"]] = row
        return list(best.values())


_cache: dict = {}
_cache_lock = threading.Lock()


def reset_cache() -> None:
    with _cache_lock:
        _cache.clear()


def get_index() -> Index:
    with _cache_lock:
        if "index" not in _cache:
            con = connect()
            try:
                if not _meta(con, "version"):
                    raise LookupError("Catálogo no cargado")
                _cache["index"] = Index(con)
            finally:
                con.close()
        return _cache["index"]


def client_payload() -> tuple[str, bytes]:
    """Catálogo compacto para el navegador: [id, principal, palabras, grupos, flags]."""
    with _cache_lock:
        if "client" not in _cache:
            con = connect()
            try:
                ver = _meta(con, "version")
                if not ver:
                    raise LookupError("Catálogo no cargado")
                gidx = {gid: i for i, (gid, _l, _t) in enumerate(GROUPS)}
                items = [
                    [r["picto_id"], r["main_keyword"], json.loads(r["keywords"]),
                     [gidx[g] for g in json.loads(r["groups"])], r["flags"]]
                    for r in con.execute("SELECT picto_id, main_keyword, keywords, groups, flags FROM catalog ORDER BY picto_id")
                ]
            finally:
                con.close()
            payload = {"version": ver, "groups": [{"id": gid, "label": label} for gid, label, _t in GROUPS], "items": items}
            _cache["client"] = (ver, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
        return _cache["client"]
