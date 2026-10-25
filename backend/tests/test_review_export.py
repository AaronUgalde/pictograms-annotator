import json

from app import backup, export, review


def _user(con, uid, name, role="annotator"):
    con.execute("INSERT INTO users(id,name,token,role,created_at) VALUES (?,?,?,?,?)", (uid, name, f"t{uid}", role, "x"))


def _annotate(con, sid, uid, ids, status="done"):
    cur = con.execute(
        "INSERT INTO annotations(sentence_id,user_id,status,catalog_version,guide_version,created_at,updated_at)"
        " VALUES (?,?,?,?,?,?,?)", (sid, uid, status, "test-v1", "v0", "x", "x"))
    for pos, pid in enumerate(ids):
        con.execute("INSERT INTO annotation_items VALUES (?,?,?,?,?)", (cur.lastrowid, pos, pid, "", None))


def _setup(con):
    for i, n in ((1, "a"), (2, "b"), (3, "rev")):
        _user(con, i, n, "reviewer" if n == "rev" else "annotator")
    con.execute("INSERT INTO sentences(id,text,batch,target_coverage,created_at) VALUES (1,'agua','',2,'x'),(2,'beber','',2,'x')")
    con.commit()


def test_auto_accept_only_full_agreement(con):
    _setup(con)
    _annotate(con, 1, 1, [1]); _annotate(con, 1, 2, [1])      # acuerdo total
    _annotate(con, 2, 1, [3]); _annotate(con, 2, 2, [9])      # desacuerdo
    con.commit()
    assert review.auto_accept(con, 3) == 1
    assert [r["sentence_id"] for r in con.execute("SELECT sentence_id FROM gold")] == [1]
    assert review.auto_accept(con, 3) == 0  # idempotente


def test_doubtful_blocks_auto_accept(con):
    _setup(con)
    _annotate(con, 1, 1, [1]); _annotate(con, 1, 2, [1], status="doubtful")
    con.commit()
    assert review.auto_accept(con, 3) == 0
    assert review.overview(con, "needs")["total"] == 1


def test_export_includes_gold_and_all_annotations(con):
    _setup(con)
    _annotate(con, 1, 1, [1]); _annotate(con, 1, 2, [2])
    con.commit()
    review.save_gold(con, 1, 3, [{"picto_id": 1, "keyword": "agua"}])
    rows = [json.loads(l) for l in export.to_jsonl(con).splitlines()]
    s1 = next(r for r in rows if r["sentence_id"] == 1)
    assert len(s1["annotations"]) == 2 and s1["gold"]["ids"] == [1] and s1["gold"]["adjudicator"] == "rev"
    assert next(r for r in rows if r["sentence_id"] == 2)["gold"] is None
    csv_text = export.to_csv(con)
    assert csv_text.count("\r\n") == 4 and ",gold," in csv_text  # cabecera + 2 anotaciones + 1 dorada


def test_gold_rejects_unknown_picto_and_empty(con):
    _setup(con)
    for bad in ([], [{"picto_id": 99999}]):
        try:
            review.save_gold(con, 1, 3, bad)
        except review.BadItems:
            continue
        raise AssertionError("debía rechazar " + repr(bad))


def test_backup_creates_db_and_jsonl_and_prunes(con, monkeypatch):
    _setup(con)
    monkeypatch.setattr("app.config.BACKUP_KEEP", 2)
    for _ in range(3):
        path = backup.run_backup()
    from app import config
    assert len(list(config.BACKUP_DIR.glob("annotator-*.db"))) <= 2
    assert len(list(config.BACKUP_DIR.glob("export-*.jsonl"))) <= 2
    assert path.endswith(".db")


def test_guide_version_is_read_from_guide():
    assert backup.guide_version() != "sin-guia"
