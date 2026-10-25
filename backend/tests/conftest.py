import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="annotator-test-")
os.environ["ANNOTATOR_DATA_DIR"] = _tmp
os.environ["ANNOTATOR_NLP"] = "simple"
os.environ["BACKUP_INTERVAL_HOURS"] = "0"
os.environ["ADMIN_PASSWORD"] = "clave-de-prueba"
os.environ["ANNOTATOR_DB"] = os.path.join(_tmp, "annotator.db")
# Para probar contra PostgreSQL:  TEST_DATABASE_URL=postgresql://… python -m pytest
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")

import pytest  # noqa: E402

from app import catalog, config, db  # noqa: E402


def P(pid, kws, tags=(), **kw):
    return {"_id": pid, "keywords": kws, "tags": list(tags), "categories": [], "synsets": [],
            "downloads": kw.get("downloads", 0), "sex": False, "violence": kw.get("violence", False)}


FAKE = [
    P(1, [{"keyword": "agua", "type": 2, "plural": "aguas"}], ["food"]),
    P(2, [{"keyword": "vaso", "type": 2, "plural": "vasos"}]),
    P(3, [{"keyword": "beber", "type": 3}], ["verb"]),
    P(4, [{"keyword": "tener hambre", "type": 3}], ["verb"]),
    P(5, [{"keyword": "manzana", "type": 2, "plural": "manzanas"}], ["food"]),
    P(6, [{"keyword": "frío", "type": 4}, {"keyword": "helado", "type": 4}], ["adjective"]),
    P(7, [{"keyword": "helado", "type": 2}], ["food"], downloads=5),
    P(8, [{"keyword": "por favor", "type": 6}]),
    P(9, [{"keyword": "comer", "type": 3}], ["verb"]),
    P(10, [{"keyword": "comer", "type": 3}], ["verb"], violence=True),
]


@pytest.fixture(scope="session", autouse=True)
def fake_catalog():
    catalog.ingest(FAKE, "test-v1")


@pytest.fixture()
def con():
    if db.using_postgres():
        c = db.connect()
        db.drop_all(c)
        c.close()
    else:
        for f in config.DB_PATH.parent.glob("annotator.db*"):
            f.unlink()
    db.init_db()
    c = db.connect()
    yield c
    c.close()
