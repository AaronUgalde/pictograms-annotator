# Cómo se obtienen las sugerencias de pictogramas

Este documento explica cómo el anotador propone pictogramas para una oración y cómo encuentra pictogramas
**relacionados** por significado. El objetivo es ahorrar búsqueda manual sin sesgar el conjunto de datos:
el sistema propone y la persona decide.

Código principal: [`backend/app/suggest.py`](../backend/app/suggest.py) (capas 1–3) y
[`backend/app/related.py`](../backend/app/related.py) (capa 4).

## Resumen

Las sugerencias se calculan por capas. Cada capa solo actúa sobre lo que la anterior dejó sin resolver o
reordena lo que ya se encontró:

| Capa | Qué hace | Resultado |
|---|---|---|
| 1. Análisis del español | Separa la oración en palabras, obtiene su lema y su categoría gramatical (spaCy) | «comimos» → *comer* (verbo) |
| 2. Coincidencia con el catálogo | Busca en las palabras clave de ARASAAC, prefiriendo expresiones de varias palabras | «tener hambre» → un solo pictograma |
| 3. Orden de los candidatos | Ordena por memoria personal, tildes, categoría gramatical, popularidad… | El primero entra en la propuesta |
| 4. Relacionados por significado | Vectores de palabras (model2vec) | «coche» → *carro*, «doctor» → *médico* |

Las capas 1–3 producen **coincidencias** y, con ellas, la **propuesta inicial** (la secuencia que aparece ya
colocada en la barra inferior). La capa 4 produce **relacionados**: se muestran aparte, con la etiqueta
«relacionado», y **nunca** entran en la propuesta inicial.

No se usa ningún modelo generativo en ninguna capa.

## Capa 1: análisis del español

Se usa spaCy con el modelo pequeño de español (`es_core_news_sm`). Se eligió el pequeño porque ocupa unos
75 MB de RAM frente a unos 285 MB del mediano, con sugerencias prácticamente iguales, y así cabe en el plan
gratuito de Render. Si spaCy no está disponible, un analizador sencillo de respaldo separa palabras y
reconoce artículos, preposiciones y conjunciones.

De cada palabra se obtiene:

- **Lema**, con correcciones propias para casos que spaCy resuelve mal:
  - pronombres pegados al verbo: «lavarme» → *lavar*, «ponérselo» → *poner*;
  - imperativos con pronombre: «ayúdame» → *ayudar*.
- **Categoría gramatical** (sustantivo, verbo, adjetivo…). Artículos, preposiciones, conjunciones y
  auxiliares se marcan como **palabras vacías**: no se buscan solas y en la interfaz aparecen tachadas.

## Capa 2: coincidencia con el catálogo

El catálogo de ARASAAC (unos 13.900 pictogramas, copia versionada en `data/catalog/`) se carga en memoria
como un índice de **palabra clave normalizada → pictogramas**. Normalizar significa pasar a minúsculas y
quitar tildes (la ñ se conserva), para que «camion» encuentre «camión». Se indexan también los plurales que
trae ARASAAC.

La oración se recorre de izquierda a derecha buscando primero la **expresión más larga** (hasta 5 palabras)
que exista en el catálogo. Así «tener hambre» o «por favor» se resuelven con un único pictograma en lugar de
uno por palabra. Para cada fragmento se prueban varias claves en orden:

1. los lemas («comimos manzanas» → *comer manzana*);
2. el texto tal cual;
3. el verbo en infinitivo con el resto tal cual («lavarme las manos» → *lavar las manos*);
4. para palabras sueltas, el singular («vasos» → *vaso*) y variantes del verbo sin pronombre.

Si nada coincide y la palabra parece un verbo conjugado que el analizador no reconoció («pintan»), se
prueban los infinitivos posibles (*pintar*, *pinter*, *pintir*) y solo se aceptan si existen en el
catálogo **como verbos**.

## Capa 3: orden de los candidatos

Una misma clave puede tener varios pictogramas (por ejemplo, varios dibujos de «comer»). Se ordenan por,
en este orden de prioridad:

