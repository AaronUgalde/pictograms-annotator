import pytest
from fastapi.testclient import TestClient

from app import assign, db
from app.main import app


@pytest.fixture()
def client(con):
    with TestClient(app) as c:
        yield c


def mkuser(con, name, role="annotator"):
    token = f"tok-{name}"
    con.execute("INSERT INTO users(name,token,role,created_at) VALUES (?,?,?,?)", (name, token, role, "x"))
    con.commit()
    return {"X-Token": token}


def test_auth_required(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"X-Token": "nope"}).status_code == 401


def test_full_flow(con, client):
    admin = mkuser(con, "admin", "admin")
    rev = mkuser(con, "rev", "reviewer")
    a, b = mkuser(con, "a"), mkuser(con, "b")
    assert client.get("/api/admin/dashboard", headers=a).status_code == 403

    r = client.post("/api/admin/sentences", headers=admin, json={"lines": ["Tener hambre y beber agua", "agua"]})
    assert r.json()["added"] == 2
    r = client.post("/api/admin/assign", headers=admin, json={"coverage": 2, "seed": 1})
    assert r.status_code == 200 and r.json()["assignments_created"] == 4

    q = client.get("/api/my/queue", headers=a).json()["items"]
    sid = q[0]["id"]
    d = client.get(f"/api/annotate/{sid}", headers=a).json()
    assert d["analysis"]["engine"] == "simple" and d["sentence"]["total"] == 2
    assert client.get("/api/catalog", headers=a).json()["version"] == "test-v1"

    items = [{"picto_id": x["picto_id"], "keyword": x["keyword"], "token": x["token"]} for x in d["analysis"]["sequence"]]
    r = client.put(f"/api/annotations/{sid}", headers=a, json={"status": "done", "items": items, "seconds": 5})
    assert r.status_code == 200
    mine = con.execute("SELECT * FROM annotations").fetchone()
    assert mine["from_suggestion"] == 1 and mine["accepted_unchanged"] == 1 and mine["blind"] == 0
    assert client.put(f"/api/annotations/{sid}", headers=a, json={"status": "done", "items": []}).status_code == 422
    assert client.put(f"/api/annotations/{sid}", headers=a,
                      json={"status": "done", "items": [{"picto_id": 99999}]}).status_code == 422

    # re-guardar no duplica la memoria
    client.put(f"/api/annotations/{sid}", headers=a, json={"status": "done", "items": items})
    assert con.execute("SELECT MAX(count) FROM choice_memory").fetchone()[0] == 1

    # segunda persona anota distinto -> necesita adjudicación
    d2 = client.get(f"/api/annotate/{sid}", headers=b).json()
    client.put(f"/api/annotations/{sid}", headers=b, json={"status": "done", "items": [{"picto_id": 2, "keyword": "vaso"}]})
    needs = client.get("/api/review/sentences?filter=needs", headers=rev).json()
    assert needs["total"] == 1 and needs["items"][0]["id"] == sid
    det = client.get(f"/api/review/{sid}", headers=rev).json()
    assert len(det["annotations"]) == 2 and det["metrics"]["exact"] == 0.0

    assert client.put(f"/api/gold/{sid}", headers=rev, json={"items": [{"picto_id": 3}]}).status_code == 200
    assert client.get("/api/review/sentences?filter=gold", headers=rev).json()["total"] == 1

    dash = client.get("/api/admin/dashboard", headers=admin).json()
    assert dash["totals"]["annotations"]["done"] == 2 and dash["agreement"]["sentences"] == 1

    jl = client.get("/api/admin/export?format=jsonl", headers=admin).text.strip().splitlines()
    assert len(jl) == 2
    csv_text = client.get("/api/admin/export?format=csv", headers=admin).text
    assert "gold" in csv_text and "catalog_version" in csv_text


def test_blind_assignment_hides_suggestions(con, client):
    admin = mkuser(con, "admin", "admin")
    a, b = mkuser(con, "a"), mkuser(con, "b")
    client.post("/api/admin/sentences", headers=admin, json={"lines": ["beber agua"]})
    client.post("/api/admin/assign", headers=admin, json={"coverage": 2, "blind_fraction": 1.0, "seed": 1})
    sid = client.get("/api/my/queue", headers=a).json()["items"][0]["id"]
    d = client.get(f"/api/annotate/{sid}", headers=a).json()
    assert d["sentence"]["blind"] and d["analysis"]["sequence"] == [] and d["analysis"]["segments"] == []
    client.put(f"/api/annotations/{sid}", headers=a, json={"status": "done", "items": [{"picto_id": 1}]})
    row = con.execute("SELECT * FROM annotations").fetchone()
    assert row["blind"] == 1 and row["from_suggestion"] == 0 and row["accepted_unchanged"] == 0


def test_catalog_freeze(con):
    from app import catalog
    catalog.freeze(con)
    with pytest.raises(catalog.CatalogFrozen):
        catalog.ingest(con, [], "other")
