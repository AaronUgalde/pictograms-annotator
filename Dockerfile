# Imagen única: API + interfaz. Los datos van a PostgreSQL (DATABASE_URL); /data solo guarda
# la caché de imágenes de ARASAAC, que se puede perder sin problema.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    ANNOTATOR_DATA_DIR=/data \
    PORT=8000

WORKDIR /app

# Dependencias primero (capa que casi nunca cambia): FastAPI, spaCy y el modelo pequeño de español.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt \
 && pip install "es_core_news_sm @ https://github.com/explosion/spacy-models/releases/download/es_core_news_sm-3.8.0/es_core_news_sm-3.8.0-py3-none-any.whl"

COPY backend backend
COPY frontend frontend
COPY docs docs
# Copia versionada del catálogo ARASAAC: el primer arranque no necesita internet.
COPY data/catalog data/catalog

RUN useradd --create-home app && mkdir -p /data && chown app:app /data
USER app
EXPOSE 8000

WORKDIR /app/backend
# PORT lo fija la plataforma (Render).
CMD ["sh", "-c", "python manage.py serve --host 0.0.0.0 --port ${PORT}"]
