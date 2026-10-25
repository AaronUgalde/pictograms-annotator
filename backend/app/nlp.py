"""Análisis lingüístico: spaCy (es_core_news_sm) con un analizador de respaldo sin dependencias."""
import re
from dataclasses import dataclass

from . import config


@dataclass
class Tok:
    text: str
    lemma: str
    pos: str


_nlp = None
_backend = None  # "spacy" | "simple"

_DET = {"el", "la", "los", "las", "un", "una", "unos", "unas", "lo"}
_ADP = {"a", "ante", "bajo", "con", "contra", "de", "del", "al", "desde", "en", "entre", "hacia",
        "hasta", "para", "por", "segun", "según", "sin", "sobre", "tras"}
_CCONJ = {"y", "e", "o", "u", "ni", "pero"}
_SCONJ = {"que", "si", "como", "cuando", "porque", "aunque"}
_WORD = re.compile(r"\w+(?:'\w+)?|[^\w\s]", re.UNICODE)


def _load() -> None:
    global _nlp, _backend
    if _backend is not None:
        return
    if config.NLP_BACKEND != "simple":
        try:
            import spacy

            _nlp = spacy.load(config.SPACY_MODEL, disable=["ner"])
            _backend = "spacy"
            return
        except Exception as exc:  # modelo no instalado o incompatible
            print(f"[nlp] spaCy no disponible ({exc.__class__.__name__}); uso analizador simple")
    _backend = "simple"


def backend() -> str:
    _load()
    return _backend


def _simple_pos(word: str) -> str:
    w = word.lower()
    if not re.search(r"\w", w):
        return "PUNCT"
    if w in _DET:
        return "DET"
    if w in _ADP:
        return "ADP"
    if w in _CCONJ:
        return "CCONJ"
    if w in _SCONJ:
        return "SCONJ"
    return "X"


def analyze(text: str) -> list[Tok]:
    _load()
    if _backend == "spacy":
        return [Tok(t.text, (t.lemma_ or t.text).lower(), t.pos_) for t in _nlp(text) if not t.is_space]
    return [Tok(w, w.lower(), _simple_pos(w)) for w in _WORD.findall(text)]
