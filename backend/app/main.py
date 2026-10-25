"""API FastAPI + servidor del frontend.

Alumnos: entran solo con su correo (si no existe, se crea la cuenta y se les asignan oraciones).
Administración: contraseña (variable ADMIN_PASSWORD). Un alumno nunca recibe un token de administrador.
"""
import asyncio
import hashlib
import json
import re
import secrets
import time
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import assign, catalog, config, db, export, guide, items as items_mod, nlp, stats, suggest


# ------------------------------------------------------------------ ciclo de vida

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(db.init_db)  # falla con un mensaje claro si no hay DATABASE_URL
    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(catalog.ensure_loaded)
    if not config.ADMIN_PASSWORD:
        print("[aviso] ADMIN_PASSWORD no está definida: nadie podrá entrar al panel de administración.")
    app.state.http = httpx.AsyncClient(timeout=20, follow_redirects=True)
    # spaCy tarda en cargar; se hace en segundo plano para que el servidor responda cuanto antes.
    warm = asyncio.create_task(asyncio.to_thread(nlp.backend))
    print("[inicio] listo")
    yield
    warm.cancel()
    await app.state.http.aclose()
    db.close_pool()


app = FastAPI(title="Anotador de pictogramas", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ------------------------------------------------------------------ identificación

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise HTTPException(422, "Escribe un correo válido, por ejemplo nombre@correo.com")
    domains = config.ALLOWED_EMAIL_DOMAINS
    if domains and email.rsplit("@", 1)[1] not in domains:
        raise HTTPException(403, "Usa tu correo institucional (@" + ", @".join(domains) + ")")
    return email


def current_user(request: Request, con=Depends(db.get_db)):
    token = request.headers.get("x-token")
    row = con.execute("SELECT * FROM users WHERE token=? AND active=1", (token,)).fetchone() if token else None
    if not row:
        raise HTTPException(401, "Identificación no válida")
    return row


def require_admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Solo la persona que administra puede hacer esto")
    return user


class LoginIn(BaseModel):
    email: str


class AdminLoginIn(BaseModel):
    password: str


@app.post("/api/login")
def login(body: LoginIn, con=Depends(db.get_db)):
    """Entrar o crear la cuenta con solo el correo. El correo identifica a la persona; no hay contraseña."""
    email = normalize_email(body.email)
    row = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    created = False
    if row is None:
        if db.get_setting(con, "registration_open", "1") != "1":
            raise HTTPException(403, "El registro de cuentas nuevas está cerrado. Pide a tu docente que lo abra.")
        new_id = con.execute("INSERT INTO users(email, token, role, created_at) VALUES (?,?,?,?) RETURNING id",
                             (email, db.new_token(), "annotator", db.now())).fetchone()["id"]
        con.commit()
        row = con.execute("SELECT * FROM users WHERE id=?", (new_id,)).fetchone()
        created = True
    elif not row["active"] or row["role"] != "annotator":
        raise HTTPException(403, "Esta cuenta está desactivada.")
    assign.ensure_assignments(con, row["id"])
    return {"token": row["token"], "email": email, "created": created}


_failures: dict[str, list[float]] = {}


def _throttle(ip: str) -> None:
    now = time.time()
    recent = [t for t in _failures.get(ip, []) if now - t < 600]
    _failures[ip] = recent
    if len(recent) >= 5:
        raise HTTPException(429, "Demasiados intentos. Espera unos minutos.")


@app.post("/api/admin/login")
def admin_login(body: AdminLoginIn, request: Request, con=Depends(db.get_db)):
    if not config.ADMIN_PASSWORD:
        raise HTTPException(503, "El servidor no tiene configurada ADMIN_PASSWORD.")
    ip = request.client.host if request.client else "?"
    _throttle(ip)
    if not secrets.compare_digest(body.password.encode(), config.ADMIN_PASSWORD.encode()):
        _failures.setdefault(ip, []).append(time.time())
        raise HTTPException(401, "Contraseña incorrecta")
    return {"token": ensure_admin(con)}


def ensure_admin(con) -> str:
    """Cuenta única de administración. Si cambia ADMIN_PASSWORD, el token anterior deja de valer."""
    fp = hashlib.sha256(config.ADMIN_PASSWORD.encode()).hexdigest()[:16]
    row = con.execute("SELECT * FROM users WHERE email='admin'").fetchone()
    if row is None:
        token = db.new_token()
        con.execute("INSERT INTO users(email, token, role, created_at) VALUES ('admin', ?, 'admin', ?)", (token, db.now()))
    elif db.get_setting(con, "admin_pw_fp") != fp or row["role"] != "admin" or not row["active"]:
        token = db.new_token()
        con.execute("UPDATE users SET token=?, role='admin', active=1 WHERE email='admin'", (token,))
    else:
        token = row["token"]
    db.set_setting(con, "admin_pw_fp", fp)
    con.commit()
    return token


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


class SentencesIn(BaseModel):
    lines: list[str]


class SettingsIn(BaseModel):
    sentences_per_student: int | None = Field(default=None, ge=1, le=500)
    registration_open: bool | None = None


def _items(con, items: list[ItemIn]):
    try:
        return items_mod.validate_items(con, [i.model_dump() for i in items])
    except items_mod.BadItems as e:
        raise HTTPException(422, str(e))


# ------------------------------------------------------------------ general

@app.get("/api/me")
def me(user=Depends(current_user), con=Depends(db.get_db)):
    if user["role"] == "annotator":
        assign.ensure_assignments(con, user["id"])  # completa si el admin subió más oraciones o subió el número
    return {"id": user["id"], "email": user["email"], "role": user["role"], "guide_version": guide.guide_version()}


@app.get("/api/catalog")
def get_catalog(request: Request, user=Depends(current_user)):
    version, payload = catalog.client_payload()
    etag = f'"{version}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(payload, media_type="application/json",
                    headers={"ETag": etag, "Cache-Control": "private, max-age=0, must-revalidate"})


