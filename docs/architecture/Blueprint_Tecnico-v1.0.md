# 📘 Blueprint Técnico — v1.0

**Estado:** Activo 🟢
**Naturaleza:** Contractual (Arquitectura Macro) + Evolutivo por Fase
**Autoridad:** Subordinado al Development Governance Framework
**Alineación:** Project Charter v1.0

---

## ⚠️ Estado y Fase Activa

- **Fase Activa Actual:** Fase 0 — Fundamento de Datos
- **Alcance Permitido:** Ingestión robusta de IBKR, persistencia estructurada (MarketDB), manejo de reconexiones y huecos, logging técnico.
- **Alcance Prohibido:** Implementación de estrategias (Fase 1), motores de evaluación (Fase 1), escáner en tiempo real (Fase 2), automatización operativa (Fase 3).
- **Criterio Formal de Cierre:** El sistema reconstruye sesiones pasadas exclusivamente con datos propios persistidos de IBKR, sin fugas ni dependencias de módulos de fases superiores.

---

## 0️⃣ Naturaleza del Documento

Este Blueprint define la arquitectura técnica del sistema cuantitativo y su modelo de evolución estructural.

Se establece explícitamente que:

- La **arquitectura macro** es contractual e inmutable entre fases.
- La **definición formal de fases** es contractual.
- Las **reglas de expansión** son contractuales.
- El **diseño técnico detallado** de cada fase es evolutivo y se desarrolla únicamente cuando dicha fase está activa.
- Los **contratos entre capas** se definen ahora para todo el sistema y no pueden romperse en fases posteriores.
- La **implementación interna** de cada capa puede crecer y evolucionar por fase sin afectar los contratos.

> **Ninguna expansión técnica podrá contradecir la arquitectura macro, violar las reglas de evolución aquí definidas, ni alterar contratos entre capas sin activar Revisión Formal de Gobernanza.**

Este documento no describe la explotación del *edge*. Describe la infraestructura que permite su desarrollo, validación y operación.

---

## 1️⃣ Arquitectura General del Sistema (Macro — Contractual)

### 1.1 Capas del Sistema

El sistema se compone de cuatro capas con responsabilidades no solapadas, coordinadas por el Session Controller:

```
┌─────────────────────────────────────────────┐
│            Session Controller               │
│  crea · configura · destruye Jobs           │
│  registra necesidades de datos en Data Layer│
└──────────────┬──────────────────────────────┘
               │
               │  gestiona N Jobs simultáneos
               │
    ┌──────────▼────────────────────────────┐
    │                Job N                  │
    │                                       │
    │  ┌─────────────────────────────────┐  │
    │  │         Data Layer              │  │ ← compartida entre Jobs
    │  │  (servicio centralizado)        │  │
    │  └──────────────┬──────────────────┘  │
    │                 │ contrato estable     │
    │  ┌──────────────▼──────────────────┐  │
    │  │   Processing  (instancia)       │  │ ← privada al Job
    │  └──────────────┬──────────────────┘  │
    │                 │ contrato estable     │
    │  ┌──────────────▼──────────────────┐  │
    │  │   Strategy    (instancia)       │  │ ← privada al Job · opcional
    │  └──────────────┬──────────────────┘  │
    │                 │ contrato estable     │
    │  ┌──────────────▼──────────────────┐  │
    │  │ Execution Support (instancia)   │  │ ← privada al Job · opcional
    │  └─────────────────────────────────┘  │
    └───────────────────────────────────────┘
```

### 1.1.1 Modelo Conceptual de Concurrencia

El sistema permite la ejecución simultánea de múltiples Jobs activos.

Cada Job opera como una unidad independiente bajo la coordinación del Session Controller.  
La arquitectura exige que el acceso concurrente a Data Layer sea seguro y consistente.

Requisitos arquitectónicos:

- Data Layer debe ser **thread-safe** o equivalente bajo el modelo de concurrencia elegido.
- Las operaciones de lectura de snapshots deben ser **consistentes e independientes** entre Jobs.
- La persistencia en MarketDB debe garantizar **integridad de datos bajo acceso concurrente**.

