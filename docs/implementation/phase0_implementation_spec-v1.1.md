# Phase 0 — Implementation Specification

**Versión:** 1.1
**Status:** Implementation Guide
**Authority:** Derived from Blueprint Técnico v1.0.1
**Scope:** Construcción del Data Layer y la infraestructura mínima para captura de datos de mercado.
**Cambios respecto a v1.0:** Correcciones derivadas de auditoría arquitectónica. Ver sección §15.

---

## 1️⃣ Propósito de la Fase 0

La Fase 0 establece la infraestructura fundamental de datos del sistema.
Su objetivo es construir un Data Layer funcional capaz de:

- Conectarse a Interactive Brokers con reconexiones automáticas y absorción de interrupciones.
- Capturar barras de mercado históricas y en tiempo real.
- Persistir datos en almacenamiento estructurado con metadatos de contrato obligatorios.
- Servir snapshots consistentes e inmutables a los Jobs del sistema.
- Detectar y registrar huecos temporales.

Esta fase **no implementa** estrategias, señales ni ejecución de órdenes.
Su función es crear el sistema de adquisición y almacenamiento de datos sobre el cual se construirá todo el sistema posterior.

> **Restricción formal:** Ningún componente de esta fase puede introducir lógica perteneciente a Fase 1 o superior. La violación de esta restricción activa revisión formal de gobernanza.

---

## 2️⃣ Alcance de la Fase

La Fase 0 incluye únicamente la implementación de:

**Infraestructura de sesión**
- `SessionController`
- `Scheduler`

**Data Layer completo**
- `ConnectionManager`
- `SubscriptionRegistry`
- `DataDispatcher`
- `DataBuffer`
- `PersistenceManager`
- `DataLayer` (façade)

**Componente mínimo de consumo**
- `ProcessingEngine` (stub)

> **Nota sobre el stub de Processing:** Se autoriza un stub de ProcessingEngine exclusivamente
> para validar el contrato `get_snapshot` durante el desarrollo. Este stub debe respetar
> exactamente el contrato de salida de Data Layer: mismo esquema de DataFrame, mismos
> metadatos de granularidad, mismo formato de columnas. Un stub que no respete ese contrato
> no es válido y su uso queda prohibido.
> Ver Blueprint §3 (Cláusula de Desarrollo Paralelo).

**Fuera del alcance de esta fase:**
- `StrategyBase` o cualquier esqueleto de Strategy Layer.
- `ExecutionSupport` o cualquier esqueleto de Execution Support Layer.
- Indicadores técnicos estratégicos en la librería común.
- Backtesting o evaluación de hipótesis.

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
```
pandas
numpy
pyarrow
ib_insync
```

---

## 4️⃣ Fuente de Datos

El sistema utilizará Interactive Brokers API.

Tipos de datos utilizados en Fase 0:
- `HistoricalBars` (vía `reqHistoricalData`)
- `RealTimeBars` (vía `reqRealTimeBars`)

**Temporalidad base:** 1 minute bars.

---

## 5️⃣ Límites Operativos de Fase 0

| Parámetro | Valor |
|---|---|
| Activos máximos simultáneos | 5 |
| Jobs simultáneos | 3 |
| Temporalidad base | 1 minuto |
| Tipo de contrato con lógica analítica | `STOCK` únicamente |

> Los tipos `OPTION` y `FUTURE` pueden ingerirse y persistirse para acumulación forward de histórico,
> pero no tendrán lógica analítica asociada hasta fases posteriores.

*Estos límites podrán ampliarse mediante decisión formal en fases posteriores.*

---

## 6️⃣ Identificador Canónico de Activo (UID)

Todo activo en el sistema se identifica mediante un **UID canónico obligatorio**.

**Estructura:**
```python
uid: tuple = (symbol: str, conId: int, exchange: str, secType: str)
```

**Ejemplo:**
```python
("AAPL", 265598, "NASDAQ", "STK")
```

