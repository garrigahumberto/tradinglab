# Data Layer — Class Architecture

**Status:** Visualización de ingeniería — Documento cognitivo sin autoridad contractual
**Authority:** Ninguna
**Source of truth:** Blueprint Técnico v1.0.1 · Phase 0 Implementation Spec v1.1
**Alineado con:** Phase 0 Implementation Roadmap v1.2
**Ubicación sugerida:** /docs/architecture/data_layer_class_diagram.md

> Este documento refleja el estado actual del diseño tal como está definido en los
> documentos rectores. No reemplaza ni extiende ninguna especificación formal.

---

## Nivel 1 — Vista estructural lógica y de flujo

```text
                    ┌────────────────────────────────────────┐
                    │              DataLayer                 │
                    │       Fachada pública del sistema      │
                    │                                        │
                    │  subscribe_asset(uid,                  │
                    │      data_types, historical_window) ───┼──┐
                    │  unsubscribe_asset(uid) ───────────────┼──┤ (Control Path)
                    │  get_snapshot(uid,                     │  │
                    │      tipo_dato, temporalidad_base) ────┼──┼──────────────┐
                    │  shutdown() ───────────────────────────┼──┘              │
                    └──────────────────┬─────────────────────┘                 │
                                       │ (Control Path)                        │ (Read Path)
                                       ▼                                       │
                           ┌───────────────────────┐                           │
                           │  SubscriptionRegistry │                           │
                           └───────────┬───────────┘                           │
                                       │                                       │
                                       ▼                                       │
┌───────────────┐       ┌──────────────────────────┐                           │
│     IBKR      │◄──────┤    ConnectionManager     │                           │
│  TWS/Gateway  │       │                          │                           │
└───────┬───────┘       │  HistoricalHandler ──────┼── reqHistoricalData       │
        │               │  RealTimeHandler  ────── ┼── reqRealTimeBars         │
        │               └────────────┬─────────────┘                           │
        │                            │ (Data Path)                             │
        │                            ▼                                         │
        │               ┌──────────────────────────┐                           │
        └──────────────►│      DataDispatcher       │                           │
                        └──────────┬───────────┬───┘                           │
              (write mem)          │           │   (write disk)                │
                                   ▼           ▼                               │
               ┌──────────────────┐       ┌──────────────────────┐             │
               │    DataBuffer    │       │  PersistenceManager  │             │
               │  (RAM storage)   │       │  (MarketDB Parquet)  │             │
               └────────▲─────────┘       └──────────────────────┘             │
                        │                                                       │
                        └───────────────────────────────────────────◄──────────┘
```

### Rutas Arquitectónicas

**Control Path** — gestión de suscripciones, solo SessionController puede iniciarlo
```text
SessionController
   │
DataLayer.subscribe_asset(uid, data_types, historical_window)
   │
SubscriptionRegistry   ← registra consumidores, evita duplicados
   │
ConnectionManager      ← abre canal con IBKR
   │
IBKR
```

**Data Write Path** — flujo de datos desde el broker hacia persistencia y buffer
```text
IBKR
   │
ConnectionManager
   │
 ┌─┴──────────────────┐
 ▼                    ▼
HistoricalHandler   RealTimeHandler   ← normalizan al Canonical Data Model
         │                  │
         └────────┬──────────┘
                  ▼
           DataDispatcher              ← costura histórico + RT, ADR-001
                  │
       ┌──────────┴──────────┐
       ▼                     ▼
  DataBuffer          PersistenceManager
  (RAM, UID canónico)  (MarketDB Parquet)
```

**Data Read Path** — snapshots inmutables hacia Processing
```text
Processing
   │
DataLayer.get_snapshot(uid, tipo_dato, temporalidad_base)
   │
DataBuffer.get_snapshot()   ← devuelve df.copy(), nunca referencia
   │
pd.DataFrame (Canonical Data Model, índice = timestamp UTC)
```

