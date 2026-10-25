"""Guía de criterios de anotación (docs/criterios-anotacion.md) y su versión."""
import re

from . import config


def guide_text() -> str:
    try:
        return config.GUIDE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def guide_version() -> str:
    m = re.search(r"\*\*Versi[oó]n:\*\*\s*(\S+)", guide_text())
    return m.group(1) if m else "sin-guia"
