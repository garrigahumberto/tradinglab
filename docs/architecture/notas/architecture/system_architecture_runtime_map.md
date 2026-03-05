# System Architecture — Runtime Map

**Status:** Visualización cognitiva de ingeniería — No contractual
**Authority:** Ninguna
**Fuente de verdad:** Blueprint Técnico
**Ubicación sugerida:** /notebooks/architecture/system_architecture_runtime_map.md

---

## Propósito

Este documento provee una visualización intuitiva de la arquitectura del sistema en tiempo de ejecución.

No es un documento contractual y no reemplaza ninguna especificación formal. Su objetivo es permitir al ingeniero ver el sistema completo de un vistazo, mantener coherencia arquitectónica durante la implementación y reducir errores de diseño mental.

El Blueprint Técnico permanece como la especificación arquitectónica de autoridad.

---

## Nivel 1 — Vista estructural completa

```
                    ┌──────────────────────────────┐
                    │       Session Controller      │
                    │  crea · configura · destruye  │
                    │  Jobs y registra sus datos    │
                    │  en Data Layer                │
                    └──────────────┬────────────────┘
                                   │
                                   │ gestiona N Jobs simultáneos
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │                      JOB (N)                         │
        │                                                       │
        │  ┌────────────────────────────────────────────────┐  │
        │  │                 Data Layer                     │  │
        │  │           (servicio centralizado)              │  │
        │  │                                                │  │
        │  │  Connection Manager ──────────────► IBKR       │  │
        │  │  Subscription Registry                         │  │
        │  │  Data Dispatcher                               │  │
        │  │  Persistence Manager ─────────────► MarketDB   │  │
        │  └──────────────┬─────────────────────────────────┘  │
        │                 │ get_snapshot(uid, tipo, temporalidad)│
        │  ┌──────────────▼─────────────────────────────────┐  │
        │  │              Processing Layer                  │  │
        │  │    resampling · alineación · features          │  │
        │  └──────────────┬─────────────────────────────────┘  │
        │                 │ get_features(config)               │
        │  ┌──────────────▼─────────────────────────────────┐  │
        │  │               Strategy Layer                   │  │
        │  │        evaluación de hipótesis                 │  │
        │  └──────────────┬─────────────────────────────────┘  │
        │                 │ evaluate() → señal + metadata      │
        │  ┌──────────────▼─────────────────────────────────┐  │
        │  │           Execution Support Layer              │  │
        │  │     alertas · preparación de órdenes           │  │
        │  └────────────────────────────────────────────────┘  │
        │                                                       │
        └───────────────────────────────────────────────────────┘

             ┌─────────────────────────────┐
             │     Calculation Library     │
             │  indicadores · resampling   │
             │  estadísticas · utilidades  │
             │  (sin estado · funcional)   │
             └─────────────────────────────┘
```

**Nota sobre contratos:**
- `get_snapshot` recibe un UID canónico `(symbol, conId, exchange, secType)`, no un string simple.
- `get_features` devuelve un DataFrame alineado temporalmente, sin estado oculto.
- `evaluate` devuelve señal con `explicability_metadata` obligatorio.

---

## Nivel 2 — Anatomía interna del Data Layer

El Data Layer es el corazón del sistema en Fase 0. Es el único componente que habla con IBKR.

```
                         Data Layer
  ┌──────────────────────────────────────────────────┐
  │                                                  │
  │  Connection Manager                              │
  │  ─────────────────                               │
  │  · única conexión IBKR                           │
  │  · reconexiones con backoff exponencial          │
  │  · gestión de pacing y throttling                │
  │  · absorción de reinicios diarios del broker     │
  │                                                  │
  │  Subscription Registry                           │
  │  ─────────────────                               │
  │  · registro de suscripciones activas             │
  │  · deduplicación entre Jobs                      │
  │  · liberación al quedar sin consumidores         │
  │                                                  │
  │  Data Dispatcher                                 │
  │  ─────────────────                               │
  │  · recibe datos de IBKR                          │
  │  · actualiza buffers internos                    │
  │  · modelo Pull — no empuja hacia los Jobs        │
  │                                                  │
  │  Persistence Manager                             │
  │  ─────────────────                               │
  │  · escritura Parquet particionado                │
  │  · metadatos de contratos (conId, mult, expiry)  │
  │  · gestión de MarketDB                           │
  │                                                  │
  └──────────────────────────────────────────────────┘
```

---

## Nivel 3 — Flujo de datos completo

