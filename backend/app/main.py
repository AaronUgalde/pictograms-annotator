"""API FastAPI + servidor del frontend."""
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import assign as assign_mod
from . import backup, catalog, config, db, export, review, suggest

RANK = {"annotator": 1, "reviewer": 2, "admin": 3}


# ------------------------------------------------------------------ ciclo de vida

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    app.state.http = httpx.AsyncClient(timeout=20, follow_redirects=True)
    task = None
    if config.BACKUP_INTERVAL_HOURS > 0:
        async def loop():
            while True:
                await asyncio.sleep(config.BACKUP_INTERVAL_HOURS * 3600)
                await asyncio.to_thread(backup.run_backup)
        task = asyncio.create_task(loop())
    yield
    if task:
        task.cancel()
    await app.state.http.aclose()


app = FastAPI(title="Pictograms Annotator", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ------------------------------------------------------------------ autenticación

def current_user(request: Request, con=Depends(db.get_db)):
    token = request.headers.get("x-token") or request.query_params.get("t")
    row = con.execute("SELECT * FROM users WHERE token=? AND active=1", (token or "",)).fetchone() if token else None
    if not row:
        raise HTTPException(401, "Identificación no válida")
    return row


def require(role: str):
    def dep(user=Depends(current_user)):
        if RANK[user["role"]] < RANK[role]:
            raise HTTPException(403, "No tienes permiso para esto")
        return user
    return dep


# ------------------------------------------------------------------ modelos

class ItemIn(BaseModel):
    picto_id: int
    keyword: str = ""
    token: str | None = None


class AnnotationIn(BaseModel):
    status: Literal["done", "doubtful", "skipped"]
    items: list[ItemIn] = Field(default_factory=list)
    note: str = ""
    seconds: float = 0


class GoldIn(BaseModel):
    items: list[ItemIn]
    note: str = ""


class UserIn(BaseModel):
    name: str
    role: Literal["annotator", "reviewer", "admin"] = "annotator"


class SentencesIn(BaseModel):
    lines: list[str]
    batch: str = ""
    pilot: bool = False


class AssignIn(BaseModel):
    coverage: int = 2
    triple_fraction: float = 0.0
    blind_fraction: float = 0.0
    seed: int | None = None
    batch: str | None = None
    include_reviewers: bool = False


class ActiveIn(BaseModel):
    active: bool


def _items(con, items: list[ItemIn]):
    try:
        return review.validate_items(con, [i.model_dump() for i in items])
    except review.BadItems as e:
        raise HTTPException(422, str(e))


def _ensure_catalog(con):
    if not db.get_setting(con, "catalog_version"):
        raise HTTPException(409, "El catálogo de ARASAAC aún no está cargado (manage.py catalog download)")


# ------------------------------------------------------------------ general

@app.get("/api/me")
def me(user=Depends(current_user), con=Depends(db.get_db)):
    return {"id": user["id"], "name": user["name"], "role": user["role"],
            "catalog": catalog.status(con), "guide_version": backup.guide_version()}


@app.get("/api/catalog")
def get_catalog(request: Request, user=Depends(current_user), con=Depends(db.get_db)):
    _ensure_catalog(con)
    version, payload = catalog.client_payload(con)
    etag = f'"{version}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(payload, media_type="application/json",
                    headers={"ETag": etag, "Cache-Control": "private, max-age=0, must-revalidate"})


@app.get("/api/guide")
def get_guide(user=Depends(current_user)):
    return {"version": backup.guide_version(), "markdown": backup.guide_text()}


@app.get("/img/{pid}.png")
async def get_image(pid: int, request: Request):
    """Imagen en caché local; se descarga una sola vez de ARASAAC (300 px, PNG con transparencia)."""
    path = config.IMAGES_DIR / f"{pid}.png"
    if not path.exists():
        try:
            r = await request.app.state.http.get(f"{config.ARASAAC_STATIC}/{pid}/{pid}_300.png")
        except httpx.HTTPError:
            raise HTTPException(502, "No se pudo contactar con ARASAAC")
        if r.status_code != 200:
            raise HTTPException(404, "Pictograma no encontrado")
        config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(r.content)
        tmp.replace(path)
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