El modelo específico de concurrencia (threads, async, multiprocessing u otro) se define durante la implementación técnica de la fase activa, pero el sistema debe garantizar desde arquitectura:

- independencia entre Jobs
- consistencia de datos
- ausencia de condiciones de carrera en Data Layer

---

### 1.2 Responsabilidades y Contratos por Capa

#### Session Controller

### 1.2.0 Contrato de Configuración de Job

Todo Job del sistema debe declararse mediante una estructura formal de configuración denominada **JobConfig**.  
El Session Controller únicamente puede crear o modificar Jobs utilizando una configuración válida.

El contrato conceptual mínimo de un Job incluye:

- **Activos monitoreados**
- **Tipos de dato requeridos** (velas, bid/ask, RT bars, etc.)
- **Temporalidad base de datos**
- **Ventana histórica requerida**
- **Configuración de features**
- **Estrategia asociada (opcional)**
- **Módulo de Execution Support (opcional)**
- **Política de persistencia**

El Session Controller valida esta configuración antes de instanciar el Job.  
Un Job no puede existir sin una configuración explícita.

Este contrato garantiza que:

- La creación de Jobs sea **determinista y reproducible**.
- Las necesidades de datos puedan registrarse correctamente en Data Layer.
- Las dependencias entre capas permanezcan explícitas.

El formato exacto de `JobConfig` se define en la implementación técnica de la fase activa, pero su existencia como contrato estructural es obligatoria desde el nivel arquitectónico.

**Responsabilidades:**
- Crear, configurar, modificar y destruir Jobs.
- Registrar y actualizar las necesidades de datos de cada Job en Data Layer.
- Gestionar el ciclo de vida de Jobs activos.
- Es la **única** entidad autorizada a modificar el universo de activos monitoreados en tiempo de ejecución.

**Restricciones:**
- No procesa datos.
- No ejecuta estrategias.
- No se conecta a IBKR.
- No conoce lógica de mercado.

**Flujo de gestión de suscripciones:**

Cuando el Session Controller crea un Job, registra sus necesidades de datos en Data Layer. Data Layer determina si existe una suscripción compatible o debe crear una nueva. Cuando el Job es destruido, Data Layer actualiza el registro y cancela suscripciones sin consumidores activos. Este flujo es unidireccional: Session Controller → Data Layer. Ninguna otra capa participa en la gestión de suscripciones.

**Control del ciclo de ejecución**

El Session Controller controla el ciclo de ejecución de todos los Jobs activos mediante un scheduler interno.

Los Jobs no ejecutan su ciclo de forma autónoma ni controlan su propio ritmo de ejecución.  
El Session Controller activa periódicamente cada Job según la temporalidad declarada en su configuración.

Este mecanismo garantiza que:

- Los Jobs no puedan consultar snapshots con una frecuencia superior a la permitida.
- El acceso concurrente a Data Layer permanezca controlado.
- El sistema mantenga comportamiento determinista entre sesiones.

---

#### Data Layer

Data Layer es un **servicio centralizado** compartido por todos los Jobs. Es el único componente del sistema que interactúa con IBKR.

**Componentes internos:**

| Componente | Responsabilidad |
|---|---|
| **Connection Manager** | Única conexión con IBKR. Reconexiones automáticas. Gestión de límites de pacing. Absorción interna de reinicios diarios forzosos del broker. |
| **Subscription Registry** | Registro de suscripciones activas. Evita duplicados entre Jobs. Libera suscripción cuando ningún Job activo la requiere. |
| **Data Dispatcher** | Recibe datos del broker. Actualiza buffers internos (pull pasivo hacia capas superiores). No empuja ni inyecta datos hacia los Jobs. |
| **Persistence Manager** | Persiste datos según política del Job. Gestiona y almacena metadatos de contratos. |

**Contrato expuesto hacia Processing:**
```python
get_snapshot(uid: tuple, tipo_dato: str, temporalidad_base: str) -> pd.DataFrame
```

El DataFrame entregado siempre incluye etiquetado explícito de granularidad y tipo de dato. Processing no infiere estos atributos; los lee del contrato.