**Regla:** El `conId` de IBKR no es opcional. Cualquier operación de buffer, suscripción
o persistencia que use únicamente `symbol` como clave es inválida por diseño.

---

## 7️⃣ Contrato de Configuración de Job (JobConfig)

Todo Job debe declararse mediante una estructura `JobConfig` explícita.
El SessionController no puede instanciar un Job sin una configuración válida.

**Estructura mínima para Fase 0:**

```python
@dataclass
class JobConfig:
    uid: tuple                  # UID canónico: (symbol, conId, exchange, secType)
    data_types: list[str]       # Tipos de dato requeridos: ["historical_bars", "rt_bars"]
    timeframe_base: str         # Temporalidad base: "1m"
    historical_window: int      # Ventana histórica requerida en barras
    persistence_policy: str     # "always" | "on_close"
    strategy_config: None       # Siempre None en Fase 0
    execution_config: None      # Siempre None en Fase 0
```

**Reglas:**
- `strategy_config` y `execution_config` son siempre `None` en Fase 0.
  Su presencia con valor no-None en Fase 0 es una violación de alcance.
- `historical_window` determina cuántas barras retiene el DataBuffer para este Job.
  Data Layer retiene en RAM la ventana máxima declarada entre todos los Jobs activos.
- La validación de JobConfig ocurre en SessionController antes de instanciar el Job.
  Un Job no puede existir sin una configuración válida.

---

## 8️⃣ Arquitectura de Flujo de Datos

**Flujo de captura (escritura):**
```
IBKR
   │
ConnectionManager
   │
DataDispatcher
   │
 ┌─┴──────────────────┐
 ▼                    ▼
DataBuffer       PersistenceManager
```

**Flujo de lectura (snapshots):**
```
ProcessingEngine (stub)
   │
DataLayer.get_snapshot()
   │
DataBuffer
```

**Modelo:** Pull determinista. Los Jobs solicitan snapshots; Data Layer no empuja eventos.

---

## 9️⃣ Contrato `get_snapshot`

Este es el contrato principal entre Data Layer y Processing.
La firma es contractual y no puede modificarse sin activar Revisión Formal de Gobernanza.

```python
def get_snapshot(
    uid: tuple,           # UID canónico del activo
    tipo_dato: str,       # "historical_bars" | "rt_bars"
    temporalidad_base: str  # "1m"
) -> pd.DataFrame
```

**Garantías del contrato:**

| Garantía | Descripción |
|---|---|
| Copia independiente | Devuelve una copia, no una referencia al buffer interno. Modificar el DataFrame retornado no afecta el buffer. |
| Inmutabilidad | El DataFrame retornado representa el estado consolidado en el momento de la llamada. |
| Ventana delimitada | Devuelve únicamente la ventana histórica declarada en JobConfig. No más. |
| Sin efecto lateral | No fuerza actualización de buffers. No altera suscripciones. |
| Etiquetado explícito | El DataFrame incluye metadatos de granularidad y tipo de dato. Processing los lee; no los infiere. |
| Frecuencia máxima | Processing no puede invocar `get_snapshot` con frecuencia superior al ciclo temporal del Job. Este límite lo hace cumplir el Scheduler. |

**Restricción NaN (ADR-001):**
El DataFrame retornado puede contener NaN. Data Layer no imputa valores ausentes.
Processing no puede aplicar `.fillna()`, `ffill()` ni `bfill()` sobre datos crudos antes
de calcular features. Los NaN deben propagarse de forma transparente.
Ver Blueprint §1.2 (Processing) y ADR-001.

---

## 🔟 Componentes a Implementar

### SessionController

**Responsabilidades:**
- Inicializar y apagar el sistema de forma controlada.
- Validar y crear Jobs a partir de JobConfig.
- Registrar necesidades de datos de cada Job en Data Layer.
- Controlar el ciclo de ejecución de Jobs mediante el Scheduler.
- Destruir Jobs y coordinar la liberación de suscripciones.
- Es la única entidad autorizada a modificar el universo de activos monitoreados.

