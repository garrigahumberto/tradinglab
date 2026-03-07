# Architecture Decision Log

**Estado:** Activo
**Versión:** 0.2
**Naturaleza:** Registro informativo de decisiones arquitectónicas
**Autoridad:** Ninguna. Los contratos derivados viven en el Blueprint.
**Alineación:** Blueprint Técnico · System Concept Specification
**Cambios respecto a v0.1:** ADR-002, ADR-003, ADR-004 y ADR-005 incorporados tras
desarrollo de Stage 1 (ConnectionManager) y Stage 2 (HistoricalHandler).

---

## Propósito

Este documento registra las decisiones arquitectónicas significativas
del sistema: qué se decidió, por qué, qué alternativas fueron
descartadas y cuáles son las consecuencias operativas.

Los ADRs no son contratos. Son el razonamiento que produjo contratos.
Cuando una sección del Blueprint referencia un ADR, este documento
provee el contexto completo de esa decisión.

---

## ADR-001 — Prohibición de Imputación de Datos y Frontera Feature/Signal

**Estado:** Aprobado
**Fecha:** 2026-03
**Documentos afectados:** Blueprint Técnico secciones 1.2, 1.4 · SCS secciones 1.16, 1.17

### Decisión

El sistema prohíbe en todas sus capas la imputación silenciosa de
datos ausentes. Los NaN deben propagarse de forma transparente desde
Data Layer hasta Strategy, que es la única capa autorizada a decidir
el comportamiento ante datos incompletos.

Se establece formalmente la frontera epistemológica entre Feature
(hecho matemático no falsable) y Signal (interpretación empírica
falsable).

### Contexto

El sistema documental anterior (SAD) contenía principios de rigor
probabilístico que no fueron trasladados a la nueva arquitectura
durante la redefinición. Esta decisión recupera y formaliza esos
principios dentro del nuevo marco.

### Problema

Sin esta frontera explícita, los implementadores tienden a:
- Usar `.fillna(0)` o `ffill()` en Processing para evitar errores
  de cálculo, introduciendo precios ficticios en las features.
- Introducir heurísticas de mercado dentro del cálculo de variables,
  colapsando la distinción entre observación e interpretación.
- Construir estrategias sobre datos que parecen limpios pero
  contienen asunciones implícitas no auditables.

### Alternativas descartadas

**Alternativa A — Imputación permitida con flag:**
Permitir imputación pero marcar el dato como imputado mediante
una columna auxiliar. Descartada porque introduce complejidad
de estado en capas que deben ser puras, y porque el flag puede
ignorarse silenciosamente en implementaciones futuras.

**Alternativa B — Responsabilidad en Data Layer:**
Que Data Layer entregue siempre DataFrames completos sin NaN.
Descartada porque obliga a Data Layer a tomar decisiones
estratégicas sobre qué hacer ante huecos, violando la separación
de responsabilidades.

### Consecuencias

- Processing debe estar preparado para recibir y propagar NaN.
- La librería común de cálculo debe comportarse de forma predecible
  ante NaN en todos sus inputs.
- Strategy debe implementar lógica explícita de manejo de
  incertidumbre. No puede asumir inputs siempre completos.
- Los tests de la librería común deben incluir casos con NaN.

---

## ADR-002 — Tipos Nullable Int64 para Campos Opcionales del Canonical Data Model

**Estado:** Aprobado
**Fecha:** 2026-03
**Documentos afectados:** Phase 0 Implementation Spec v1.1 §5 · Stage 2 (HistoricalHandler)
**Origen:** Decisión tomada durante implementación y auditoría de Stage 2.

### Decisión

Los campos `volume` y `barCount` del Canonical Data Model se tipan como
`pandas.Int64Dtype()` (Int64 nullable), no como `float64`.

IBKR devuelve `-1` para indicar ausencia de dato en ambos campos.
El valor `-1` debe convertirse a `pd.NA` en el momento de la normalización,
antes de que el dato entre al DataBuffer o sea persistido.

### Contexto

ADR-001 establece que los datos ausentes deben representarse como NaN
y nunca ser enmascarados. Esta decisión es la materialización de ADR-001
a nivel de tipo de dato para campos opcionales del CDM.