**Restricciones del contrato:**
- Devuelve una **copia independiente e inmutable** de los datos, no una referencia en memoria.
- Devuelve únicamente la **ventana histórica** declarada por la configuración del Job.
- Data Layer no decide la profundidad histórica; sirve la porción que el Job declare necesitar.
- `get_snapshot` no fuerza actualización de buffers en IBKR.
- `get_snapshot` no altera suscripciones existentes.
- Processing no puede invocar `get_snapshot` con frecuencia superior al ciclo temporal declarado por el Job.
- El snapshot devuelto corresponde siempre al último estado consolidado disponible.

**Reglas operativas:**
- Data es el **único** componente del sistema que interactúa con IBKR.
- Persiste metadatos obligatorios de cada contrato: `conId`, `exchange`, `multiplier`, `trading_hours`, `currency`, `tipo_contrato`, `expiry` (para opciones y futuros).
- Una serie de tiempo sin su definición contractual asociada no se considera válida.
- El determinismo se exige a nivel de **vela consolidada**, no tick-level.
- En Fase 0: detecta y registra huecos en log estructurado. La corrección es manual y posterior. No existe sanación automática.
- Las interrupciones de IBKR son **absorbidas internamente**. Las capas superiores no deben conocer ni sufrir estas interrupciones. Ante caída de conexión, Data Layer orquesta pausa controlada y reanuda al recuperar conexión.
- Data Layer puede implementar amortiguación temporal interna ante cancelaciones y reactivaciones sucesivas de una misma suscripción dentro de una ventana breve, exclusivamente para evitar violaciones de pacing. Esta lógica es interna y no se expone a capas superiores.
- **Estrategia de degradación obligatoria:** Ante alertas de pacing limit o throttling, el sistema reduce frecuencia de polling mediante backoff exponencial o pausa peticiones por rotación. El sistema nunca insiste ante rechazos reiterados del broker.

**Modelo de transporte (Fase 0 — Pull Determinista):**
- Data Layer mantiene buffers internos actualizados bajo su propio ritmo de consolidación.
- Las capas superiores consultan snapshots ya consolidados mediante contrato estable.
- Data Layer no empuja datos hacia Processing ni orquesta el ciclo de ejecución de los Jobs.
- El ritmo de actualización pertenece exclusivamente a Data Layer.
- El ritmo de consulta pertenece exclusivamente al ciclo interno del Job.
- No existe sincronización implícita por eventos.

**Gestión de memoria:**
- Cada Job define por contrato su **ventana histórica máxima** requerida.
- Data Layer no mantiene histórico ilimitado en RAM. Retiene únicamente la ventana máxima declarada por el Job activo de mayor requerimiento.
- Los datos fuera de esa ventana son descargados de memoria tras ser persistidos en disco.

---

#### Processing Layer

**Responsabilidades:**
- Recibir DataFrames estandarizados desde Data Layer vía contrato estable.
- Ejecutar resampling, alineación temporal y agrupación de DataFrames. Es la **única** capa autorizada para estas operaciones.
- Calcular features según configuración del Job usando la librería común de cálculo.
- Mantener estado propio de la instancia (ventanas históricas, acumuladores).

**Restricciones:**
- No accede a IBKR.
- No modifica datos persistidos.
- No comparte estado con instancias de Processing de otros Jobs.
- No realiza operaciones de red ni accede a disco directamente. Todo dato externo entra exclusivamente vía Data Layer.

**Contrato expuesto hacia Strategy:**
```python
get_features(config_features: dict) -> pd.DataFrame
```
El output es un DataFrame alineado temporalmente, sin dependencias de estado ocultas. Las funciones de cálculo deben ser **puras**.

**Regla crítica:** Strategy nunca ejecuta resampling, agrupación ni transformación temporal. Si Strategy requiere datos en una temporalidad distinta a la que Processing entrega, esa necesidad se declara en la configuración del Job y se resuelve en Processing.

---

#### Strategy Layer *(opcional por Job)*

**Responsabilidades:**
- Consumir el DataFrame enriquecido entregado por Processing.
- Aplicar las reglas de la estrategia configurada.
- Generar señales con sus parámetros asociados.