**Restricciones:**
- No procesa datos.
- No accede a IBKR.
- No conoce lógica de mercado.

---

### Scheduler

**Responsabilidades:**
- Activar el ciclo de ejecución de cada Job según la temporalidad declarada en su JobConfig.
- Garantizar que ningún Job ejecute múltiples ciclos dentro de la misma unidad temporal.
- Prevenir que Processing invoque `get_snapshot` con frecuencia superior a la permitida.

**Mecanismo:**
- Opera sobre un loop de control interno con tick mínimo de 1 segundo.
- Lleva registro del último timestamp de activación por Job.
- Bloquea activaciones anticipadas: un Job no puede reactivarse hasta que haya transcurrido su temporalidad completa desde la última activación.

---

### DataLayer (façade)

**Responsabilidades:**
- Exponer la interfaz pública del sistema de datos hacia Processing.
- Coordinar los componentes internos (Connection, Registry, Dispatcher, Buffer, Persistence).
- Absorber internamente las interrupciones de IBKR. Las capas superiores nunca reciben errores de broker.

**Métodos públicos mínimos:**
```python
def subscribe_asset(uid: tuple, data_types: list[str], historical_window: int) -> None
def get_snapshot(uid: tuple, tipo_dato: str, temporalidad_base: str) -> pd.DataFrame
def unsubscribe_asset(uid: tuple) -> None
def shutdown() -> None
```

---

### ConnectionManager

**Responsabilidades:**
- Gestionar la única conexión con IBKR.
- Ejecutar reconexión automática ante desconexión.
- Absorber el reinicio diario forzoso de TWS sin exponer la interrupción a capas superiores.
- Aplicar la política de degradación ante pacing limits.
- Enviar solicitudes de datos al broker.

**Métodos principales:**
```python
def connect() -> None
def disconnect() -> None
def subscribe_realtime_bars(contract) -> None
def request_historical_bars(contract, duration: str, bar_size: str) -> None
```

**Política de reconexión:**
- Ante desconexión: backoff exponencial. Intentos: 1s, 2s, 4s, 8s, 16s, 32s, máximo 60s.
- Durante reconexión: Data Layer pausa activaciones de Jobs. Las capas superiores no perciben la interrupción.
- Al recuperar conexión: Data Layer reanuda operación y solicita refresco de datos si el gap supera el umbral definido en JobConfig.

**Política de absorción del reinicio diario de TWS:**
- TWS ejecuta un reinicio forzoso una vez al día (configurable en el broker, típicamente entre 23:45 y 00:15 EST).
- ConnectionManager debe detectar este ciclo y orquestar una reconexión silenciosa.
- El gap generado por el reinicio se registra en `critical_error.log` como hueco esperado.
- No se intenta recuperar datos de ese intervalo automáticamente en Fase 0.

**Política de degradación ante pacing limits (obligatoria):**
- Ante respuesta de throttling o alerta de pacing limit del broker: pausa de 10 segundos mínimo antes de reintentar.
- Ante rechazos reiterados (3 o más consecutivos): backoff exponencial adicional. Máximo 5 minutos de pausa.
- El sistema nunca insiste ante rechazos reiterados del broker.
- Todo evento de pacing limit se registra en `critical_error.log`.

---

### SubscriptionRegistry

**Responsabilidades:**
- Registrar y mantener las suscripciones activas por UID canónico y tipo de dato.
- Evitar suscripciones duplicadas entre Jobs.
- Rastrear qué Jobs consumen cada suscripción.
- Liberar una suscripción cuando ningún Job activo la requiere.

**Regla de deduplicación:**
- Si dos Jobs declaran necesitar el mismo `(uid, tipo_dato)`, SubscriptionRegistry mantiene
  una única suscripción activa y registra ambos Jobs como consumidores.
- La suscripción solo se cancela cuando el último consumidor registrado es eliminado.