# ------------------------------------------------------------------ anotación

def _assignment(con, sid: int, uid: int):
    row = con.execute(
        "SELECT s.*, a.seq FROM assignments a JOIN sentences s ON s.id=a.sentence_id "
        "WHERE a.sentence_id=? AND a.user_id=?", (sid, uid)).fetchone()
    if not row:
        raise HTTPException(404, "Esa frase no está asignada a esta persona")
    return row


def _annotation(con, sid: int, uid: int):
    a = con.execute("SELECT * FROM annotations WHERE sentence_id=? AND user_id=?", (sid, uid)).fetchone()
    if not a:
        return None
    items = [dict(i) for i in con.execute(
        "SELECT picto_id, keyword, token FROM annotation_items WHERE annotation_id=? ORDER BY position", (a["id"],))]
    return {"status": a["status"], "note": a["note"], "items": items, "seconds": a["seconds"]}


def _next_pending(con, uid: int, after_seq: int | None = None):
    base = ("SELECT a.sentence_id id FROM assignments a LEFT JOIN annotations n "
            "ON n.sentence_id=a.sentence_id AND n.user_id=a.user_id WHERE a.user_id=? AND n.id IS NULL")
    if after_seq is not None:
        r = con.execute(base + " AND a.seq>? ORDER BY a.seq LIMIT 1", (uid, after_seq)).fetchone()
        if r:
            return r["id"]
    r = con.execute(base + " ORDER BY a.seq LIMIT 1", (uid,)).fetchone()
    return r["id"] if r else None


def _memory_apply(con, uid: int, items, delta: int):
    ts = db.now()
    for it in items:
        tok = it["token"]
        if not tok:
            continue
        con.execute(
            "INSERT INTO choice_memory(lemma, picto_id, user_id, count, last_used) VALUES (?,?,?,?,?) "
            "ON CONFLICT(lemma, picto_id, user_id) DO UPDATE SET count=count+?, last_used=?",
            (tok, it["picto_id"], uid, max(delta, 0), ts, delta, ts))
    con.execute("DELETE FROM choice_memory WHERE count<=0")


def _team_memory(con) -> bool:
    return db.get_setting(con, "team_memory", "0") == "1"


@app.get("/api/my/queue")
def my_queue(user=Depends(current_user), con=Depends(db.get_db)):
    rows = con.execute(
        "SELECT a.sentence_id id, a.seq, s.text, n.status FROM assignments a JOIN sentences s ON s.id=a.sentence_id "
        "LEFT JOIN annotations n ON n.sentence_id=a.sentence_id AND n.user_id=a.user_id "
        "WHERE a.user_id=? ORDER BY a.seq", (user["id"],)).fetchall()
    return {"items": [dict(r) for r in rows]}


@app.get("/api/my/next")
def my_next(user=Depends(current_user), con=Depends(db.get_db)):
    return {"next": _next_pending(con, user["id"])}


@app.get("/api/annotate/{sid}")
def annotate(sid: int, user=Depends(current_user), con=Depends(db.get_db)):
    _ensure_catalog(con)
    s = _assignment(con, sid, user["id"])
    blind = bool(s["blind"])
    pos = con.execute("SELECT COUNT(*) FROM assignments WHERE user_id=? AND seq<=?", (user["id"], s["seq"])).fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM assignments WHERE user_id=?", (user["id"],)).fetchone()[0]
    analysis = suggest.analyze_sentence(con, s["text"], user["id"], _team_memory(con), blind=blind)
    return {
        "sentence": {"id": s["id"], "text": s["text"], "blind": blind, "pos": pos, "total": total},
        "annotation": _annotation(con, sid, user["id"]),
        "analysis": analysis,
    }


