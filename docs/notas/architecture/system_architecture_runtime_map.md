# System Architecture — Runtime Map

**Status:** Visualización cognitiva de ingeniería — No contractual
**Authority:** Ninguna
**Fuente de verdad:** Blueprint Técnico v1.0.1
**Alineado con:** Phase 0 Implementation Roadmap v1.2 · Phase 0 Implementation Spec v1.1
**Ubicación sugerida:** /docs/architecture/system_architecture_runtime_map.md

---

## Propósito

Este documento provee una visualización intuitiva de la arquitectura del sistema
en tiempo de ejecución. Cubre el sistema completo (todas las fases) para permitir
al ingeniero ver el diseño final mientras trabaja en la fase activa.

No es un documento contractual y no reemplaza ninguna especificación formal.

**Fase activa actual: Fase 0 — Fundamento de Datos.**
Las capas marcadas con `[Fase 1]` y `[Fase 2]` están definidas arquitectónicamente
pero no se implementan hasta cerrar las fases previas.

El Blueprint Técnico permanece como la especificación arquitectónica de autoridad.

---

## Nivel 1 — Vista estructural completa del sistema

```text
                    ┌──────────────────────────────────┐
                    │        Session Controller        │
                    │  crea · configura · destruye     │
                    │  Jobs · registra datos en        │
                    │  Data Layer · coordina Scheduler │
                    └──────────────┬───────────────────┘
                                   │
                              ┌────▼────┐
                              │Scheduler│  controla ritmo de ejecución
                              └────┬────┘  impide activaciones anticipadas
                                   │
                                   │ activa N Jobs según temporalidad
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │                      JOB (N)                        │
        │                                                      │
        │  ┌───────────────────────────────────────────────┐  │
        │  │                 Data Layer                    │  │  ← Fase 0 ✔
        │  │           (servicio centralizado)             │  │
        │  │                                               │  │
        │  │  ConnectionManager ──────────────► IBKR       │  │
        │  │    HistoricalHandler                          │  │
        │  │    RealTimeHandler                            │  │
        │  │  SubscriptionRegistry                         │  │
        │  │  DataDispatcher                               │  │
        │  │  DataBuffer                                   │  │
        │  │  PersistenceManager ─────────────► MarketDB   │  │
        │  └──────────────┬────────────────────────────────┘  │
        │                 │ get_snapshot(uid, tipo_dato,       │
        │                 │             temporalidad_base)     │
        │  ┌──────────────▼────────────────────────────────┐  │
        │  │           Processing Layer                    │  │  ← Fase 0: stub de validación
        │  │  resampling · alineación · features           │  │    Fase 1: implementación completa
        │  └──────────────┬────────────────────────────────┘  │
        │                 │ get_features(config)              │
        │  ┌──────────────▼────────────────────────────────┐  │
        │  │            Strategy Layer          [Fase 1]   │  │  ← no existe en Fase 0
        │  │        evaluación de hipótesis                │  │
        │  └──────────────┬────────────────────────────────┘  │
        │                 │ evaluate() → señal + metadata     │
        │  ┌──────────────▼────────────────────────────────┐  │
        │  │       Execution Support Layer      [Fase 2]   │  │  ← no existe en Fase 0
        │  │     alertas · preparación de órdenes          │  │
        │  └───────────────────────────────────────────────┘  │
        │                                                      │
        └──────────────────────────────────────────────────────┘

             ┌──────────────────────────────┐
             │      Calculation Library     │
             │  resampling · estadísticas   │
             │  indicadores (Fase 1+)       │
             │  (sin estado · funcional)    │
             └──────────────────────────────┘
```

**Contratos entre capas:**

| Contrato | Firma | Fase activa |
|---|---|---|
| Data Layer → Processing | `get_snapshot(uid, tipo_dato, temporalidad_base) → pd.DataFrame` | Fase 0 |
| Processing → Strategy | `get_features(config) → pd.DataFrame` | Fase 1 |
| Strategy → Execution | `evaluate(features) → {action, price, explicability_metadata}` | Fase 1 |

**Nota sobre UIDs:** `uid` es siempre el UID canónico `(symbol, conId, exchange, secType)`.
Un string simple como `"AAPL"` no es un UID válido.

---

