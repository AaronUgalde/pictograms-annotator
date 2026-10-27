import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="annotator-test-")
os.environ["ANNOTATOR_DATA_DIR"] = _tmp
os.environ["ANNOTATOR_NLP"] = "simple"
os.environ["ANNOTATOR_RELATED_DIR"] = os.path.join(_tmp, "sin-vectores")  # test_related.py usa un modelo falso
os.environ["ADMIN_PASSWORD"] = "clave-de-prueba"
# Las pruebas usan una base PostgreSQL desechable (SE BORRA en cada prueba). Nunca la de producción:
#   TEST_DATABASE_URL=postgresql://postgres@localhost:5432/annotator_test python -m pytest
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")

import pytest  # noqa: E402

from app import catalog, db  # noqa: E402


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


def pytest_configure(config):
    if not os.environ["DATABASE_URL"]:
        pytest.exit("Define TEST_DATABASE_URL con una base PostgreSQL de prueba (se borra en cada prueba).", returncode=2)


@pytest.fixture()
def con():
    c = db.connect()
    db.drop_all(c)
    c.close()
    db.init_db()
    c = db.connect()
    yield c
    c.close()
