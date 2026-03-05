# Phase 0 Implementation Map

**Status:** Cognitive engineering map
**Authority:** None

---

## Etapa 1 — Foundation

**Objetivo:** crear la estructura mínima ejecutable.

**Implementar:**
`/production/session/session_controller.py`

**Responsabilidades:**
- crear Jobs
- iniciar Data Layer
- manejar ciclo principal

**Skeleton:**
```python
class SessionController:
    def __init__(self):
        self.jobs = []

    def register_job(self, job_config):
        ...

    def start(self):
        ...
```

---

## Etapa 2 — Connection Manager

**Archivo:**
`/production/data_layer/connection_manager.py`

**Responsabilidades:**
- conexión a IBKR
- reconexión
- inicializar cliente

**Funciones mínimas:**
- `connect()`
- `disconnect()`
- `is_connected()`

**En Fase 0 no implementar aún:**
- backoff avanzado
- failover
- multi-client

---

## Etapa 3 — Subscription Registry

**Archivo:**
`/production/data_layer/subscription_registry.py`

**Responsabilidades:**
- registrar qué instrumento está suscrito
- evitar duplicaciones

**Ejemplo interno:**
```python
subscriptions = {
    uid : {
        "consumers": [jobA, jobB],
        "stream": stream_handle
    }
}
```

---

## Etapa 4 — Data Dispatcher

**Archivo:**
`/production/data_layer/data_dispatcher.py`

**Responsabilidades:**
- recibir datos de IBKR
- actualizar buffers internos

**Buffers mínimos:**
```python
buffers = {
    uid : DataFrame
}
```

- No hay push.
- Solo almacenamiento.

---

## Etapa 5 — Persistence Manager

**Archivo:**
`/production/data_layer/persistence_manager.py`

**Responsabilidades:**
- guardar barras en Parquet
- construir MarketDB

**Ruta:**
`/marketdb/stock/AAPL/2026/03/AAPL_202603.parquet`

**En Fase 0:**
- append simple
- sin optimización

---

## Etapa 6 — Snapshot API

**Función crítica:**
`get_snapshot(uid, timeframe)`

**Responsabilidad:**
- devolver DataFrame de velas

Esto es el contrato entre Data y Processing.

---

## Etapa 7 — Processing Engine

**Archivo:**
`/production/processing/processing_engine.py`

**Responsabilidades:**
- resampling
- indicadores

**Usará:**
`/production/common/indicators.py`

---

## Etapa 8 — Strategy Base

**Archivo:**
`/production/strategy/strategy_base.py`

**Interfaz mínima:**
```python
class Strategy:
    def evaluate(self, features):
        return signal
```

---

## Etapa 9 — Execution Support

**Archivo:**
`/production/execution/execution_support.py`

**En Fase 0:**
- solo logging
- sin órdenes reales

---

## 4️⃣ Resultado al terminar Fase 0

Tendrás algo extremadamente valioso:

```
IBKR → Data Layer → MarketDB
                 → Jobs
```

Y simultáneamente:

```
IBKR → MarketDB (histórico acumulándose)
```

Esto significa:
- ✔ dataset histórico propio
- ✔ arquitectura ya escalable
- ✔ sistema vivo funcionando
