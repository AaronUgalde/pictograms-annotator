"""Medidas de acuerdo entre anotadores (PLAN 13.2).

Todas operan sobre secuencias de IDs de pictograma:
- exact: 1 si las secuencias son idénticas.
- distance: distancia de edición de Levenshtein dividida por la longitud de la más larga (0 = igual).
- positional: fracción de posiciones con el mismo ID (sobre la longitud de la más larga).
- jaccard: solape de conjuntos de IDs, sin tener en cuenta el orden.
"""
from itertools import combinations
from statistics import mean


def levenshtein(a: list, b: list) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def norm_distance(a: list, b: list) -> float:
    m = max(len(a), len(b))
    return 0.0 if m == 0 else levenshtein(a, b) / m


def positional(a: list, b: list) -> float:
    m = max(len(a), len(b))
    return 1.0 if m == 0 else sum(x == y for x, y in zip(a, b)) / m


def jaccard(a: list, b: list) -> float:
    sa, sb = set(a), set(b)
    return 1.0 if not sa and not sb else len(sa & sb) / len(sa | sb)


def pair_metrics(a: list, b: list) -> dict:
    return {
        "exact": 1.0 if a == b else 0.0,
        "distance": norm_distance(a, b),
        "positional": positional(a, b),
        "jaccard": jaccard(a, b),
    }


def sentence_metrics(seqs: dict) -> dict | None:
    """seqs: {user_id: [ids]}. Media sobre todas las parejas; None si hay menos de dos anotadores."""
    if len(seqs) < 2:
        return None
    pairs = []
    for (ua, a), (ub, b) in combinations(sorted(seqs.items()), 2):
        pairs.append({"a": ua, "b": ub, **pair_metrics(a, b)})
    return {
        "n": len(seqs),
        "exact": mean(p["exact"] for p in pairs),
        "distance": mean(p["distance"] for p in pairs),
        "positional": mean(p["positional"] for p in pairs),
        "jaccard": mean(p["jaccard"] for p in pairs),
        "pairs": pairs,
    }


def load_sequences(con, statuses=("done", "doubtful")) -> dict:
    """{sentence_id: {user_id: {'status': s, 'ids': [...]}}}"""
    ph = ",".join("?" * len(statuses))
    anns = {}
    for r in con.execute(f"SELECT id, sentence_id, user_id, status FROM annotations WHERE status IN ({ph})", statuses):
        anns[r["id"]] = r
    items: dict = {}
    for r in con.execute("SELECT annotation_id, picto_id FROM annotation_items ORDER BY annotation_id, position"):
        items.setdefault(r["annotation_id"], []).append(r["picto_id"])
    out: dict = {}
    for aid, r in anns.items():
        out.setdefault(r["sentence_id"], {})[r["user_id"]] = {"status": r["status"], "ids": items.get(aid, [])}
    return out


def agreement_report(sent_seqs: dict, top_pairs: int = 30, top_sentences: int = 20) -> dict:
    """sent_seqs: {sentence_id: {user_id: [ids]}}"""
    pair_acc: dict = {}
    per_user: dict = {}
    per_sentence = []
    for sid, seqs in sent_seqs.items():
        m = sentence_metrics(seqs)
        if not m:
            continue
        per_sentence.append({"sentence_id": sid, "n": m["n"], "distance": m["distance"], "exact": m["exact"]})
        for p in m["pairs"]:
            key = (p["a"], p["b"])
            acc = pair_acc.setdefault(key, {"n": 0, "exact": 0.0, "distance": 0.0, "positional": 0.0, "jaccard": 0.0})
            acc["n"] += 1
            for k in ("exact", "distance", "positional", "jaccard"):
                acc[k] += p[k]
            for u in key:
                ua = per_user.setdefault(u, {"n": 0, "distance": 0.0})
                ua["n"] += 1
                ua["distance"] += p["distance"]
    pairs = []
    for (a, b), acc in pair_acc.items():
        n = acc["n"]
        pairs.append({"a": a, "b": b, "n": n, **{k: acc[k] / n for k in ("exact", "distance", "positional", "jaccard")}})
    pairs.sort(key=lambda p: -p["distance"])
    per_sentence.sort(key=lambda s: -s["distance"])
    overall = None
    if per_sentence:
        total = sum(p["n"] for p in pairs)
        overall = {
            "pairs_evaluated": total,
            "sentences": len(per_sentence),
            **{k: sum(p[k] * p["n"] for p in pairs) / total for k in ("exact", "distance", "positional", "jaccard")},
        }
    users = {u: v["distance"] / v["n"] for u, v in per_user.items()}
    return {"overall": overall, "pairs": pairs[:top_pairs], "worst_sentences": per_sentence[:top_sentences],
            "user_distance": users}