**Amortiguación de cancelaciones:**
- SubscriptionRegistry puede diferir la cancelación de una suscripción hasta 5 segundos
  ante cancelaciones y reactivaciones sucesivas del mismo activo dentro de esa ventana,
  exclusivamente para evitar violaciones de pacing. Esta lógica es interna y no se expone.

---

### DataDispatcher

**Responsabilidades:**
- Recibir datos crudos del broker a través de los callbacks de `ib_insync`.
- Normalizar estructura al Canonical Data Model.
- Actualizar DataBuffer con cada barra consolidada.
- Enviar datos a PersistenceManager.
- Registrar huecos detectados.

**Política de dato consolidado:**
Un dato se considera consolidado y servible vía `get_snapshot` cuando:
- Para `RealTimeBars`: al completarse el intervalo de 5 segundos nativo de IBKR y ser agregado a la barra de 1 minuto en curso.
- Para `HistoricalBars`: al recibirse la barra completa del broker (evento `historicalData`).
- Una barra parcial (en construcción) nunca se expone como dato consolidado.

**Política de costura histórico + RT bars:**
Al inicializar un activo, el orden de operaciones es:
1. Solicitar `HistoricalBars` con la ventana declarada en JobConfig.
2. Esperar la respuesta completa del broker (`historicalDataEnd`).
3. Activar `RealTimeBars` únicamente después de recibir el histórico completo.
4. Al recibir la primera RT bar, verificar continuidad temporal con la última barra histórica.
5. Si existe solapamiento (la RT bar tiene timestamp ≤ última barra histórica): descartar RT bar duplicada.
6. Si existe hueco (gap > 1 minuto entre última barra histórica y primera RT bar): registrar hueco en log y continuar.
7. Ningún mecanismo de interpolación ni imputación se aplica en este punto.

**Thread safety:**
- DataDispatcher opera bajo el modelo de concurrencia del event loop de `ib_insync`.
- El acceso al DataBuffer debe ser thread-safe. Toda escritura al buffer usa lock explícito.

---

### DataBuffer

**Responsabilidades:**
- Mantener en memoria los datos consolidados recientes por activo.
- Permitir acceso rápido e inmutable a snapshots.
- Gestionar la ventana de retención según la ventana histórica máxima declarada entre Jobs activos.

**Estructura interna:**
```python
# Clave: (uid_canónico, tipo_dato, temporalidad_base)
# Valor: DataFrame con columnas [timestamp, open, high, low, close, volume, barCount]
dict[
    tuple[tuple, str, str],  # ((symbol, conId, exchange, secType), tipo_dato, timeframe)
    pd.DataFrame
]
```

**Gestión de memoria:**
- El buffer retiene únicamente las últimas N barras, donde N es el `historical_window` máximo
  declarado entre todos los Jobs activos que consumen ese activo.
- Barras fuera de esa ventana son descartadas de memoria tras ser confirmadas como persistidas.

**Thread safety:**
- Toda operación de lectura y escritura sobre el buffer usa `threading.RLock`.
- `get_snapshot` siempre devuelve `df.copy()`, nunca una referencia directa al DataFrame interno.

---

### PersistenceManager

**Responsabilidades:**
- Persistir datos de mercado en MarketDB en formato Parquet.
- Persistir metadatos de contrato por cada activo.
- Gestionar el esquema de partición físico.
- Garantizar integridad: nunca persistir DataFrames con estructura corrupta.

**Esquema de partición físico (obligatorio):**
```
/marketdb/{asset_type}/{symbol}/{year}/{month}/{symbol}_{year}{month}.parquet
```

Ejemplo:
```
/marketdb/STK/AAPL/2026/03/AAPL_202603.parquet
```

**Frecuencia de escritura:**
- Escritura por barra consolidada para `RealTimeBars` (continua durante sesión activa).
- Escritura en batch al recibir `historicalDataEnd` para `HistoricalBars`.
- Al cierre de sesión: flush forzoso de cualquier dato en buffer no persistido aún.

**Persistencia obligatoria de metadatos de contrato:**
Por cada activo, PersistenceManager persiste y mantiene actualizado un archivo de metadatos:
```
/marketdb/{asset_type}/{symbol}/contract_metadata.json
```

