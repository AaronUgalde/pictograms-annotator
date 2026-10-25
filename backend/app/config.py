"""Configuración. Todo se puede cambiar con variables de entorno."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _path(env: str, default: Path) -> Path:
    return Path(os.environ.get(env, default))


DATA_DIR = _path("ANNOTATOR_DATA_DIR", ROOT / "data")
DB_PATH = _path("ANNOTATOR_DB", DATA_DIR / "annotator.db")
CATALOG_DIR = DATA_DIR / "catalog"
IMAGES_DIR = DATA_DIR / "images"
BACKUP_DIR = DATA_DIR / "backups"
FRONTEND_DIR = ROOT / "frontend"
DOCS_DIR = ROOT / "docs"
GUIDE_PATH = DOCS_DIR / "criterios-anotacion.md"

ARASAAC_API = "https://api.arasaac.org/v1"
ARASAAC_STATIC = "https://static.arasaac.org/pictograms"
CATALOG_LANG = "es"

BACKUP_INTERVAL_HOURS = float(os.environ.get("BACKUP_INTERVAL_HOURS", "6"))
BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "30"))

SPACY_MODEL = os.environ.get("SPACY_MODEL", "es_core_news_md")
# "auto" usa spaCy si está disponible; "simple" fuerza el analizador de respaldo (tests).
NLP_BACKEND = os.environ.get("ANNOTATOR_NLP", "auto")
