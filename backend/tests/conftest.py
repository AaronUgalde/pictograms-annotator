import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="annotator-test-")
os.environ["ANNOTATOR_DATA_DIR"] = _tmp
os.environ["ANNOTATOR_NLP"] = "simple"
os.environ["BACKUP_INTERVAL_HOURS"] = "0"

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


@pytest.fixture()
def con():
    for f in config.DB_PATH.parent.glob("annotator.db*"):
        f.unlink()
    db.init_db()
    c = db.connect()
    catalog.ingest(c, FAKE, "test-v1", force=True)
    yield c
    c.close()