---

## Nivel 2 — Componentes del Data Layer

```text
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

**Dependencias entre componentes:**
```text
ConnectionManager
    │
    ├── HistoricalHandler   ← solicita y normaliza histórico
    └── RealTimeHandler     ← agrega RT bars de 5s a barras de 1m

DataDispatcher
    │
    ├── DataBuffer          ← escritura en memoria
    └── PersistenceManager  ← escritura en disco

SubscriptionRegistry
    │
    └── ConnectionManager   ← instruye apertura/cierre de canales IBKR
```

Ningún componente externo al Data Layer accede directamente a estos componentes.
Todo acceso externo pasa exclusivamente por `DataLayer` (façade).

---

## Nivel 3 — Canonical Data Model

Todo DataFrame que circula entre componentes debe adherirse a este esquema.

```text
Índice:   timestamp   datetime64[ns, UTC]   ← índice del DataFrame, nunca columna
Columnas:
          open        float64
          high        float64
          low         float64
          close       float64
          volume      Int64   ← nullable, NaN cuando IBKR devuelve -1
          barCount    Int64   ← nullable, NaN cuando IBKR devuelve -1
```

**Regla ADR-001:** Los valores ausentes se representan como NaN.
Nunca como 0, nunca como -1, nunca como el valor anterior.
Ningún componente imputa datos ausentes excepto Strategy (Fase 1).

---

## Nivel 4 — Identificador Canónico de Activo (UID)

Toda operación del Data Layer requiere el UID canónico obligatorio.

```python
uid: tuple = (symbol: str, conId: int, exchange: str, secType: str)

# Ejemplo:
("AAPL", 265598, "NASDAQ", "STK")
```

Usar únicamente `symbol` como identificador es inválido por diseño.
El `conId` de IBKR no es opcional.

---

## Nivel 5 — Definición de clases

### DataLayer (façade)

Punto único de acceso para el resto del sistema.
Coordina todos los componentes internos.
Absorbe interrupciones del broker sin exponerlas a capas superiores.

```python
class DataLayer:
    def subscribe_asset(
        uid: tuple,               # UID canónico
        data_types: list[str],    # ["historical_bars", "rt_bars"]
        historical_window: int    # barras a retener en buffer
    ) -> None: ...

    def unsubscribe_asset(uid: tuple) -> None: ...

    def get_snapshot(
        uid: tuple,
        tipo_dato: str,           # "historical_bars" | "rt_bars"
        temporalidad_base: str    # "1m"
    ) -> pd.DataFrame: ...        # Canonical Data Model, copia inmutable

    def shutdown() -> None: ...
```

Processing solo interactúa con `DataLayer.get_snapshot()`.
SessionController solo interactúa con `subscribe_asset` y `unsubscribe_asset`.

---

### ConnectionManager

Canal único de comunicación con IBKR.
Gestiona reconexiones, absorbe interrupciones y controla pacing.

```python
class ConnectionManager:
    PACING_CODES = {162, 420, 10167}   # códigos de throttling de IBKR

    async def connect() -> bool: ...
    def disconnect() -> None: ...
    def is_connected() -> bool: ...
    def can_request() -> bool: ...     # False si pacing activo o reconectando

    async def request_historical_bars(*args, **kwargs) -> Any: ...
    def subscribe_realtime_bars(*args, **kwargs) -> Any: ...

    def _reset_pacing_state() -> None: ...  # llamar tras solicitud exitosa