## Nivel 2 — Anatomía interna del Data Layer

El Data Layer es el corazón del sistema en Fase 0. Es el único componente que interactúa con IBKR.

```text
                         DataLayer (façade)
  ┌────────────────────────────────────────────────────────┐
  │                                                        │
  │  ConnectionManager                                     │
  │  ──────────────────                                    │
  │  · única conexión IBKR (TWS / IB Gateway)              │
  │  · reconexión automática con backoff exponencial       │
  │  · absorción silenciosa del reinicio diario de TWS     │
  │  · control de pacing — PACING_CODES = {162, 420, 10167}│
  │  · can_request() como válvula central de control       │
  │  · _ib privado — nunca accesible desde fuera           │
  │                                                        │
  │    HistoricalHandler                                   │
  │    ─────────────────                                   │
  │    · solicita reqHistoricalData vía ConnectionManager  │
  │    · normaliza barras al Canonical Data Model          │
  │    · gestiona recepción completa (historicalDataEnd)   │
  │    · no activa RT bars                                 │
  │                                                        │
  │    RealTimeHandler                                     │
  │    ─────────────────                                   │
  │    · gestiona reqRealTimeBars                          │
  │    · agrega barras de 5s a barras de 1m                │
  │    · solo entrega barras consolidadas                  │
  │    · nunca entrega barras parciales                    │
  │                                                        │
  │  SubscriptionRegistry                                  │
  │  ──────────────────                                    │
  │  · registro de suscripciones por (uid, tipo_dato)      │
  │  · deduplicación entre Jobs                            │
  │  · liberación al quedar sin consumidores               │
  │  · amortiguación de cancelaciones (5 segundos)         │
  │                                                        │
  │  DataDispatcher                                        │
  │  ──────────────                                        │
  │  · recibe barras normalizadas de los Handlers          │
  │  · actualiza DataBuffer (thread-safe)                  │
  │  · envía a PersistenceManager                          │
  │  · aplica costura histórico + RT (ADR-001)             │
  │  · registra huecos en critical_error.log               │
  │                                                        │
  │  DataBuffer                                            │
  │  ──────────                                            │
  │  · barras consolidadas en RAM por clave canónica       │
  │  · clave: (uid, tipo_dato, temporalidad_base)          │
  │  · thread-safe mediante RLock                          │
  │  · get_snapshot devuelve df.copy() — nunca referencia  │
  │  · retiene N barras = historical_window máximo activo  │
  │                                                        │
  │  PersistenceManager                                    │
  │  ──────────────────                                    │
  │  · escritura Parquet con esquema de partición canónico │
  │  · metadatos de contratos (conId, mult, expiry, etc.)  │
  │  · rechaza barras sin metadata de contrato asociada    │
  │  · gestión de MarketDB                                 │
  │                                                        │
  └────────────────────────────────────────────────────────┘
```

---

## Nivel 3 — Flujo de datos completo

**Flujo de escritura — desde el broker hacia persistencia y buffer:**

```text
IBKR (TWS / Gateway)
        │
        ▼
ConnectionManager
        │
        ├──────────────────────────┐
        ▼                          ▼
HistoricalHandler          RealTimeHandler
(normaliza al CDM)         (agrega 5s → 1m)
        │                          │
        └──────────┬───────────────┘
                   ▼
            DataDispatcher
            (costura histórico + RT — ADR-001)
                   │
       ┌───────────┴───────────┐
       ▼                       ▼
  DataBuffer             PersistenceManager
  (RAM — UID canónico)   (MarketDB — Parquet)
```

**Flujo de lectura — desde Processing hacia el buffer:**

```text
ProcessingEngine
(stub en Fase 0 · completo en Fase 1)
        │
        ▼
DataLayer.get_snapshot(uid, tipo_dato, temporalidad_base)
        │
        ▼
DataBuffer.get_snapshot()
        │
        ▼
pd.DataFrame
· índice: timestamp datetime64[ns, UTC]
· puede contener NaN — ADR-001
· es una copia inmutable — nunca referencia al buffer
```

**Tres propiedades críticas de este diseño:**