**Restricciones:**
- No accede a datos crudos.
- No accede a IBKR.
- No ejecuta transformaciones de datos.

**Contrato expuesto hacia Execution Support:**
```python
evaluate(features: pd.DataFrame) -> dict
# Retorna: {'action': str, 'price': float, 'explicability_metadata': dict}
```

**Restricción de señal explicable:**
- Toda señal emitida debe incluir en `explicability_metadata` los valores exactos de las features y el timestamp que generaron la decisión.
- Si una señal no es matemáticamente reproducible en `HISTORICAL_MODE` con los mismos inputs, se considera inválida por diseño.

---

#### Execution Support Layer *(opcional por Job)*

**Responsabilidades:**
- Consumir señales generadas por Strategy.
- Generar alertas, registros de decisión y preparación estructurada de órdenes.

**Restricciones:**
- No genera señales propias.
- No accede a IBKR directamente en Fase 0.
- No modifica datos ni features.
- No instruye a Data Layer ni al Session Controller.

---

### 1.3 Flujo de Datos

El flujo de datos dentro de cada Job es **estrictamente descendente**:

```
Data Layer → Processing → Strategy → Execution Support
```

### 1.3.1 Ciclo de Ejecución de un Job

Cada Job ejecuta un ciclo determinista activado por el Session Controller.

El ciclo de ejecución sigue siempre el mismo orden:

1. Solicitud de snapshot a Data Layer mediante el contrato `get_snapshot`.
2. Procesamiento de datos en Processing Layer (alineación, resampling, cálculo de features).
3. Evaluación de la estrategia configurada (si existe).
4. Generación de señal estructurada.
5. Transferencia de la señal a Execution Support (si existe).

Representación simplificada:

```
Job Tick
↓
Data Snapshot
↓
Processing (features)
↓
Strategy (señal)
↓
Execution Support (alerta / registro)
```

Este ciclo se ejecuta únicamente cuando el Session Controller lo activa.  
Un Job no puede ejecutar múltiples ciclos dentro de la misma unidad temporal declarada en su configuración.

Existe una distinción formal entre dos dominios:

| Dominio | Dirección | Responsable |
|---|---|---|
| **Flujo de datos** | Descendente estricto | Capas funcionales |
| **Gestión de suscripciones** | Session Controller → Data Layer | Session Controller exclusivamente |

**Está prohibido:**
- Que cualquier capa acceda a una capa superior en el flujo de datos.
- Que Strategy o Execution accedan directamente a Data Layer.
- Que Processing solicite o modifique suscripciones.
- Que Execution Support instruya a Data Layer o al Session Controller.
- Que existan dependencias circulares entre capas.
- Que la lógica de una capa esté distribuida en otra.

---

### 1.4 Librería Común de Cálculo

Módulo independiente de todas las capas que contiene:

- Funciones de indicadores técnicos.
- Funciones de transformación y normalización.
- Funciones de resampling.
- Funciones de métricas estadísticas.

**Reglas:**
- Ninguna capa reimplementa funciones ya definidas en esta librería.
- Las instancias de Processing importan y usan esta librería.
- La librería no tiene estado propio. Es funcional y pura.
- Toda función requiere prueba determinista en el repositorio antes de considerarse aprobada.
- La modificación del comportamiento de una función ya aprobada constituye cambio de contrato y está prohibida sin incremento de versión mayor.

---

### 1.5 Canonical Data Model y Esquema Físico

Todo dato consolidado debe adherirse a este formato antes de ser persistido o transmitido:

- **Timestamp canonical:** Formato `UTC` estricto. Tipo: `datetime64[ns, UTC]`.
- **Identificador único (UID):** Tupla obligatoria `(symbol, conId, exchange, secType)`. El `conId` de IBKR no es opcional.
- **Estructura mínima de vela:** Esquema obligatorio `[timestamp, open, high, low, close, volume, barCount]`.

**Organización física en disco (MarketDB):**

Persistencia en formato Parquet bajo esquema de partición jerárquico:
```
/marketdb/{asset_type}/{symbol}/{year}/{month}/{symbol}_{year}{month}.parquet
```

