"""Validación de las secuencias de pictogramas que envían los alumnos."""
from . import catalog


class BadItems(ValueError):
    pass


def validate_items(con, items: list[dict]) -> list[dict]:
    known = catalog.get_index().pictos
    missing = {i["picto_id"] for i in items} - known.keys()
    if missing:
        raise BadItems(f"Pictogramas que no están en el catálogo: {sorted(missing)}")
    return [
        {"picto_id": i["picto_id"], "keyword": (i.get("keyword") or "")[:120],
         "token": catalog.norm(i["token"]) if i.get("token") else None}
        for i in items
    ]
