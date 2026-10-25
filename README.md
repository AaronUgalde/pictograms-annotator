# Pictograms Annotator

Herramienta web para anotar frases en español con secuencias de pictogramas [ARASAAC](https://arasaac.org), pensada para construir un conjunto de evaluación con unas 30 personas. La interfaz está inspirada en un inventario de cuadrícula (pestañas, buscador, barra de secuencia). El diseño completo y sus razones están en [`PLAN.md`](PLAN.md).

## Puesta en marcha

Requiere Python 3.12 (con 3.14 spaCy falla al cargar modelos).

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install "es_core_news_md @ https://github.com/explosion/spacy-models/releases/download/es_core_news_md-3.8.0/es_core_news_md-3.8.0-py3-none-any.whl"

python manage.py init
python manage.py catalog download          # ~14.000 pictogramas; guarda una copia versionada en data/catalog/
python manage.py prefetch-images           # opcional: imágenes en local para trabajar sin conexión
python manage.py user add "Tu nombre" --role admin --base-url http://SERVIDOR:8000
python manage.py serve --host 0.0.0.0      # http://localhost:8000
```

Cada persona entra con **su enlace personal** (`/?t=…`). `manage.py user list` los muestra, y el panel de coordinación permite copiarlos o regenerarlos.

## Flujo de un proyecto

1. **Redactar y congelar la guía** (`docs/criterios-anotacion.md`; la versión se lee de la línea `**Versión:**` y queda registrada en cada anotación).
2. Crear personas (`user add`, o en el panel → *Personas*). Roles: `annotator`, `reviewer` (adjudica), `admin` (coordina).
3. Importar frases (`sentences import archivo.txt|.csv --batch piloto --pilot`, o en el panel).
4. **Congelar el catálogo** (panel → *Sistema*, o `catalog freeze`) antes de empezar, para que todos los IDs sean comparables.
5. Repartir (`assign --coverage 2 --triple-fraction 0.1 --blind-fraction 0.1 --seed 1`): cada frase la anotan ≥ 2 personas distintas; una fracción va **a ciegas** (sin propuesta del sistema).
6. Anotar → adjudicar desacuerdos (*Revisión*) → exportar JSONL/CSV (panel o `export`).

Hacer primero un **piloto** de 30–50 frases con 3–5 personas, corregir la guía y solo entonces lanzar el trabajo completo (PLAN 13.4).

## Uso de la interfaz

| Acción | Cómo |
|---|---|
| Colocar un pictograma | Clic en el catálogo: reemplaza la casilla activa y avanza |
| Añadir al final | `Mayús` + clic |
| Elegir casilla | Clic o teclas `1`–`9` |
| Quitar | `Supr`, arrastrar a la papelera, o botón de la papelera |
| Reordenar | Arrastrar casillas, o `Alt` + flechas |
| Deshacer / rehacer | `Ctrl+Z` / `Ctrl+Y` |
| Buscar | `/` (por nombre, sin tildes, o por número de ID); `Intro` coloca el primer resultado |
| Guardar y siguiente | `Ctrl+Intro` |
| Guía de criterios | `?` o `F1` |

Marcar una frase como **dudosa** u **omitida** exige una nota. En una frase *a ciegas* no hay pestaña de sugeridos; la pestaña *Usados antes* (tu propio historial) sí está disponible.

## Sugerencias y sesgo

Solo usan diccionario, lematización (spaCy) y la memoria personal de cada anotador; **nunca un modelo generativo**, porque el conjunto servirá para evaluar uno (PLAN 13.2). La memoria de equipo está desactivada por defecto (hace converger a los anotadores). Cada anotación guarda si partió de una propuesta, si se aceptó sin cambios y el tiempo empleado, y el panel compara el acuerdo con y sin sugerencias.

## Estructura

```
backend/app/   API FastAPI + SQLite (WAL): catalog, nlp, suggest, assign, metrics, review, export, backup
backend/manage.py   línea de órdenes
backend/tests/      pytest (usa un catálogo falso; no necesita red ni spaCy)
frontend/           HTML + CSS + JS sin dependencias ni paso de compilación (módulos ES)
data/               annotator.db, catalog/ (copias versionadas), sentences/ (ignorado en git: db, images, backups)
docs/               guía de criterios
```

Pruebas: `cd backend && ANNOTATOR_NLP=simple python -m pytest`.

## Licencia y atribución

Los pictogramas son de ARASAAC (Gobierno de Aragón), autor Sergio Palao, bajo **CC BY-NC-SA**: hay que citar la fuente, no usarlos comercialmente y compartir con la misma licencia. Un dataset publicado hereda esa licencia. La interfaz imita un patrón genérico de inventario; no usa texturas, fuentes, sonidos ni marcas de ningún juego (la fuente pixelada es Press Start 2P, OFL).
