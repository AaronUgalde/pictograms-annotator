"""Catálogo local de ARASAAC: descarga, instantánea versionada, ingesta en SQLite e índice en memoria."""
import gzip
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone

import httpx

from . import config, db

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


class CatalogFrozen(Exception):
    pass


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


# ---------------------------------------------------------------- ingesta

def ingest(con, raw: list[dict], version: str, force: bool = False) -> int:
    if db.get_setting(con, "catalog_frozen") == "1" and not force:
        raise CatalogFrozen("El catálogo está congelado; usa force para reemplazarlo.")
    con.execute("DELETE FROM catalog_kw")
    con.execute("DELETE FROM catalog")
    count = 0
    for p in raw:
        kws = p.get("keywords") or []
        if not kws or p.get("_id") is None:
            continue
        flags = (1 if p.get("sex") else 0) | (2 if p.get("violence") else 0)
        con.execute(
            "INSERT INTO catalog(picto_id, main_keyword, keywords, groups, categories, synsets, popularity, flags)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                p["_id"],
                kws[0]["keyword"].strip(),
                json.dumps([k["keyword"].strip() for k in kws], ensure_ascii=False),
                json.dumps(groups_for(p)),
                json.dumps(p.get("categories") or []),
                json.dumps(p.get("synsets") or []),
                int(p.get("downloads") or 0),
                flags,
            ),
        )
        for rank, k in enumerate(kws):
            for kind, text in (("kw", k.get("keyword")), ("plural", k.get("plural"))):
                n = norm(text or "")
                if n:
                    con.execute(
                        "INSERT INTO catalog_kw(norm, picto_id, keyword, rank, kind, type) VALUES (?,?,?,?,?,?)",
                        (n, p["_id"], (text or "").strip(), rank, kind, k.get("type")),
                    )
        count += 1
    db.set_setting(con, "catalog_version", version)
    db.set_setting(con, "catalog_loaded_at", db.now())
    db.set_setting(con, "catalog_count", count)
    con.commit()
    reset_cache()
    return count


def freeze(con) -> None:
    if not db.get_setting(con, "catalog_version"):
        raise ValueError("No hay catálogo cargado.")
    db.set_setting(con, "catalog_frozen", "1")
    con.commit()


def status(con) -> dict:
    return {
        "version": db.get_setting(con, "catalog_version"),
        "frozen": db.get_setting(con, "catalog_frozen") == "1",
        "count": int(db.get_setting(con, "catalog_count", "0")),
        "loaded_at": db.get_setting(con, "catalog_loaded_at"),
    }


def ensure_loaded(con) -> str:
    """Deja el catálogo listo al arrancar (primer despliegue incluido).

    Si la base no tiene catálogo, carga la copia más reciente que viaja con el código (o la que haya en
    el volumen de datos) y, solo si no existe ninguna, la descarga de ARASAAC. El catálogo queda
    congelado: todos los alumnos anotan con los mismos IDs.
    """
    version = db.get_setting(con, "catalog_version")
    if version and con.execute("SELECT 1 FROM catalog LIMIT 1").fetchone():
        return version
    snapshots = sorted(
        [*config.CATALOG_SEED_DIR.glob("arasaac-*.json.gz"), *config.CATALOG_DIR.glob("arasaac-*.json.gz")],
        key=lambda p: p.name,
    )
    if snapshots:
        version, raw = load_snapshot(snapshots[-1])
    else:
        version, raw, _ = download()
    ingest(con, raw, version, force=True)
    db.set_setting(con, "catalog_frozen", "1")
    con.commit()
    return version


# ---------------------------------------------------------------- índice en memoria

class Index:
    def __init__(self, con):
        self.version = db.get_setting(con, "catalog_version")
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


_index_cache: dict = {}
_client_cache: dict = {}


def reset_cache() -> None:
    _index_cache.clear()
    _client_cache.clear()


def _db_key(con) -> str:
    return con.execute("PRAGMA database_list").fetchone()["file"]


def get_index(con) -> Index:
    version = db.get_setting(con, "catalog_version")
    if not version:
        raise LookupError("Catálogo no cargado")
    key = (_db_key(con), version)
    if key not in _index_cache:
        _index_cache.clear()
        _index_cache[key] = Index(con)
    return _index_cache[key]


def client_payload(con) -> tuple[str, bytes]:
    """Catálogo compacto para el navegador: [id, principal, palabras, grupos, flags]."""
    version = db.get_setting(con, "catalog_version")
    if not version:
        raise LookupError("Catálogo no cargado")
    key = (_db_key(con), version)
    if key not in _client_cache:
        _client_cache.clear()
        gidx = {gid: i for i, (gid, _l, _t) in enumerate(GROUPS)}
        items = []
        for r in con.execute("SELECT picto_id, main_keyword, keywords, groups, flags FROM catalog ORDER BY picto_id"):
            items.append(
                [r["picto_id"], r["main_keyword"], json.loads(r["keywords"]),
                 [gidx[g] for g in json.loads(r["groups"])], r["flags"]]
            )
        payload = {
            "version": version,
            "groups": [{"id": gid, "label": label} for gid, label, _t in GROUPS],
            "items": items,
        }
        _client_cache[key] = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return version, _client_cache[key]
