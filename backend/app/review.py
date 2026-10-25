"""Revisión, adjudicación (referencia dorada) y panel de coordinación."""
import json
from collections import Counter

from . import backup, catalog, db, metrics


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


def classify(entries: dict, has_gold: bool) -> str:
    if has_gold:
        return "gold"
    if len(entries) < 2:
        return "waiting"
    seqs = [e["ids"] for e in entries.values()]
    doubt = any(e["status"] == "doubtful" for e in entries.values())
    if not doubt and all(s == seqs[0] for s in seqs):
        return "agree"
    return "needs"


def overview(con, flt: str = "needs", min_distance: float = 0.0, limit: int = 200, offset: int = 0) -> dict:
    seqs = metrics.load_sequences(con)
    golds = {r["sentence_id"] for r in con.execute("SELECT sentence_id FROM gold")}
    rows = []
    for s in con.execute("SELECT id, text, target_coverage, blind FROM sentences ORDER BY id"):
        entries = seqs.get(s["id"], {})
        state = classify(entries, s["id"] in golds)
        sm = metrics.sentence_metrics({u: e["ids"] for u, e in entries.items()})
        rows.append({
            "id": s["id"], "text": s["text"], "state": state, "blind": bool(s["blind"]),
            "n": len(entries), "target": s["target_coverage"],
            "doubtful": sum(1 for e in entries.values() if e["status"] == "doubtful"),
            "distance": sm["distance"] if sm else None,
        })
    counts = Counter(r["state"] for r in rows)
    if flt != "all":
        rows = [r for r in rows if r["state"] == flt]
    if flt == "needs":
        rows = [r for r in rows if r["doubtful"] or (r["distance"] or 0) >= min_distance]
        rows.sort(key=lambda r: (-(r["distance"] or 0), r["id"]))
    return {"counts": dict(counts), "total": len(rows), "items": rows[offset : offset + limit]}


def detail(con, sid: int) -> dict | None:
    s = con.execute("SELECT * FROM sentences WHERE id=?", (sid,)).fetchone()
    if not s:
        return None
    names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM users")}
    anns = []
    for a in con.execute("SELECT * FROM annotations WHERE sentence_id=? ORDER BY user_id", (sid,)):
        items = [dict(i) for i in con.execute(
            "SELECT picto_id, keyword, token FROM annotation_items WHERE annotation_id=? ORDER BY position", (a["id"],))]
        anns.append({"user_id": a["user_id"], "annotator": names.get(a["user_id"]), "status": a["status"],
                     "note": a["note"], "blind": bool(a["blind"]), "from_suggestion": bool(a["from_suggestion"]),
                     "accepted_unchanged": bool(a["accepted_unchanged"]), "seconds": round(a["seconds"], 1),
                     "items": items})
    gold = None
    g = con.execute("SELECT * FROM gold WHERE sentence_id=?", (sid,)).fetchone()
    if g:
        gold = {"adjudicator": names.get(g["adjudicator_id"]), "note": g["note"], "updated_at": g["updated_at"],
                "items": [dict(i) for i in con.execute(
                    "SELECT picto_id, keyword FROM gold_items WHERE sentence_id=? ORDER BY position", (sid,))]}
    sm = metrics.sentence_metrics({a["user_id"]: [i["picto_id"] for i in a["items"]]
                                   for a in anns if a["status"] != "skipped"})
    if sm:
        for p in sm["pairs"]:
            p["a"], p["b"] = names.get(p["a"]), names.get(p["b"])
    return {"sentence": dict(s), "annotations": anns, "gold": gold, "metrics": sm}


def save_gold(con, sid: int, user_id: int, items: list[dict], note: str = "", agreement_note: bool = False) -> None:
    items = validate_items(con, items)
    if not items:
        raise BadItems("La referencia dorada necesita al menos un pictograma.")
    ts = db.now()
    version = db.get_setting(con, "catalog_version") or ""
    existing = con.execute("SELECT created_at FROM gold WHERE sentence_id=?", (sid,)).fetchone()
    con.execute("DELETE FROM gold WHERE sentence_id=?", (sid,))
    con.execute(
        "INSERT INTO gold(sentence_id, adjudicator_id, note, catalog_version, guide_version, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (sid, user_id, note, version, backup.guide_version(), existing["created_at"] if existing else ts, ts),
    )
    for pos, it in enumerate(items):
        con.execute("INSERT INTO gold_items(sentence_id, position, picto_id, keyword) VALUES (?,?,?,?)",
                    (sid, pos, it["picto_id"], it["keyword"]))
    con.commit()


