# Phase 0 — Implementation Map

**Status:** Cognitive engineering map — Documento sin autoridad contractual
**Authority:** None
**Source of truth:** Phase 0 Implementation Roadmap v1.2 · Phase 0 Implementation Spec v1.1
**Ubicación sugerida:** /docs/architecture/phase0_implementation_map.md

> Este documento es una ayuda visual para comprender el plan de implementación de Fase 0.
> El documento de referencia operativo es el **Phase 0 Implementation Roadmap v1.2**.
> En caso de contradicción, prevalece el Roadmap.

---

## Objetivo de Fase 0

Construir la infraestructura base de adquisición y persistencia de datos de mercado.

```text
Al finalizar Fase 0 el sistema puede:

IBKR ──► ConnectionManager ──► DataDispatcher ──► DataBuffer
                                                └──► MarketDB (Parquet)
                                                         │
                                               get_snapshot()
                                                         │
                                                   Processing (stub)
```

Esta fase **no implementa** estrategias, señales ni ejecución de órdenes.

---

## Estructura del Repositorio

```text
production/
    data_layer/
        data_layer.py              ← façade pública
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
        processing_engine.py       ← stub en Fase 0

    common/
        indicators.py
        resampling.py
        statistics.py

marketdb/
    {asset_type}/{symbol}/{year}/{month}/

tests/
docs/
```

> `strategy/` y `execution/` **no existen en Fase 0**.

---

## Orden de Implementación

```text
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

Cada stage produce componentes funcionales con tests unitarios aprobados
antes de pasar al siguiente. No se crean archivos fuera de los declarados en cada stage.

---

## Stage 1 — ConnectionManager

**Archivo:** `production/data_layer/connection_manager.py`

**Qué hace:**
Canal único de comunicación con IBKR. Gestiona el ciclo de vida de la conexión,
absorbe interrupciones y controla el ritmo de solicitudes al broker.

**Responsabilidades clave:**
- Conexión y reconexión automática con backoff exponencial
- Absorción silenciosa del reinicio diario de TWS
- Control de pacing: pausa ante throttling, backoff ante rechazos reiterados
- Exposición de `can_request()` como válvula central de control

**API pública:**
```python
async def connect() -> bool
def disconnect() -> None
def is_connected() -> bool
def can_request() -> bool          # False si pacing activo o reconectando
async def request_historical_bars(*args, **kwargs) -> Any
def subscribe_realtime_bars(*args, **kwargs) -> Any
def _reset_pacing_state() -> None  # llamar tras solicitud exitosa
```

**Estado interno relevante:**
```python
PACING_CODES = {162, 420, 10167}
_ib                           # cliente ib_insync — nunca exponer
_backoff_sequence = [1, 2, 4, 8, 16, 32, 60]   # segundos
_pacing_backoff_until: float  # time.monotonic()
_reconnect_task: Optional[asyncio.Task]
```

**Notas de implementación:**
- `_ib` es privado. Ningún componente externo accede a él directamente.
- `request_historical_bars` y `subscribe_realtime_bars` son provisionales.
  Su lógica migrará a HistoricalHandler y RealTimeHandler en Stages 2 y 3.
- `time.monotonic()` para todo control de tiempo interno. Nunca `time.time()`.

**Resultado esperado:**
El sistema puede conectarse, reconectarse automáticamente y gestionar
interrupciones del broker sin propagar errores a capas superiores.

---

## Stage 2 — HistoricalHandler

**Archivo:** `production/data_layer/historical_handler.py`

**Qué hace:**
Solicita datos históricos a IBKR y los normaliza al Canonical Data Model.
Depende de ConnectionManager para todas las operaciones de red.

**Responsabilidades clave:**
- Solicitar datos históricos vía `ConnectionManager.request_historical_bars()`
- Gestionar la recepción completa (`historicalDataEnd`)
- Normalizar barras al Canonical Data Model
- No activar RealTimeBars

**API pública:**
```python
async def fetch_historical_bars(contract, durationStr, barSizeSetting, ...) -> pd.DataFrame
```

**Notas de implementación:**
- Nunca accede a `_cm._ib` directamente. Solo usa métodos públicos del ConnectionManager.
- Llama a `_cm._reset_pacing_state()` tras recepción exitosa.
- `CancelledError` no se silencia: siempre se propaga con `raise`.
- Devuelve DataFrame vacío con esquema canónico ante fallo (nunca `None`).

**Canonical Data Model obligatorio de salida:**
```text
Índice:   timestamp   datetime64[ns, UTC]
          open        float64
          high        float64
          low         float64
          close       float64
          volume      Int64    ← NaN cuando IBKR devuelve -1
          barCount    Int64    ← NaN cuando IBKR devuelve -1