@app.put("/api/annotations/{sid}")
def put_annotation(sid: int, body: AnnotationIn, user=Depends(current_user), con=Depends(db.get_db)):
    _ensure_catalog(con)
    s = _assignment(con, sid, user["id"])
    if body.status == "done" and not body.items:
        raise HTTPException(422, "Una frase hecha necesita al menos un pictograma")
    items = _items(con, body.items)
    blind = bool(s["blind"])
    uid = user["id"]
    ts = db.now()
    existing = con.execute("SELECT * FROM annotations WHERE sentence_id=? AND user_id=?", (sid, uid)).fetchone()
    final_ids = [i["picto_id"] for i in items]

    if existing:
        if existing["status"] == "done":
            old = con.execute("SELECT picto_id, token FROM annotation_items WHERE annotation_id=?", (existing["id"],)).fetchall()
            _memory_apply(con, uid, [dict(o) for o in old], -1)
        proposal = json.loads(existing["proposal"]) if existing["proposal"] is not None else None
        seconds = existing["seconds"] + max(0.0, min(body.seconds, 3600))
        con.execute("DELETE FROM annotation_items WHERE annotation_id=?", (existing["id"],))
        aid = existing["id"]
    else:
        proposal = None
        if not blind:
            a = suggest.analyze_sentence(con, s["text"], uid, _team_memory(con))
            proposal = [x["picto_id"] for x in a["sequence"]]
        seconds = max(0.0, min(body.seconds, 3600))
        aid = None

    from_suggestion = 1 if proposal else 0
    unchanged = 1 if (proposal and proposal == final_ids and body.status == "done") else 0
    version = db.get_setting(con, "catalog_version")
    if aid is None:
        cur = con.execute(
            "INSERT INTO annotations(sentence_id, user_id, status, note, proposal, from_suggestion, accepted_unchanged,"
            " blind, seconds, catalog_version, guide_version, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, uid, body.status, body.note[:500], json.dumps(proposal) if proposal is not None else None,
             from_suggestion, unchanged, 1 if blind else 0, seconds, version, backup.guide_version(), ts, ts))
        aid = cur.lastrowid
    else:
        con.execute(
            "UPDATE annotations SET status=?, note=?, from_suggestion=?, accepted_unchanged=?, seconds=?,"
            " catalog_version=?, guide_version=?, updated_at=? WHERE id=?",
            (body.status, body.note[:500], from_suggestion, unchanged, seconds, version, backup.guide_version(), ts, aid))
    for pos, it in enumerate(items):
        con.execute("INSERT INTO annotation_items(annotation_id, position, picto_id, keyword, token) VALUES (?,?,?,?,?)",
                    (aid, pos, it["picto_id"], it["keyword"], it["token"]))
    if body.status == "done":
        _memory_apply(con, uid, items, 1)
    con.commit()
    return {"ok": True, "next": _next_pending(con, uid, s["seq"])}


# ------------------------------------------------------------------ revisión

@app.get("/api/review/sentences")
def review_sentences(filter: str = "needs", min_distance: float = 0.0, limit: int = 200, offset: int = 0,
                     user=Depends(require("reviewer")), con=Depends(db.get_db)):
    return review.overview(con, filter, min_distance, limit, offset)


@app.get("/api/review/{sid}")
def review_detail(sid: int, user=Depends(require("reviewer")), con=Depends(db.get_db)):
    _ensure_catalog(con)
    d = review.detail(con, sid)
    if not d:
        raise HTTPException(404, "Frase no encontrada")
    d["analysis"] = suggest.analyze_sentence(con, d["sentence"]["text"], None, False)
    nxt = review.overview(con, "needs", limit=1000)["items"]
    ids = [r["id"] for r in nxt]
    d["next_needs"] = next((i for i in ids if i > sid), ids[0] if ids and ids[0] != sid else None)
    return d