def auto_accept(con, user_id: int) -> int:
    """Convierte en referencia dorada las frases con acuerdo total y cobertura completa."""
    seqs = metrics.load_sequences(con)
    golds = {r["sentence_id"] for r in con.execute("SELECT sentence_id FROM gold")}
    count = 0
    for s in con.execute("SELECT id, target_coverage FROM sentences"):
        entries = seqs.get(s["id"], {})
        if s["id"] in golds or len(entries) < s["target_coverage"]:
            continue
        if classify(entries, False) != "agree":
            continue
        first = next(iter(entries))
        ann = con.execute("SELECT id FROM annotations WHERE sentence_id=? AND user_id=?", (s["id"], first)).fetchone()
        items = [dict(i) for i in con.execute(
            "SELECT picto_id, keyword, token FROM annotation_items WHERE annotation_id=? ORDER BY position", (ann["id"],))]
        if not items:
            continue
        save_gold(con, s["id"], user_id, items, note="acuerdo total entre anotadores")
        count += 1
    return count


def dashboard(con) -> dict:
    status = {r["status"]: r["c"] for r in con.execute("SELECT status, COUNT(*) c FROM annotations GROUP BY status")}
    ov = overview(con, "all", limit=0)
    users = []
    for r in con.execute("""
        SELECT u.id, u.name, u.role, u.active,
          (SELECT COUNT(*) FROM assignments a WHERE a.user_id=u.id) assigned,
          (SELECT COUNT(*) FROM annotations a WHERE a.user_id=u.id AND a.status='done') done,
          (SELECT COUNT(*) FROM annotations a WHERE a.user_id=u.id AND a.status='doubtful') doubtful,
          (SELECT COUNT(*) FROM annotations a WHERE a.user_id=u.id AND a.status='skipped') skipped,
          (SELECT AVG(seconds) FROM annotations a WHERE a.user_id=u.id AND a.status IN ('done','doubtful')) avg_seconds,
          (SELECT AVG(accepted_unchanged) FROM annotations a
             WHERE a.user_id=u.id AND a.status='done' AND a.blind=0 AND a.from_suggestion=1) unchanged_rate
        FROM users u ORDER BY u.name"""):
        users.append(dict(r))

    seqs = metrics.load_sequences(con)
    flat = {sid: {u: e["ids"] for u, e in ents.items()} for sid, ents in seqs.items()}
    report = metrics.agreement_report(flat)
    names = {u["id"]: u["name"] for u in users}
    for u in users:
        u["mean_distance_to_others"] = report["user_distance"].get(u["id"])
    pairs = [{**p, "a": names.get(p["a"]), "b": names.get(p["b"])} for p in report["pairs"]]
    texts = {r["id"]: r["text"] for r in con.execute("SELECT id, text FROM sentences")}
    worst = [{**w, "text": texts.get(w["sentence_id"], "")} for w in report["worst_sentences"]]

    blind_ids = {r["id"] for r in con.execute("SELECT id FROM sentences WHERE blind=1")}
    rep_blind = metrics.agreement_report({s: v for s, v in flat.items() if s in blind_ids})["overall"]
    rep_open = metrics.agreement_report({s: v for s, v in flat.items() if s not in blind_ids})["overall"]
    bias = {"agreement_blind": rep_blind, "agreement_with_suggestions": rep_open, "by_mode": {}}
    for r in con.execute("""SELECT blind, COUNT(*) n, AVG(seconds) s,
            AVG(CASE WHEN from_suggestion=1 THEN accepted_unchanged END) u
            FROM annotations WHERE status='done' GROUP BY blind"""):
        bias["by_mode"]["blind" if r["blind"] else "with_suggestions"] = {
            "n": r["n"], "avg_seconds": r["s"], "accepted_unchanged_rate": r["u"]}

    return {
        "totals": {
            "sentences": con.execute("SELECT COUNT(*) FROM sentences").fetchone()[0],
            "assignments": con.execute("SELECT COUNT(*) FROM assignments").fetchone()[0],
            "annotations": status,
            "states": ov["counts"],
            "catalog": catalog.status(con),
            "guide_version": backup.guide_version(),
        },
        "users": users,
        "agreement": report["overall"],
        "pairs": pairs,
        "worst_sentences": worst,
        "bias": bias,
    }
