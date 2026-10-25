from app import metrics as m


def test_levenshtein_and_distance():
    assert m.levenshtein([1, 2, 3], [1, 2, 3]) == 0
    assert m.levenshtein([1, 2, 3], [1, 3]) == 1
    assert m.levenshtein([], [1, 2]) == 2
    assert m.norm_distance([1, 2, 3, 4], [1, 2, 9, 4]) == 0.25
    assert m.norm_distance([], []) == 0.0


def test_positional_jaccard_exact():
    assert m.positional([1, 2, 3], [1, 9, 3]) == 2 / 3
    assert m.jaccard([1, 2], [2, 1]) == 1.0
    assert m.pair_metrics([1, 2], [2, 1])["exact"] == 0.0


def test_sentence_metrics_needs_two():
    assert m.sentence_metrics({1: [1, 2]}) is None
    r = m.sentence_metrics({1: [1, 2], 2: [1, 2], 3: [1, 9]})
    assert r["n"] == 3 and len(r["pairs"]) == 3
    assert abs(r["exact"] - 1 / 3) < 1e-9


def test_agreement_report_flags_outlier():
    data = {s: {1: [1, 2], 2: [1, 2], 3: [7, 8]} for s in range(5)}
    rep = m.agreement_report(data)
    assert rep["user_distance"][3] > rep["user_distance"][1]
    assert rep["overall"]["sentences"] == 5
