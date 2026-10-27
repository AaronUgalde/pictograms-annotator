import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.main import app


@pytest.fixture()
def client(con):
    main._failures.clear()
    with TestClient(app) as c:
        yield c


def login(client, email):
    r = client.post("/api/login", json={"email": email})
    assert r.status_code == 200, r.text
    return {"X-Token": r.json()["token"]}


def admin(client):
    r = client.post("/api/admin/login", json={"password": "clave-de-prueba"})
    assert r.status_code == 200
    return {"X-Token": r.json()["token"]}


def test_email_login_creates_then_continues(con, client):
    client.post("/api/admin/sentences", headers=admin(client), json={"lines": [f"frase {i}" for i in range(20)]})
    r1 = client.post("/api/login", json={"email": "  Ana@Correo.COM "}).json()
    assert r1["created"] is True and r1["email"] == "ana@correo.com"
    r2 = client.post("/api/login", json={"email": "ana@correo.com"}).json()
    assert r2["created"] is False and r2["token"] == r1["token"]
    q = client.get("/api/my/queue", headers={"X-Token": r1["token"]}).json()["items"]
    assert len(q) == 15


def test_invalid_email_and_domain_restriction(client, monkeypatch):
    assert client.post("/api/login", json={"email": "no-es-correo"}).status_code == 422
    assert client.post("/api/login", json={"email": "admin"}).status_code == 422
    monkeypatch.setattr(config, "ALLOWED_EMAIL_DOMAINS", ["uni.edu"])
    assert client.post("/api/login", json={"email": "x@gmail.com"}).status_code == 403
    assert client.post("/api/login", json={"email": "x@uni.edu"}).status_code == 200


def test_registration_can_be_closed_but_existing_students_still_enter(client):
    a = admin(client)
    login(client, "viejo@x.com")
    client.put("/api/admin/settings", headers=a, json={"registration_open": False})
    assert client.post("/api/login", json={"email": "nuevo@x.com"}).status_code == 403
    assert client.post("/api/login", json={"email": "viejo@x.com"}).status_code == 200


def test_students_cannot_use_admin_things(client):
    s = login(client, "alumno@x.com")
    for method, path in [("get", "/api/admin/dashboard"), ("get", "/api/admin/export"),
                         ("put", "/api/admin/settings"), ("post", "/api/admin/sentences"),
                         ("delete", "/api/admin/sentences/unannotated")]:
        r = getattr(client, method)(path, headers=s, **({"json": {}} if method in ("put", "post") else {}))
        assert r.status_code == 403, path
        assert getattr(client, method)(path, **({"json": {}} if method in ("put", "post") else {})).status_code == 401
    # el correo del "admin" no concede nada: la cuenta de administración no se puede crear ni usar por correo
    assert client.post("/api/login", json={"email": "admin"}).status_code == 422


def test_admin_login_password_and_throttle(client, monkeypatch):
    assert client.post("/api/admin/login", json={"password": "mal"}).status_code == 401
    for _ in range(4):
        client.post("/api/admin/login", json={"password": "mal"})
    assert client.post("/api/admin/login", json={"password": "clave-de-prueba"}).status_code == 429
    main._failures.clear()
    t1 = client.post("/api/admin/login", json={"password": "clave-de-prueba"}).json()["token"]
    assert client.post("/api/admin/login", json={"password": "clave-de-prueba"}).json()["token"] == t1
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "otra-clave")
    t2 = client.post("/api/admin/login", json={"password": "otra-clave"}).json()["token"]
    assert t2 != t1
    assert client.get("/api/admin/dashboard", headers={"X-Token": t1}).status_code == 401