### Problema

Si `volume` y `barCount` se tipan como `float64`:
- IBKR entrega `-1` para ausencia, que en `float64` se almacena como
  `-1.0` — un valor numérico aparentemente legítimo.
- El dato ausente queda enmascarado. Strategy podría recibir volúmenes
  negativos sin saber que representan ausencia.
- Viola directamente ADR-001.

Si se usa `float64` con NaN:
- NaN en `float64` es técnicamente posible pero semánticamente ambiguo
  para campos que representan enteros (conteos de barras, volumen).
- `Int64` nullable es el tipo correcto: entero, admite `pd.NA`, sin
  ambigüedad semántica.

### Alternativas descartadas

**Alternativa A — float64 con conversión de -1 a NaN:**
Técnicamente funcional pero semánticamente incorrecto. `volume` y
`barCount` son conteos enteros. Representarlos como float introduce
imprecisión innecesaria y podría causar errores en operaciones
aritméticas posteriores que asuman integralidad.

**Alternativa B — int64 estándar (no nullable):**
`int64` de numpy no admite NaN. Ante ausencia de dato la única opción
sería usar un valor centinela (-1, 0) violando ADR-001, o lanzar
excepción. Ninguna opción es aceptable.

### Consecuencias

- HistoricalHandler y RealTimeHandler deben convertir `-1` de IBKR
  a `pd.NA` durante la normalización, antes de insertar en el CDM.
- Los tests de normalización deben verificar que `-1` produce `pd.NA`
  y que el tipo resultante es `Int64`.
- La librería common debe ser compatible con `Int64` nullable en
  operaciones sobre `volume` y `barCount`.
- Los tests de la librería common deben incluir casos con `pd.NA`
  en estos campos.
- DataBuffer almacena y retorna DataFrames con tipos `Int64` preservados.
- PersistenceManager debe verificar que Parquet serializa y deserializa
  `Int64` nullable correctamente.

---

## ADR-003 — Clave Compuesta del DataBuffer

**Estado:** Aprobado
**Fecha:** 2026-03
**Documentos afectados:** Phase 0 Implementation Spec v1.1 §6 · Stage 4 (DataBuffer)
**Origen:** Decisión tomada durante diseño de Stage 4 y alineación con el contrato
de `get_snapshot`.

### Decisión

El DataBuffer indexa sus entradas mediante una clave compuesta de tres
elementos:

```python
clave: tuple = (uid, tipo_dato, temporalidad_base)
# donde uid = (symbol, conId, exchange, secType)
```

Ejemplo:
```python
(("AAPL", 265598, "NASDAQ", "STK"), "historical_bars", "1m")
```

### Contexto

El contrato de `get_snapshot` requiere tres parámetros:
`uid`, `tipo_dato` y `temporalidad_base`. El DataBuffer debe
poder resolver cada combinación de forma independiente y unívoca.
Un mismo activo puede tener múltiples tipos de dato y múltiples
temporalidades activas simultáneamente.

### Problema

Si el DataBuffer se indexa únicamente por `uid`:
- Un Job que requiere `historical_bars` a 1m y otro que requiere
  `rt_bars` a 1m del mismo activo compartirían la misma entrada,
  corrompiendo los datos del primero o del segundo.
- La resolución en `get_snapshot` requeriría lógica adicional fuera
  del buffer, distribuyendo responsabilidad.

Si el DataBuffer se indexa por `(uid, tipo_dato)`:
- No soporta múltiples temporalidades del mismo activo y tipo de dato.
- Restringe capacidad de expansión futura sin cambio de contrato.

### Alternativas descartadas

**Alternativa A — Indexar solo por uid:**
Descartada. Un mismo activo puede tener datos de distintos tipos
y temporalidades activos simultáneamente. La clave simple genera
colisiones inevitables.

**Alternativa B — Indexar por (uid, tipo_dato):**
Descartada. Insuficiente para soportar múltiples temporalidades.
Además, el contrato de `get_snapshot` ya expone `temporalidad_base`
como parámetro de primer nivel, indicando que debe ser parte de la
resolución de la clave.

