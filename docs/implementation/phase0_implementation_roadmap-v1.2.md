# Phase 0 — Implementation Roadmap

**Estado:** Aprobado para implementación
**Versión:** 1.2
**Naturaleza:** Guía operativa de implementación
**Autoridad:** Derivada del Blueprint Técnico v1.0.1 y Phase 0 Implementation Spec v1.1
**Alineación:** Blueprint Técnico · System Concept Specification · Architecture Decision Log · Development Governance Framework
**Cambios respecto a v1.1:** Scheduler incorporado en estructura y stages; esquema MarketDB corregido; campos de JobConfig alineados con spec; ProcessingEngine stub con stage propio.

---

## 1. Objetivo de Fase 0

Fase 0 establece la **infraestructura base de ingestión y persistencia de datos de mercado**.

Al finalizar esta fase el sistema debe ser capaz de:

- Conectarse a Interactive Brokers (IBKR) con reconexión automática y absorción de interrupciones.
- Suscribirse a activos definidos por los Jobs.
- Recibir Historical Bars y RealTimeBars.
- Almacenar datos de forma persistente en MarketDB con metadatos de contrato obligatorios.
- Mantener un buffer en memoria con acceso thread-safe.
- Exponer snapshots inmutables mediante el contrato `get_snapshot`.
- Controlar el ciclo de ejecución de Jobs mediante el Scheduler.
- Detectar y registrar huecos en log estructurado.

Esta fase **no implementa lógica de trading, indicadores estratégicos ni generación de señales**.

> **Restricción formal:** Ningún componente de esta fase puede introducir lógica perteneciente
> a Fase 1 o superior. La violación de esta restricción activa revisión formal de gobernanza.

---

## 2. Estructura del Repositorio

La implementación seguirá estrictamente la estructura definida en Phase 0 Implementation Spec v1.1 §15.

```
production/

    data_layer/
        data_layer.py
        connection_manager.py
        historical_handler.py
        realtime_handler.py
        data_dispatcher.py
        data_buffer.py
        persistence_manager.py
        subscription_registry.py

    session/
        session_controller.py
        scheduler.py
        job_config.py

    processing/
        processing_engine.py          ← stub en Fase 0

    common/
        indicators.py
        resampling.py
        statistics.py

marketdb/
    {asset_type}/
        {symbol}/
            contract_metadata.json
            {year}/{month}/

tests/
docs/
```

> Los directorios `strategy/` y `execution/` **no existen en Fase 0**.
> Su creación anticipada viola la Regla Anti-Abstracciones Preventivas del Blueprint §1.8.

---

## 3. Arquitectura del Data Layer

El Data Layer es el núcleo técnico de Fase 0.
La façade `DataLayer` es el único punto de acceso desde el resto del sistema.

```
DataLayer (façade)
    │
    ├─ ConnectionManager
    │       ├─ HistoricalHandler
    │       └─ RealTimeHandler
    │
    ├─ SubscriptionRegistry
    ├─ DataDispatcher
    ├─ DataBuffer
    └─ PersistenceManager
```

Ningún componente externo al Data Layer accede directamente a sus componentes internos.

---

## 4. Contrato Público del DataLayer

El archivo `production/data_layer/data_layer.py` implementa la façade oficial.

Métodos públicos contractuales (firma obligatoria, no modificable sin Revisión Formal de Gobernanza):

```python
def subscribe_asset(uid: tuple, data_types: list[str], historical_window: int) -> None
def unsubscribe_asset(uid: tuple) -> None
def get_snapshot(uid: tuple, tipo_dato: str, temporalidad_base: str) -> pd.DataFrame
def shutdown() -> None
```

**Garantías de `get_snapshot`:**
- Devuelve una copia independiente del buffer. Nunca una referencia.
- El DataFrame retornado puede contener NaN. Data Layer no imputa valores ausentes. Ver ADR-001.
- Devuelve únicamente la ventana histórica declarada en JobConfig.
- No fuerza actualización de buffers ni altera suscripciones.

---

## 5. Identificador Canónico de Activo (UID)

Todo activo se identifica mediante el UID canónico. Es obligatorio en todos los componentes.

```python
uid: tuple = (symbol: str, conId: int, exchange: str, secType: str)
```

Ejemplo:
```python
("AAPL", 265598, "NASDAQ", "STK")
```

Cualquier operación de buffer, suscripción o persistencia que use únicamente `symbol`
como clave es inválida por diseño.

---

## 6. Estructura de JobConfig

Todo Job debe declararse mediante una estructura `JobConfig` explícita.
El SessionController no puede instanciar un Job sin una configuración válida.

