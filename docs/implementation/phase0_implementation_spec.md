# Phase 0 — Implementation Specification

**Status:** Implementation Guide
**Authority:** Derived from Blueprint Técnico v1.0
**Scope:** Construcción del Data Layer y la infraestructura mínima para captura de datos de mercado.

---

## 1️⃣ Propósito de la Fase 0

La Fase 0 establece la infraestructura fundamental de datos del sistema.
Su objetivo es construir un Data Layer funcional capaz de:
- Conectarse al broker Interactive Brokers.
- Capturar barras de mercado en tiempo real.
- Persistir datos en almacenamiento estructurado.
- Servir snapshots a los Jobs del sistema.

Esta fase **no implementa** estrategias ni ejecución de órdenes.
Su función es crear el sistema de adquisición y almacenamiento de datos sobre el cual se construirá todo el sistema posterior.

---

## 2️⃣ Alcance de la Fase

La Fase 0 incluye la implementación de:

**Infraestructura de sesión**
- `SessionController`
- `Scheduler` básico

**Data Layer completo**
- `ConnectionManager`
- `SubscriptionRegistry`
- `DataDispatcher`
- `DataBuffer`
- `PersistenceManager`
- `DataLayer` (façade)

**Componentes mínimos de consumo (stubs)**
- `ProcessingEngine` (stub)
- `StrategyBase` (stub)
- `ExecutionSupport` (stub)

---

## 3️⃣ Entorno Tecnológico

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Broker API | Interactive Brokers |
| Cliente API | `ib_insync` |
| Datos | `pandas` |
| Persistencia | Parquet (`pyarrow`) |
| Cálculo numérico | `numpy` |

**Dependencias iniciales:**
- `pandas`
- `numpy`
- `pyarrow`
- `ib_insync`

---

## 4️⃣ Fuente de Datos

El sistema utilizará Interactive Brokers API.
Tipos de datos utilizados en Fase 0:
- HistoricalBars
- RealTimeBars

**Unidad temporal base:**
- 1 minute bars

Los datos se recibirán a través de:
- `reqHistoricalData`
- `reqRealTimeBars`

---

## 5️⃣ Límites Operativos de Fase 0

Para simplificar el sistema durante la fase inicial se establecen los siguientes límites:

| Parámetro | Valor |
|---|---|
| Activos máximos | 5 |
| Jobs simultáneos | 3 |
| Temporalidad base | 1m |

*Estos límites podrán ampliarse en fases posteriores.*

---

## 6️⃣ Arquitectura de Flujo de Datos

**Flujo de captura:**
```text
IBKR
   │
ConnectionManager
   │
DataDispatcher
   │
 ┌─┴───────────────┐
 ▼                 ▼
DataBuffer    PersistenceManager
```

**Flujo de lectura:**
```text
Processing
   │
DataLayer.get_snapshot()
   │
DataBuffer
```

El sistema utiliza un **modelo Pull**.
Los Jobs solicitan snapshots al Data Layer en lugar de recibir eventos de tipo push asíncrono.

---

## 7️⃣ Componentes a Implementar

### SessionController
**Responsabilidades:**
- Inicializar el sistema.
- Crear Jobs.
- Controlar ciclo de ejecución.
- Gestionar shutdown.

### DataLayer (fachada)
**Responsabilidades:**
- Exponer interfaz pública del sistema de datos.
- Coordinar componentes internos.

**Métodos mínimos:**
- `subscribe_asset(uid)`
- `get_snapshot(uid, timeframe)`
- `shutdown()`

### ConnectionManager
**Responsabilidades:**
- Gestionar conexión con IBKR.
- Manejar reconexiones.
- Enviar solicitudes de datos.

**Funciones principales:**
- `connect()`
- `disconnect()`
- `subscribe_realtime_bars(contract)`
- `request_historical_bars(contract)`

### SubscriptionRegistry
**Responsabilidades:**
- Registrar activos suscritos.
- Evitar suscripciones duplicadas.
- Liberar suscripciones sin consumidores.

### DataDispatcher
**Responsabilidades:**
- Recibir datos del broker.
- Normalizar estructura.
- Actualizar buffers.
- Enviar datos a persistencia.

### DataBuffer
**Responsabilidades:**
- Almacenar datos recientes en memoria.
- Permitir acceso rápido a snapshots.

**Estructura base:**
`dict[(symbol, timeframe)] → pandas.DataFrame`

### PersistenceManager
**Responsabilidades:**
- Persistir datos en disco.
- Gestionar MarketDB.

**Formato:**
Parquet

---

## 8️⃣ Contratos de Datos

Los activos se identificarán mediante un **UID canónico**.

**Estructura:**
`(symbol, conId, exchange, secType)`

**Ejemplo:**
`("AAPL", 265598, "NASDAQ", "STK")`

---

## 9️⃣ Estructura de Repositorio

```text
/production
    /session
        session_controller.py

    /data_layer
        data_layer.py
        connection_manager.py
        subscription_registry.py
        data_dispatcher.py
        data_buffer.py
        persistence_manager.py

    /processing
        processing_engine.py

    /strategy
        strategy_base.py

    /execution
        execution_support.py

    /common
        indicators.py
        resampling.py
        statistics.py

/marketdb

/research
    /notebooks

/docs
    /architecture
    /implementation
```

---

## 🔟 Orden de Implementación

Los componentes deben implementarse de la base hacia arriba en el siguiente orden:

1. `ConnectionManager`
2. `SubscriptionRegistry`
3. `DataBuffer`
4. `DataDispatcher`
5. `PersistenceManager`
6. `DataLayer`
7. `SessionController`

Este orden permite validar cada componente de forma incremental y unitaria.

---

## 1️⃣1️⃣ Modos Operativos

Durante Fase 0 el sistema operará en:
`FORWARD_RECORDING_MODE`

**Características:**
- Captura pasiva de datos
- Persistencia continua
- Sin evaluación de estrategias

Otros modos quedan reservados para fases posteriores.

---

## 1️⃣2️⃣ Criterios de Finalización

La Fase 0 se considera completada cuando el sistema puede:
- [ ] Conectarse a IBKR
- [ ] Suscribirse a activos
- [ ] Recibir barras de mercado
- [ ] Persistir datos en MarketDB
- [ ] Servir snapshots desde DataBuffer

---

## 1️⃣3️⃣ Fuera de Alcance

No forman parte de Fase 0:
- ejecución de órdenes
- optimización de estrategias
- backtesting completo
- manejo de portafolio
- gestión avanzada de riesgos

Estos componentes se implementarán en fases posteriores.

---

## 1️⃣4️⃣ Relación con el Blueprint

Este documento **no redefine la arquitectura**.
Su función es traducir el Blueprint Técnico en un plan de implementación concreto para Fase 0.
El Blueprint permanece como fuente de verdad arquitectónica absoluta.