### Consecuencias

- DataBuffer implementa `dict[tuple[tuple, str, str], pd.DataFrame]`.
- Toda operación de escritura (DataDispatcher) y lectura (`get_snapshot`)
  construye la clave completa antes de operar.
- Ningún componente puede operar sobre el DataBuffer usando únicamente
  `symbol` como identificador. Hacerlo es inválido por diseño.
- SubscriptionRegistry usa `(uid, tipo_dato)` como clave, que es un
  subconjunto de la clave del buffer — la distinción es intencional:
  las suscripciones no dependen de la temporalidad.

---

## ADR-004 — Política de Costura entre Datos Históricos y RealTimeBars

**Estado:** Aprobado
**Fecha:** 2026-03
**Documentos afectados:** Phase 0 Implementation Spec v1.1 §9 · Stage 7 (DataDispatcher)
**Origen:** Decisión tomada durante diseño de Stage 7 y especificación del flujo de
datos en el Roadmap v1.2.

### Decisión

El DataDispatcher aplica la siguiente política de costura entre el
histórico recibido de HistoricalHandler y las barras en tiempo real
recibidas de RealTimeHandler:

1. **Secuencia obligatoria:** RealTimeHandler no se activa hasta que
   HistoricalHandler confirme recepción completa del histórico
   mediante el evento `historicalDataEnd`.

2. **Solapamiento:** Si el timestamp de la primera RT bar es igual o
   anterior al timestamp de la última barra histórica, la RT bar se
   descarta silenciosamente como duplicado esperado.

3. **Hueco:** Si existe un gap mayor a 1 minuto entre la última barra
   histórica y la primera RT bar, el hueco se registra en
   `critical_error.log` y la ejecución continúa sin interrupciones.

4. **Sin imputación:** No se interpolan barras para cubrir el hueco.
   El gap queda representado como ausencia real en el buffer.
   Ver ADR-001.

### Contexto

La transición entre datos históricos y datos en tiempo real es
inherentemente imprecisa: IBKR puede devolver la última barra histórica
con el mismo timestamp que la primera RT bar, o puede existir un pequeño
gap por latencia o por el tiempo de procesamiento de la solicitud.
El sistema necesita una política determinista para ambos casos.

### Problema

Sin una política explícita:
- Un implementador podría intentar imputar el hueco para mantener
  continuidad aparente, violando ADR-001.
- Otro podría activar RT antes de confirmar el histórico, introduciendo
  barras duplicadas o desordenadas en el buffer.
- El comportamiento ante solapamiento quedaría indefinido, generando
  resultados no reproducibles entre sesiones.

### Alternativas descartadas

**Alternativa A — Activar RT inmediatamente, deduplicar después:**
Descartada. Introduce complejidad de estado en DataDispatcher y
genera condiciones de carrera entre la recepción del histórico y
la llegada de las primeras RT bars.

**Alternativa B — Imputar el hueco con barras sintéticas:**
Descartada. Viola directamente ADR-001. Un hueco real no debe
representarse como continuidad artificial.

**Alternativa C — Detener el sistema ante cualquier hueco:**
Descartada. Los huecos son esperados y operativamente normales
(reinicios de TWS, pacing, cortes de sesión). Detener el sistema
ante cada hueco lo hace inoperable en condiciones reales.

### Consecuencias

- DataDispatcher mantiene el timestamp de la última barra histórica
  consolidada para resolver la costura con RT.
- RealTimeHandler no emite barras hacia DataDispatcher hasta recibir
  autorización explícita de que el histórico está completo.
- `critical_error.log` debe soportar entradas estructuradas de tipo
  `GAP_DETECTED` con campos: `uid`, `last_historical_ts`,
  `first_rt_ts`, `gap_seconds`.
- Los tests de DataDispatcher deben cubrir los tres escenarios:
  continuidad perfecta, solapamiento y hueco.

---

## ADR-005 — Provisionalidad de Métodos de Solicitud en ConnectionManager