*(Nota de Diseño Futuro: La persistencia física y estructurada de Señales y Features, por ejemplo SignalsDB, será delimitada formalmente durante la especificación técnica de la Fase 1).*

---

### 1.6 Modos Operativos

El sistema define tres modos explícitos e aislados:

| Modo | Descripción | Permitido en Fase 0 |
|---|---|---|
| `HISTORICAL_MODE` | Backtesting usando data en reposo. Corte absoluto a la API. | Uso de stubs locales en Fase 0. Explotación completa de MarketDB reservada a Fase 1. |
| `FORWARD_RECORDING_MODE` | Captura pasiva de datos hacia MarketDB. Sin ejecución estratégica. | ✔️ |
| `LIVE_SCAN_MODE` | Operativa real con señales activas. | ❌ |

**Restricciones adicionales:**
- El código de exploración (`/research`) está físicamente aislado del núcleo de ejecución (`/production`). Están prohibidos los imports desde producción hacia research.
- El escaneo concurrente en Fase 0 queda restringido a un máximo de **5 activos simultáneos** para prevenir violaciones de pacing en IBKR.

---

### 1.7 Fault Handling Policy

- **Reconexión:** Backoff exponencial obligatorio tras desconexión del broker o TWS.
- **Logging mínimo:** Todo fallo de red, pacing detectado o hueco temporal entra en `critical_error.log`.
- **Integridad pre-persistencia:** Prohibido persistir DataFrames corruptos. Los huecos se registran como huecos explícitos; no se interpolan en la capa de datos.

---

### 1.8 Restricciones Operativas de Construcción Temprana

Durante Fase 0 y Fase 1:

- **Límite de tipos de activo:** La lógica analítica y operativa se restringe a contratos tipo `STOCK`.  
  Los tipos `OPTION` y `FUTURE` pueden ser ingeridos y persistidos en MarketDB desde Fase 0 con el objetivo de iniciar la **grabación forward de histórico**, dado que IBKR no provee histórico profundo de estos instrumentos.  
  Sin embargo, estos datos no tendrán lógica analítica asociada hasta fases posteriores.
- **Límite de complejidad estratégica:** Un Job ejecuta una única estrategia activa con un único set de parámetros fijos. Quedan prohibidos los optimizadores de parámetros y meta-estrategias.
- **Regla anti-abstracciones preventivas:** Está prohibida la inclusión de código, interfaces o abstracciones diseñadas para complejidades futuras no requeridas por la fase activa.

---

### 1.9 Política de Versionado

| Tipo de cambio | Versión |
|---|---|
| Cambio en contratos entre capas, principios o estructura macro | Mayor (v1→v2) |
| Expansión por nueva fase activa | Menor (v1.0→v1.1) |
| Corrección técnica sin impacto estructural | Revisión (v1.0→v1.0.1) |

> Cambios de versión mayor activan **Revisión Formal de Gobernanza**.

---

## 2️⃣ Definición Formal de Fases (Contractual)

### Fase 0 — Fundamento de Datos

**Objetivo:** Garantizar ingestión confiable, persistencia estructurada y estabilidad de conexión. Establecer la base sobre la que todas las fases siguientes operarán sin necesidad de rediseño.

**Incluye:**
- Conexión estable a IBKR con manejo de reconexiones y reinicios diarios.
- Subscription Registry funcional con soporte multi-activo y multi-tipo de dato.
- Ingestión de: velas históricas, RT bars, bid/ask, cadenas de opciones (IV, Greeks), futuros.
- Grabación *forward* estructurada desde el primer día en formato Parquet particionado.
- Persistencia estructurada por activo, tipo de dato y temporalidad.
- Persistencia obligatoria de metadatos de contratos.
- Identificación y logging de huecos. Corrección manual y posterior.
- Session Controller con gestión básica de Jobs.
- Processing instanciable restringido a alineamiento temporal y resampling técnico validado.
- Librería común de cálculo con funciones base estructurales, sin componentes estratégicos.
- Logs técnicos estructurados.

**Excluye:**
- Features estratégicas o cálculo de indicadores de trading (reservado a Fase 1).
- Strategy Layer.
- Execution Support Layer.
- Automatización de cualquier tipo.
- Procesamiento o almacenamiento tick-by-tick.

