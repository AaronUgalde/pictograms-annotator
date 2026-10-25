from app import suggest


def keywords(con, text, **kw):
    a = suggest.analyze_sentence(con, text, **kw)
    return [s["keyword"] for s in a["sequence"]], a


def test_multiword_before_single(con):
    kws, _ = keywords(con, "Tener hambre y beber agua")
    assert kws == ["tener hambre", "beber", "agua"]


def test_function_words_skipped_and_plurals(con):
    kws, a = keywords(con, "Un vaso de manzanas")
    assert kws == ["vaso", "manzana"]
    assert [t["skip"] for t in a["tokens"]] == [True, False, True, False]


def test_pos_type_preference(con):
    # "helado" como adjetivo (tipo 4) frente a nombre; sin POS (simple) gana el rank de la palabra clave
    kws, a = keywords(con, "helado")
    assert a["segments"][0]["candidates"][0]["id"] in (6, 7)


def test_flagged_pictogram_ranked_last(con):
    _, a = keywords(con, "comer")
    ids = [c["id"] for c in a["segments"][0]["candidates"]]
    assert ids == [9, 10]


def test_blind_mode_has_no_proposal(con):
    a = suggest.analyze_sentence(con, "beber agua", blind=True)
    assert a["sequence"] == [] and a["segments"] == [] and a["tokens"]


def test_personal_memory_wins(con):
    con.execute("INSERT INTO users(id,email,token,role,created_at) VALUES (1,'a','t1','annotator','x')")
    con.execute("INSERT INTO choice_memory VALUES ('helado',6,1,3,'x')")
    con.commit()
    a = suggest.analyze_sentence(con, "helado", user_id=1)
    assert a["sequence"][0]["picto_id"] == 6
    other = suggest.analyze_sentence(con, "helado", user_id=2)
    assert other["sequence"][0]["picto_id"] == 7  # otra persona no hereda la memoria



def test_exact_accent_beats_accentless_homograph(con):
    """«papá» (padre) y «papa» (patata) comparten clave sin tildes; con tilde en la frase gana el padre."""
    from app import catalog
    from tests.conftest import FAKE, P

    extra = [
        P(20, [{"keyword": "papá", "type": 2}], downloads=1),
        P(21, [{"keyword": "papa", "type": 2}], downloads=999),  # más popular: ganaba antes del arreglo
    ]
    catalog.ingest(FAKE + extra, "test-v2")
    try:
        kws, _ = keywords(con, "papá")
        assert kws == ["papá"]
        kws, _ = keywords(con, "papa")
        assert kws == ["papa"]
    finally:
        catalog.ingest(FAKE, "test-v1")  # deja el catálogo de prueba como estaba