**Estado:** Aprobado — pendiente de migración en Stage 8
**Fecha:** 2026-03
**Documentos afectados:** Stage 1 (ConnectionManager) · Stage 2 (HistoricalHandler) ·
Stage 3 (RealTimeHandler) · Stage 8 (DataLayer Façade)
**Origen:** Decisión de diseño incremental tomada durante Stage 1 para permitir
avanzar sin bloquear el desarrollo.

### Decisión

Los métodos `request_historical_bars()` y `subscribe_realtime_bars()`
residen provisionalmente en ConnectionManager durante Fase 0, con la
condición expresa de que serán migrados a sus componentes naturales
(HistoricalHandler y RealTimeHandler respectivamente) cuando la
façade DataLayer sea ensamblada en Stage 8.

Esta es una decisión de desarrollo incremental, no una decisión
arquitectónica permanente.

### Contexto

Durante Stage 1, HistoricalHandler y RealTimeHandler no existían aún.
Colocar los métodos de solicitud en ConnectionManager permitió:
- Completar y testear ConnectionManager de forma autónoma.
- Que HistoricalHandler (Stage 2) pudiera desarrollarse con una
  interfaz real disponible, sin necesidad de stubs adicionales.
- Avanzar sin introducir dependencias circulares entre stages.

La ubicación provisional no refleja la arquitectura final, pero
respeta el principio de no crear abstracciones preventivas: los
Handlers no existían en Stage 1 y no debían crearse anticipadamente.

### Problema que resuelve la migración futura

En la arquitectura final, ConnectionManager es responsable exclusivamente
de la conexión y de la válvula de control de pacing. La lógica de
qué solicitar, cuándo y cómo normalizar la respuesta pertenece a
HistoricalHandler y RealTimeHandler. Mantener indefinidamente los
métodos de solicitud en ConnectionManager viola la separación de
responsabilidades del Blueprint §1.2.

### Condición de migración

En Stage 8 (DataLayer Façade), durante el ensamblado de los componentes:
- `request_historical_bars()` se migra a HistoricalHandler, que
  invoca `ConnectionManager` internamente.
- `subscribe_realtime_bars()` se migra a RealTimeHandler, con la
  misma lógica.
- ConnectionManager retiene únicamente: `connect()`, `disconnect()`,
  `can_request()`, `_reset_pacing_state()` y el manejo de
  reconexión/pacing.

### Consecuencias

- HistoricalHandler (Stage 2) y RealTimeHandler (Stage 3) invocan
  hoy los métodos desde ConnectionManager. Esta dependencia es
  correcta y no debe eliminarse prematuramente.
- En Stage 8, los métodos migran. Los tests de Stage 1 que cubren
  esos métodos en ConnectionManager deberán actualizarse o trasladarse.
- Ningún componente fuera de los Handlers debe invocar
  `request_historical_bars()` o `subscribe_realtime_bars()`
  directamente desde ConnectionManager. Hacerlo crearía una
  dependencia que dificulta la migración.

---

## ADR-006 — Canonical Data Model e Invariantes del Índice Temporal

**Estado:** Aprobado
**Fecha:** 2026-03
**Documentos afectados:** Blueprint Técnico §Data Layer · Stage 2 (HistoricalHandler) · Stage 3 (RealTimeHandler) · Stage 4 (DataBuffer) · Stage 7 (DataDispatcher)

### Decisión

El sistema adopta un Canonical Data Model (CDM) único para representar barras OHLCV dentro del Data Layer.

Todo componente que produzca barras (HistoricalHandler, RealTimeHandler o fuentes futuras) debe normalizar sus datos a esta estructura antes de entregarlos al sistema.

La estructura obligatoria es:

`index: DatetimeIndex[datetime64[ns, UTC], name="timestamp"]`

*   `open`:      `float64`
*   `high`:      `float64`
*   `low`:       `float64`
*   `close`:     `float64`
*   `volume`:    `Int64`   (nullable)
*   `barCount`:  `Int64`   (nullable)

No se permiten variaciones en:
*   nombres de columnas
*   tipos de datos
*   zona horaria del índice
*   estructura del DataFrame

El CDM es el único formato aceptado por:
*   DataDispatcher
*   DataBuffer
*   Processing Layer
*   Strategy Layer

### Invariantes del Canonical Data Model

