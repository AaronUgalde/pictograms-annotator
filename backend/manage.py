#!/usr/bin/env python
"""Línea de órdenes (opcional: casi todo se hace desde el panel de administración).

Ejemplos (desde la carpeta backend/):
    python manage.py sentences import ../data/sentences/ejemplo.txt
    python manage.py export --format csv --out resultados.csv
    python manage.py reset
    python manage.py prefetch-images
    python manage.py serve --host 0.0.0.0
"""
import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path

import httpx

from app import assign as assign_mod
from app import catalog, config, db, export


def _con():
    db.init_db()
    return db.connect()


def cmd_init(args):
    db.init_db()
    print("Tablas listas en la base de DATABASE_URL.")


def cmd_reset(args):
    """Borra TODOS los datos (alumnos, oraciones, respuestas y ajustes) y deja las tablas vacías."""
    if not args.yes:
        answer = input("Se borrarán todos los alumnos, oraciones y respuestas. Escribe BORRAR para confirmar: ")
        if answer.strip() != "BORRAR":
            sys.exit("Cancelado.")
    con = db.connect()
    try:
        db.drop_all(con)
    finally:
        con.close()
    db.init_db()
    print("Base de datos vacía y lista.")


def cmd_catalog(args):
    """El catálogo se carga solo al arrancar; esto sirve para cambiarlo a mano (cambia los IDs disponibles)."""
    if args.action == "download":
        print("Descargando catálogo completo de ARASAAC (unos 8 MB)…")
        version, raw, path = catalog.download()
        n = catalog.ingest(raw, version)
        print(f"{n} pictogramas cargados. Versión: {version}\nCopia: {path}")
    elif args.action == "load":
        version, raw = catalog.load_snapshot(args.path)
        n = catalog.ingest(raw, version)
        print(f"{n} pictogramas cargados desde {args.path}. Versión: {version}")
    else:
        catalog.ensure_loaded()
        print(catalog.status())


def _read_lines(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        if not rows:
            return []
        header = [h.strip().lower() for h in rows[0]]
        col = header.index("text") if "text" in header else (header.index("frase") if "frase" in header else None)
        data = rows[1:] if col is not None else rows
        return [r[col or 0] for r in data if r]
    return path.read_text(encoding="utf-8-sig").splitlines()


def cmd_sentences(args):
    con = _con()
    try:
        res = assign_mod.import_sentences(con, _read_lines(Path(args.file)))
        print(res)
    finally:
        con.close()


def cmd_export(args):
    con = _con()
    try:
        text = export.to_csv(con) if args.format == "csv" else export.to_jsonl(con)
    finally:
        con.close()
    Path(args.out).write_text(text, encoding="utf-8")
    print("Exportado a", args.out)


def cmd_prefetch(args):
    """Descarga y guarda todas las imágenes (≈14.000 PNG) para trabajar sin conexión."""
    con = _con()
    ids = [r["picto_id"] for r in con.execute("SELECT picto_id FROM catalog ORDER BY picto_id")]
    con.close()
    if not ids:
        sys.exit("Primero carga el catálogo.")
    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    todo = [i for i in ids if not (config.IMAGES_DIR / f"{i}.png").exists()]
    print(f"{len(todo)} imágenes por descargar de {len(ids)}")

    async def run():
        sem = asyncio.Semaphore(args.concurrency)
        done = failed = 0
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            async def one(pid):
                nonlocal done, failed
                async with sem:
                    try:
                        r = await client.get(f"{config.ARASAAC_STATIC}/{pid}/{pid}_300.png")
                        if r.status_code == 200:
                            tmp = config.IMAGES_DIR / f"{pid}.tmp"
                            tmp.write_bytes(r.content)
                            tmp.replace(config.IMAGES_DIR / f"{pid}.png")
                            done += 1
                        else:
                            failed += 1
                    except httpx.HTTPError:
                        failed += 1
                    if (done + failed) % 500 == 0:
                        print(f"  {done + failed}/{len(todo)} (fallos: {failed})", flush=True)
            await asyncio.gather(*(one(i) for i in todo))
        print(f"Listo. Descargadas: {done}, fallos: {failed}")

    asyncio.run(run())


def cmd_serve(args):
    import uvicorn
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload,
                proxy_headers=True, forwarded_allow_ips="*")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)

    c = sub.add_parser("catalog")
    c.add_argument("action", choices=["download", "load", "status"])
    c.add_argument("path", nargs="?")
    c.set_defaults(fn=cmd_catalog)

    s = sub.add_parser("sentences")
    s.add_argument("action", choices=["import"])
    s.add_argument("file")
    s.set_defaults(fn=cmd_sentences)

    r = sub.add_parser("reset", help="borra todos los datos")
    r.add_argument("--yes", action="store_true", help="no pedir confirmación")
    r.set_defaults(fn=cmd_reset)

    e = sub.add_parser("export")
    e.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    e.add_argument("--out", required=True)
    e.set_defaults(fn=cmd_export)

    f = sub.add_parser("prefetch-images")
    f.add_argument("--concurrency", type=int, default=8)
    f.set_defaults(fn=cmd_prefetch)

    v = sub.add_parser("serve")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    v.add_argument("--reload", action="store_true")
    v.set_defaults(fn=cmd_serve)

    args = p.parse_args()
    if args.cmd == "catalog" and args.action == "load" and not args.path:
        p.error("falta la ruta")
    args.fn(args)


if __name__ == "__main__":
    main()
