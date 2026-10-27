"""Pictogramas relacionados por significado, con los vectores de palabras de model2vec
(potion-multilingual-128M, recortado por tools/build_related.py).

Un texto se representa con la media de los vectores de sus palabras, que es exactamente lo que hace
model2vec cuando cada palabra es un solo fragmento. Las palabras que el modelo no tiene completas se
ignoran: trocearlas («enojado» → en·oj·ado) da parecidos de ortografía («candado»), no de significado.

Los relacionados nunca sustituyen a las coincidencias: se devuelven aparte, la interfaz los marca como
«relacionado» y la propuesta automática no los usa. Si la tabla de vectores no está, todo devuelve [].
"""
import re
import threading
import unicodedata

import numpy as np

from . import catalog, config, nlp
from .catalog import norm

MIN_SCORE = 0.45  # coseno mínimo: por debajo casi todo es ruido (revisado a mano con el catálogo real)
# Palabras vacías: no aportan significado y no cuentan para decidir qué ya es una coincidencia.
STOP = nlp._DET | nlp._ADP | nlp._CCONJ | nlp._SCONJ
_WORD = re.compile(r"[^\W\d_]+")


def words(text: str) -> list[str]:
    """Palabras en minúsculas, CON tildes (para el modelo «mamá» y «mama» son palabras distintas)."""
    return [w for w in _WORD.findall(unicodedata.normalize("NFC", (text or "").lower())) if w not in STOP]


class Model:
    """Tabla palabra → vector. Los vectores se abren con mmap: solo ocupan RAM las filas consultadas."""

    def __init__(self, path):
        self.vectors = np.load(path / "vectors.npy", mmap_mode="r")
        self.row = {w: i for i, w in enumerate((path / "words.txt").read_text(encoding="utf-8").split("\n")) if w}

    def embed(self, ws: list[str]):
        rows = [self.row[w] for w in ws if w in self.row]
        if not rows:
            return None
        v = np.asarray(self.vectors[rows], dtype=np.float32).mean(axis=0)
        n = float(np.linalg.norm(v))
        return v / n if n else None


class CatalogVectors:
    """Un vector por palabra clave del catálogo (las que el modelo conoce), para un índice del catálogo."""

    def __init__(self, model: Model, idx: catalog.Index):
        self.model = model
        self.index = idx
        self.lexical: dict[int, set] = {}  # pictograma → palabras (sin tildes) de todas sus palabras clave
        self.accents: dict[str, str] = {}  # «camion» → «camión», para quien escribe sin tildes
        ids, keywords, vecs = [], [], []
        seen = set()
        for rows in idx.by_key.values():
            for r in rows:
                if r["kind"] != "kw" or (r["id"], r["keyword"]) in seen:
                    continue
                seen.add((r["id"], r["keyword"]))
                ws = words(r["keyword"])
                self.lexical.setdefault(r["id"], set()).update(norm(w) for w in ws)
                for w in ws:
                    if w in model.row:
                        self.accents.setdefault(norm(w), w)
                v = model.embed(ws)
                if v is not None:
                    ids.append(r["id"])
                    keywords.append(r["keyword"])
                    vecs.append(v)
        self.ids = ids
        self.keywords = keywords
        self.matrix = np.stack(vecs) if vecs else np.zeros((0, model.vectors.shape[1]), dtype=np.float32)

    def query_words(self, text: str) -> list[str]:
        return [w if w in self.model.row else self.accents.get(norm(w), w) for w in words(text)]

    def search(self, text: str, exclude=(), limit: int = 24) -> list[dict]:
        ws = self.query_words(text)
        v = self.model.embed(ws)
        if v is None or not len(self.ids):
            return []
        qkeys = {norm(w) for w in ws}
        scores = self.matrix @ v
        seen = set(exclude)
        out = []
        for i in np.argsort(-scores):
            s = float(scores[i])
            if s < MIN_SCORE:
                break
            pid = self.ids[i]
            if pid in seen:
                continue
            seen.add(pid)
            if self.lexical.get(pid, set()) & qkeys:
                continue  # comparte una palabra con la consulta: eso ya es una coincidencia, no un relacionado
            out.append({"id": pid, "keyword": self.keywords[i], "score": round(s, 3)})
            if len(out) == limit:
                break
        return out


_model: Model | None | bool = None  # False: no hay tabla de vectores
_vectors: CatalogVectors | None = None
_lock = threading.Lock()


def reset() -> None:
    """Olvida el modelo cargado (para las pruebas o tras regenerar la tabla)."""
    global _model, _vectors
    with _lock:
        _model = None
        _vectors = None


def _get() -> CatalogVectors | None:
    global _model, _vectors
    idx = catalog.get_index()
    cv = _vectors
    if cv is not None and cv.index is idx:
        return cv
    with _lock:
        if _model is None:
            path = config.RELATED_DIR
            if (path / "vectors.npy").exists() and (path / "words.txt").exists():
                _model = Model(path)
            else:
                print(f"[related] no hay vectores en {path}; sin pictogramas relacionados (ver tools/build_related.py)")
                _model = False
        if _model is False:
            return None
        if _vectors is None or _vectors.index is not idx:
            _vectors = CatalogVectors(_model, idx)
        return _vectors


def available() -> bool:
    return _get() is not None


def related(text: str, exclude=(), limit: int = 24) -> list[dict]:
    """Pictogramas parecidos en significado a `text`, de más a menos parecido: [{id, keyword, score}].
    Nunca incluye los de `exclude` ni los que comparten una palabra con `text` (son coincidencias)."""
    cv = _get()
    return cv.search(text, exclude, limit) if cv else []