@app.get("/api/guide")
def get_guide(user=Depends(current_user)):
    return {"version": guide.guide_version(), "markdown": guide.guide_text()}


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


# ------------------------------------------------------------------ anotación (alumnos)

def _assignment(con, sid: int, uid: int):
    row = con.execute(
        "SELECT s.*, a.seq FROM assignments a JOIN sentences s ON s.id=a.sentence_id "
        "WHERE a.sentence_id=? AND a.user_id=?", (sid, uid)).fetchone()
    if not row:
        raise HTTPException(404, "Esa oración no está asignada a esta cuenta")
    return row


def _annotation(con, sid: int, uid: int):
    a = con.execute("SELECT * FROM annotations WHERE sentence_id=? AND user_id=?", (sid, uid)).fetchone()
    if not a:
        return None
    its = [dict(i) for i in con.execute(
        "SELECT picto_id, keyword, token FROM annotation_items WHERE annotation_id=? ORDER BY position", (a["id"],))]
    return {"status": a["status"], "note": a["note"], "items": its, "seconds": a["seconds"]}


def _next_pending(con, uid: int, after_seq: int | None = None):
    base = ("SELECT a.sentence_id id FROM assignments a LEFT JOIN annotations n "
            "ON n.sentence_id=a.sentence_id AND n.user_id=a.user_id WHERE a.user_id=? AND n.id IS NULL")
    if after_seq is not None:
        r = con.execute(base + " AND a.seq>? ORDER BY a.seq LIMIT 1", (uid, after_seq)).fetchone()
        if r:
            return r["id"]
    r = con.execute(base + " ORDER BY a.seq LIMIT 1", (uid,)).fetchone()
    return r["id"] if r else None


def _memory_apply(con, uid: int, its, delta: int):
    ts = db.now()
    for it in its:
        tok = it["token"]
        if not tok:
            continue
        con.execute(
            "INSERT INTO choice_memory(lemma, picto_id, user_id, count, last_used) VALUES (?,?,?,?,?) "
            "ON CONFLICT(lemma, picto_id, user_id) DO UPDATE SET count=choice_memory.count+?, last_used=?",
            (tok, it["picto_id"], uid, max(delta, 0), ts, delta, ts))
    con.execute("DELETE FROM choice_memory WHERE count<=0")


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
    s = _assignment(con, sid, user["id"])
    pos = con.execute("SELECT COUNT(*) FROM assignments WHERE user_id=? AND seq<=?", (user["id"], s["seq"])).fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM assignments WHERE user_id=?", (user["id"],)).fetchone()[0]
    return {
        "sentence": {"id": s["id"], "text": s["text"], "blind": False, "pos": pos, "total": total},
        "annotation": _annotation(con, sid, user["id"]),
        "analysis": suggest.analyze_sentence(con, s["text"], user["id"]),
    }


