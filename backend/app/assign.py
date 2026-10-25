"""Carga de oraciones y reparto automático entre alumnos.

Regla de reparto: cada alumno recibe N oraciones (N = «oraciones por alumno», por defecto 15).
Se eligen primero las oraciones que tienen **menos alumnos asignados**, de modo que las que aún no
tiene nadie o solo uno se cubren antes; a igualdad se elige al azar. Nunca se repite una oración
para el mismo alumno.
"""
from . import config, db


def per_student(con) -> int:
    try:
        return max(1, int(db.get_setting(con, "sentences_per_student", config.DEFAULT_SENTENCES_PER_STUDENT)))
    except ValueError:
        return config.DEFAULT_SENTENCES_PER_STUDENT


def import_sentences(con, lines) -> dict:
    added = dup = 0
    for line in lines:
        text = " ".join((line or "").split())
        if not text:
            continue
        cur = con.execute("INSERT OR IGNORE INTO sentences(text, created_at) VALUES (?,?)", (text, db.now()))
        if cur.rowcount:
            added += 1
        else:
            dup += 1
    con.commit()
    return {"added": added, "duplicates": dup}


def delete_unannotated(con) -> int:
    """Borra las oraciones que nadie ha anotado todavía (y sus asignaciones). Sirve para corregir una carga errónea."""
    cur = con.execute("DELETE FROM sentences WHERE id NOT IN (SELECT sentence_id FROM annotations)")
    con.commit()
    return cur.rowcount


def ensure_assignments(con, user_id: int, n: int | None = None) -> int:
    """Completa hasta N las oraciones del alumno. Devuelve cuántas se añadieron.

    Se llama al crear la cuenta y cada vez que el alumno entra: si había menos oraciones cargadas,
    o el admin subió más o aumentó N, se completa en ese momento.
    """
    n = n or per_student(con)
    con.commit()
    con.execute("BEGIN IMMEDIATE")  # evita que dos alumnos nuevos a la vez reciban lo mismo
    try:
        have = con.execute("SELECT COUNT(*) FROM assignments WHERE user_id=?", (user_id,)).fetchone()[0]
        need = n - have
        if need <= 0:
            con.commit()
            return 0
        rows = con.execute(
            "SELECT s.id FROM sentences s "
            "WHERE s.id NOT IN (SELECT sentence_id FROM assignments WHERE user_id=?) "
            "ORDER BY (SELECT COUNT(*) FROM assignments a WHERE a.sentence_id=s.id), RANDOM() LIMIT ?",
            (user_id, need),
        ).fetchall()
        seq = con.execute("SELECT COALESCE(MAX(seq),0) FROM assignments WHERE user_id=?", (user_id,)).fetchone()[0]
        for r in rows:
            seq += 1
            con.execute("INSERT INTO assignments(sentence_id, user_id, seq) VALUES (?,?,?)", (r["id"], user_id, seq))
        con.commit()
        return len(rows)
    except Exception:
        con.rollback()
        raise
