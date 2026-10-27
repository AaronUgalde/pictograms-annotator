"""Prepara la tabla de vectores de palabras para «Relacionados» (data/models/related/).

Parte del modelo model2vec potion-multilingual-128M (minishlab, licencia MIT): 500.353 fragmentos de
muchos idiomas con un vector de 256 números cada uno (≈490 MB). Para que quepa en el plan gratuito de
Render se queda solo con las palabras completas en alfabeto latino (≈178.000) y en float16 (≈90 MB en
disco). La aplicación abre la tabla con mmap, así que en RAM solo ocupan las filas que se consultan.

Solo usa httpx y numpy (ya están en requirements.txt). Se ejecuta una vez; el Dockerfile lo hace al
construir la imagen:
    python tools/build_related.py            # escribe data/models/related/
    python tools/build_related.py --out DIR
"""
import argparse
import json
import re
import struct
import tempfile
from pathlib import Path

import httpx
import numpy as np

REPO = "minishlab/potion-multilingual-128M"
REVISION = "73908c3438cf03b6a01bcb9611d62b23d0726f08"  # fijada: el mismo modelo en cada construcción
BASE = f"https://huggingface.co/{REPO}/resolve/{REVISION}"
OUT = Path(__file__).resolve().parents[1] / "data" / "models" / "related"

# «▁» marca el inicio de palabra en el tokenizador (Unigram); sin él son trozos de palabra.
WORD = re.compile(r"^▁([a-záéíóúüñàèìòùç]+)$")


def download(url: str, dest: Path) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)


def read_safetensors(path: Path, name: str) -> np.ndarray:
    """Tensor `name` de un archivo safetensors, como memmap (no lo carga entero en memoria)."""
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(n))
    t = header[name]
    assert t["dtype"] == "F32", t["dtype"]
    start, _end = t["data_offsets"]
    return np.memmap(path, dtype="<f4", mode="r", offset=8 + n + start, shape=tuple(t["shape"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        print(f"Descargando {REPO}@{REVISION[:7]} (≈500 MB)…", flush=True)
        download(f"{BASE}/tokenizer.json", tmp / "tokenizer.json")
        download(f"{BASE}/model.safetensors", tmp / "model.safetensors")
        vocab = json.loads((tmp / "tokenizer.json").read_text(encoding="utf-8"))["model"]["vocab"]
        emb = read_safetensors(tmp / "model.safetensors", "embeddings")
        assert emb.shape[0] == len(vocab), (emb.shape, len(vocab))

        rows, words = [], []
        for i, (piece, _score) in enumerate(vocab):
            m = WORD.match(piece)
            if m:
                rows.append(i)
                words.append(m.group(1))
        vectors = np.asarray(emb[rows], dtype=np.float16)
        del emb

    args.out.mkdir(parents=True, exist_ok=True)
    np.save(args.out / "vectors.npy", vectors)
    (args.out / "words.txt").write_text("\n".join(words) + "\n", encoding="utf-8")
    (args.out / "meta.json").write_text(json.dumps(
        {"source": REPO, "revision": REVISION, "license": "MIT", "words": len(words), "dims": vectors.shape[1]},
        indent=2), encoding="utf-8")
    print(f"{len(words)} palabras × {vectors.shape[1]} dimensiones → {args.out} ({vectors.nbytes >> 20} MB)")


if __name__ == "__main__":
    main()