1. **Memoria personal:** cuántas veces *esta misma persona* eligió ese pictograma para esa palabra en
   oraciones anteriores. La memoria del equipo existe pero está desactivada: haría que todos los
   anotadores converjan y las respuestas dejarían de ser independientes.
2. **Coincidencia exacta con tildes:** «papá» (padre) y «papa» (patata) comparten clave sin tildes; gana el
   que coincide con la tilde escrita.
3. **Categoría gramatical:** si la palabra es un verbo, se prefieren las palabras clave que ARASAAC marca
   como verbo (lo mismo con sustantivos y adjetivos).
4. **Posición de la palabra clave** dentro del pictograma (la primera es la principal).
5. **Marcas de contenido:** los pictogramas marcados por ARASAAC como sexuales o violentos van al final.
6. **Popularidad** (descargas en ARASAAC).

El primer candidato de cada fragmento forma la propuesta inicial. Cada fragmento lleva además una
**confianza** (alta, media o baja) según la memoria personal y cuántos candidatos hay; las propuestas de
confianza baja se resaltan en la barra para que se revisen.

## Capa 4: relacionados por significado

Las capas anteriores solo encuentran pictogramas cuya palabra clave **coincide** con la oración. Si alguien
escribe «carro» y el pictograma se llama «coche», no lo encuentran. La capa 4 busca pictogramas **parecidos
en significado** usando vectores de palabras.

### Modelo

