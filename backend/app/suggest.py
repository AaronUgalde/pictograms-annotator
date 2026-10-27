"""Sugerencias automáticas por capas (sección 7 del plan).

Capas implementadas: (1) lematización con spaCy, (2) coincidencia contra el catálogo local con
preferencia por expresiones de varias palabras, (3) memoria de decisiones personal, (4) pictogramas
relacionados por significado (related.py). Los relacionados van en una lista aparte: la propuesta
inicial solo usa coincidencias.
Deliberadamente NO hay modelo generativo (ver PLAN 13.2) y la memoria de equipo está desactivada
por defecto porque hace converger a los anotadores y rompe la independencia de las referencias.
"""
import re

from . import catalog, nlp, related
from .catalog import norm

# Las palabras con estas categorías gramaticales no se buscan solas (artículos, preposiciones…).
STOP_POS = {"DET", "ADP", "CCONJ", "SCONJ", "PUNCT", "SPACE", "AUX", "PART", "SYM"}
MAX_N = 5
MAX_CANDIDATES = 12
MAX_RELATED = 8
# Tipo de palabra clave de ARASAAC: 1 nombre propio, 2 nombre común, 3 verbo, 4 descriptivo,
# 5 contenido social, 6 miscelánea.
POS_TYPES = {"VERB": {3}, "NOUN": {1, 2}, "PROPN": {1, 2}, "ADJ": {4}}


_CLITIC = re.compile(r"^(\w{2,}?(?:ar|er|ir|ár|ér|ír))(?:me|te|se|nos|os|lo|la|le|los|las|les)+$")
_ACCENT_INF = {"ár": "ar", "ér": "er", "ír": "ir"}
_PRON_LEMMAS = {"yo", "tú", "él", "ella", "nosotros", "vosotros", "ellos", "ellas", "usted", "ustedes", "se", "uno"}
_ANY_CLITIC = re.compile(r"^(\w{3,}?)(?:me|te|se|nos|os|lo|la|le|los|las|les)+$")


def _verb_variants(t) -> list[str]:
    """Último recurso para imperativos con enclítico («ayúdame» → «ayudar»)."""
    if t.pos not in ("VERB", "AUX", "X"):
        return []
    m = _ANY_CLITIC.match(t.text.lower())
    if not m:
        return []
    stem = norm(m.group(1))
    out = []
    if stem.endswith(("ar", "er", "ir")):
        out.append(stem)
    if stem.endswith("a"):
        out.append(stem[:-1] + "ar")
    if stem.endswith("e"):
        out += [stem[:-1] + "er", stem[:-1] + "ir", stem[:-1] + "ar"]
    return out


# Terminaciones verbales comunes (sin tildes, de más larga a más corta).
_VERB_ENDINGS = sorted({
    "aremos", "eremos", "iremos", "abamos", "iamos", "ieron", "aron", "aban", "ando", "iendo", "amos", "emos",
    "imos", "aste", "iste", "aria", "eria", "iria", "aba", "ado", "ido", "ara", "era", "ira", "ian", "io", "ia",
    "an", "en", "as", "es", "a", "e", "o", "i",
}, key=len, reverse=True)


def _conjugation_guesses(word: str) -> list[str]:
    """Infinitivos posibles de una forma conjugada que el analizador no reconoció
    («pintan» → pintar/pinter/pintir, «ayúdame» → ayudar…). Solo se aceptan si son verbos del catálogo."""
    w = norm(word)
    if len(w) < 4 or " " in w:
        return []
    forms = [w]
    m = _ANY_CLITIC.match(w)
    if m:
        forms.append(m.group(1))
    out: list[str] = []
    for f in forms:
        if f.endswith(("ar", "er", "ir")):
            out.append(f)
        for end in _VERB_ENDINGS:
            if f.endswith(end) and len(f) - len(end) >= 2:
                stem = f[: -len(end)]
                out += [stem + "ar", stem + "er", stem + "ir"]
    seen: set = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _lemma(t) -> str:
    """Lema con los pronombres enclíticos quitados: «lavarme» → «lavar», «ponérselo» → «poner»."""
    lemma = t.lemma
    parts = lemma.split()
    # spaCy lematiza «lavarme» como «lavar yo»: nos quedamos con el verbo.
    if t.pos in ("VERB", "AUX") and len(parts) == 2 and parts[1] in _PRON_LEMMAS:
        lemma = parts[0]
    if t.pos in ("VERB", "AUX", "X"):
        m = _CLITIC.match(lemma)
        if m:
            inf = m.group(1)
            return inf[:-2] + _ACCENT_INF[inf[-2:]] if inf[-2:] in _ACCENT_INF else inf
    return lemma


