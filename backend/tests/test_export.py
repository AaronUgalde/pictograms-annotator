import csv
import io
import json

from app import export


def test_export_contains_every_annotation(con):
    con.execute("INSERT INTO users(id,email,token,role,created_at) VALUES (1,'a@x.com','t1','annotator','x'),(2,'b@x.com','t2','annotator','x')")
    con.execute("INSERT INTO sentences(id,text,created_at) VALUES (1,'agua','x'),(2,'beber','x')")
    for uid, pid in ((1, 1), (2, 2)):
        aid = con.execute("INSERT INTO annotations(sentence_id,user_id,status,catalog_version,guide_version,created_at,updated_at)"
                          " VALUES (1,?,?,?,?,?,?) RETURNING id", (uid, "done", "v1", "v0", "x", "x")).fetchone()["id"]
        con.execute("INSERT INTO annotation_items VALUES (?,?,?,?,?)", (aid, 0, pid, "kw", None))
    con.commit()
    rows = [json.loads(l) for l in export.to_jsonl(con).splitlines()]
    assert [len(r["annotations"]) for r in rows] == [2, 0]
    assert {a["email"] for a in rows[0]["annotations"]} == {"a@x.com", "b@x.com"}
    parsed = list(csv.DictReader(io.StringIO(export.to_csv(con))))
    assert len(parsed) == 2 and parsed[0]["catalog_version"] == "v1" and parsed[0]["ids"] in ("1", "2")
