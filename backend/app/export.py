"""Exportación a JSONL y CSV: todas las anotaciones, una por alumno y oración."""
import csv
import io
import json


def records(con):
    items: dict = {}
    for r in con.execute("SELECT annotation_id, picto_id, keyword, token FROM annotation_items ORDER BY annotation_id, position"):
        items.setdefault(r["annotation_id"], []).append({"id": r["picto_id"], "keyword": r["keyword"], "token": r["token"]})
    emails = {r["id"]: r["email"] for r in con.execute("SELECT id, email FROM users")}
    anns: dict = {}
    for r in con.execute("SELECT * FROM annotations ORDER BY sentence_id, user_id"):
        its = items.get(r["id"], [])
        anns.setdefault(r["sentence_id"], []).append({
            "email": emails.get(r["user_id"], str(r["user_id"])),
            "status": r["status"],
            "ids": [i["id"] for i in its],
            "keywords": [i["keyword"] for i in its],
            "from_suggestion": bool(r["from_suggestion"]),
            "accepted_unchanged": bool(r["accepted_unchanged"]),
            "seconds": round(r["seconds"], 1),
            "date": r["updated_at"],
            "catalog_version": r["catalog_version"],
            "guide_version": r["guide_version"],
            "note": r["note"],
        })
    for s in con.execute("SELECT id, text FROM sentences ORDER BY id"):
        yield {"sentence_id": s["id"], "text": s["text"], "annotations": anns.get(s["id"], [])}


def to_jsonl(con) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records(con))


CSV_FIELDS = ["sentence_id", "text", "email", "status", "ids", "keywords", "from_suggestion",
              "accepted_unchanged", "seconds", "date", "catalog_version", "guide_version", "note"]


def to_csv(con) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    w.writeheader()
    for r in records(con):
        for a in r["annotations"]:
            w.writerow({"sentence_id": r["sentence_id"], "text": r["text"], "email": a["email"], "status": a["status"],
                        "ids": " ".join(map(str, a["ids"])), "keywords": " | ".join(a["keywords"]),
                        "from_suggestion": int(a["from_suggestion"]), "accepted_unchanged": int(a["accepted_unchanged"]),
                        "seconds": a["seconds"], "date": a["date"], "catalog_version": a["catalog_version"],
                        "guide_version": a["guide_version"], "note": a["note"]})
    return buf.getvalue()