def _deplural(key: str):
    if key.endswith("es") and len(key) > 3:
        yield key[:-2]
    if key.endswith("s") and len(key) > 2:
        yield key[:-1]


def _is_stop(t) -> bool:
    if t.pos not in STOP_POS:
        return False
    # spaCy etiqueta como AUX imperativos con enclítico («ayúdame»): no son palabras vacías.
    return not (t.pos == "AUX" and len(t.text) > 4 and _ANY_CLITIC.match(t.text.lower()))


def _window_keys(window, single: bool) -> list[str]:
    lemma = norm(" ".join(_lemma(t) for t in window))
    surface = norm(" ".join(t.text for t in window))
    keys = [lemma, surface]
    if not single:  # verbo en infinitivo + resto tal cual: «lavarme las manos» → «lavar las manos»
        keys.append(norm(" ".join(_lemma(t) if t.pos in ("VERB", "AUX") else t.text for t in window)))
    if single:
        for base in (surface, lemma):
            keys.extend(_deplural(base))
        keys.extend(_verb_variants(window[0]))
    seen, out = set(), []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _memory(con, keys, user_id, team: bool) -> tuple[dict, dict]:
    """(personal, equipo): {lemma: {picto_id: veces}}."""
    keys = [k for k in set(keys) if k]
    personal: dict = {}
    teamm: dict = {}
    if not keys:
        return personal, teamm
    ph = ",".join("?" * len(keys))
    if user_id is not None:
        for r in con.execute(
            f"SELECT lemma, picto_id, count FROM choice_memory WHERE lemma IN ({ph}) AND user_id=? AND count>0",
            (*keys, user_id),
        ):
            personal.setdefault(r["lemma"], {})[r["picto_id"]] = r["count"]
    if team:
        for r in con.execute(
            f"SELECT lemma, picto_id, SUM(count) c FROM choice_memory WHERE lemma IN ({ph}) GROUP BY lemma, picto_id HAVING c>0",
            keys,
        ):
            teamm.setdefault(r["lemma"], {})[r["picto_id"]] = r["c"]
    return personal, teamm


def _rank(cands: list[dict], pos: str | None, mem_user: dict, mem_team: dict, idx, forms: frozenset = frozenset()) -> list[dict]:
    """`forms`: formas del texto (superficie y lema, en minúsculas y CON tildes). La clave de búsqueda
    no lleva tildes, así que «papá» y «papa» (patata) empatan; la coincidencia exacta desempata."""
    wanted = POS_TYPES.get(pos or "")
    have = {c["id"] for c in cands}
    cands = list(cands)
    for pid in mem_user:  # lo que la persona eligió antes entra aunque no sea coincidencia exacta
        if pid not in have and pid in idx.pictos:
            cands.append({"id": pid, "keyword": idx.pictos[pid]["main"], "rank": 0, "kind": "kw", "type": None})

    def score(c):
        p = idx.pictos[c["id"]]
        type_ok = 0 if (wanted is None or c["type"] is None or c["type"] in wanted) else 1
        return (
            -mem_user.get(c["id"], 0),
            -mem_team.get(c["id"], 0),
            0 if c["keyword"].lower() in forms else 1,
            type_ok,
            c["rank"],
            1 if p["flags"] else 0,
            -p["popularity"],
            c["id"],
        )

    return sorted(cands, key=score)