```

**Resultado esperado:**
El sistema puede solicitar y recibir datos históricos en el formato canónico.

---

## Stage 3 — RealTimeHandler

**Archivo:** `production/data_layer/realtime_handler.py`

**Qué hace:**
Recibe barras de 5 segundos de IBKR y las agrega a barras de 1 minuto consolidadas.
Solo entrega barras completas al DataDispatcher.

**Responsabilidades clave:**
- Gestionar `reqRealTimeBars`
- Agregar barras de 5s a la barra de 1m en construcción
- Marcar la barra como consolidada al completar el intervalo de 1 minuto
- Entregar únicamente barras consolidadas. Nunca barras parciales.

**Notas de implementación:**
- RealTimeHandler no se activa hasta confirmar recepción completa del histórico.
  El DataDispatcher controla este orden en Stage 7.
- Las barras de 5 segundos son internas. El DataDispatcher nunca las ve.

**Resultado esperado:**
El sistema recibe barras en tiempo real y entrega barras de 1 minuto consolidadas.

---

## Stage 4 — DataBuffer

**Archivo:** `production/data_layer/data_buffer.py`

**Qué hace:**
Buffer en memoria de barras consolidadas. Permite acceso rápido e inmutable
a snapshots. Punto de lectura para `get_snapshot`.

**Responsabilidades clave:**
- Almacenar barras indexadas por clave canónica
- Gestionar ventana de retención (N barras máximo por activo)
- Garantizar thread-safety en lectura y escritura
- Devolver siempre copias inmutables

**Estructura interna:**
```python
# Clave: (uid_canónico, tipo_dato, temporalidad_base)
# Valor: DataFrame con Canonical Data Model
dict[tuple[tuple, str, str], pd.DataFrame]

# Ejemplo de clave:
(("AAPL", 265598, "NASDAQ", "STK"), "historical_bars", "1m")
```

**Notas de implementación:**
- `threading.RLock` para toda operación de lectura y escritura.
- `get_snapshot` devuelve siempre `df.copy()`. Nunca una referencia directa.
- N barras = `historical_window` máximo declarado entre Jobs activos para ese activo.

**Resultado esperado:**
El sistema puede almacenar y consultar barras recientes en memoria
de forma thread-safe e inmutable.

---

## Stage 5 — SubscriptionRegistry

**Archivo:** `production/data_layer/subscription_registry.py`

**Qué hace:**
Registro central de suscripciones activas. Evita que dos Jobs generen
dos conexiones al mismo activo en IBKR.

**Responsabilidades clave:**
- Registrar y rastrear suscripciones por `(uid, tipo_dato)`
- Deduplicar: una sola suscripción activa por `(uid, tipo_dato)`, múltiples consumidores
- Cancelar suscripción solo cuando el último consumidor es eliminado
- Amortiguar cancelaciones: diferir 5 segundos para evitar violaciones de pacing

**Estructura interna:**
```python
# Clave: (uid_canónico, tipo_dato)
# Valor: lista de consumer_ids (Jobs)
subscriptions: dict[tuple[tuple, str], list[str]]
```

**Resultado esperado:**
El sistema gestiona correctamente múltiples consumidores sin duplicados.

---

## Stage 6 — PersistenceManager

**Archivo:** `production/data_layer/persistence_manager.py`

**Qué hace:**
Persiste datos en MarketDB en formato Parquet y gestiona metadatos de contratos.

**Responsabilidades clave:**
- Escribir barras en el esquema de partición canónico
- Persistir y mantener actualizado `contract_metadata.json` por activo
- Rechazar persistencia si no existe metadata de contrato asociada
- Verificar integridad antes de persistir

**Esquema de partición físico (obligatorio):**
```text
/marketdb/{asset_type}/{symbol}/{year}/{month}/{symbol}_{year}{month}.parquet