**1. Modelo Pull:** Processing solicita snapshots. Data Layer no empuja datos hacia los Jobs.
El ritmo de actualización del buffer pertenece a Data Layer.
El ritmo de consulta pertenece al ciclo del Job, controlado por el Scheduler.
No existe sincronización implícita entre ambos.

**2. Persistencia paralela:** Mientras los Jobs procesan, `IBKR → MarketDB` corre
en paralelo construyendo histórico de forma acumulativa (grabación forward).
Este histórico es el activo más valioso del sistema en Fase 0.

**3. Determinismo pragmático:** Los Jobs consumen velas consolidadas, no ticks.
La unidad mínima de reproducibilidad es el dato consolidado persistido.
Dado el mismo conjunto de datos consolidados, el sistema produce siempre el mismo output.

---

## Nivel 4 — Topología de concurrencia

```text
              Session Controller
                     │
                 Scheduler
                     │
       ┌─────────────┼─────────────┐
       │             │             │
     Job A         Job B         Job C
     (AAPL 1m)   (IWM 1m)    (TSLA 1m)    ← Fase 0: máx. 3 Jobs, 5 activos
       │             │             │          solo tipo STOCK con lógica analítica
       └──────┬──────┴──────┬──────┘
              │             │
              ▼             ▼
        DataLayer (único · centralizado · thread-safe)
              │
    ┌─────────┴──────────┐
    ▼                    ▼
DataBuffer          MarketDB
(RAM compartida)    (disco compartido)
```

**Modelo de estado por Job:**

| Componente | Compartido | Privado al Job |
|---|---|---|
| DataLayer | ✔ | |
| DataBuffer | ✔ | |
| PersistenceManager | ✔ | |
| Processing | | ✔ |
| Strategy [Fase 1] | | ✔ |
| Execution [Fase 2] | | ✔ |

El estado en ejecución de Processing, Strategy y Execution es privado al Job.
Las clases son compartidas; las instancias son independientes.

**Límites operativos en Fase 0:**

| Parámetro | Límite |
|---|---|
| Jobs simultáneos | 3 |
| Activos simultáneos | 5 |
| Temporalidad base | 1 minuto |
| Tipos con lógica analítica | STOCK únicamente |

---

## Nivel 5 — Modelo de control

```text
    Session Controller
           │
           ▼
       Scheduler
       (loop interno, tick = 1s)
           │
           │ cada ciclo temporal del Job
           ▼
       Job Tick
           │
           ▼
     DataLayer.get_snapshot()    ← único acceso permitido a Data Layer
           │
           ▼
       Processing                ← stub en Fase 0
       (resampling, features)    ← completo en Fase 1
           │
           ▼ [Fase 1]
        Strategy
           │
           ▼ [Fase 2]
    Execution Support
```

**Separación de ritmos:**

```text
Ritmo de actualización del buffer → pertenece a Data Layer
                                    (actualizado por DataDispatcher al recibir barras)

Ritmo de consulta del Job         → pertenece al Scheduler
                                    (activado según timeframe_base del JobConfig)

No existe sincronización implícita entre ambos ritmos.
```

**Restricción del Scheduler:**
Un Job no puede ejecutar múltiples ciclos dentro de la misma unidad temporal.
El Scheduler bloquea activaciones anticipadas comparando:
`timestamp_actual < última_activación + timeframe_base → no activar`

---

## Nivel 6 — Canonical Data Model

Todo DataFrame que circula entre capas respeta este esquema.

```text
Índice:   timestamp   datetime64[ns, UTC]   ← índice del DataFrame, nunca columna

Columnas:
          open        float64
          high        float64
          low         float64
          close       float64
          volume      Int64    ← nullable, NaN cuando IBKR devuelve -1
          barCount    Int64    ← nullable, NaN cuando IBKR devuelve -1
```

**Regla ADR-001 — Manejo de datos ausentes:**
Los valores ausentes se representan como NaN. Nunca como 0 ni como el valor anterior.
Ninguna capa imputa datos ausentes excepto Strategy (Fase 1).
La presencia de NaN es una señal legítima del sistema, no un error.

---

## Nivel 7 — Estructura física del repositorio