def _confidence(ranked, mem_user, length) -> str:
    top_mem = mem_user.get(ranked[0]["id"], 0)
    if top_mem >= 2 or len(ranked) == 1:
        return "high"
    if top_mem == 1 or len(ranked) <= 3 or length > 1:
        return "medium"
    return "low"


def _related(idx, text: str, exclude) -> list[dict]:
    """Relacionados por significado con el mismo formato que los candidatos, más la similitud."""
    return [{"id": r["id"], "keyword": r["keyword"], "main": idx.pictos[r["id"]]["main"], "score": r["score"]}
            for r in related.related(text, exclude, MAX_RELATED)]


def analyze_sentence(con, text: str, user_id=None, team_memory: bool = False, blind: bool = False) -> dict:
    idx = catalog.get_index()
    toks = nlp.analyze(text)
    tokens = [
        {
            "text": t.text,
            "lemma": t.lemma,
            "pos": t.pos,
            "key": norm(_lemma(t)) or norm(t.text),
            "skip": _is_stop(t),
            "segment": None,
        }
        for t in toks
    ]

    raw_segments = []
    if not blind:
        i, n = 0, len(toks)
        while i < n:
            found = None
            for length in range(min(MAX_N, n - i), 0, -1):
                window = toks[i : i + length]
                if any(t.pos in ("PUNCT", "SPACE") for t in window):
                    continue
                if length == 1 and _is_stop(window[0]):
                    continue
                for key in _window_keys(window, single=length == 1):
                    cands = idx.lookup(key)
                    if cands:
                        found = (i, length, window, key, cands)
                        break
                if not found and length == 1:
                    # Último recurso: un verbo conjugado que el analizador no supo lematizar.
                    for key in _conjugation_guesses(window[0].text):
                        cands = [c for c in idx.lookup(key) if c["type"] == 3]
                        if cands:
                            found = (i, length, window, key, cands)
                            break
                if found:
                    break
            if found:
                raw_segments.append(found)
                i += found[1]
            else:
                i += 1

    seg_keys = [norm(" ".join(_lemma(t) for t in w)) for (_i, _l, w, _k, _c) in raw_segments]
    mem_user, mem_team = _memory(con, seg_keys + [t["key"] for t in tokens], user_id, team_memory)

    segments, sequence = [], []
    for si, ((start, length, window, match_key, cands), mkey) in enumerate(zip(raw_segments, seg_keys)):
        pos = window[0].pos if length == 1 else None
        forms = frozenset({" ".join(t.text for t in window).lower(), " ".join(_lemma(t) for t in window).lower()})
        ranked = _rank(cands, pos, mem_user.get(mkey, {}), mem_team.get(mkey, {}), idx, forms)
        out_c = []
        for c in ranked[:MAX_CANDIDATES]:
            main = idx.pictos[c["id"]]["main"]
            out_c.append({"id": c["id"], "keyword": c["keyword"] if c["kind"] == "kw" else main, "main": main})
        seg = {
            "index": si,
            "start": start,
            "end": start + length,
            "text": " ".join(t.text for t in window),
            "key": mkey,
            "match_key": match_key,
            "candidates": out_c,
            "related": _related(idx, " ".join(_lemma(t) for t in window), {c["id"] for c in ranked}),
            "confidence": _confidence(ranked, mem_user.get(mkey, {}), length),
        }
        segments.append(seg)
        for k in range(start, start + length):
            tokens[k]["segment"] = si
        sequence.append({"picto_id": out_c[0]["id"], "keyword": out_c[0]["keyword"], "token": mkey, "segment": si})

    if not blind:  # palabras sin coincidencia: solo relacionados (nunca entran en la propuesta)
        for t, tok in zip(toks, tokens):
            if tok["segment"] is None and not tok["skip"] and tok["pos"] not in ("PUNCT", "SPACE"):
                tok["related"] = _related(idx, _lemma(t), ())

    memory = {}
    for key, d in mem_user.items():
        memory[key] = [{"id": pid, "count": c} for pid, c in sorted(d.items(), key=lambda kv: -kv[1])]

    return {"tokens": tokens, "segments": segments, "sequence": sequence, "memory": memory,
            "engine": nlp.backend(), "blind": blind}
