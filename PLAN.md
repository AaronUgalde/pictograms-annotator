> **Nota:** este documento es el plan original (30 anotadores, revisores, adjudicación, modo ciego). La aplicación actual está simplificada: los alumnos entran solo con su correo, no hay revisores y el reparto es automático. Para saber cómo funciona hoy, lee el [README](README.md).

# Pictograms Annotator: plan del proyecto

Herramienta para anotar frases en español con secuencias de pictogramas ARASAAC, con una interfaz inspirada en el inventario del modo creativo de Minecraft.

## 1. Objetivo

Que una persona pueda etiquetar por sí sola un conjunto de frases en español, eligiendo para cada una la secuencia de pictogramas que la representa. El sistema propone y la persona decide. Cuanto menos tenga que buscar a mano, más rápido y más consistente será el dataset.

## 2. Contexto: qué es ARASAAC

- ARASAAC es el Centro Aragonés para la Comunicación Aumentativa y Alternativa (Gobierno de Aragón). Mantiene una biblioteca abierta de pictogramas para comunicación aumentativa y alternativa (CAA).
- Licencia: **CC BY-NC-SA**. Si se publica el dataset hay que citar la fuente, no usarlo comercialmente y compartirlo con la misma licencia. Autor de los pictogramas: Sergio Palao (ARASAAC).
- El tamaño del catálogo varía según la fuente (de unos 12.000 a más de 25.000). La cifra real saldrá de descargar el catálogo.
- API pública usada por otros proyectos (por confirmar en https://arasaac.org/developers/api):
  - Búsqueda: `https://api.arasaac.org/v1/pictograms/es/bestsearch/{texto}` y `/search/{texto}`
  - Imagen: `https://api.arasaac.org/v1/pictograms/{id}?download=false`
  - Catálogo completo por idioma (ruta por verificar).

## 3. Proyectos similares (revisar antes de construir)

| Proyecto | Qué ofrece | Utilidad para nosotros |
|---|---|---|
| Interfaces web de PROPICTO (Dion et al.) | Tres interfaces: anotar textos con ARASAAC, crear vocabulario, post-editar frases anotadas | El más cercano. Verificar si aceptan español y si se pueden instalar por cuenta propia |
| PictoEduca (ACL 2026 Findings) | Dataset español texto a pictogramas, con anotación automática y corrección experta | Referencia de método y de criterios de calidad |
| ARASAAC-WN (github.com/getalp/Arasaac-WN) | Vínculo entre WordNet y ARASAAC | Sugerencias por significado, no solo por palabra |
| Text2Picto (KU Leuven) | Traducción automática, demos en español | Referencia, no sirve para anotar |
| Pictotraductor, AraTraductor, Pictar | Traductores texto a pictogramas | Referencia de arquitectura |
| Picto-Selector, AraWord | Pictogramas al escribir texto | Referencia de interfaz |
| PictoFacile | Elegir pictogramas por palabra | Referencia de interfaz |

**Fase 0:** probar las interfaces de PROPICTO y leer PictoEduca. Si cubren la necesidad, se reutilizan; si no, se construye esta herramienta.

## 4. Decisiones de diseño

- **La unidad de anotación es la secuencia.** Cada frase termina con una lista ordenada de pictogramas, sin obligar a que cada palabra tenga uno. Cubre palabras sin pictograma ("el", "de"), expresiones con un solo pictograma ("por favor") y conceptos con varios ("tener hambre").
- **Catálogo local de ARASAAC.** Se descarga una vez la lista completa con sus palabras clave y se guarda en una base propia. Búsquedas instantáneas, sin depender de la API en cada clic, y dataset reproducible aunque ARASAAC cambie.
- **La persona siempre decide.** Toda sugerencia es una propuesta editable.
- **Registro de versión.** Cada anotación guarda el ID del pictograma, la palabra clave, la fecha y la versión del catálogo.

## 5. Flujo de trabajo de la persona

1. Carga las frases (`.txt` o `.csv`) o continúa una sesión anterior.
2. Ve una frase con una secuencia ya propuesta.
3. Si está bien, la acepta con un clic o una tecla. Si no, corrige las casillas que no le convenzan.
4. Guarda y pasa a la siguiente. Lo normal debe ser un clic por frase.
5. Puede marcar una frase como *dudosa* u *omitida* para revisión posterior.

## 6. Interfaz: inspirada en el inventario creativo de Minecraft

La idea es reutilizar una metáfora que mucha gente ya conoce: un inventario con una cuadrícula de objetos, pestañas por categoría y una barra rápida (hotbar) con los objetos en uso. Aquí los "objetos" son pictogramas y la "barra rápida" es la secuencia de la frase.

### 6.1 Equivalencias

| Minecraft creativo | En esta herramienta |
|---|---|
| Cuadrícula del inventario | Catálogo de pictogramas, con scroll |
| Pestañas por categoría | Categorías (Sugeridos, Usados antes, Alimentos, Acciones, Lugares…) |
| Pestaña de búsqueda con cuadro de texto | Buscador sobre todo el catálogo |
| Hotbar de 9 casillas | Secuencia de pictogramas de la frase |
| Casilla seleccionada con marco blanco | Casilla activa de la secuencia |
| Teclas 1 a 9 | Seleccionar la casilla 1 a 9 de la secuencia |
| Papelera (destruir objeto) | Casilla para quitar un pictograma de la secuencia |
| Tooltip con el nombre al pasar el cursor | Palabra clave, ID y categorías del pictograma |
| Shift + clic para mover rápido | Shift + clic añade el pictograma al final de la secuencia |
| Barra de desplazamiento lateral | Scroll del catálogo con carga progresiva |

### 6.2 Pantalla (esquema)

```
┌────────────────────────────────────────────────────────────────────┐
│ Frase 12 de 200:  "Quiero un vaso de agua fría"       [dudosa] [omitir]
├────────────────────────────────────────────────────────────────────┤
│ [Sugeridos][Usados][Acciones][Comida][Lugares][Personas]…  [🔍 ______]
│ ┌──┬──┬──┬──┬──┬──┬──┬──┬──┐                                    ▲ │
│ │  │  │  │  │  │  │  │  │  │   cuadrícula del catálogo         █ │
│ ├──┼──┼──┼──┼──┼──┼──┼──┼──┤   (casillas cuadradas,            █ │
│ │  │  │  │  │  │  │  │  │  │    una por pictograma)            ░ │
│ ├──┼──┼──┼──┼──┼──┼──┼──┼──┤                                    ▼ │
│ │  │  │  │  │  │  │  │  │  │                                      │
│ └──┴──┴──┴──┴──┴──┴──┴──┴──┘                                      │
├────────────────────────────────────────────────────────────────────┤
│ Secuencia de la frase (hotbar):                                    │
│ ┌──┐┌──┐┌──┐┌──┐┌──┐┌──┐┌──┐┌──┐┌──┐  ┌──┐                         │
│ │1 ││2 ││3 ││4 ││5 ││6 ││7 ││8 ││9 │  │🗑│                         │
│ └──┘└──┘└──┘└──┘└──┘└──┘└──┘└──┘└──┘  └──┘                         │
│ [◀ anterior]            [aceptar todo]          [guardar y siguiente ▶]
└────────────────────────────────────────────────────────────────────┘
```

Si una frase necesita más de 9 pictogramas, la secuencia continúa en una segunda fila o con scroll horizontal. El límite de 9 solo existe en Minecraft, aquí no debe limitar.

### 6.3 Interacciones

- **Añadir un pictograma:** clic en una casilla del catálogo lo coloca en la casilla activa de la secuencia (reemplazando lo que hubiera) y avanza a la siguiente. También se puede arrastrar a una casilla concreta.
- **Insertar al final:** Shift + clic.
- **Cambiar un pictograma:** seleccionar la casilla en la secuencia (clic o tecla 1 a 9) y elegir otro en el catálogo.
- **Quitar:** arrastrar a la papelera, o tecla Supr sobre la casilla activa.
- **Reordenar:** arrastrar casillas dentro de la secuencia.
- **Deshacer y rehacer:** Ctrl+Z y Ctrl+Y.
- **Tooltip** al pasar el cursor: palabra clave, ID, categorías y sinónimos.
- **Vista previa:** al pasar el cursor sobre un pictograma del catálogo, la casilla activa lo muestra de forma temporal.
- **Todo con teclado:** flechas para moverse por el catálogo, Enter para elegir, Tab para cambiar de zona, `/` para ir al buscador, Ctrl+Enter para guardar y pasar a la siguiente.

### 6.4 Contenido de las pestañas

1. **Sugeridos:** lo que propone el sistema para esta frase (por palabra y por significado).
2. **Usados antes:** pictogramas que esta persona eligió para las palabras de esta frase en frases anteriores.
3. **Categorías de ARASAAC:** alimentos, acciones, lugares, personas, etc. (confirmar que la API expone categorías).
4. **Buscar:** cuadro de texto sobre todo el catálogo, tolerante a tildes y a coincidencias parciales, más búsqueda por significado (ARASAAC-WN) y entrada directa por ID.
5. **Recientes:** los últimos pictogramas elegidos.

### 6.5 Estilo visual

- Panel gris con relieve, casillas cuadradas con borde hundido (sombra oscura arriba-izquierda, clara abajo-derecha), marco blanco para la casilla activa, pestañas con forma de carpeta. Se dibuja todo con CSS propio, sin imágenes del juego.
- Tipografía pixelada **solo en títulos y pestañas**. Las palabras clave de los pictogramas y la frase usan una fuente muy legible, porque se leen todo el día.
- Los pictogramas se muestran grandes dentro de la casilla (mínimo 64 px, ideal 96 px), con la palabra clave debajo o en el tooltip.
- Tema claro y oscuro, con contraste suficiente.
- Animaciones mínimas: solo respuesta a acciones (colocar, quitar, cambiar).

### 6.6 Aspectos legales y de accesibilidad

- Es una interfaz **inspirada** en el inventario: no se usan texturas, fuentes, sonidos, logotipos ni el nombre de Minecraft. La mecánica (cuadrícula, pestañas, hotbar) es un patrón de interfaz genérico. Conviene no usar la marca en el nombre ni en la documentación pública.
- Casillas con foco visible, navegación completa por teclado, etiquetas accesibles para lectores de pantalla y objetivos táctiles grandes si se usa en tableta.
- Fuente pixelada solo decorativa, nunca para información importante.

## 7. Sugerencias automáticas, en capas

1. **Procesamiento del lenguaje** con spaCy en español: tokenizar, lematizar ("comimos" → "comer") y detectar la categoría gramatical para ignorar artículos y preposiciones.
2. **Coincidencia contra el catálogo local:** lema contra palabras clave, y expresiones de varias palabras antes que palabras sueltas.
3. **Memoria de decisiones:** lo que esa persona (o el equipo) eligió antes para ese lema sale primero.
4. **Significado (opcional):** ARASAAC-WN para ordenar candidatos por sentido cuando una palabra es ambigua.
5. **Modelo de lenguaje: descartado para este dataset.** Como el conjunto servirá para evaluar un modelo, proponer secuencias con un modelo generativo sesgaría la anotación (ver sección 13.2).

Las sugerencias llegan ya colocadas en la secuencia, con un indicador de confianza en las dudosas, salvo en el modo ciego.

## 8. Arquitectura

- **Backend:** Python con FastAPI y SQLite. Guarda frases, anotaciones, catálogo y memoria de decisiones. Local, simple y suficiente para decenas de miles de frases.
- **Frontend:** web ligera en HTML, CSS y JavaScript, sin framework pesado. La cuadrícula del catálogo usa carga progresiva (virtualización) porque son miles de imágenes.
- **Ejecución:** servidor compartido al que acceden los ~30 anotadores desde el navegador (ver sección 13.3).
- **Imágenes:** servidas desde ARASAAC o guardadas localmente una vez (respetando la licencia) para trabajar sin conexión.

### Estructura de carpetas propuesta

```
pictograms-annotator/
├── PLAN.md
├── README.md
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI
│   │   ├── db.py              # SQLite
│   │   ├── catalog.py         # descarga y consulta del catálogo ARASAAC
│   │   ├── nlp.py             # spaCy: lemas y categorías
│   │   ├── suggest.py         # sugerencias en capas
│   │   └── export.py          # JSONL y CSV
│   ├── requirements.txt
│   └── tests/
├── frontend/
│   ├── index.html
│   ├── css/inventory.css      # estilo de inventario
│   └── js/
│       ├── grid.js            # catálogo con scroll
│       ├── hotbar.js          # secuencia
│       ├── tabs.js
│       └── api.js
├── data/
│   ├── catalog/               # copia versionada del catálogo
│   └── sentences/             # frases a anotar
└── docs/
    └── criterios-anotacion.md
```

### Modelo de datos básico

- `sentences`: id, texto, lote, estado.
- `annotations`: id, id de frase, anotador, estado (hecha, dudosa, omitida), fecha, versión del catálogo.
- `annotation_items`: id de anotación, posición, id del pictograma, palabra clave, token de origen (opcional).
- `catalog`: id del pictograma, palabras clave, categorías, versión.
- `choice_memory`: lema, id del pictograma, veces elegido, anotador.

## 9. Exportación

- **JSONL:** una línea por frase, con texto, secuencia de IDs y palabras clave, estado, anotador, fecha y versión del catálogo.
- **CSV:** la misma información en forma plana, para revisar en hoja de cálculo.
- Opcional: formato similar al de ToPicto (secuencia de términos más lista de IDs alineada) por si el dataset se usará en tareas comparables.

## 10. Calidad del dataset

- **Guía breve de criterios** antes de empezar (`docs/criterios-anotacion.md`): artículos, tiempos verbales, plurales, negaciones, expresiones y palabras sin pictograma. Sin ella, dos personas anotan distinto la misma frase.
- **Doble anotación de una muestra** (por ejemplo, 10 %) y medición del acuerdo entre anotadores.
- **Estado "dudoso"** y una vista de revisión para quien actúe de revisor.
- **Registro** de quién anotó cada frase y cuándo.
- **Piloto de 20 a 50 frases** antes de lanzar el trabajo completo.

## 11. Fases de construcción

| Fase | Contenido | Resultado |
|---|---|---|
| 0 | Revisar PROPICTO y PictoEduca | Decidir reutilizar o construir |
| 1 | Versión mínima: cargar frases, buscar, armar secuencia, exportar | Borrador funcional (ya existe un prototipo) |
| 2 | Catálogo local, lematización y sugerencias por palabra | Búsquedas rápidas y propuestas |
| 3 | Interfaz de inventario: cuadrícula, pestañas, hotbar, teclado, memoria, deshacer | Interfaz cómoda de verdad |
| 4 | Multiusuario, asignación con solapamiento, revisión y métricas de acuerdo | Obligatoria: 30 anotadores y uso como conjunto de evaluación |
| 5 | Sugerencias con modelo de lenguaje | Descartada para el conjunto de evaluación (ver sección 13) |

Recomendación: llegar hasta la fase 4. Antes de la fase 4 debe existir la guía de criterios (sección 13.4).

## 12. Riesgos y puntos por verificar

- **Licencia:** ARASAAC es CC BY-NC-SA. Citar la fuente y compartir igual.
- **Cambios en ARASAAC:** nuevos pictogramas, IDs y palabras clave. Se mitiga guardando la versión del catálogo.
- **Ambigüedad y criterios:** es el mayor riesgo de calidad. Se mitiga con la guía y la doble anotación.
- **Rendimiento:** miles de imágenes en la cuadrícula. Se mitiga con carga progresiva y miniaturas en caché.
- **Fondo de las imágenes:** comprobar si los PNG de ARASAAC traen fondo transparente o blanco, para que se vean bien sobre las casillas grises.
- **Por confirmar antes de construir:** rutas exactas de la API, si expone categorías, y si las interfaces de PROPICTO aceptan español y se pueden instalar por cuenta propia.

## 13. Requisitos confirmados y su efecto en el diseño

### 13.1 Respuestas

| Pregunta | Respuesta |
|---|---|
| Número de anotadores | Alrededor de 30 personas |
| Número de frases | Por definir |
| Dispositivo | Solo computador |
| Uso del dataset | Evaluar la calidad de un modelo de traducción a pictogramas |
| Guía de criterios | No existe, hay que redactarla |

### 13.2 Consecuencias de ser un conjunto de evaluación

- **Rigor alto.** Los errores de anotación se convierten en errores de medición del modelo. La calidad pesa más que la velocidad.
- **Varias referencias válidas.** Una frase puede tener más de una secuencia correcta. Se guardan todas las anotaciones independientes de cada frase, y además una versión final adjudicada (la "referencia dorada"). Así se pueden usar métricas con múltiples referencias.
- **Solapamiento obligatorio.** Cada frase la anotan al menos 2 personas distintas (ideal 3 en una muestra). Con 30 anotadores se reparte de forma automática para equilibrar la carga y cruzar parejas distintas.
- **Adjudicación.** Un revisor (o dos) resuelve las frases donde las anotaciones difieren mucho. La interfaz tiene una vista de comparación lado a lado.
- **Medidas de acuerdo.** Porcentaje de coincidencia exacta de secuencias, distancia de edición normalizada entre secuencias de IDs, y acuerdo por posición. Se calculan por pareja de anotadores y por frase, para detectar frases problemáticas y personas que se desvían de la guía.
- **Sin sesgo del sistema en la anotación.** Las sugerencias no deben provenir del modelo que se va a evaluar. Si el anotador parte de una propuesta parecida a la del modelo, el conjunto favorecería a ese modelo. Reglas:
  - Las sugerencias usan solo diccionario, lemas y memoria personal, nunca un modelo generativo (la fase 5 queda descartada para este dataset).
  - Los relacionados por significado (vectores de palabras, no generativo) se muestran aparte y marcados; nunca forman parte de la propuesta inicial.
  - En una muestra de frases con solapamiento se ofrece un **modo ciego**: la secuencia empieza vacía.
  - Se registra por cada anotación si partió de una sugerencia y si la aceptó sin cambios, y el tiempo que tomó. Permite analizar el sesgo después.

### 13.3 Consecuencias de 30 anotadores

- **Servidor compartido** en lugar de ejecución local por persona. Una máquina en la red de la institución o un servidor pequeño en la nube.
- **Identificación sencilla** de cada anotador (usuario y clave simple o enlace personal), sin necesidad de un sistema complejo.
- **Base de datos:** SQLite en modo WAL alcanza para 30 personas con escrituras ligeras. Si se prevén muchas frases o más usuarios, pasar a PostgreSQL.
- **Panel de coordinación** para quien dirige el proyecto: progreso por persona, frases pendientes, frases dudosas, acuerdo entre anotadores, exportación.
- **Copias de seguridad** automáticas de la base y exportación periódica.
- **Un solo catálogo congelado.** Todos anotan con la misma versión del catálogo de ARASAAC, fijada antes de empezar, para que los IDs sean comparables.

### 13.4 Guía de criterios (hay que redactarla)

Es el entregable más importante antes de anotar. Se propone este proceso:

1. **Borrador v0** (1 a 2 días): decidir criterios sobre los casos que más aparecen. Temas mínimos:
   - artículos, preposiciones y conjunciones (¿se omiten o se representan?);
   - tiempos verbales y personas (¿se representa el tiempo? ¿cómo?);
   - plurales, género y diminutivos;
   - negación y preguntas;
   - expresiones y locuciones (¿un pictograma o varios?);
   - nombres propios y números;
   - palabras sin pictograma y qué hacer en ese caso;
   - elección entre pictogramas parecidos de una misma palabra;
   - orden de la secuencia (¿sigue el orden de la frase?).
2. **Piloto** con 30 a 50 frases anotadas por 3 a 5 personas.
3. **Revisión de desacuerdos:** cada frase con baja coincidencia revela un criterio ambiguo. Se corrige la guía con ejemplos.
4. **Congelar v1** y repetir un piloto corto. Solo cuando el acuerdo sea aceptable se lanza la anotación completa.
5. **Versionar la guía.** Cada anotación guarda la versión de la guía con la que se hizo. Si se cambia una regla a mitad del trabajo, se identifican las frases afectadas.
6. **Capacitación breve** (30 a 45 minutos) y prueba corta con las 30 personas antes de empezar.

La guía vive en `docs/criterios-anotacion.md` y se muestra también dentro de la herramienta, con un acceso rápido a los ejemplos.

### 13.5 Consecuencias de usar solo computador

- Se diseña para pantallas de escritorio (mínimo 1366×768). Sin gestos táctiles.
- Prioridad al teclado y al ratón: atajos completos, arrastrar y soltar, tooltips al pasar el cursor.
- Casillas del catálogo algo más pequeñas, para ver más pictogramas a la vez.

### 13.6 Pendiente

- **Número de frases.** Define cuánto trabajo hay por persona. Con 30 anotadores y cobertura de 2 a 3 anotaciones por frase, cada persona anota entre 2/30 y 3/30 del total. Por ejemplo, con 1.000 frases y cobertura 2, serían unas 67 frases por persona.
- **Revisor(es):** quién adjudica los desacuerdos y cuántos.
- **Dónde se aloja el servidor** y quién lo administra.
- **Plazo y calendario** de la anotación.


## 14. Estado de avance (actualizado 25-oct-2026)

| Fase | Estado | Notas |
|---|---|---|
| 0 | Sin hacer | Revisar PROPICTO y PictoEduca. De facto se decidió construir; queda documentar la comparación. |
| 1 | Hecha | Cargar frases, buscar, secuencia, exportar. |
| 2 | Hecha (capas 1–4) | spaCy, coincidencia con expresiones, memoria personal. Capa 4: pictogramas **relacionados** por significado con vectores de palabras model2vec (`backend/app/related.py`), en una lista aparte con etiqueta, fuera de la propuesta inicial y desactivados en modo ciego. ARASAAC-WN (los `synsets` ya están en el catálogo) queda como alternativa sin hacer. |
| 3 | Hecha | Cuadrícula virtualizada, pestañas, buscador (tildes, parcial, ID), secuencia, arrastrar/soltar, papelera, deshacer/rehacer, teclado, vista previa, tooltips, tema claro/oscuro. |
| 4 | Hecha | Multiusuario por enlace, reparto con solapamiento y modo ciego, adjudicación lado a lado, métricas de acuerdo, panel, copias, exportación. |
| 5 | Descartada | Ver 13.2. |

Verificado con el catálogo real (13.891 pictogramas) y Chrome: flujo de anotación, adjudicación, exportación, login inválido y tema oscuro a 1366×768, sin errores de consola.

### Pendiente (decisiones humanas, no de código)

- Redactar y congelar la guía v1 tras el piloto (la actual es `v0-borrador`). Casos que aún no cubre: pronombres sujeto y reflexivos («me», «yo»: hoy se proponen como pictograma «yo»), y números compuestos.
- Número de frases, revisores, alojamiento del servidor y calendario (13.6).
- Capacitación de 30–45 min y prueba corta con las 30 personas.
- Congelar el catálogo (`catalog freeze`) antes de empezar.
- Opcional: capa de significado (ARASAAC-WN) y exportación en formato ToPicto.