```python
@dataclass
class JobConfig:
    uid: tuple                  # UID canónico: (symbol, conId, exchange, secType)
    data_types: list[str]       # ["historical_bars", "rt_bars"]
    timeframe_base: str         # "1m"
    historical_window: int      # Ventana histórica requerida en número de barras
    persistence_policy: str     # "always" | "on_close"
    strategy_config: None       # Siempre None en Fase 0
    execution_config: None      # Siempre None en Fase 0
```

**Reglas:**
- `strategy_config` y `execution_config` son siempre `None` en Fase 0.
  Su presencia con valor no-None es una violación de alcance.
- `historical_window` determina cuántas barras retiene DataBuffer para este Job.
- La validación de JobConfig ocurre en SessionController antes de instanciar el Job.

---

## 7. Límites Operativos de Fase 0

| Parámetro | Valor |
|---|---|
| Activos máximos simultáneos | 5 |
| Jobs simultáneos | 3 |
| Temporalidad base | 1 minuto |
| Tipo de contrato con lógica analítica | `STOCK` únicamente |

---

## 8. Plan de Implementación por Stages

La implementación se realiza en stages incrementales verificables.
Cada stage produce componentes funcionales con tests unitarios aprobados
antes de pasar al siguiente.

Los implementadores no deben crear archivos fuera de los declarados en cada stage.

```
Stage 1  — ConnectionManager
Stage 2  — HistoricalHandler
Stage 3  — RealTimeHandler
Stage 4  — DataBuffer
Stage 5  — SubscriptionRegistry
Stage 6  — PersistenceManager
Stage 7  — DataDispatcher
Stage 8  — DataLayer Façade
Stage 9  — Librería Common (base mínima)
Stage 10 — JobConfig
Stage 11 — Scheduler
Stage 12 — SessionController
Stage 13 — ProcessingEngine Stub
```

---

## Stage 1 — ConnectionManager

**Archivos:**
```
CREATE  production/data_layer/connection_manager.py
```

**Responsabilidades:**
- Establecer conexión con TWS / IB Gateway mediante `ib_insync`.
- Mantener y exponer estado de conexión.
- Ejecutar reconexión automática con backoff exponencial ante desconexión.
  Secuencia: 1s, 2s, 4s, 8s, 16s, 32s, máximo 60s.
- Absorber el reinicio diario forzoso de TWS sin exponer la interrupción a capas superiores.
  El gap generado se registra en `critical_error.log` como hueco esperado.
- Aplicar la política de degradación ante pacing limits:
  - Ante throttling: pausa mínima de 10 segundos antes de reintentar.
  - Ante 3 rechazos consecutivos: backoff exponencial adicional, máximo 5 minutos.
  - El sistema nunca insiste ante rechazos reiterados del broker.
  - Todo evento de pacing limit se registra en `critical_error.log`.
- Exponer métodos para solicitar datos al broker:
  `connect()` · `disconnect()` · `request_historical_bars()` · `subscribe_realtime_bars()`

**Resultado esperado:**
El sistema puede conectarse, reconectarse automáticamente y gestionar interrupciones
del broker sin propagar errores a capas superiores.

---

## Stage 2 — HistoricalHandler

**Archivos:**
```
CREATE  production/data_layer/historical_handler.py
```

**Responsabilidades:**
- Solicitar datos históricos a IBKR mediante `reqHistoricalData`.
- Gestionar la recepción completa de la respuesta (evento `historicalDataEnd`).
- Normalizar barras recibidas al Canonical Data Model.
- Entregar barras normalizadas al DataDispatcher.
- No activar RealTimeBars hasta confirmar recepción completa del histórico.

**Canonical Data Model (estructura obligatoria de salida):**
```
[timestamp (datetime64[ns, UTC]), open, high, low, close, volume, barCount]
```

**Resultado esperado:**
El sistema puede solicitar y recibir datos históricos de un activo
en el formato canónico del sistema.

---

## Stage 3 — RealTimeHandler

**Archivos:**
```
CREATE  production/data_layer/realtime_handler.py
```

**Responsabilidades:**
- Gestionar `reqRealTimeBars` de IBKR.
- Recibir barras de 5 segundos.
- Agregar barras de 5 segundos a la barra de 1 minuto en construcción.
- Marcar la barra de 1 minuto como consolidada al completarse el intervalo.
- Entregar únicamente barras consolidadas al DataDispatcher. Nunca barras parciales.
- Normalizar al Canonical Data Model.

**Resultado esperado:**
El sistema recibe barras en tiempo real y entrega barras de 1 minuto
consolidadas al DataDispatcher.