```text
/project_root
  │
  ├── /production
  │     ├── /session
  │     │     ├── session_controller.py
  │     │     ├── scheduler.py
  │     │     └── job_config.py
  │     │
  │     ├── /data_layer
  │     │     ├── data_layer.py              ← façade pública
  │     │     ├── connection_manager.py
  │     │     ├── historical_handler.py
  │     │     ├── realtime_handler.py
  │     │     ├── data_dispatcher.py
  │     │     ├── data_buffer.py
  │     │     ├── persistence_manager.py
  │     │     └── subscription_registry.py
  │     │
  │     ├── /processing
  │     │     └── processing_engine.py       ← stub en Fase 0
  │     │
  │     └── /common
  │           ├── indicators.py
  │           ├── resampling.py
  │           └── statistics.py
  │
  │     ── /strategy                         ← no existe en Fase 0
  │     ── /execution                        ← no existe en Fase 0
  │
  ├── /marketdb
  │     └── /STK
  │           └── /AAPL
  │                 └── /2026
  │                       └── /03
  │                             ├── AAPL_202603.parquet
  │                             └── contract_metadata.json
  │
  ├── /research
  │     └── /notebooks          ← experimentos · imports desde producción prohibidos
  │
  └── /docs
        └── /architecture       ← documentación cognitiva
```

La separación `/production` vs `/research` es obligatoria.
Los imports desde producción hacia research están prohibidos.

---

## Nivel 8 — Modos operativos

| Modo | Descripción | Fase 0 |
|---|---|---|
| `HISTORICAL_MODE` | Backtesting con data en reposo. Sin acceso a IBKR. Stubs locales en Fase 0; MarketDB completo en Fase 1. | Solo stubs |
| `FORWARD_RECORDING_MODE` | Captura pasiva hacia MarketDB. Sin lógica estratégica. | ✔ Activo |
| `LIVE_SCAN_MODE` | Operativa real con todas las capas activas. | ✗ Bloqueado |

---

## Nivel 9 — Estado del sistema por fase

| Componente | Fase 0 | Fase 1 | Fase 2 |
|---|---|---|---|
| ConnectionManager | ✔ Completo | — | — |
| HistoricalHandler | ✔ Completo | — | — |
| RealTimeHandler | ✔ Completo | — | — |
| SubscriptionRegistry | ✔ Completo | — | — |
| DataDispatcher | ✔ Completo | — | — |
| DataBuffer | ✔ Completo | — | — |
| PersistenceManager | ✔ Completo | — | — |
| DataLayer façade | ✔ Completo | — | — |
| Librería Common (base) | ✔ Base mínima | ✔ Expandida | — |
| JobConfig | ✔ Completo | — | — |
| Scheduler | ✔ Completo | — | — |
| SessionController | ✔ Completo | — | — |
| ProcessingEngine | ✔ Stub | ✔ Completo | — |
| Strategy Layer | ✗ | ✔ | — |
| Execution Support | ✗ | ✗ | ✔ |

---

## Nivel 10 — Qué separa este sistema de un script de trading común

| Problema habitual | Solución en este sistema |
|---|---|
| Datos y estrategia mezclados | Data Layer aislado con contrato estable |
| Múltiples activos = código duplicado | Modelo multi-job con instancias independientes |
| Resultados no reproducibles | Determinismo pragmático sobre velas consolidadas |
| Histórico de opciones inexistente | Grabación forward desde Fase 0 |
| Código que no escala | Arquitectura por fases sin rediseño estructural |
| Pacing storms ante reconexión | ConnectionManager con backoff y válvula can_request() |
| Datos ausentes enmascarados | ADR-001: NaN propagado, sin imputación silenciosa |

---

## Relación con la documentación oficial

| Documento | Rol |
|---|---|
| Development Governance Framework | Rige cómo evoluciona el proyecto |
| Project Charter | Define propósito y límites estratégicos |
| System Concept Specification | Define los principios conceptuales |
| Blueprint Técnico | Define la arquitectura técnica contractual |
| Phase 0 Implementation Spec v1.1 | Define qué debe existir y cómo debe comportarse |
| Phase 0 Implementation Roadmap v1.2 | Define el orden de construcción |
| **Este documento** | Visualización cognitiva de ingeniería |

---

*Este documento es una ayuda cognitiva. No modifica, extiende ni reemplaza el Blueprint Técnico.
Toda autoridad arquitectónica reside en el Blueprint.*
