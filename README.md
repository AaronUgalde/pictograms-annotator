# Anotador de pictogramas

Aplicación web para que los alumnos de una materia representen oraciones en español con pictogramas de [ARASAAC](https://arasaac.org). El docente sube las oraciones, cada alumno entra con su correo, recibe sus oraciones y elige para cada una la secuencia de pictogramas que la representa. El docente ve el avance de todos en una tabla y descarga los resultados.

## Cómo funciona

### Para el alumno

1. Abre el enlace de la aplicación y escribe **su correo**. No hay contraseña.
   - Si es la primera vez, se crea su cuenta y se le asignan sus oraciones (15 por defecto).
   - Si ya había entrado, sigue exactamente donde lo dejó, desde cualquier computadora.
2. Ve una oración con una **propuesta de pictogramas** ya colocada en la barra inferior.
3. Si la propuesta está bien, pulsa **Aceptar propuesta**. Si no, cambia las casillas que no le convenzan eligiendo otros pictogramas del catálogo (pestañas por tema y buscador).
4. Pulsa **Guardar y siguiente**. Arriba a la derecha siempre ve **cuántas oraciones le faltan**.
5. Si duda, puede marcar la oración como **Dudosa** u **Omitirla**, con una nota breve.

La guía de criterios (qué hacer con artículos, verbos, negaciones…) se abre con el botón **Guía** o la tecla `?`.

| Acción | Cómo |
|---|---|
| Poner un pictograma | Clic en el catálogo: reemplaza la casilla seleccionada y avanza |
| Añadir al final | `Mayús` + clic |
| Elegir casilla | Clic o teclas `1`–`9` |
| Quitar | `Supr` o arrastrar a la papelera |
| Reordenar | Arrastrar las casillas |
| Deshacer / rehacer | `Ctrl+Z` / `Ctrl+Y` |
| Buscar | `/` y escribir (sin importar tildes) |
| Guardar y siguiente | `Ctrl+Intro` |

### Para el docente (administrador)

En la pantalla de entrada, abre **Soy administrador** y escribe la contraseña (la variable `ADMIN_PASSWORD` del servidor). El panel tiene:

- **Oraciones:** sube un archivo `.txt` (una oración por línea) o `.csv` (columna `oracion`). Puedes subir más archivos cuando quieras; las repetidas se ignoran. Hay ejemplos en `data/sentences/`.
- **Ajustes:** cuántas oraciones recibe cada alumno (15 por defecto) y si se permiten cuentas nuevas.
- **Alumnos:** tabla con el correo de cada alumno, cuántas oraciones tiene, cuántas hizo, cuántas le faltan, una barra de progreso y si ya terminó.
- **Resultados:** descarga en CSV (se abre en Excel) o JSONL.

Los alumnos no pueden entrar al panel: todas las rutas de administración exigen la sesión de administrador, que solo se obtiene con la contraseña.

### Cómo se reparten las oraciones

No hace falta saber de antemano cuántos alumnos habrá:

- Cuando un alumno nuevo entra, recibe N oraciones (N = «oraciones por alumno»).
- Se eligen primero las oraciones **que tienen menos alumnos asignados**: las que no tiene nadie, luego las que tiene uno, y así. A igualdad, al azar. Un alumno nunca recibe la misma oración dos veces.
- Si subes más oraciones o aumentas N, a los alumnos que ya tienen cuenta se les completan la próxima vez que entren. Si bajas N, nadie pierde las que ya tenía.

Así, con pocos alumnos se cubren todas las oraciones al menos una vez, y con más alumnos cada oración acaba con dos o más respuestas. El resumen del panel muestra cuántas oraciones tienen 0, 1 o 2+ respuestas.

### Sugerencias

La propuesta inicial sale de un diccionario (el catálogo de ARASAAC) y de un analizador del español (spaCy, para pasar «comimos» a «comer»), más lo que ese mismo alumno eligió antes para esa palabra. No se usa ningún modelo generativo. Cada respuesta guarda si el alumno aceptó la propuesta sin cambios y cuánto tardó, por si se quiere analizar después.

## Publicar la aplicación (deploy): Render + Neon, gratis

La aplicación es **un solo contenedor Docker** (API + interfaz) y guarda los datos (alumnos, oraciones y respuestas) en **PostgreSQL**. Se publica gratis así:

- **Neon** guarda la base de datos.
- **Render** ejecuta la aplicación. Su plan gratuito no tiene disco, y no hace falta: el catálogo de pictogramas viaja dentro de la imagen y se carga en memoria al arrancar.

Usa unos 200 MB de RAM, holgado para los 512 MB del plan gratuito de Render.

Variables (ver `.env.example`):

| Variable | Para qué | Valor por defecto |
|---|---|---|
| `DATABASE_URL` | Cadena de conexión de PostgreSQL (Neon) | — (obligatoria) |
| `ADMIN_PASSWORD` | Contraseña del panel | — (obligatoria) |
| `ALLOWED_EMAIL_DOMAINS` | Solo esos dominios pueden crear cuenta, p. ej. `alumnos.uni.mx` | vacío = cualquier correo |
| `SENTENCES_PER_STUDENT` | Valor inicial de oraciones por alumno | `15` |

### 1. Base de datos en Neon

1. Crea una cuenta en [neon.com](https://neon.com) (no pide tarjeta) y un proyecto nuevo, con la región *AWS US East (Ohio)*, que queda cerca de Render.
2. En el panel del proyecto pulsa **Connect** y copia la *connection string*. Se ve así: `postgresql://usuario:clave@ep-xxxx.us-east-2.aws.neon.tech/neondb?sslmode=require`.

La aplicación crea sus tablas sola al arrancar. El plan gratuito da 0.5 GB, de sobra para miles de respuestas.

### 2. Aplicación en Render

1. Sube este repositorio a GitHub.
2. En [render.com](https://render.com): **New → Blueprint** y elige el repositorio. Render lee `render.yaml` y te pide:
   - `DATABASE_URL`: la cadena de Neon;
   - `ADMIN_PASSWORD`: tu contraseña del panel;
   - `ALLOWED_EMAIL_DOMAINS`: opcional, puedes dejarla vacía.
3. Espera a que termine la construcción (10–15 minutos la primera vez) y comparte la URL `https://….onrender.com`.

### Cómo se comporta el plan gratuito

- El servicio **se duerme tras 15 minutos sin visitas**. La siguiente visita tarda alrededor de un minuto en cargar; después funciona normal. Abre tú la página unos minutos antes de la clase.
- La base de Neon también se duerme sola y despierta en unos segundos con la primera consulta.
- Los pictogramas se vuelven a descargar de ARASAAC después de cada reinicio. Es automático; solo la primera carga es algo más lenta.
- El respaldo es **descargar el CSV o el JSONL** desde el panel. Neon guarda además un historial corto que permite restaurar.
- Para actualizar la aplicación basta con hacer `git push`: Render vuelve a desplegar solo, y los datos siguen en Neon.
- Para **borrar todos los datos**, abre el *SQL Editor* de Neon y ejecuta `DROP TABLE annotation_items, annotations, assignments, choice_memory, settings, sentences, users CASCADE;`. Después reinicia el servicio en Render (*Manual Deploy → Restart service*), que vuelve a crear las tablas vacías.

### Después de publicar

1. Entra como administrador y sube el archivo de oraciones.
2. Ajusta «oraciones por alumno» si no quieres 15.
3. Comparte la URL con los alumnos.
4. Cuando ya hayan entrado todos, puedes desactivar «Permitir que se creen cuentas nuevas» para evitar cuentas con correos mal escritos.
5. Descarga el CSV de vez en cuando como respaldo.

## Desarrollo local

Requiere Python 3.12 (con 3.14 spaCy falla al cargar el modelo) y una base PostgreSQL. Puede ser un segundo proyecto o *branch* de Neon, o un PostgreSQL local:

```bash
brew install postgresql@17 && brew services start postgresql@17
/opt/homebrew/opt/postgresql@17/bin/createdb annotator
```

Instalación y arranque:

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pip install "es_core_news_sm @ https://github.com/explosion/spacy-models/releases/download/es_core_news_sm-3.8.0/es_core_news_sm-3.8.0-py3-none-any.whl"

export DATABASE_URL=postgresql://localhost/annotator ADMIN_PASSWORD=prueba
python manage.py serve                               # http://localhost:8000
```

También puedes poner las variables en un archivo `.env` en la raíz del proyecto.

Pruebas: usan una base aparte que **se borra en cada prueba**; nunca uses la de producción.

```bash
/opt/homebrew/opt/postgresql@17/bin/createdb annotator_test
TEST_DATABASE_URL=postgresql://localhost/annotator_test python -m pytest
```

`manage.py` tiene órdenes opcionales: `sentences import`, `export`, `reset` (borra todos los datos), `catalog status` y `prefetch-images`. Todo lo habitual se hace desde el panel.

## Estructura

```
backend/app/
  main.py      API: entrada con correo, anotación, panel de administración
  assign.py    carga de oraciones y reparto automático
  stats.py     datos del panel (progreso por alumno)
  suggest.py   propuestas de pictogramas (catálogo + spaCy + memoria del alumno)
  catalog.py   catálogo ARASAAC, cargado en memoria desde data/catalog/
  export.py    CSV y JSONL
  db.py        base de datos PostgreSQL
frontend/      interfaz (HTML, CSS y JavaScript sin dependencias ni compilación)
data/catalog/  copia versionada del catálogo ARASAAC
data/sentences/ ejemplos de archivos de oraciones
docs/criterios-anotacion.md  guía de criterios que ven los alumnos
Dockerfile, render.yaml  despliegue
```

`PLAN.md` es el plan original del proyecto (pensado para un equipo con revisores); la aplicación actual es la versión simplificada descrita aquí.

## Licencia y atribución

Los pictogramas son de ARASAAC (Gobierno de Aragón), autor Sergio Palao, bajo **CC BY-NC-SA**: hay que citar la fuente, no usarlos comercialmente y compartir con la misma licencia. Un conjunto de datos publicado con ellos hereda esa licencia. La fuente pixelada es Press Start 2P (licencia OFL).
