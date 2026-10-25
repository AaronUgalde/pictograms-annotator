"""Datos del panel del admin: progreso de cada alumno y cobertura de las oraciones."""
from . import assign, config, db


def dashboard(con) -> dict:
    students = []
    for r in con.execute("""
        SELECT u.id, u.email, u.active, u.created_at,
          (SELECT COUNT(*) FROM assignments a WHERE a.user_id=u.id) assigned,
          (SELECT COUNT(*) FROM annotations n WHERE n.user_id=u.id) finished,
          (SELECT COUNT(*) FROM annotations n WHERE n.user_id=u.id AND n.status='done') done,
          (SELECT COUNT(*) FROM annotations n WHERE n.user_id=u.id AND n.status='doubtful') doubtful,
          (SELECT COUNT(*) FROM annotations n WHERE n.user_id=u.id AND n.status='skipped') skipped,
          (SELECT MAX(updated_at) FROM annotations n WHERE n.user_id=u.id) last_activity
        FROM users u WHERE u.role='annotator' ORDER BY u.email"""):
        s = dict(r)
        s["remaining"] = max(0, s["assigned"] - s["finished"])
        students.append(s)

    coverage = {"0": 0, "1": 0, "2+": 0}
    for r in con.execute("""SELECT c, COUNT(*) n FROM (
            SELECT (SELECT COUNT(*) FROM annotations n WHERE n.sentence_id=s.id) c FROM sentences s) GROUP BY c"""):
        coverage["0" if r["c"] == 0 else "1" if r["c"] == 1 else "2+"] += r["n"]

    finished_students = sum(1 for s in students if s["assigned"] and s["remaining"] == 0)
    return {
        "totals": {
            "students": len(students),
            "students_finished": finished_students,
            "sentences": con.execute("SELECT COUNT(*) FROM sentences").fetchone()[0],
            "annotations": con.execute("SELECT COUNT(*) FROM annotations").fetchone()[0],
            "coverage": coverage,
        },
        "settings": settings(con),
        "students": students,
    }


def settings(con) -> dict:
    return {
        "sentences_per_student": assign.per_student(con),
        "registration_open": db.get_setting(con, "registration_open", "1") == "1",
        "allowed_domains": config.ALLOWED_EMAIL_DOMAINS,
    }