Se usa [model2vec](https://github.com/MinishLab/model2vec) con el modelo
`minishlab/potion-multilingual-128M` (licencia MIT, revisión fijada en `tools/build_related.py`). model2vec
destila un modelo de frases (*sentence transformer*) en una tabla fija de vectores: cada fragmento de
palabra tiene un vector de 256 números, y un texto se representa con la **media** de los vectores de sus
fragmentos. No hay red neuronal al consultar, solo una búsqueda en la tabla y una media.

Se descartó usar `sentence-transformers` directamente porque depende de PyTorch (más de 300 MB de RAM aun
con un modelo pequeño) y no cabe junto a spaCy en los 512 MB del plan gratuito de Render. Además, las
consultas aquí son de una o dos palabras, donde el contexto de un modelo de frases aporta poco.

### Adaptación para el servidor

El modelo completo ocupa 489 MB en memoria (500.353 fragmentos de muchos idiomas). Se recorta con
`tools/build_related.py`, que se ejecuta una vez (el Dockerfile lo hace al construir la imagen):

- Se conservan solo las **palabras completas en alfabeto latino** (178.206), en `float16`: unos 90 MB en
  disco, en `data/models/related/`.
- La tabla se abre con *mmap*: solo pasan a memoria las filas que se consultan. Medido con el catálogo
  real: **44 MB de RAM**, menos de 1 s de carga y unos 2 ms por consulta.
- El servidor calcula los vectores con numpy, sin instalar model2vec. Se comprobó que da exactamente el
  mismo vector que model2vec (similitud coseno 1,0).

### Cálculo

1. **Vectores del catálogo.** Al arrancar se calcula un vector por cada palabra clave del catálogo
   (unas 15.700 de 21.200; el resto contiene solo palabras que el modelo no conoce).
2. **Vector de la consulta.** La consulta es el lema del fragmento en la pestaña *Sugeridos* o el texto
   escrito en el buscador. Se pasa a minúsculas **conservando tildes** («mamá» y «mama» son palabras
   distintas para el modelo), se quitan las palabras vacías y se promedian los vectores. Si una palabra no
   está en la tabla pero coincide sin tildes con una palabra del catálogo, se usa la forma con tildes
   («camion» → «camión»).
3. **Similitud.** Se calcula la similitud coseno con todas las palabras clave. Cada pictograma toma la de
   su palabra clave más parecida.
4. **Filtros.**
   - Umbral mínimo de **0,45**: por debajo, casi todo es ruido.
   - Se excluyen los pictogramas que ya son coincidencias y los que **comparten una palabra** con la
     consulta («pasear al perro» para «perro»): esos ya los encuentra la búsqueda normal.
   - Hasta 8 relacionados por fragmento en *Sugeridos* y 40 en el buscador.

### Palabras que el modelo no conoce

Si una palabra no está completa en la tabla (por ejemplo «enojado», que el tokenizador partiría en
*en·oj·ado*), **no se calculan relacionados**. Promediar trozos de palabra da parecidos de ortografía, no de
significado: con el modelo sin recortar, «enojado» devolvía «candado». Es preferible no sugerir nada a
sugerir ruido.

### Dónde aparecen

- **Pestaña *Sugeridos*:** después de las coincidencias de cada palabra aparecen sus relacionados. Las
  palabras de la oración que no tienen ninguna coincidencia también reciben relacionados.
- **Buscador:** después de los resultados normales (que se calculan en el navegador), el navegador pide
  `/api/related?q=…` al dejar de escribir y añade los relacionados al final, sin mover la selección.

En ambos casos cada relacionado lleva la etiqueta **«relacionado»** y una nota al pasar el cursor
(«parecido en significado, no es coincidencia exacta»). `Intro` en el buscador solo coloca coincidencias:
un relacionado hay que elegirlo a propósito.

### Ejemplos con el catálogo real

| Consulta | Relacionados (similitud) |
|---|---|
| coche | carro (0,72) |
| camión | camioneta (0,72), furgoneta (0,49) |
| doctor | médico internista (0,82), medicina (0,72), médica (0,69) |
| hambre | alimentos (0,55), comida (0,53) |
| mamá | madre (0,80), madres (0,75) |
| lluvia | precipitaciones (0,71) |
| triste | tristeza (0,76) |
| enojado | — (el modelo no conoce la palabra completa) |

### Limitaciones conocidas

- **Parecidos de escritura.** Los vectores de model2vec conservan parte de la forma de la palabra, así que
  aparecen relacionados como «manejar» → *manija* (0,51), «gato» → *rato* o «sol» → *sola*. Su similitud
  es parecida a la de relaciones buenas, por lo que el umbral no los separa. La etiqueta «relacionado»
  avisa de que hay que revisarlos.
- **Variante del español.** ARASAAC es de España (*ordenador*, *coche*); el modelo ayuda a encontrar
  equivalentes de otras variantes (*computadora*, *carro*), pero no siempre.
- **Sin contexto.** Cada palabra tiene un único vector: «banco» mezcla el de sentarse y el del dinero.

Una mejora natural es armar un conjunto de prueba (consultas con los pictogramas esperados) para ajustar el
umbral con números, y comparar con la alternativa basada en WordNet: el catálogo ya trae los `synsets` de
cada pictograma.

## Por qué los relacionados van aparte

El conjunto de datos se usará para evaluar modelos de traducción de texto a pictogramas. Si la propuesta
inicial viniera de un modelo, quienes anotan tenderían a aceptarla y el conjunto favorecería a modelos
parecidos. Por eso:

- la propuesta inicial solo usa coincidencias del diccionario, lemas y memoria personal;
- los relacionados solo aparecen como opciones marcadas, nunca colocadas de antemano;
- en **modo ciego** no hay propuesta ni relacionados;
- cada anotación guarda si partió de la propuesta y si se aceptó sin cambios, para poder analizar el sesgo
  después.

## Parámetros y archivos

| Qué | Dónde | Valor |
|---|---|---|
| Longitud máxima de expresión | `suggest.MAX_N` | 5 palabras |
| Candidatos por fragmento | `suggest.MAX_CANDIDATES` | 12 |
| Relacionados por fragmento | `suggest.MAX_RELATED` | 8 |
| Umbral de similitud | `related.MIN_SCORE` | 0,45 |
| Modelo de spaCy | variable `SPACY_MODEL` | `es_core_news_sm` |
| Tabla de vectores | variable `ANNOTATOR_RELATED_DIR` | `data/models/related/` |

Para regenerar la tabla de vectores (descarga unos 500 MB y guarda unos 90 MB):

```bash
python tools/build_related.py
```

Si la tabla no existe, la aplicación funciona igual pero sin relacionados.