```
           IBKR (TWS / Gateway)
                  │
                  ▼
       Connection Manager
                  │
                  ▼
          Data Dispatcher
                  │
                  ├──────────────► Persistence Manager
                  │                       │
                  │                       ▼
                  │               MarketDB (Parquet)
                  │
                  ▼
          Buffers internos
                  │
                  ▼
    get_snapshot(uid, tipo, temporalidad)
                  │
                  ▼
             Processing
                  │
                  ▼
              Strategy
                  │
                  ▼
        Execution Support
```

Tres propiedades críticas de este flujo:

**1. Modelo Pull:** Processing solicita snapshots. No hay push ni eventos asíncronos en Fase 0.

**2. Persistencia paralela:** Mientras los Jobs procesan, `IBKR → MarketDB` corre en paralelo construyendo histórico de forma acumulativa (grabación forward).

**3. Determinismo pragmático:** Los Jobs consumen velas consolidadas, no ticks. La unidad mínima de reproducibilidad es el dato consolidado persistido.

---

## Nivel 4 — Topología de concurrencia

```
              Session Controller
                     │
       ┌─────────────┼─────────────┐
       │             │             │
     Job A         Job B         Job C
     (AAPL 1m)   (IWM 5m)    (opciones 0DTE)
       │             │             │
       └──────┬──────┴──────┬──────┘
              │             │
              ▼             ▼
           Data Layer (único · centralizado)
```

Cada Job tiene sus propias instancias de Processing, Strategy y Execution. Las clases son compartidas; el estado en ejecución es privado al Job. Data Layer es el único componente genuinamente compartido.

---

## Nivel 5 — Modelo de control

```
    Session Controller
           │
           ▼
       Scheduler
           │
           ▼  (cada ciclo temporal del Job)
       Job Tick
           │
           ▼
     get_snapshot()
           │
           ▼
       Processing
           │
           ▼
        Strategy
           │
           ▼
    Execution Support
```

Los Jobs no se autoejecutan. El Scheduler central controla el ritmo de cada ciclo. El ritmo de actualización de buffers pertenece a Data Layer. El ritmo de consulta pertenece al ciclo del Job. No existe sincronización implícita entre ambos.

---

## Nivel 6 — Estructura física del repositorio

```
/project_root
  │
  ├── /production
  │     ├── /session
  │     │     └── session_controller.py
  │     │
  │     ├── /data_layer
  │     │     ├── connection_manager.py
  │     │     ├── subscription_registry.py
  │     │     ├── data_dispatcher.py
  │     │     └── persistence_manager.py
  │     │
  │     ├── /processing
  │     │     └── processing_engine.py
  │     │
  │     ├── /strategy
  │     │     └── strategy_base.py
  │     │
  │     ├── /execution
  │     │     └── execution_support.py
  │     │
  │     └── /common
  │           ├── indicators.py
  │           ├── resampling.py
  │           └── statistics.py
  │
  ├── /marketdb
  │     └── /stock
  │           └── /AAPL
  │                 └── /2026
  │                       └── /03
  │                             └── AAPL_202603.parquet
  │
  ├── /research
  │     └── /notebooks       # Experimentos de investigación
  │
  └── /notebooks
        └── /architecture    # Documentación cognitiva
```

La separación `/production` vs `/research` es obligatoria según el Blueprint. Los imports desde producción hacia research están prohibidos.

---

## Nivel 7 — Modos operativos

| Modo | Descripción | Fase 0 |
|---|---|---|
| `HISTORICAL_MODE` | Backtesting con data en reposo. Sin acceso a IBKR. Stubs en Fase 0; MarketDB real en Fase 1. | Solo stubs |
| `FORWARD_RECORDING_MODE` | Captura pasiva hacia MarketDB. Sin lógica estratégica. | ✔ Activo |
| `LIVE_SCAN_MODE` | Operativa real con todas las capas activas. | ✗ Bloqueado |

---

## Qué separa este sistema de un script de trading común

| Problema habitual | Solución en este sistema |
|---|---|
| Datos y estrategia mezclados | Data Layer aislado con contrato estable |
| Múltiples activos = código duplicado | Modelo multi-job con instancias independientes |
| Resultados no reproducibles | Determinismo pragmático sobre velas consolidadas |
| Histórico de opciones inexistente | Grabación forward desde Fase 0 |
| Código que no escala | Arquitectura por fases sin rediseño |

---

## Relación con la documentación oficial

| Documento | Rol |
|---|---|
| Development Governance Framework | Rige cómo evoluciona el proyecto |
| Project Charter | Define propósito y límites estratégicos |
| System Concept Specification | Define los principios conceptuales |
| Blueprint Técnico | Define la arquitectura técnica |
| **Este documento** | Visualización cognitiva de ingeniería |

---

*Este documento es una ayuda cognitiva. No modifica, extiende ni reemplaza el Blueprint Técnico. Toda autoridad arquitectónica reside en el Blueprint.*