Ejemplo:
/marketdb/STK/AAPL/2026/03/AAPL_202603.parquet
```

**Frecuencia de escritura:**
```text
RealTimeBars   → por barra consolidada durante sesión activa
HistoricalBars → batch al recibir historicalDataEnd
Cierre sesión  → flush forzoso de pendientes
```

**Notas de implementación:**
- Rechaza DataFrames con columnas faltantes o timestamps no-UTC.
- Los huecos no se interpolan. Se registran en log.

**Resultado esperado:**
Las barras se persisten correctamente con esquema canónico y metadatos asociados.

---

## Stage 7 — DataDispatcher

**Archivo:** `production/data_layer/data_dispatcher.py`

**Qué hace:**
Coordina el flujo de datos desde los handlers hacia buffer y disco.
Aplica la política de costura entre histórico y tiempo real.

**Responsabilidades clave:**
- Recibir barras normalizadas desde HistoricalHandler y RealTimeHandler
- Actualizar DataBuffer
- Enviar datos a PersistenceManager
- Aplicar política de costura histórico + RT
- Registrar huecos en log estructurado

**Política de costura (obligatoria — ADR-001):**
```text
1. Esperar historicalDataEnd antes de activar RT bars
2. Primera RT bar: verificar continuidad con última barra histórica
3. Solapamiento (RT timestamp ≤ última histórica): descartar RT bar
4. Hueco (gap > 1 minuto): registrar en critical_error.log, continuar
5. Sin imputación en ningún caso
```

**Notas de implementación:**
- Thread-safety obligatoria en escritura al buffer.
- Los huecos son señales legítimas del sistema, no errores a corregir.

**Resultado esperado:**
Los datos fluyen correctamente a buffer y persistencia.
La costura entre histórico y tiempo real es determinista.

---

## Stage 8 — DataLayer Façade

**Archivo:** `production/data_layer/data_layer.py`

**Qué hace:**
Punto único de acceso al Data Layer para el resto del sistema.
Coordina todos los componentes internos. Ningún componente externo
accede a los internos directamente.

**API contractual (no modificable sin Revisión Formal de Gobernanza):**
```python
def subscribe_asset(uid: tuple, data_types: list[str], historical_window: int) -> None
def unsubscribe_asset(uid: tuple) -> None
def get_snapshot(uid: tuple, tipo_dato: str, temporalidad_base: str) -> pd.DataFrame
def shutdown() -> None
```

**Garantías de `get_snapshot`:**
```text
- Devuelve df.copy() — nunca una referencia
- Puede contener NaN — ADR-001
- Solo la ventana histórica declarada en JobConfig
- No fuerza actualización de buffers
- No altera suscripciones
```

**Resultado esperado:**
El Data Layer es accesible mediante una API estable.
Ningún componente externo necesita conocer la estructura interna.

---

## Stage 9 — Librería Common (base mínima)

**Archivos:**
```text
production/common/indicators.py
production/common/resampling.py
production/common/statistics.py
```

**Alcance en Fase 0 — únicamente lo necesario:**

`resampling.py`:
- Función de resampling de barras de 1 minuto a temporalidades superiores
- Funciones puras, sin estado
- Propagan NaN de forma transparente — ADR-001

`indicators.py` y `statistics.py`:
- Estructura vacía con docstring de propósito
- Sin indicadores estratégicos — pertenecen a Fase 1

> No se implementan funciones para fases futuras.

**Resultado esperado:**
Utilidades base disponibles. Estructura establecida para fases posteriores.

---

## Stage 10 — JobConfig

**Archivo:** `production/session/job_config.py`

**Qué hace:**
Define la estructura de configuración de un Job y valida su contenido.
SessionController no puede instanciar un Job sin una configuración válida.

**Estructura obligatoria:**
```python
@dataclass
class JobConfig:
    uid: tuple                  # (symbol, conId, exchange, secType)
    data_types: list[str]       # ["historical_bars", "rt_bars"]
    timeframe_base: str         # "1m"
    historical_window: int      # barras a retener en buffer
    persistence_policy: str     # "always" | "on_close"
    strategy_config: None       # siempre None en Fase 0
    execution_config: None      # siempre None en Fase 0