Los siguientes invariantes deben cumplirse en todo DataFrame que represente barras dentro del sistema.

**1 — Índice temporal en UTC**
El índice debe ser: `DatetimeIndex[datetime64[ns, UTC]]`
Todos los timestamps recibidos desde fuentes externas deben convertirse a UTC durante la normalización. Esto evita inconsistencias cuando distintas bolsas utilizan zonas horarias diferentes.

**2 — Índice monotónicamente creciente**
Las barras deben ordenarse temporalmente: `timestampₙ < timestampₙ₊₁`
Los productores de datos deben aplicar: `df = df.sort_index()`
Esto es requisito para operaciones posteriores como resampling, rolling windows, joins temporales y stitching histórico/RT.

**3 — Unicidad del timestamp**
Cada timestamp representa exactamente una barra.
Si una fuente externa produce duplicados (por reconexión, pacing o reintentos), el productor debe resolverlos antes de entregar el DataFrame al sistema.
Política adoptada: `df = df[~df.index.duplicated(keep="last")]`
La última barra recibida se considera la más completa.

**4 — Eliminación de timestamps inválidos**
Durante la normalización pueden generarse timestamps inválidos (`NaT`) si la fuente entrega datos corruptos o no parseables.
Estas filas deben eliminarse: `df = df[~df.index.isna()]`
Una barra sin timestamp válido no es una observación utilizable.

**5 — Tipos numéricos obligatorios**
Las columnas OHLC se tipan como `float64`.
Los campos opcionales se tipan como `Int64` (nullable) según ADR-002.
Esto permite representar ausencia de dato mediante `pd.NA`.

**6 — Política de datos ausentes**
El sistema no imputa datos ausentes. Los valores faltantes deben propagarse como `NaN` o `pd.NA` hacia capas superiores. Ver ADR-001.

### Contexto

El sistema recibe datos desde IBKR mediante dos fuentes:
*   Historical API
*   RealTimeBars API

Ambas presentan inconsistencias conocidas:
*   timestamps en distintos formatos
*   valores `-1` para campos ausentes
*   barras duplicadas bajo reconexión
*   timestamps no parseables en casos raros

Sin una normalización estricta, cada componente del sistema debería manejar estas inconsistencias de forma independiente, aumentando la complejidad y el riesgo de errores.

### Alternativas descartadas

**Alternativa A — Permitir múltiples formatos internos:**
Cada módulo acepta su propio formato de datos. Descartada porque introduce adaptadores innecesarios, aumenta el acoplamiento entre módulos y dificulta auditorías de datos.

**Alternativa B — Normalización en DataBuffer:**
Delegar la normalización al buffer. Descartada porque DataBuffer debe ser una estructura pasiva y la limpieza de datos es responsabilidad del productor.

**Alternativa C — Normalización parcial:**
Solo estandarizar nombres de columnas. Descartada porque no resuelve problemas de timezone, no elimina duplicados y no garantiza invariantes del índice.

### Consecuencias

*   `HistoricalHandler` debe producir DataFrames compatibles con el CDM.
*   `RealTimeHandler` debe aplicar la misma normalización antes de emitir barras.
*   `DataDispatcher` puede asumir que todos los DataFrames cumplen los invariantes.
*   `DataBuffer` puede almacenar datos sin realizar validación adicional.
*   `Processing Layer` puede operar sobre los datos sin realizar limpieza previa.

### Relación con otros ADR

| ADR | Relación |
| :--- | :--- |
| ADR-001 | Define política de NaN |
| ADR-002 | Define tipos nullable |
| ADR-004 | Usa el índice temporal para stitching histórico/RT |

### Beneficios arquitectónicos

La existencia de un CDM estricto produce: desacoplamiento entre módulos, pipeline determinista, auditoría de datos simplificada y menor complejidad en capas superiores.

---

## Registro de versiones

| Versión | Cambio |
|---|---|
| v0.1 | ADR-001 incorporado. ADR-002 reservado. |
| v0.2 | ADR-002 al ADR-005 incorporados tras desarrollo de Stage 1 y Stage 2. |
| v0.3 | ADR-006 incorporado (Canonical Data Model) |
