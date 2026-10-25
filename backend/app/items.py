"""Validación de las secuencias de pictogramas que envían los alumnos."""
from . import catalog


class BadItems(ValueError):
    pass


def validate_items(con, items: list[dict]) -> list[dict]:
    ids = {i["picto_id"] for i in items}
    if ids:
        ph = ",".join("?" * len(ids))
        found = {r["picto_id"] for r in con.execute(f"SELECT picto_id FROM catalog WHERE picto_id IN ({ph})", list(ids))}
        missing = ids - found
        if missing:
            raise BadItems(f"Pictogramas que no están en el catálogo: {sorted(missing)}")
    return [
        {"picto_id": i["picto_id"], "keyword": (i.get("keyword") or "")[:120],
         "token": catalog.norm(i["token"]) if i.get("token") else None}
        for i in items
    ]
