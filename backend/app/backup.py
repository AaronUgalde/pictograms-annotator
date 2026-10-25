"""Copias de seguridad (base SQLite + exportación JSONL) y versión de la guía de criterios."""
import re
import sqlite3
from datetime import datetime, timezone

from . import config, db, export


def run_backup() -> str:
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = config.BACKUP_DIR / f"annotator-{ts}.db"
    src = db.connect()
    try:
        dst = sqlite3.connect(dest)
        src.backup(dst)  # copia consistente aunque haya escrituras en curso
        dst.close()
        (config.BACKUP_DIR / f"export-{ts}.jsonl").write_text(export.to_jsonl(src), encoding="utf-8")
    finally:
        src.close()
    for pattern in ("annotator-*.db", "export-*.jsonl"):
        files = sorted(config.BACKUP_DIR.glob(pattern))
        for old in files[: max(0, len(files) - config.BACKUP_KEEP)]:
            old.unlink()
    return str(dest)


def guide_text() -> str:
    try:
        return config.GUIDE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def guide_version() -> str:
    m = re.search(r"\*\*Versi[oó]n:\*\*\s*(\S+)", guide_text())
    return m.group(1) if m else "sin-guia"
