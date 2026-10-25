"""Importación de frases y reparto automático con solapamiento (PLAN 13.2 y 13.3)."""
import random
from collections import defaultdict

from . import db


def import_sentences(con, lines, batch: str = "", pilot: bool = False) -> dict:
    added = dup = 0
    for line in lines:
        text = " ".join((line or "").split())
        if not text:
            continue
        cur = con.execute(
            "INSERT OR IGNORE INTO sentences(text, batch, is_pilot, created_at) VALUES (?,?,?,?)",
            (text, batch, 1 if pilot else 0, db.now()),
        )
        if cur.rowcount:
            added += 1
        else:
            dup += 1
    con.commit()
    return {"added": added, "duplicates": dup}


def assign(con, coverage: int = 2, triple_fraction: float = 0.0, blind_fraction: float = 0.0,
           seed: int | None = None, batch: str | None = None, roles=("annotator",)) -> dict:
    """Reparte las frases sin asignar entre los anotadores activos.

    - Cada frase recibe `coverage` anotadores distintos (3 para una fracción `triple_fraction`).
    - Una fracción `blind_fraction` de las frases nuevas se marca como modo ciego.
    - Se equilibra la carga y se evita que siempre coincidan las mismas parejas.
    """
    if coverage < 1:
        raise ValueError("La cobertura mínima es 1.")
    rng = random.Random(seed)
    ph = ",".join("?" * len(roles))
    users = [r["id"] for r in con.execute(f"SELECT id FROM users WHERE active=1 AND role IN ({ph}) ORDER BY id", roles)]
    max_needed = 3 if triple_fraction > 0 else coverage
    if len(users) < max(coverage, max_needed):
        raise ValueError(f"Hacen falta al menos {max_needed} anotadores activos (hay {len(users)}).")

    load = {u: 0 for u in users}
    seqmax = {u: 0 for u in users}
    for r in con.execute("SELECT user_id, COUNT(*) c, MAX(seq) m FROM assignments GROUP BY user_id"):
        if r["user_id"] in load:
            load[r["user_id"]] = r["c"]
            seqmax[r["user_id"]] = r["m"] or 0
    pair = defaultdict(int)
    by_sentence = defaultdict(set)
    for r in con.execute("SELECT sentence_id, user_id FROM assignments"):
        by_sentence[r["sentence_id"]].add(r["user_id"])
    for us in by_sentence.values():
        ul = sorted(us)
        for i in range(len(ul)):
            for j in range(i + 1, len(ul)):
                pair[(ul[i], ul[j])] += 1

    q = "SELECT id, target_coverage FROM sentences"
    params: tuple = ()
    if batch is not None:
        q += " WHERE batch=?"
        params = (batch,)
    sents = list(con.execute(q, params))
    new = [s["id"] for s in sents if not by_sentence.get(s["id"])]
    rng.shuffle(new)
    n_triple = round(triple_fraction * len(new))
    n_blind = round(blind_fraction * len(new))
    triple_ids = set(new[:n_triple])
    blind_ids = set(rng.sample(new, n_blind)) if n_blind else set()
    for sid in new:
        con.execute(
            "UPDATE sentences SET target_coverage=?, blind=? WHERE id=?",
            (3 if sid in triple_ids else coverage, 1 if sid in blind_ids else 0, sid),
        )

    todo = []
    for r in con.execute(
        "SELECT s.id, s.target_coverage FROM sentences s" + (" WHERE s.batch=?" if batch is not None else ""), params
    ):
        have = len(by_sentence.get(r["id"], ()))
        if have < r["target_coverage"]:
            todo.append((r["id"], r["target_coverage"] - have))
    rng.shuffle(todo)

    created = 0
    for sid, needed in todo:
        others = set(by_sentence.get(sid, ()))
        chosen: list[int] = []
        for _ in range(needed):
            pool = [u for u in users if u not in others]
            if not pool:
                break
            low = min(load[u] for u in pool)
            cands = [u for u in pool if load[u] <= low + 2]
            cands.sort(key=lambda u: (
                sum(pair[tuple(sorted((u, o)))] for o in others),
                load[u],
                rng.random(),
            ))
            u = cands[0]
            for o in others:
                pair[tuple(sorted((u, o)))] += 1
            others.add(u)
            chosen.append(u)
            load[u] += 1
        for u in chosen:
            seqmax[u] += 1
            con.execute("INSERT INTO assignments(sentence_id, user_id, seq) VALUES (?,?,?)", (sid, u, seqmax[u]))
            created += 1
        by_sentence[sid] = others
    con.commit()
    return {
        "sentences_assigned": len(todo),
        "assignments_created": created,
        "triple": len(triple_ids),
        "blind": len(blind_ids),
        "load": load,
    }