@app.put("/api/gold/{sid}")
def put_gold(sid: int, body: GoldIn, user=Depends(require("reviewer")), con=Depends(db.get_db)):
    if not con.execute("SELECT 1 FROM sentences WHERE id=?", (sid,)).fetchone():
        raise HTTPException(404, "Frase no encontrada")
    try:
        review.save_gold(con, sid, user["id"], [i.model_dump() for i in body.items], body.note[:500])
    except review.BadItems as e:
        raise HTTPException(422, str(e))
    ov = review.overview(con, "needs", limit=1000)["items"]
    ids = [r["id"] for r in ov]
    return {"ok": True, "next": next((i for i in ids if i > sid), ids[0] if ids else None)}


@app.post("/api/gold/auto-accept")
def gold_auto_accept(user=Depends(require("reviewer")), con=Depends(db.get_db)):
    return {"accepted": review.auto_accept(con, user["id"])}


# ------------------------------------------------------------------ administración

@app.get("/api/admin/dashboard")
def admin_dashboard(user=Depends(require("admin")), con=Depends(db.get_db)):
    return review.dashboard(con)


@app.get("/api/admin/users")
def admin_users(user=Depends(require("admin")), con=Depends(db.get_db)):
    return {"items": [dict(r) for r in con.execute("SELECT id, name, role, active, token FROM users ORDER BY name")]}


@app.post("/api/admin/users")
def admin_add_user(body: UserIn, user=Depends(require("admin")), con=Depends(db.get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Falta el nombre")
    try:
        cur = con.execute("INSERT INTO users(name, token, role, created_at) VALUES (?,?,?,?)",
                          (name, db.new_token(), body.role, db.now()))
    except Exception:
        raise HTTPException(409, "Ya existe una persona con ese nombre")
    con.commit()
    row = con.execute("SELECT id, name, role, active, token FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@app.post("/api/admin/users/{uid}/regen-token")
def admin_regen(uid: int, user=Depends(require("admin")), con=Depends(db.get_db)):
    token = db.new_token()
    if not con.execute("UPDATE users SET token=? WHERE id=?", (token, uid)).rowcount:
        raise HTTPException(404, "Persona no encontrada")
    con.commit()
    return {"token": token}


@app.patch("/api/admin/users/{uid}")
def admin_user_active(uid: int, body: ActiveIn, user=Depends(require("admin")), con=Depends(db.get_db)):
    if uid == user["id"] and not body.active:
        raise HTTPException(422, "No puedes desactivarte a ti mismo")
    con.execute("UPDATE users SET active=? WHERE id=?", (1 if body.active else 0, uid))
    con.commit()
    return {"ok": True}


@app.post("/api/admin/sentences")
def admin_sentences(body: SentencesIn, user=Depends(require("admin")), con=Depends(db.get_db)):
    return assign_mod.import_sentences(con, body.lines, body.batch, body.pilot)


@app.post("/api/admin/assign")
def admin_assign(body: AssignIn, user=Depends(require("admin")), con=Depends(db.get_db)):
    roles = ("annotator", "reviewer") if body.include_reviewers else ("annotator",)
    try:
        return assign_mod.assign(con, body.coverage, body.triple_fraction, body.blind_fraction,
                                 body.seed, body.batch, roles)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/admin/backup")
def admin_backup(user=Depends(require("admin"))):
    return {"path": backup.run_backup()}


@app.post("/api/admin/catalog/freeze")
def admin_freeze(user=Depends(require("admin")), con=Depends(db.get_db)):
    try:
        catalog.freeze(con)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return catalog.status(con)


@app.get("/api/admin/export")
def admin_export(format: Literal["jsonl", "csv"] = "jsonl", user=Depends(require("admin")), con=Depends(db.get_db)):
    if format == "csv":
        return PlainTextResponse(export.to_csv(con), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": 'attachment; filename="pictogramas.csv"'})
    return PlainTextResponse(export.to_jsonl(con), media_type="application/x-ndjson; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="pictogramas.jsonl"'})


# ------------------------------------------------------------------ frontend (debe ir al final)

app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
