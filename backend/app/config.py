"""Configuración. Todo se puede cambiar con variables de entorno (o con un archivo .env en la raíz)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Lee ROOT/.env (líneas CLAVE=valor) sin pisar las variables ya definidas."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _path(env: str, default: Path) -> Path:
    return Path(os.environ.get(env, default))


DATA_DIR = _path("ANNOTATOR_DATA_DIR", ROOT / "data")
# OBLIGATORIA: base de datos PostgreSQL (Neon), p. ej. postgresql://usuario:clave@servidor/neondb?sslmode=require
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
CATALOG_DIR = DATA_DIR / "catalog"
# Copia del catálogo que viaja con el código; se usa para arrancar sin depender de internet.
CATALOG_SEED_DIR = _path("ANNOTATOR_CATALOG_SEED", ROOT / "data" / "catalog")
IMAGES_DIR = DATA_DIR / "images"          # caché de imágenes de ARASAAC (se puede perder sin problema)
FRONTEND_DIR = ROOT / "frontend"
DOCS_DIR = ROOT / "docs"
GUIDE_PATH = DOCS_DIR / "criterios-anotacion.md"

ARASAAC_API = "https://api.arasaac.org/v1"
ARASAAC_STATIC = "https://static.arasaac.org/pictograms"
CATALOG_LANG = "es"

# Contraseña de la persona que administra (obligatoria para entrar al panel).
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
# Si se define (p. ej. "alumnos.uni.edu,uni.edu"), solo esos dominios de correo pueden crear cuenta.
ALLOWED_EMAIL_DOMAINS = [
    d.strip().lower().lstrip("@") for d in os.environ.get("ALLOWED_EMAIL_DOMAINS", "").split(",") if d.strip()
]
# Valor inicial de «oraciones por alumno»; después lo cambia el admin desde el panel.
DEFAULT_SENTENCES_PER_STUDENT = int(os.environ.get("SENTENCES_PER_STUDENT", "15"))

# Modelo pequeño: ~75 MB de RAM frente a ~285 MB del mediano, con las mismas sugerencias en la práctica
# (cabe holgado en los 512 MB de Render gratis).
SPACY_MODEL = os.environ.get("SPACY_MODEL", "es_core_news_sm")
# "auto" usa spaCy si está disponible; "simple" fuerza el analizador de respaldo (tests).
NLP_BACKEND = os.environ.get("ANNOTATOR_NLP", "auto")