```

**Estado interno clave:**
```python
_ib                           # cliente ib_insync — privado, nunca acceder desde fuera
_is_connecting: bool
_shutdown_requested: bool
_reconnect_task: Optional[asyncio.Task]
_backoff_sequence: list       # [1, 2, 4, 8, 16, 32, 60] segundos
_pacing_backoff_until: float  # time.monotonic()
_consecutive_pacing_rejects: int
```

**Política de reconexión:** backoff exponencial, máximo 60s.
**Política de pacing:** pausa 10s ante throttling, backoff exponencial ante 3+ rechazos, máximo 300s.
**Reinicio diario de TWS:** absorbido internamente, hueco registrado en `critical_error.log`.

---

### HistoricalHandler

Solicita y normaliza barras históricas desde IBKR.
Opera exclusivamente a través de `ConnectionManager`.

```python
class HistoricalHandler:
    async def fetch_historical_bars(
        contract: Contract,
        durationStr: str,
        barSizeSetting: str,
        ...
    ) -> pd.DataFrame: ...    # Canonical Data Model

    def _normalize_to_canonical(bars: list[BarData]) -> pd.DataFrame: ...
```

**Regla:** No activa RealTimeBars. No accede a `_ib` directamente.
Toda solicitud pasa por `ConnectionManager.request_historical_bars()`.
Llama a `_reset_pacing_state()` tras recepción exitosa.

---

### RealTimeHandler

Recibe barras de 5 segundos de IBKR y las agrega a barras de 1 minuto.

```python
class RealTimeHandler:
    def subscribe(contract: Contract) -> None: ...
    def unsubscribe(contract: Contract) -> None: ...

    def _on_realtime_bar(bar: RealTimeBar) -> None: ...   # callback IBKR
    def _aggregate_to_1m(bar: RealTimeBar) -> Optional[pd.Series]: ...
```

**Regla:** Solo entrega barras consolidadas (1 minuto completo) al DataDispatcher.
Nunca entrega barras parciales.

---

### SubscriptionRegistry

Registra y deduplica suscripciones activas entre Jobs.

```python
class SubscriptionRegistry:
    def register(uid: tuple, tipo_dato: str, consumer_id: str) -> None: ...
    def unregister(uid: tuple, tipo_dato: str, consumer_id: str) -> None: ...
    def is_subscribed(uid: tuple, tipo_dato: str) -> bool: ...
    def get_consumers(uid: tuple, tipo_dato: str) -> list[str]: ...
```

**Estructura interna:**
```python
# Clave: (uid_canónico, tipo_dato)
# Valor: lista de consumer_ids (Jobs)
subscriptions: dict[tuple[tuple, str], list[str]]
```

Cuando dos Jobs declaran el mismo `(uid, tipo_dato)`: una sola suscripción activa,
dos consumers registrados. La suscripción se cancela solo cuando el último consumer
es eliminado. Amortiguación de cancelaciones: 5 segundos.

---

### DataDispatcher

Recibe datos normalizados y coordina escritura a buffer y disco.

```python
class DataDispatcher:
    def on_historical_bars_complete(uid: tuple, bars: pd.DataFrame) -> None: ...
    def on_realtime_bar(uid: tuple, bar: pd.Series) -> None: ...
```

**Política de costura histórico + RT (obligatoria):**
```text
1. Esperar historicalDataEnd antes de activar RT
2. Primera RT bar: verificar continuidad temporal con última barra histórica
3. Solapamiento (RT timestamp ≤ última histórica): descartar RT bar
4. Hueco (gap > 1 minuto): registrar en critical_error.log, continuar
5. Sin imputación — ADR-001
```

**Thread safety:** toda escritura al buffer usa lock explícito.

---

### DataBuffer

Buffer en memoria de barras consolidadas por activo.

```python
class DataBuffer:
    def update(key: tuple, bar: pd.Series) -> None: ...
    def get_snapshot(key: tuple, window: int) -> pd.DataFrame: ...
