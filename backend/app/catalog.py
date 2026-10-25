"""Catálogo de ARASAAC: descarga, copia versionada (data/catalog/*.json.gz) e índice en memoria.

El catálogo es de solo lectura: al arrancar se carga en memoria desde la copia que viaja con el
código, así que no se guarda en la base de datos ni necesita disco persistente.
"""
import gzip
import hashlib
import json
import re
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


# ---------------------------------------------------------------- índice en memoria

class Index:
    """Catálogo listo para consultar: pictogramas por ID y candidatos por palabra clave normalizada."""

    def __init__(self, raw: list[dict], version: str):
        self.version = version
        self.pictos: dict[int, dict] = {}
        self.by_key: dict[str, list[dict]] = {}
        gidx = {gid: i for i, (gid, _l, _t) in enumerate(GROUPS)}
        client_items = []
        for p in sorted(raw, key=lambda x: x.get("_id") or 0):
            kws = p.get("keywords") or []
            pid = p.get("_id")
            if not kws or pid is None:
                continue
            groups = groups_for(p)
            flags = (1 if p.get("sex") else 0) | (2 if p.get("violence") else 0)
            main = kws[0]["keyword"].strip()
            self.pictos[pid] = {"id": pid, "main": main, "groups": groups,
                                "popularity": int(p.get("downloads") or 0), "flags": flags}
            client_items.append([pid, main, [k["keyword"].strip() for k in kws], [gidx[g] for g in groups], flags])
            for rank, k in enumerate(kws):
                for kind, text in (("kw", k.get("keyword")), ("plural", k.get("plural"))):
                    n = norm(text or "")
                    if n:
                        self.by_key.setdefault(n, []).append(
                            {"id": pid, "keyword": (text or "").strip(), "rank": rank, "kind": kind, "type": k.get("type")})
        payload = {"version": version, "groups": [{"id": gid, "label": label} for gid, label, _t in GROUPS],
                   "items": client_items}
        self.client_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()

    def lookup(self, key: str) -> list[dict]:
        """Candidatos para una clave normalizada, sin repetir pictograma (gana la mejor fila)."""
        best: dict[int, dict] = {}
        for row in self.by_key.get(key, []):
            cur = best.get(row["id"])
            if cur is None or (row["kind"] == "kw", -row["rank"]) > (cur["kind"] == "kw", -cur["rank"]):
                best[row["id"]] = row
        return list(best.values())


_index: Index | None = None
_lock = threading.Lock()


def ingest(raw: list[dict], version: str) -> int:
    """Carga en memoria el catálogo `raw` (lista de pictogramas tal como la entrega ARASAAC)."""
    global _index
    idx = Index(raw, version)
    with _lock:
        _index = idx
    return len(idx.pictos)


def latest_snapshot():
    snaps = sorted(
        {*config.CATALOG_SEED_DIR.glob("arasaac-*.json.gz"), *config.CATALOG_DIR.glob("arasaac-*.json.gz")},
        key=lambda p: p.name,
    )
    return snaps[-1] if snaps else None


def ensure_loaded() -> str:
    """Carga la copia más reciente del catálogo (la que viaja con el código). Solo si no hay ninguna,
    la descarga de ARASAAC. Así todos los alumnos anotan siempre con los mismos IDs."""
    if _index is not None:
        return _index.version
    path = latest_snapshot()
    if path:
        version, raw = load_snapshot(path)
    else:
        version, raw, _ = download()
    ingest(raw, version)
    return version


def get_index() -> Index:
    if _index is None:
        ensure_loaded()
    return _index


def client_payload() -> tuple[str, bytes]:
    """Catálogo compacto para el navegador: [id, principal, palabras, grupos, flags]."""
    idx = get_index()
    return idx.version, idx.client_json


def status() -> dict:
    idx = _index
    return {"version": idx.version if idx else None, "count": len(idx.pictos) if idx else 0}
