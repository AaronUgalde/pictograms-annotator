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
- **Resultados:** descarga en CSV (se abre en Excel) o JSONL, y copia de seguridad de la base de datos.

Los alumnos no pueden entrar al panel: todas las rutas de administración exigen la sesión de administrador, que solo se obtiene con la contraseña.

### Cómo se reparten las oraciones

No hace falta saber de antemano cuántos alumnos habrá:

- Cuando un alumno nuevo entra, recibe N oraciones (N = «oraciones por alumno»).
- Se eligen primero las oraciones **que tienen menos alumnos asignados**: las que no tiene nadie, luego las que tiene uno, y así. A igualdad, al azar. Un alumno nunca recibe la misma oración dos veces.
- Si subes más oraciones o aumentas N, a los alumnos que ya tienen cuenta se les completan la próxima vez que entren. Si bajas N, nadie pierde las que ya tenía.

Así, con pocos alumnos se cubren todas las oraciones al menos una vez, y con más alumnos cada oración acaba con dos o más respuestas. El resumen del panel muestra cuántas oraciones tienen 0, 1 o 2+ respuestas.

### Sugerencias

La propuesta inicial sale de un diccionario (el catálogo de ARASAAC) y de un analizador del español (spaCy, para pasar «comimos» a «comer»), más lo que ese mismo alumno eligió antes para esa palabra. No se usa ningún modelo generativo. Cada respuesta guarda si el alumno aceptó la propuesta sin cambios y cuánto tardó, por si se quiere analizar después.

## Publicar la aplicación (deploy)

La aplicación es **un solo contenedor Docker** (API + interfaz) con una base SQLite. Lo único que necesita es:

1. La variable **`ADMIN_PASSWORD`** (obligatoria).
2. Un **disco persistente montado en `/data`**. Ahí vive la base de datos; sin disco persistente, las respuestas se pierden en cada reinicio.
3. Una sola instancia (no escalar a varias réplicas: SQLite escribe desde un único servidor).

El catálogo de ARASAAC viaja dentro de la imagen y se carga solo en el primer arranque. Las imágenes de los pictogramas se descargan de ARASAAC la primera vez que alguien las ve y quedan guardadas en `/data/images`. Necesita unos 300 MB de RAM: usa al menos 512 MB, mejor 1 GB.

Variables disponibles (ver `.env.example`):

| Variable | Para qué | Valor por defecto |
|---|---|---|
| `ADMIN_PASSWORD` | Contraseña del panel | — (obligatoria) |
| `ALLOWED_EMAIL_DOMAINS` | Solo esos dominios pueden crear cuenta, p. ej. `alumnos.uni.mx` | vacío = cualquier correo |
| `SENTENCES_PER_STUDENT` | Valor inicial de oraciones por alumno | `15` |
| `BACKUP_INTERVAL_HOURS` | Copia automática de la base en `/data/backups` | `6` |

### Opción A: Render (lo más sencillo)

1. Sube este repositorio a GitHub.
2. En [render.com](https://render.com): **New → Blueprint**, elige el repositorio. Render lee `render.yaml`, crea el servicio con su disco de 1 GB en `/data` y te pide `ADMIN_PASSWORD`.
3. Cuando termine, comparte la URL `https://….onrender.com` con los alumnos.

El disco persistente de Render requiere un plan de pago (Starter). El plan gratuito no sirve porque borra los datos.

### Opción B: Fly.io

```bash
fly launch --no-deploy --copy-config      # cambia el nombre "app" en fly.toml si ya está ocupado
fly volumes create datos --size 1 --region qro
fly secrets set ADMIN_PASSWORD='una-clave-larga'
fly deploy
```

### Opción C: un servidor propio (VPS o equipo de la universidad)

```bash
cp .env.example .env        # y edita ADMIN_PASSWORD
docker compose up -d --build
```

La aplicación queda en el puerto 8000 y los datos en la carpeta `./datos`. Para publicarla con HTTPS, ponla detrás de un proxy como Caddy o Nginx.

### Después de publicar

1. Entra como administrador y sube el archivo de oraciones.
2. Ajusta «oraciones por alumno» si no quieres 15.
3. Comparte la URL con los alumnos.
4. Cuando ya hayan entrado todos, puedes desactivar «Permitir que se creen cuentas nuevas» para evitar cuentas con correos mal escritos.
5. Descarga el CSV de vez en cuando como respaldo.

## Desarrollo local

Requiere Python 3.12 (con 3.14 spaCy falla al cargar el modelo).

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pip install "es_core_news_md @ https://github.com/explosion/spacy-models/releases/download/es_core_news_md-3.8.0/es_core_news_md-3.8.0-py3-none-any.whl"

ADMIN_PASSWORD=prueba python manage.py serve      # http://localhost:8000
python -m pytest                                    # pruebas (no necesitan red ni spaCy)
```

También puedes poner las variables en un archivo `.env` en la raíz del proyecto. `manage.py` tiene órdenes opcionales (`sentences import`, `export`, `backup`, `prefetch-images`), pero todo lo habitual se hace desde el panel.

## Estructura

```
backend/app/
  main.py      API: entrada con correo, anotación, panel de administración
  assign.py    carga de oraciones y reparto automático
  stats.py     datos del panel (progreso por alumno)
  suggest.py   propuestas de pictogramas (catálogo + spaCy + memoria del alumno)
  catalog.py   catálogo ARASAAC local
  export.py    CSV y JSONL
  db.py        esquema SQLite
frontend/      interfaz (HTML, CSS y JavaScript sin dependencias ni compilación)
data/catalog/  copia versionada del catálogo ARASAAC
data/sentences/ ejemplos de archivos de oraciones
docs/criterios-anotacion.md  guía de criterios que ven los alumnos
Dockerfile, docker-compose.yml, render.yaml, fly.toml  despliegue
```

`PLAN.md` es el plan original del proyecto (pensado para un equipo con revisores); la aplicación actual es la versión simplificada descrita aquí.

## Licencia y atribución

Los pictogramas son de ARASAAC (Gobierno de Aragón), autor Sergio Palao, bajo **CC BY-NC-SA**: hay que citar la fuente, no usarlos comercialmente y compartir con la misma licencia. Un conjunto de datos publicado con ellos hereda esa licencia. La fuente pixelada es Press Start 2P (licencia OFL).