---

## Stage 4 — DataBuffer

**Archivos:**
```
CREATE  production/data_layer/data_buffer.py
```

**Responsabilidades:**
- Mantener en memoria las barras consolidadas activas por activo.
- Indexar por clave compuesta: `(uid_canónico, tipo_dato, temporalidad_base)`.
- Gestionar la ventana de retención: retener únicamente las últimas N barras,
  donde N es el `historical_window` máximo declarado entre Jobs activos para ese activo.
- Garantizar thread-safety en todas las operaciones de lectura y escritura mediante `threading.RLock`.
- `get_snapshot` devuelve siempre `df.copy()`. Nunca una referencia directa al DataFrame interno.

**Estructura interna:**
```python
# Clave: ((symbol, conId, exchange, secType), tipo_dato, timeframe)
# Valor: pd.DataFrame con esquema Canonical Data Model
dict[tuple[tuple, str, str], pd.DataFrame]
```

**Resultado esperado:**
El sistema puede almacenar y consultar barras recientes en memoria
de forma thread-safe e inmutable desde el exterior.

---

## Stage 5 — SubscriptionRegistry

**Archivos:**
```
CREATE  production/data_layer/subscription_registry.py
```

**Responsabilidades:**
- Registrar y mantener suscripciones activas por `(uid, tipo_dato)`.
- Evitar suscripciones duplicadas entre Jobs: ante dos Jobs que declaren
  el mismo `(uid, tipo_dato)`, mantener una única suscripción activa y registrar
  ambos como consumidores.
- Cancelar una suscripción únicamente cuando el último consumidor registrado sea eliminado.
- Amortiguación de cancelaciones: diferir hasta 5 segundos la cancelación de una suscripción
  ante cancelaciones y reactivaciones sucesivas del mismo activo dentro de esa ventana,
  para evitar violaciones de pacing. Esta lógica es interna y no se expone.

**Resultado esperado:**
El sistema gestiona correctamente múltiples consumidores de datos
sin suscripciones duplicadas ni cancelaciones prematuras.

---

## Stage 6 — PersistenceManager

**Archivos:**
```
CREATE  production/data_layer/persistence_manager.py
```

**Responsabilidades:**
- Persistir barras en formato Parquet bajo el esquema de partición canónico.
- Persistir y mantener actualizado `contract_metadata.json` por activo.
- Rechazar persistencia de barras si no existe metadata de contrato asociada.
- Garantizar integridad pre-persistencia: rechazar DataFrames con columnas
  faltantes o con timestamps no-UTC.
- Los huecos se registran en log. No se interpolan ni corrigen automáticamente.

**Esquema de partición físico (obligatorio):**
```
/marketdb/{asset_type}/{symbol}/{year}/{month}/{symbol}_{year}{month}.parquet
```

Ejemplo:
```
/marketdb/STK/AAPL/2026/03/AAPL_202603.parquet
```

**Campos obligatorios de contract_metadata.json:**
```json
{
  "symbol": "AAPL",
  "conId": 265598,
  "exchange": "NASDAQ",
  "secType": "STK",
  "currency": "USD",
  "multiplier": 1,
  "trading_hours": "...",
  "tipo_contrato": "STK",
  "expiry": null
}
```

**Frecuencia de escritura:**
- `RealTimeBars`: escritura por barra consolidada durante sesión activa.
- `HistoricalBars`: escritura en batch al recibir `historicalDataEnd`.
- Cierre de sesión: flush forzoso de cualquier dato en buffer no persistido.

**Resultado esperado:**
Las barras recibidas se persisten correctamente en disco con el esquema
canónico y con metadatos de contrato asociados.

---

## Stage 7 — DataDispatcher

**Archivos:**
```
CREATE  production/data_layer/data_dispatcher.py
```

**Responsabilidades:**
- Recibir barras normalizadas desde HistoricalHandler y RealTimeHandler.
- Actualizar DataBuffer con cada barra consolidada.
- Enviar datos a PersistenceManager.
- Aplicar la política de costura histórico + RT bars:
  1. Esperar recepción completa del histórico (`historicalDataEnd`) antes de activar RT.
  2. Al recibir la primera RT bar, verificar continuidad con la última barra histórica.
  3. Si existe solapamiento (timestamp RT ≤ última barra histórica): descartar RT bar duplicada.
  4. Si existe hueco (gap > 1 minuto): registrar en `critical_error.log` y continuar.
  5. Ningún mecanismo de imputación se aplica. Ver ADR-001.
- Registrar huecos detectados en log estructurado.
- Garantizar thread-safety: toda escritura al buffer usa lock explícito.