```

**Estructura interna:**
```python
# Clave: (uid_canónico, tipo_dato, temporalidad_base)
# Valor: DataFrame con Canonical Data Model
buffers: dict[
    tuple[tuple, str, str],   # ((symbol,conId,exchange,secType), tipo_dato, timeframe)
    pd.DataFrame
]
```

**Reglas:**
- `get_snapshot` devuelve siempre `df.copy()`. Nunca una referencia.
- Retiene únicamente las últimas N barras (N = `historical_window` máximo entre Jobs activos).
- Thread-safe mediante `threading.RLock`.

---

### PersistenceManager

Persiste datos en MarketDB y gestiona metadatos de contratos.

```python
class PersistenceManager:
    def write_bars(uid: tuple, df: pd.DataFrame) -> None: ...
    def write_contract_metadata(uid: tuple, metadata: dict) -> None: ...
    def flush() -> None: ...
```

**Esquema de partición físico (obligatorio):**
```text
/marketdb/{asset_type}/{symbol}/{year}/{month}/{symbol}_{year}{month}.parquet

Ejemplo:
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

**Reglas:**
- Rechaza persistencia si no existe `contract_metadata.json` asociado.
- Rechaza DataFrames con columnas faltantes o timestamps no-UTC.
- Los huecos se registran en log. No se interpolan.
- Frecuencia: por barra para RT bars, batch al recibir `historicalDataEnd` para histórico.

---

## Nivel 6 — Flujo real de ejecución

**Cuando llega un dato del broker:**
```text
IBKR
  │
ConnectionManager
  │
  ├── HistoricalHandler (normaliza → Canonical Data Model)
  │         │
  │         └──► DataDispatcher.on_historical_bars_complete()
  │
  └── RealTimeHandler (agrega 5s → 1m consolidada)
            │
            └──► DataDispatcher.on_realtime_bar()

DataDispatcher
  │
  ├──► DataBuffer.update()              ← escritura en memoria (thread-safe)
  └──► PersistenceManager.write_bars()  ← escritura en disco
```

**Cuando un Job pide datos:**
```text
ProcessingEngine (stub en Fase 0)
      │
DataLayer.get_snapshot(uid, tipo_dato, temporalidad_base)
      │
DataBuffer.get_snapshot(key, window)
      │
pd.DataFrame — copia inmutable, índice timestamp UTC
               puede contener NaN — ADR-001
```

---

## Nivel 7 — Regla crítica de encapsulamiento

El resto del sistema **nunca accede directamente a**:
- `ConnectionManager`
- `HistoricalHandler`
- `RealTimeHandler`
- `DataDispatcher`
- `DataBuffer`
- `PersistenceManager`
- `SubscriptionRegistry`

**Solo accede a:**
- `DataLayer` (façade)

Esto incluye no acceder a atributos privados (`_ib`, `_buffer`, etc.)
desde componentes externos al Data Layer.

---

## Nivel 8 — Vista de dependencias en el sistema completo

```text
Session Controller
   │
   ├── DataLayer.subscribe_asset()    ← registra necesidades de datos
   └── Scheduler ──► Job Tick
                          │
                     DataLayer.get_snapshot()
                          │
                     Processing
                          │
                     Strategy (Fase 1)
                          │
                     Execution Support (Fase 2)

                    ┌──────────────────────────────┐
                    │      DataLayer (interno)      │
                    │  ConnectionManager            │
                    │    HistoricalHandler          │
                    │    RealTimeHandler            │
                    │  SubscriptionRegistry         │
                    │  DataDispatcher               │
                    │  DataBuffer                   │
                    │  PersistenceManager           │
                    └──────────────────────────────┘
```

---

## Nivel 9 — Qué garantiza este diseño

| Propiedad | Mecanismo |
|---|---|
| Multi-asset | UID canónico como clave compuesta |
| Multi-job | SubscriptionRegistry deduplica, DataBuffer es compartido |
| Reproducibilidad | Canonical Data Model determinista, sin imputación |
| Resiliencia ante caídas del broker | ConnectionManager absorbe internamente |
| Histórico acumulativo desde Fase 0 | PersistenceManager graba forward continuamente |
| Snapshots inmutables | `df.copy()` obligatorio en DataBuffer |
| Punto único de acceso | DataLayer façade, sin exposición de internos |