Campos obligatorios:
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

> Una serie de tiempo sin su definición contractual asociada no se considera válida.
> PersistenceManager debe rechazar la persistencia de barras si no existe metadata de contrato asociada.

**Integridad pre-persistencia:**
- Prohibido persistir DataFrames con columnas faltantes del Canonical Data Model.
- Prohibido persistir DataFrames con timestamp no-UTC o tipo distinto a `datetime64[ns, UTC]`.
- Los huecos se registran como huecos explícitos en log. No se interpolan.

---

## 1️⃣1️⃣ Canonical Data Model

Todo DataFrame persistido o transmitido entre capas debe adherirse a este esquema:

| Campo | Tipo | Descripción |
|---|---|---|
| `timestamp` | `datetime64[ns, UTC]` | Timestamp UTC estricto. Nunca naive. |
| `open` | `float64` | Precio de apertura |
| `high` | `float64` | Precio máximo |
| `low` | `float64` | Precio mínimo |
| `close` | `float64` | Precio de cierre |
| `volume` | `int64` | Volumen |
| `barCount` | `int64` | Número de trades en la barra |

**Reglas:**
- El índice del DataFrame es `timestamp`.
- Las columnas deben estar presentes y con los tipos exactos declarados.
- Los valores ausentes se representan como NaN. Nunca como 0 ni como el valor anterior.
  Ver ADR-001.

---

## 1️⃣2️⃣ Manejo de Datos Ausentes (ADR-001)

> **Referencia obligatoria:** Architecture Decision Log — ADR-001.

**Reglas de implementación:**

- Data Layer entrega DataFrames que pueden contener NaN. No los imputa.
- DataDispatcher no rellena huecos temporales. Los registra en log y los propaga.
- Processing (stub en Fase 0) no puede aplicar `.fillna()`, `ffill()` ni `bfill()` sobre
  datos crudos. Esta restricción es aplicable desde Fase 0 para establecer el patrón correcto.
- La librería común de cálculo debe propagar NaN de forma predecible. Ninguna función
  puede enmascarar ausencia de datos mediante imputación implícita.
- La presencia de NaN en un DataFrame es una señal legítima del sistema, no un error.

---

## 1️⃣3️⃣ Fault Handling Policy

| Evento | Comportamiento requerido |
|---|---|
| Desconexión de broker | Backoff exponencial. Pausa controlada de Jobs. Reanudación silenciosa al reconectar. |
| Reinicio diario de TWS | Reconexión silenciosa. Hueco registrado en log como esperado. |
| Pacing limit / throttling | Pausa mínima 10s. Backoff exponencial ante rechazos reiterados. Registro en `critical_error.log`. |
| Hueco temporal detectado | Registro en `critical_error.log`. Sin sanación automática en Fase 0. Corrección manual posterior. |
| DataFrame corrupto | Rechazo de persistencia. Registro en `critical_error.log`. |
| Error en un Job | Aislado. No compromete otros Jobs ni el sistema completo. |

**Logs mínimos requeridos:**
- `critical_error.log`: fallos de red, pacing, huecos temporales, errores de persistencia.
- `system.log`: eventos de ciclo de vida (conexión, suscripciones, Jobs activos, shutdown).

Formato de log: estructurado (JSON o similar). No texto libre.

---

## 1️⃣4️⃣ Modos Operativos

Durante Fase 0 el sistema opera exclusivamente en:

**`FORWARD_RECORDING_MODE`**
- Captura pasiva de datos.
- Persistencia continua.
- Sin evaluación de estrategias.

Los modos `HISTORICAL_MODE` y `LIVE_SCAN_MODE` quedan reservados para fases posteriores.

---

## 1️⃣5️⃣ Estructura de Repositorio

