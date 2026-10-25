from collections import Counter

from app import assign, db


def make_users(con, n):
    for i in range(n):
        con.execute("INSERT INTO users(name,token,role,created_at) VALUES (?,?,?,?)",
                    (f"u{i}", f"tok{i}", "annotator", "x"))
    con.commit()


def test_overlap_distinct_and_balanced(con):
    make_users(con, 10)
    assign.import_sentences(con, [f"frase {i}" for i in range(100)])
    res = assign.assign(con, coverage=2, triple_fraction=0.1, blind_fraction=0.2, seed=1)
    per_sentence = Counter(r["sentence_id"] for r in con.execute("SELECT sentence_id FROM assignments"))
    assert set(per_sentence.values()) == {2, 3}
    assert sum(1 for v in per_sentence.values() if v == 3) == 10
    pairs = con.execute("SELECT COUNT(*) FROM (SELECT sentence_id, user_id FROM assignments GROUP BY sentence_id, user_id HAVING COUNT(*)>1)").fetchone()[0]
    assert pairs == 0
    loads = res["load"].values()
    assert max(loads) - min(loads) <= 3
    assert con.execute("SELECT COUNT(*) FROM sentences WHERE blind=1").fetchone()[0] == 20


def test_assign_is_idempotent_and_tops_up(con):
    make_users(con, 4)
    assign.import_sentences(con, ["a", "b", "c"])
    assign.assign(con, coverage=2, seed=2)
    n = con.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
    assign.assign(con, coverage=2, seed=2)
    assert con.execute("SELECT COUNT(*) FROM assignments").fetchone()[0] == n
    assign.import_sentences(con, ["d"])
    assign.assign(con, coverage=2, seed=2)
    assert con.execute("SELECT COUNT(*) FROM assignments").fetchone()[0] == n + 2


def test_not_enough_annotators(con):
    make_users(con, 1)
    assign.import_sentences(con, ["x"])
    try:
        assign.assign(con, coverage=2)
        assert False
    except ValueError:
        pass