**Resultado esperado:**
Los datos fluyen correctamente a buffer y persistencia.
La costura entre histórico y tiempo real es determinista y sin imputación silenciosa.

---

## Stage 8 — DataLayer Façade

**Archivos:**
```
CREATE  production/data_layer/data_layer.py
```

**Responsabilidades:**
- Orquestar todos los componentes internos del Data Layer.
- Exponer el contrato público hacia el resto del sistema.
- Absorber internamente las interrupciones de IBKR. Las capas superiores nunca reciben errores de broker.
- Gestionar el ciclo de vida completo: inicialización, operación y shutdown.

**Métodos públicos (contractuales):**
```python
def subscribe_asset(uid: tuple, data_types: list[str], historical_window: int) -> None
def unsubscribe_asset(uid: tuple) -> None
def get_snapshot(uid: tuple, tipo_dato: str, temporalidad_base: str) -> pd.DataFrame
def shutdown() -> None
```

**Resultado esperado:**
El Data Layer es accesible mediante una API estable.
Ningún componente externo necesita conocer la estructura interna.

---

## Stage 9 — Librería Common (base mínima)

**Archivos:**
```
CREATE  production/common/indicators.py
CREATE  production/common/resampling.py
CREATE  production/common/statistics.py
```

**Alcance en Fase 0 (únicamente lo necesario para esta fase):**

`resampling.py`:
- Función de resampling de barras de 1 minuto a temporalidades superiores.
- Las funciones deben ser puras y sin estado.
- Deben propagar NaN de forma transparente. Ver ADR-001.

`indicators.py` y `statistics.py`:
- Estructura base vacía con docstring de propósito.
- Sin implementación de indicadores estratégicos. Éstos pertenecen a Fase 1.

> **Restricción:** No se implementan funciones diseñadas para fases futuras.
> La librería se expande únicamente cuando la fase activa lo requiere.

**Resultado esperado:**
Las utilidades base necesarias para Fase 0 están disponibles.
La estructura que usarán las fases posteriores está establecida sin anticipar su contenido.

---

## Stage 10 — JobConfig

**Archivos:**
```
CREATE  production/session/job_config.py
```

**Responsabilidades:**
- Definir la estructura de configuración de un Job.
- Implementar validación de la configuración antes de ser usada por SessionController.

**Estructura obligatoria (spec v1.1 §7):**
```python
@dataclass
class JobConfig:
    uid: tuple                  # UID canónico: (symbol, conId, exchange, secType)
    data_types: list[str]       # ["historical_bars", "rt_bars"]
    timeframe_base: str         # "1m"
    historical_window: int      # Número de barras a retener en buffer
    persistence_policy: str     # "always" | "on_close"
    strategy_config: None       # Siempre None en Fase 0
    execution_config: None      # Siempre None en Fase 0
```

**Validaciones requeridas:**
- `uid` debe tener exactamente 4 elementos con tipos correctos.
- `data_types` debe contener únicamente valores del conjunto permitido.
- `historical_window` debe ser un entero positivo.
- `strategy_config` y `execution_config` deben ser `None`. Si no lo son, lanzar excepción.

**Resultado esperado:**
Los Jobs tienen configuración estructurada, validable y coherente con el contrato del sistema.

---

## Stage 11 — Scheduler

**Archivos:**
```
CREATE  production/session/scheduler.py
```

**Responsabilidades:**
- Activar el ciclo de ejecución de cada Job según la temporalidad declarada en su JobConfig.
- Garantizar que ningún Job ejecute múltiples ciclos dentro de la misma unidad temporal.
- Impedir que Processing invoque `get_snapshot` con frecuencia superior a la permitida:
  bloquear activaciones anticipadas hasta que haya transcurrido la temporalidad completa
  desde la última activación del Job.
- Llevar registro del último timestamp de activación por Job.

**Mecanismo:**
- Loop de control interno con tick mínimo de 1 segundo.
- Por cada Job activo: comparar timestamp actual con `última_activación + temporalidad_base`.
- Si el intervalo no se ha cumplido: no activar el Job en ese tick.
- Si el intervalo se ha cumplido: activar el Job y registrar el nuevo timestamp de activación.

**Resultado esperado:**
El sistema controla el ritmo de ejecución de Jobs de forma determinista.
Ningún Job puede consultar datos con mayor frecuencia que la declarada en su configuración.

---

## Stage 12 — SessionController

**Archivos:**
```
CREATE  production/session/session_controller.py
```