```
/production
    /session
        session_controller.py
        scheduler.py

    /data_layer
        data_layer.py
        connection_manager.py
        subscription_registry.py
        data_dispatcher.py
        data_buffer.py
        persistence_manager.py

    /processing
        processing_engine.py       ← stub en Fase 0

    /common
        indicators.py
        resampling.py
        statistics.py

/marketdb
    /STK
        /{symbol}
            /contract_metadata.json
            /{year}/{month}/
    /OPT
        ...
    /FUT
        ...

/research
    /notebooks

/docs
    /architecture
    /implementation
```

> Los directorios `/strategy` y `/execution` no existen en Fase 0.
> Su creación anticipada viola la Regla Anti-Abstracciones Preventivas del Blueprint.

---

## 1️⃣6️⃣ Orden de Implementación

Los componentes deben implementarse en el siguiente orden, de la base hacia arriba:

1. `ConnectionManager` — conexión básica, reconexión, callbacks de datos
2. `SubscriptionRegistry` — registro de suscripciones y deduplicación
3. `DataBuffer` — almacenamiento en memoria con UID canónico y thread safety
4. `DataDispatcher` — normalización, costura histórico+RT, actualización de buffer
5. `PersistenceManager` — escritura Parquet, metadatos de contrato, integridad
6. `DataLayer` — façade que coordina los anteriores
7. `Scheduler` — control de ciclo temporal de Jobs
8. `SessionController` — ciclo de vida completo del sistema
9. `ProcessingEngine` (stub) — validación del contrato `get_snapshot`

Cada componente debe tener tests unitarios aprobados antes de pasar al siguiente.

---

## 1️⃣7️⃣ Criterios de Finalización

La Fase 0 se considera completada cuando:

- [ ] El sistema se conecta a IBKR y gestiona reconexiones automáticamente
- [ ] El sistema absorbe el reinicio diario de TWS sin intervención manual
- [ ] El sistema gestiona pacing limits sin fallar ni insistir ante rechazos
- [ ] El sistema suscribe activos usando UID canónico sin duplicados
- [ ] El sistema recibe y costura barras históricas y RT correctamente
- [ ] El sistema persiste datos en el esquema de partición definido
- [ ] El sistema persiste metadatos de contrato por cada activo
- [ ] El sistema registra huecos en log estructurado
- [ ] `get_snapshot` devuelve copias inmutables respetando la ventana histórica
- [ ] El sistema opera con 3 Jobs simultáneos sobre 5 activos sin condiciones de carrera
- [ ] El sistema puede reconstruir cualquier sesión pasada exclusivamente con datos propios persistidos

---

## 1️⃣8️⃣ Fuera de Alcance

No forman parte de Fase 0:

- Strategy Layer (ningún esqueleto ni stub)
- Execution Support Layer (ningún esqueleto ni stub)
- Indicadores técnicos estratégicos
- Backtesting o evaluación de hipótesis
- HISTORICAL_MODE completo (uso de stubs locales permitido para validación de contratos únicamente)
- Ejecución de órdenes
- Optimización de parámetros
- Gestión de portafolio

---

## 1️⃣9️⃣ Relación con el Blueprint

Este documento traduce el Blueprint Técnico v1.0.1 en un plan de implementación concreto para Fase 0.

**El Blueprint permanece como fuente de verdad arquitectónica absoluta.**

En caso de contradicción entre este documento y el Blueprint, prevalece el Blueprint
y la contradicción debe reportarse al Núcleo Arquitectónico antes de continuar.

---

## 📌 Registro de Cambios

| Versión | Cambio |
|---|---|
| v1.0 | Versión inicial |
| v1.1 | Correcciones post-auditoría: eliminación de stubs de Strategy y Execution; firma completa de `get_snapshot`; clave de DataBuffer corregida al UID canónico; esquema de partición de MarketDB incorporado; persistencia de metadatos de contrato; requisitos de thread-safety; política de pacing limits; política de reinicio diario de TWS; definición de JobConfig; política de costura histórico+RT; frecuencia de persistencia; definición de dato consolidado; mecanismo del Scheduler; referencia a ADR-001 |
