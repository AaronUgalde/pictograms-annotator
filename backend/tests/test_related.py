import numpy as np
import pytest

from app import config, related, suggest

# Vectores de juguete: dimensión 0 = «bebidas», 1 = «frío», 2 = «comida».
WORDS = {
    "agua": [1, 0, 0], "vaso": [0.9, 0, 0.1], "beber": [1, 0, 0.1], "sed": [1, 0.1, 0],
    "frío": [0, 1, 0], "helado": [0.1, 1, 0.3], "manzana": [0, 0, 1], "comer": [0, 0, 1], "hambre": [0, 0.1, 1],
    "tener": [0.3, 0.3, 0.3],
}


@pytest.fixture()
def fake_model(tmp_path, monkeypatch):
    (tmp_path / "words.txt").write_text("\n".join(WORDS) + "\n", encoding="utf-8")
    np.save(tmp_path / "vectors.npy", np.array(list(WORDS.values()), dtype=np.float16))
    monkeypatch.setattr(config, "RELATED_DIR", tmp_path)
    related.reset()
    yield
    related.reset()


def ids(text, **kw):
    return [r["id"] for r in related.related(text, **kw)]


def test_without_vectors_everything_is_empty(con):
    related.reset()
    assert related.related("agua") == []
    a = suggest.analyze_sentence(con, "beber agua")
    assert all(s["related"] == [] for s in a["segments"])


def test_similar_meaning_ranked_and_lexical_matches_excluded(fake_model):
    # «sed» no está en el catálogo de prueba: sale lo más parecido (bebidas) y nunca la comida
    got = ids("sed")
    assert got[:3] == [1, 3, 2]  # agua, beber, vaso
    assert 5 not in got and 9 not in got
    # el propio «agua» (pictograma 1) comparte palabra con la consulta: es coincidencia, no relacionado
    assert 1 not in ids("agua")


def test_unknown_words_and_stopwords_give_nothing(fake_model):
    assert related.related("zzz") == []
    assert related.related("de la") == []


def test_accentless_query_uses_catalog_spelling(fake_model):
    # «frio» no está en la tabla; se usa «frío», que sí aparece en el catálogo
    assert ids("frio")[0] == 7  # helado (nombre); el 6 contiene «frío» y queda fuera por ser coincidencia


def test_suggestions_keep_related_apart_from_the_proposal(con, fake_model):
    a = suggest.analyze_sentence(con, "beber agua")
    beber, agua = a["segments"]
    assert [c["id"] for c in agua["candidates"]] == [1]
    assert agua["related"] and all(r["id"] != 1 for r in agua["related"])
    assert {r["id"] for r in beber["related"]}.isdisjoint(c["id"] for c in beber["candidates"])
    assert [s["picto_id"] for s in a["sequence"]] == [3, 1]  # la propuesta solo usa coincidencias


def test_word_without_match_gets_only_related(con, fake_model):
    a = suggest.analyze_sentence(con, "sed")
    assert a["segments"] == [] and a["sequence"] == []
    assert a["tokens"][0]["related"][0]["id"] == 1


def test_blind_mode_has_no_related(con, fake_model):
    a = suggest.analyze_sentence(con, "sed", blind=True)
    assert "related" not in a["tokens"][0]