**Responsabilidades:**
- Cargar y validar JobConfigs.
- Registrar las necesidades de datos de cada Job en Data Layer mediante `subscribe_asset`.
- Instanciar y destruir Jobs.
- Coordinar el Scheduler para controlar el ciclo de ejecución de Jobs activos.
- Gestionar shutdown ordenado del sistema: detener Jobs, vaciar buffers pendientes, cerrar conexión.
- Es la única entidad autorizada a modificar el universo de activos monitoreados en tiempo de ejecución.

**Restricciones:**
- No procesa datos.
- No accede a IBKR directamente.
- No conoce lógica de mercado.

**Resultado esperado:**
El sistema puede inicializar, operar y detener múltiples Jobs simultáneamente
de forma controlada y reproducible.

---

## Stage 13 — ProcessingEngine Stub

**Archivos:**
```
CREATE  production/processing/processing_engine.py
```

**Propósito:**
Stub mínimo para validar el contrato `get_snapshot` end-to-end.
No implementa lógica analítica. No calcula indicadores.

**Responsabilidades del stub:**
- Invocar `DataLayer.get_snapshot(uid, tipo_dato, temporalidad_base)`.
- Verificar que el DataFrame retornado respeta el Canonical Data Model:
  columnas correctas, tipos correctos, índice timestamp UTC.
- Verificar que el DataFrame retornado es una copia independiente
  (modificarlo no afecta al buffer interno).
- Registrar en log el resultado de la verificación.

**Restricción ADR-001:**
El stub no puede aplicar `.fillna()`, `ffill()` ni `bfill()` sobre los datos recibidos.
Su propósito es verificar el contrato, no limpiar datos.

**Resultado esperado:**
El pipeline completo Data Layer → Processing está validado end-to-end.
El contrato `get_snapshot` se verifica con datos reales o con datos estáticos
que respeten exactamente el esquema canónico.

---

## 9. Criterios de Finalización de Fase 0

Fase 0 se considera completada cuando el sistema demuestra:

- [ ] Conexión estable con IBKR
- [ ] Reconexión automática tras desconexión con backoff exponencial
- [ ] Absorción silenciosa del reinicio diario de TWS
- [ ] Manejo de pacing limits sin fallar ni insistir ante rechazos reiterados
- [ ] Recepción correcta de datos históricos
- [ ] Recepción correcta de RealTimeBars
- [ ] Costura determinista entre histórico y tiempo real
- [ ] Persistencia correcta en el esquema de partición canónico de MarketDB
- [ ] Persistencia de `contract_metadata.json` por cada activo
- [ ] Mantenimiento de buffer en memoria con UID canónico y thread-safety
- [ ] Snapshots accesibles mediante `get_snapshot` con copia inmutable garantizada
- [ ] Scheduler controlando el ciclo de ejecución sin activaciones anticipadas
- [ ] Operación estable con 3 Jobs concurrentes sobre 5 activos sin condiciones de carrera
- [ ] Registro de huecos de datos en log estructurado
- [ ] Sistema capaz de reconstruir cualquier sesión pasada exclusivamente con datos propios persistidos

---

## 10. Notas de Gobernanza

Durante Fase 0:

- No se introducen optimizaciones prematuras.
- No se crean abstracciones no definidas en la arquitectura.
- No se crean directorios o archivos fuera de los declarados en §2.
- Cualquier desviación de diseño debe documentarse mediante ADR antes de implementarse.
- Si una necesidad de implementación no puede satisfacerse sin modificar un contrato,
  se detiene el desarrollo y se reporta al Núcleo Arquitectónico.

---

## 11. Relación con Otros Documentos

Este roadmap implementa las decisiones establecidas en:

- Blueprint Técnico v1.0.1
- Phase 0 Implementation Spec v1.1
- System Concept Specification v1.1
- Architecture Decision Log
- Development Governance Framework

**El Blueprint y el Phase 0 Implementation Spec son fuente de verdad.**
En caso de contradicción entre este documento y el spec, prevalece el spec
y la contradicción debe reportarse antes de continuar.

---

## 📌 Registro de Cambios

| Versión | Cambio |
|---|---|
| v1.0 | Versión inicial |
| v1.1 | Incorporación de DataLayer façade, SubscriptionRegistry, corrección de ADR-002 a ADR-001, criterios de finalización expandidos, estructura de repositorio alineada |
| v1.2 | Scheduler incorporado en estructura y Stage 11; esquema MarketDB corregido al canónico del spec; campos de JobConfig alineados con spec v1.1 §7; Stage 13 ProcessingEngine stub agregado; restricción de Fase 0 en librería Common; política de pacing y reinicio TWS incorporadas en Stage 1; criterio de carrera concurrente agregado |
