# Data Layer — Class Architecture

**Status:** Visualización de ingeniería
**Authority:** Ninguna
**Source of truth:** Blueprint Técnico
**Ubicación sugerida:** /research/notebooks/architecture/data_layer_class_diagram.md

## Nivel 1 — Vista estructural lógica y de flujo
```text
                    ┌───────────────────────────────┐
                    │           DataLayer           │
                    │  Fachada pública del sistema  │
                    │                               │
                    │  get_snapshot() ──────────────┼──────────────┐
                    │  subscribe_asset() ────────┐  │              │
                    │  shutdown()                │  │              │
                    └───────────────┬────────────┴──┘              │
                                    │ (Control Path)               │ (Read Path)
                                    ▼                              │
                        ┌──────────────────────┐                   │
                        │ SubscriptionRegistry │                   │
                        └───────────┬──────────┘                   │
                                    │                              │
                                    ▼                              │
┌───────────────┐       ┌──────────────────────┐                   │
│     IBKR      │◄──────┤  ConnectionManager   │                   │
└───────────────┘       └───────────┬──────────┘                   │
                                    │ (Data Path)                  │
                                    ▼                              │
                        ┌──────────────────────┐                   │
                        │    DataDispatcher    │                   │
                        └──────┬────────────┬──┘                   │
             (write mem)       │            │   (write disk)       │
                               ▼            ▼                      │
              ┌─────────────────┐       ┌──────────────────┐       │
              │   DataBuffer    │       │ PersistenceManager│       │
              │  (RAM storage)  │       │ (MarketDB Parquet)│       │
              └─────────▲───────┘       └──────────────────┘       │
                        │                                          │
                        └───────────────────────◄──────────────────┘
```

### Rutas Arquitectónicas

**Control Path**
```text
DataLayer
   │
SubscriptionRegistry
   │
ConnectionManager
   │
IBKR
```

**Data Write Path**
```text
IBKR
   │
ConnectionManager
   │
DataDispatcher
   │
 ┌─┴─────────────┐
 ▼               ▼
DataBuffer   PersistenceManager
```

**Data Read Path**
```text
Processing
   │
DataLayer.get_snapshot()
   │
DataBuffer
```

## Nivel 2 — Relación entre clases
```text
DataLayer
  │
  ├── ConnectionManager
  │
  ├── SubscriptionRegistry
  │
  ├── DataDispatcher
  │
  ├── PersistenceManager
  │
  └── DataBuffer
```

**Dependencias:**
```text
ConnectionManager
        │
        ▼
DataDispatcher

DataDispatcher
        │
        ├── DataBuffer
        └── PersistenceManager

SubscriptionRegistry
        │
        ▼
ConnectionManager
```

## Nivel 3 — Definición de clases

### DataLayer (fachada)
**Responsabilidad:**
Punto único de acceso para el resto del sistema
Oculta la complejidad del Data Layer
Coordina todos los componentes internos

```python
class DataLayer:
    def subscribe_asset(uid):
        pass

    def get_snapshot(uid, timeframe, lookback):
        pass

    def shutdown():
        pass
```
Nunca expone componentes internos.
Processing solo interactúa con: `DataLayer.get_snapshot()`

### ConnectionManager
**Responsabilidad:**
- mantener una única conexión con IBKR
- manejar reconexiones
- controlar pacing

```python
class ConnectionManager:
    def connect():
        pass

    def disconnect():
        pass

    def request_historical_bars(contract):
        pass

    def subscribe_realtime_bars(contract):
        pass

    def handle_reconnect():
        pass
```

**Propiedades clave:**
- `connection_state`
- `retry_backoff`
- `active_requests`

### SubscriptionRegistry
**Responsabilidad:**
- saber qué activos están siendo usados
- evitar suscripciones duplicadas
- liberar recursos

```python
class SubscriptionRegistry:
    def register(uid):
        pass

    def unregister(uid):
        pass

    def get_active_subscriptions():
        pass
```

Internamente mantiene:
```python
subscriptions = {
   uid : reference_count
}
```
Esto permite que varios Jobs compartan datos.

### DataDispatcher
**Responsabilidad:**
- recibir datos de IBKR
- actualizar buffers
- enviar datos a persistencia

```python
class DataDispatcher:
    def on_historical_bar(bar):
        pass

    def on_realtime_bar(bar):
        pass

    def dispatch():
        pass
```

**Flujo:**
```text
IBKR callback
      │
      ▼
DataDispatcher
      │
      ├── DataBuffer.update()
      │
      └── PersistenceManager.write()
```

### DataBuffer
**Responsabilidad:**
- mantener estado temporal de mercado en memoria

```python
class DataBuffer:
    def update_bar(uid, bar):
        pass

    def get_snapshot(uid, timeframe, lookback):
        pass
```

Internamente:
```python
buffers = {
   uid : dataframe
}
```
Esto permite responder rápidamente a: `get_snapshot()`

### PersistenceManager
**Responsabilidad:**
- escribir histórico de mercado
- manejar estructura de MarketDB

```python
class PersistenceManager:
    def write_bar(uid, bar):
        pass

    def flush():
        pass

    def write_contract_metadata(contract):
        pass
```

**Formato:**
Parquet
partitioned by:
- asset
- year
- month

## Nivel 4 — Flujo real de ejecución

Cuando llega un dato del broker:
```text
IBKR
  │
  ▼
ConnectionManager
  │
  ▼
DataDispatcher
  │
  ├── DataBuffer.update()
  │
  └── PersistenceManager.write()
```

Cuando un Job pide datos:
```text
Processing Layer
      │
      ▼
DataLayer.get_snapshot()
      │
      ▼
DataBuffer.get_snapshot()
      │
      ▼
DataFrame
```

## Nivel 5 — Regla crítica de arquitectura

El resto del sistema **nunca ve esto**:
- `ConnectionManager`
- `DataDispatcher`
- `PersistenceManager`
- `DataBuffer`
- `SubscriptionRegistry`

**Solo ve:**
- `DataLayer`

Esto evita acoplamiento.

## Nivel 6 — Vista de dependencias
```text
Strategy
   │
   ▼
Processing
   │
   ▼
DataLayer
   │
   ▼
┌─────────────────────────┐
│   Componentes internos  │
│                         │
│ ConnectionManager       │
│ SubscriptionRegistry    │
│ DataDispatcher          │
│ PersistenceManager      │
│ DataBuffer              │
└─────────────────────────┘
```

## Qué garantiza este diseño

Este Data Layer:
- ✔ soporta multi-asset
- ✔ soporta multi-job
- ✔ evita duplicación de suscripciones
- ✔ graba histórico de mercado automáticamente
- ✔ permite backtesting posterior
- ✔ mantiene un único punto de acceso

## Comentario de ingeniería

Este Data Layer es mucho más robusto que el 95% de sistemas retail de trading.

La mayoría de sistemas hacen esto:
```text
Strategy
   │
   ▼
IBKR API
```
Eso crea:
- caos de conexiones
- duplicación de datos
- sistemas no reproducibles

Tu arquitectura hace esto:
```text
Strategy
   │
Processing
   │
DataLayer
   │
IBKR
```
Eso crea un **sistema escalable**.
