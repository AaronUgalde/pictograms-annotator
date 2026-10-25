from collections import Counter

from app import assign, db


def student(con, n):
    uid = con.execute("INSERT INTO users(email,token,role,created_at) VALUES (?,?,?,?) RETURNING id",
                      (f"s{n}@x.com", f"tok{n}", "annotator", "x")).fetchone()["id"]
    con.commit()
    return uid


def counts(con):
    return Counter(r["sentence_id"] for r in con.execute("SELECT sentence_id FROM assignments"))


def test_each_student_gets_n_distinct_sentences(con):
    assign.import_sentences(con, [f"frase {i}" for i in range(40)])
    for n in range(4):
        uid = student(con, n)
        assert assign.ensure_assignments(con, uid, 15) == 15
        rows = con.execute("SELECT sentence_id FROM assignments WHERE user_id=?", (uid,)).fetchall()
        assert len({r["sentence_id"] for r in rows}) == 15


def test_least_covered_sentences_first(con):
    assign.import_sentences(con, [f"frase {i}" for i in range(30)])
    # 3 alumnos x 10 = 30 asignaciones: cada oración debe quedar con exactamente 1
    for n in range(3):
        assign.ensure_assignments(con, student(con, n), 10)
    assert set(counts(con).values()) == {1} and len(counts(con)) == 30
    # un 4.º alumno completa una segunda vuelta; nadie queda con 3 mientras haya oraciones con 1
    assign.ensure_assignments(con, student(con, 3), 10)
    assert max(counts(con).values()) == 2
    # nuevas oraciones (0 anotadores) tienen prioridad sobre las que ya tienen alguno
    assign.import_sentences(con, [f"nueva {i}" for i in range(5)])
    uid = student(con, 4)
    assign.ensure_assignments(con, uid, 5)
    got = {r["text"] for r in con.execute(
        "SELECT s.text FROM assignments a JOIN sentences s ON s.id=a.sentence_id WHERE a.user_id=?", (uid,))}
    assert got == {f"nueva {i}" for i in range(5)}


def test_top_up_when_more_sentences_or_bigger_n(con):
    uid = student(con, 0)
    assign.import_sentences(con, ["a", "b", "c"])
    assert assign.ensure_assignments(con, uid, 15) == 3          # solo había 3
    assert assign.ensure_assignments(con, uid, 15) == 0          # idempotente
    assign.import_sentences(con, [f"x{i}" for i in range(20)])
    assert assign.ensure_assignments(con, uid, 15) == 12         # completa hasta 15
    assert assign.ensure_assignments(con, uid, 18) == 3          # el admin subió N
    seqs = [r["seq"] for r in con.execute("SELECT seq FROM assignments WHERE user_id=? ORDER BY seq", (uid,))]
    assert seqs == list(range(1, 19))


def test_default_setting_and_change(con):
    assert assign.per_student(con) == 15
    db.set_setting(con, "sentences_per_student", 7)
    assert assign.per_student(con) == 7


def test_import_dedupes_and_delete_unannotated(con):
    assert assign.import_sentences(con, ["hola", " hola ", "adiós", ""]) == {"added": 2, "duplicates": 1}
    uid = student(con, 0)
    assign.ensure_assignments(con, uid, 5)
    sid = con.execute("SELECT id FROM sentences WHERE text='hola'").fetchone()[0]
    con.execute("INSERT INTO annotations(sentence_id,user_id,status,catalog_version,guide_version,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?)", (sid, uid, "done", "v", "v", "x", "x"))
    con.commit()
    assert assign.delete_unannotated(con) == 1
    assert [r["text"] for r in con.execute("SELECT text FROM sentences")] == ["hola"]
    assert con.execute("SELECT COUNT(*) FROM assignments").fetchone()[0] == 1