```

**Validaciones requeridas:**
```text
- uid: exactamente 4 elementos con tipos correctos
- data_types: solo valores del conjunto permitido
- historical_window: entero positivo
- strategy_config y execution_config: deben ser None (lanzar excepción si no)
```

**Resultado esperado:**
Los Jobs tienen configuración estructurada y validable.

---

## Stage 11 — Scheduler

**Archivo:** `production/session/scheduler.py`

**Qué hace:**
Controla el ritmo de ejecución de Jobs. Impide que un Job ejecute
múltiples ciclos dentro de la misma unidad temporal.

**Responsabilidades clave:**
- Activar cada Job según su `timeframe_base`
- Bloquear activaciones anticipadas
- Registrar timestamp de última activación por Job

**Mecanismo:**
```text
Loop interno (tick = 1 segundo)
│
Por cada Job activo:
│   timestamp_actual < última_activación + timeframe_base
│         → no activar
│   timestamp_actual ≥ última_activación + timeframe_base
│         → activar Job, registrar nueva activación
```

**Resultado esperado:**
Ningún Job puede consultar datos con mayor frecuencia que la declarada.
El sistema controla el ritmo de ejecución de forma determinista.

---

## Stage 12 — SessionController

**Archivo:** `production/session/session_controller.py`

**Qué hace:**
Coordina el ciclo de vida completo del sistema: inicialización, operación
y shutdown ordenado.

**Responsabilidades clave:**
- Validar y cargar JobConfigs
- Registrar necesidades de datos en Data Layer vía `subscribe_asset`
- Instanciar y destruir Jobs
- Coordinar el Scheduler
- Gestionar shutdown ordenado

**Restricciones:**
- No procesa datos
- No accede a IBKR directamente
- No conoce lógica de mercado
- Es la única entidad autorizada a modificar el universo de activos monitoreados

**Resultado esperado:**
El sistema puede inicializar, operar y detener múltiples Jobs simultáneamente
de forma controlada y reproducible.

---

## Stage 13 — ProcessingEngine Stub

**Archivo:** `production/processing/processing_engine.py`

**Qué hace:**
Stub mínimo para validar el contrato `get_snapshot` end-to-end.
No implementa lógica analítica. No calcula indicadores.

**Responsabilidades del stub:**
- Invocar `DataLayer.get_snapshot(uid, tipo_dato, temporalidad_base)`
- Verificar que el DataFrame respeta el Canonical Data Model
- Verificar que el DataFrame es una copia independiente
- Registrar resultado en log

**Restricción ADR-001:**
El stub no puede aplicar `.fillna()`, `ffill()` ni `bfill()` sobre los datos.
Su propósito es verificar el contrato, no limpiar datos.

**Resultado esperado:**
El pipeline completo `Data Layer → Processing` está validado end-to-end.

---

## Resultado al Terminar Fase 0

```text
                    Session Controller
                           │
                       Scheduler
                           │
              ┌────────────┴────────────┐
           Job A                     Job B
              │                         │
              └──────────┬──────────────┘
                         │
                    DataLayer.get_snapshot()
                         │
                    DataBuffer (RAM)
                         │
              ┌──────────┴──────────────────┐
              │                             │
           IBKR ──► ConnectionManager       MarketDB
                         │                 (histórico acumulándose
                    DataDispatcher          desde el primer día)
                         │
               ┌─────────┴─────────┐
          DataBuffer          PersistenceManager
```

Al finalizar Fase 0 el sistema tiene:

- ✔ Dataset histórico propio acumulándose en forward
- ✔ Arquitectura con contratos estables para Fase 1
- ✔ Pipeline de datos validado end-to-end
- ✔ Base sobre la que se construirán Strategy y Execution sin rediseño

---

## Criterios de Finalización

```text
- [ ] Conexión estable con IBKR
- [ ] Reconexión automática con backoff exponencial
- [ ] Absorción silenciosa del reinicio diario de TWS
- [ ] Manejo de pacing limits sin insistir ante rechazos
- [ ] Recepción correcta de Historical Bars
- [ ] Recepción correcta de RealTimeBars
- [ ] Costura determinista entre histórico y tiempo real
- [ ] Persistencia en esquema canónico de MarketDB
- [ ] Persistencia de contract_metadata.json por activo
- [ ] Buffer en memoria con UID canónico y thread-safety
- [ ] get_snapshot con copia inmutable garantizada
- [ ] Scheduler controlando ciclo sin activaciones anticipadas
- [ ] 3 Jobs concurrentes sobre 5 activos sin condiciones de carrera
- [ ] Registro de huecos en log estructurado
- [ ] Sistema capaz de reconstruir sesiones pasadas con datos propios
```
