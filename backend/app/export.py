"""Exportación a JSONL y CSV (PLAN sección 9). Incluye todas las anotaciones independientes y la referencia dorada."""
import csv
import io
import json


def _load(con):
    names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM users")}
    items: dict = {}
    for r in con.execute("SELECT annotation_id, picto_id, keyword, token FROM annotation_items ORDER BY annotation_id, position"):
        items.setdefault(r["annotation_id"], []).append({"id": r["picto_id"], "keyword": r["keyword"], "token": r["token"]})
    anns: dict = {}
    for r in con.execute("SELECT * FROM annotations ORDER BY sentence_id, user_id"):
        anns.setdefault(r["sentence_id"], []).append({
            "annotator": names.get(r["user_id"], str(r["user_id"])),
            "status": r["status"],
            "ids": [i["id"] for i in items.get(r["id"], [])],
            "keywords": [i["keyword"] for i in items.get(r["id"], [])],
            "from_suggestion": bool(r["from_suggestion"]),
            "accepted_unchanged": bool(r["accepted_unchanged"]),
            "blind": bool(r["blind"]),
            "seconds": round(r["seconds"], 1),
            "date": r["updated_at"],
            "catalog_version": r["catalog_version"],
            "guide_version": r["guide_version"],
            "note": r["note"],
        })
    gitems: dict = {}
    for r in con.execute("SELECT sentence_id, picto_id, keyword FROM gold_items ORDER BY sentence_id, position"):
        gitems.setdefault(r["sentence_id"], []).append((r["picto_id"], r["keyword"]))
    golds = {}
    for r in con.execute("SELECT * FROM gold"):
        gi = gitems.get(r["sentence_id"], [])
        golds[r["sentence_id"]] = {
            "adjudicator": names.get(r["adjudicator_id"], str(r["adjudicator_id"])),
            "ids": [i for i, _ in gi],
            "keywords": [k for _, k in gi],
            "note": r["note"],
            "date": r["updated_at"],
            "catalog_version": r["catalog_version"],
            "guide_version": r["guide_version"],
        }
    return anns, golds


def records(con):
    anns, golds = _load(con)
    for s in con.execute("SELECT * FROM sentences ORDER BY id"):
        yield {
            "sentence_id": s["id"],
            "text": s["text"],
            "batch": s["batch"],
            "pilot": bool(s["is_pilot"]),
            "blind": bool(s["blind"]),
            "target_coverage": s["target_coverage"],
            "annotations": anns.get(s["id"], []),
            "gold": golds.get(s["id"]),
        }


def to_jsonl(con) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records(con))


CSV_FIELDS = ["sentence_id", "text", "batch", "pilot", "annotator", "role", "status", "ids", "keywords",
              "from_suggestion", "accepted_unchanged", "blind", "seconds", "date",
              "catalog_version", "guide_version", "note"]


def to_csv(con) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    w.writeheader()
    for r in records(con):
        base = {"sentence_id": r["sentence_id"], "text": r["text"], "batch": r["batch"], "pilot": int(r["pilot"])}
        for a in r["annotations"]:
            w.writerow({**base, "annotator": a["annotator"], "role": "annotation", "status": a["status"],
                        "ids": " ".join(map(str, a["ids"])), "keywords": " | ".join(a["keywords"]),
                        "from_suggestion": int(a["from_suggestion"]), "accepted_unchanged": int(a["accepted_unchanged"]),
                        "blind": int(a["blind"]), "seconds": a["seconds"], "date": a["date"],
                        "catalog_version": a["catalog_version"], "guide_version": a["guide_version"], "note": a["note"]})
        g = r["gold"]
        if g:
            w.writerow({**base, "annotator": g["adjudicator"], "role": "gold", "status": "gold",
                        "ids": " ".join(map(str, g["ids"])), "keywords": " | ".join(g["keywords"]),
                        "date": g["date"], "catalog_version": g["catalog_version"],
                        "guide_version": g["guide_version"], "note": g["note"]})
    return buf.getvalue()