**Criterio de Cierre:**
> El sistema puede reconstruir cualquier sesión pasada utilizando exclusivamente datos propios persistidos, con múltiples Jobs activos simultáneamente sobre distintos activos y tipos de dato.

---

### Fase 1 — Motor de Análisis

**Objetivo:** Convertir datos confiables en información cuantitativa validable. Permitir evaluación estadística rigurosa de hipótesis.

**Incluye:**
- Strategy Layer completa.
- Backtesting determinista.
- Validación Out-Of-Sample.
- Métricas estadísticas robustas (win rate, expectancy, drawdown, sensibilidad paramétrica).
- Walk-forward básico.
- Expansión de librería de cálculo con indicadores estratégicos.

**Excluye:**
- Ejecución real o simulada automática.
- Automatización operativa.

**Criterio de Cierre:**
> Hipótesis pueden formularse, evaluarse y descartarse sin modificar arquitectura. Al menos una hipótesis supera validación OOS con métricas documentadas.

---

### Fase 2 — Integración Operativa

**Objetivo:** Convertir el sistema en herramienta activa de apoyo a la operativa real.

**Incluye:**
- Execution Support Layer completa.
- Scanner en tiempo real sobre universo configurable.
- Sistema de alertas accionables.
- Preparación estructurada de órdenes con gestión de spread y liquidez.
- Registro de slippage real.
- Comparación esperado vs ejecutado.

**Excluye:**
- Ejecución automática sin supervisión humana.

**Criterio de Cierre:**
> El sistema mejora demostrablemente la operativa discrecional actual. Las métricas reales son comparables con las del backtesting.

---

### Fase 3 — Automatización Progresiva *(condicional)*

**Condición de activación:** Edge validado en cuenta real dedicada con métricas consistentes y control de riesgo sólido documentado.

**Incluye:**
- Ejecución parcial automática bajo supervisión.
- Gestión automática de órdenes con parámetros predefinidos.
- Supervisión humana obligatoria.

---

## 3️⃣ Reglas de Expansión del Blueprint (Contractual)

1. Ninguna fase futura se detalla antes de cerrar formalmente la fase activa.
2. Ningún diseño incremental puede romper contratos entre capas ya establecidos.
3. Ninguna funcionalidad perteneciente a una fase futura puede implementarse en una fase activa.
4. Toda expansión debe ser auditada por el Núcleo Arquitectónico antes de integrarse.
5. Cambios en contratos entre capas activan **Revisión Formal de Gobernanza** con independencia de la magnitud percibida.
6. La librería común de cálculo puede expandirse en cualquier fase sin activar revisión formal, siempre que no modifique el comportamiento de funciones ya aprobadas.
7. Si una necesidad de implementación no puede satisfacerse sin modificar un contrato existente, se detiene el desarrollo y se evalúa el rediseño antes de continuar.

**Cláusula de Desarrollo Paralelo:**

Durante el desarrollo de Fase 0 está permitido construir y probar instancias de Processing y Strategy utilizando datos estáticos locales como sustituto temporal de Data Layer, con la condición estricta de que dichos datos respeten exactamente el contrato de salida de Data Layer: mismo esquema de DataFrame, mismos metadatos de granularidad, mismo formato de columnas. Un stub que no respete ese contrato no es válido y su uso queda prohibido. Esta cláusula no autoriza avanzar al criterio de cierre de Fase 1 antes de cerrar Fase 0.

> **El Blueprint es evolutivo por fase, no por entusiasmo técnico.**

---

## 4️⃣ Diseño Técnico de Fases

El diseño técnico detallado de cada fase se mantiene en
documentos independientes de implementación.

Esta decisión evita que el Blueprint crezca excesivamente
y permite versionar cada fase de forma independiente.

### Fases definidas

Phase 0 — Data Layer
→ docs/implementation/phase0_implementation_spec.md

Phase 1 — Historical Engine
→ (pendiente)

Phase 2 — Strategy Runtime
→ (pendiente)

---

*Fin del documento — Versión Dorada (v1.0)*