def test_admin_disabled_without_password(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    assert client.post("/api/admin/login", json={"password": ""}).status_code == 503


def test_full_flow_progress_and_export(con, client):
    a = admin(client)
    r = client.post("/api/admin/sentences", headers=a, json={"lines": ["Tener hambre y beber agua", "agua", "vaso"]})
    assert r.json()["added"] == 3
    client.put("/api/admin/settings", headers=a, json={"sentences_per_student": 2})
    s1, s2 = login(client, "uno@x.com"), login(client, "dos@x.com")

    q = client.get("/api/my/queue", headers=s1).json()["items"]
    assert len(q) == 2
    sid = q[0]["id"]
    d = client.get(f"/api/annotate/{sid}", headers=s1).json()
    items = [{"picto_id": x["picto_id"], "keyword": x["keyword"], "token": x["token"]} for x in d["analysis"]["sequence"]]
    assert client.put(f"/api/annotations/{sid}", headers=s1, json={"status": "done", "items": items, "seconds": 4}).status_code == 200
    # una oración que no es suya
    other = next(r["id"] for r in client.get("/api/my/queue", headers=s2).json()["items"] if r["id"] not in {i["id"] for i in q})
    assert client.get(f"/api/annotate/{other}", headers=s1).status_code == 404
    assert client.put(f"/api/annotations/{sid}", headers=s1, json={"status": "done", "items": []}).status_code == 422
    assert client.put(f"/api/annotations/{sid}", headers=s1,
                      json={"status": "done", "items": [{"picto_id": 99999}]}).status_code == 422

    dash = client.get("/api/admin/dashboard", headers=a).json()
    rows = {s["email"]: s for s in dash["students"]}
    assert rows["uno@x.com"]["assigned"] == 2 and rows["uno@x.com"]["finished"] == 1 and rows["uno@x.com"]["remaining"] == 1
    assert rows["dos@x.com"]["remaining"] == 2
    assert dash["totals"]["students"] == 2 and dash["totals"]["annotations"] == 1
    assert dash["totals"]["coverage"]["1"] == 1
    assert dash["settings"]["sentences_per_student"] == 2

    nxt = client.get("/api/my/next", headers=s1).json()["next"]
    client.put(f"/api/annotations/{nxt}", headers=s1, json={"status": "done", "items": [{"picto_id": 1}]})
    dash = client.get("/api/admin/dashboard", headers=a).json()
    assert dash["totals"]["students_finished"] == 1
    assert client.get("/api/my/next", headers=s1).json()["next"] is None

    jl = client.get("/api/admin/export?format=jsonl", headers=a).text.strip().splitlines()
    assert len(jl) == 3
    csv_text = client.get("/api/admin/export?format=csv", headers=a).text
    assert "uno@x.com" in csv_text and "catalog_version" in csv_text


def test_raising_n_tops_up_on_next_visit(client):
    a = admin(client)
    client.post("/api/admin/sentences", headers=a, json={"lines": [f"f{i}" for i in range(10)]})
    client.put("/api/admin/settings", headers=a, json={"sentences_per_student": 3})
    s = login(client, "ana@x.com")
    assert len(client.get("/api/my/queue", headers=s).json()["items"]) == 3
    client.put("/api/admin/settings", headers=a, json={"sentences_per_student": 6})
    client.get("/api/me", headers=s)
    assert len(client.get("/api/my/queue", headers=s).json()["items"]) == 6
    assert client.put("/api/admin/settings", headers=a, json={"sentences_per_student": 0}).status_code == 422



def test_concurrent_new_students_get_balanced_sentences(client):
    """Muchos alumnos entrando a la vez: nadie recibe repetidas y la cobertura queda pareja."""
    from concurrent.futures import ThreadPoolExecutor
    from collections import Counter

    a = admin(client)
    client.post("/api/admin/sentences", headers=a, json={"lines": [f"oración {i}" for i in range(30)]})
    client.put("/api/admin/settings", headers=a, json={"sentences_per_student": 10})
    with ThreadPoolExecutor(max_workers=6) as ex:
        tokens = list(ex.map(lambda i: login(client, f"alumno{i}@x.com"), range(6)))
    per_sentence = Counter()
    for t in tokens:
        ids = [r["id"] for r in client.get("/api/my/queue", headers=t).json()["items"]]
        assert len(ids) == len(set(ids)) == 10
        per_sentence.update(ids)
    # 6 alumnos × 10 = 60 asignaciones sobre 30 oraciones: exactamente 2 cada una
    assert set(per_sentence.values()) == {2} and len(per_sentence) == 30


def test_related_requires_login_and_never_fails(client):
    assert client.get("/api/related?q=agua").status_code == 401
    s = login(client, "alumno@x.com")
    r = client.get("/api/related?q=agua", headers=s)
    assert r.status_code == 200 and r.json() == {"items": []}  # sin tabla de vectores: lista vacía