@app.put("/api/annotations/{sid}")
def put_annotation(sid: int, body: AnnotationIn, user=Depends(current_user), con=Depends(db.get_db)):
    s = _assignment(con, sid, user["id"])
    if body.status == "done" and not body.items:
        raise HTTPException(422, "Una oración hecha necesita al menos un pictograma")
    its = _items(con, body.items)
    uid = user["id"]
    ts = db.now()
    existing = con.execute("SELECT * FROM annotations WHERE sentence_id=? AND user_id=?", (sid, uid)).fetchone()
    final_ids = [i["picto_id"] for i in its]

    if existing:
        if existing["status"] == "done":
            old = con.execute("SELECT picto_id, token FROM annotation_items WHERE annotation_id=?", (existing["id"],)).fetchall()
            _memory_apply(con, uid, [dict(o) for o in old], -1)
        proposal = json.loads(existing["proposal"]) if existing["proposal"] is not None else None
        seconds = existing["seconds"] + max(0.0, min(body.seconds, 3600))
        con.execute("DELETE FROM annotation_items WHERE annotation_id=?", (existing["id"],))
        aid = existing["id"]
    else:
        a = suggest.analyze_sentence(con, s["text"], uid)
        proposal = [x["picto_id"] for x in a["sequence"]]
        seconds = max(0.0, min(body.seconds, 3600))
        aid = None

    from_suggestion = 1 if proposal else 0
    unchanged = 1 if (proposal and proposal == final_ids and body.status == "done") else 0
    version = catalog.get_index().version
    if aid is None:
        aid = con.execute(
            "INSERT INTO annotations(sentence_id, user_id, status, note, proposal, from_suggestion, accepted_unchanged,"
            " seconds, catalog_version, guide_version, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " RETURNING id",
            (sid, uid, body.status, body.note[:500], json.dumps(proposal), from_suggestion, unchanged,
             seconds, version, guide.guide_version(), ts, ts)).fetchone()["id"]
    else:
        con.execute(
            "UPDATE annotations SET status=?, note=?, from_suggestion=?, accepted_unchanged=?, seconds=?,"
            " catalog_version=?, guide_version=?, updated_at=? WHERE id=?",
            (body.status, body.note[:500], from_suggestion, unchanged, seconds, version, guide.guide_version(), ts, aid))
    for pos, it in enumerate(its):
        con.execute("INSERT INTO annotation_items(annotation_id, position, picto_id, keyword, token) VALUES (?,?,?,?,?)",
                    (aid, pos, it["picto_id"], it["keyword"], it["token"]))
    if body.status == "done":
        _memory_apply(con, uid, its, 1)
    con.commit()
    return {"ok": True, "next": _next_pending(con, uid, s["seq"])}


# ------------------------------------------------------------------ administración

@app.get("/api/admin/dashboard")
def admin_dashboard(user=Depends(require_admin), con=Depends(db.get_db)):
    return stats.dashboard(con)


@app.put("/api/admin/settings")
def admin_settings(body: SettingsIn, user=Depends(require_admin), con=Depends(db.get_db)):
    if body.sentences_per_student is not None:
        db.set_setting(con, "sentences_per_student", body.sentences_per_student)
    if body.registration_open is not None:
        db.set_setting(con, "registration_open", "1" if body.registration_open else "0")
    con.commit()
    return stats.settings(con)


@app.post("/api/admin/sentences")
def admin_sentences(body: SentencesIn, user=Depends(require_admin), con=Depends(db.get_db)):
    return assign.import_sentences(con, body.lines)


@app.delete("/api/admin/sentences/unannotated")
def admin_delete_unannotated(user=Depends(require_admin), con=Depends(db.get_db)):
    return {"deleted": assign.delete_unannotated(con)}


@app.get("/api/admin/export")
def admin_export(format: Literal["jsonl", "csv"] = "jsonl", user=Depends(require_admin), con=Depends(db.get_db)):
    if format == "csv":
        return PlainTextResponse(export.to_csv(con), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": 'attachment; filename="pictogramas.csv"'})
    return PlainTextResponse(export.to_jsonl(con), media_type="application/x-ndjson; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="pictogramas.jsonl"'})


# ------------------------------------------------------------------ frontend (debe ir al final)

app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
