# 📙 System Concept Specification (SCS)

**Versión:** 1.0
**Estado:** Activo 🟢
**Naturaleza:** Documento Informativo — Marco Conceptual
**Autoridad:** Define principios conceptuales. No define implementación.
**Alineación:** Project Charter v1.0 · Blueprint Técnico v1.0

## 0️⃣ Propósito del Documento

El System Concept Specification (SCS) define los principios conceptuales que gobiernan el sistema cuantitativo.

Su función es:
- Establecer un vocabulario común.
- Definir el significado preciso de los conceptos fundamentales.
- Proveer el marco interpretativo para decisiones arquitectónicas.

Este documento:
- No define estructuras técnicas.
- No define organización de carpetas.
- No define contratos concretos.
- No contiene decisiones de implementación.

El Blueprint traduce estos principios en estructura técnica concreta.
El SCS no puede imponer estructura.
El Blueprint no puede contradecir principios conceptuales aquí definidos.

Ambos documentos son complementarios y operan en niveles distintos.

---

## 1️⃣ Principios Fundamentales

### 1.1 Sistema Híbrido
El sistema opera en dos planos simultáneos:
- **Plano de Investigación:** formulación, validación y descarte de hipótesis cuantitativas.
- **Plano Operativo:** asistencia activa a la operativa discrecional en tiempo real.

Ambos planos comparten infraestructura, pero sus garantías de aislamiento deben preservarse.
La coexistencia de investigación y operativa es una característica estructural del sistema, no una etapa transitoria.

### 1.2 Job
Un Job es la unidad lógica de trabajo del sistema.
Representa una tarea completamente definida que:
- Declara sus requerimientos de datos.
- Declara su lógica de procesamiento.
- Produce un resultado autónomo.

Un Job:
- No conoce otros Jobs.
- No comparte estado con otros Jobs.
- Puede fallar sin comprometer el sistema completo.

El aislamiento de Jobs es un principio conceptual de resiliencia y modularidad.

### 1.3 Data-First
Ninguna lógica estratégica puede construirse sobre datos cuya confiabilidad no haya sido establecida.

El orden conceptual del sistema es:
1. Datos confiables
2. Features derivadas
3. Señales
4. Soporte de ejecución

Alterar este orden introduce deuda técnica invisible y compromete la validez de cualquier resultado posterior.

### 1.4 Determinismo Pragmático
El sistema exige reproducibilidad bajo condiciones realistas.
Dado el mismo conjunto de datos consolidados como input, el sistema debe producir exactamente el mismo output.

La unidad mínima de reproducibilidad es el dato consolidado persistido.
El sistema no exige determinismo a nivel de tick si la fuente externa no lo garantiza.

### 1.5 Reproducibilidad
Un resultado es reproducible si puede reconstruirse exclusivamente a partir de datos persistidos y reglas determinísticas.

La reproducibilidad es condición necesaria para:
- Auditoría científica.
- Validación de hipótesis.
- Identificación real de edge.

Sin reproducibilidad no existe base empírica.

### 1.6 Contratos Estables
Un contrato es la interfaz pública entre dos capas.

Un contrato define:
- Inputs aceptados.
- Outputs garantizados.
- Formato y reglas de intercambio.

La implementación interna puede cambiar libremente mientras el contrato permanezca estable.
Modificar un contrato implica un cambio arquitectónico y requiere revisión formal.

### 1.7 Separación Estricta de Responsabilidades
Cada capa del sistema tiene responsabilidades claramente delimitadas.

Una capa no debe:
- Asumir responsabilidades de otra.
- Acceder a estado interno de otra.
- Crear dependencias implícitas.

La separación estricta es un principio de auditabilidad y mantenibilidad.

### 1.8 Fuente de Verdad
Para cada tipo de información el sistema reconoce una única fuente de verdad.
Una fuente de verdad es el origen autorizado y persistido desde el cual pueden reconstruirse estados pasados.

No pueden coexistir múltiples fuentes conflictivas para el mismo tipo de dato dentro del sistema.

### 1.9 Tolerancia al Error Aislada
El sistema está diseñado bajo el principio de aislamiento de fallos.

Un error en una unidad lógica:
- No debe corromper datos persistidos.
- No debe comprometer la integridad del sistema completo.
- No debe generar efectos laterales ocultos.

La tolerancia al error es un principio conceptual de resiliencia.

### 1.10 No Sobreingeniería
La sobreingeniería se define como la implementación de capacidades no requeridas por la fase activa del proyecto.
La elegancia técnica o utilidad anticipada no justifican su implementación anticipada.

Cada fase define su alcance.
Las fases futuras no se implementan por adelantado.

### 1.11 Librería Común de Cálculo
Los cálculos cuantitativos deben producir resultados consistentes independientemente del contexto donde se ejecuten.

Para ello, los cálculos compartidos deben centralizarse en módulos determinísticos y sin estado.
La consistencia matemática es requisito para la reproducibilidad del sistema.

### 1.12 Grabación Forward
Cuando la fuente externa no provee histórico suficiente, el sistema puede adoptar estrategias de acumulación progresiva de datos.

La grabación forward es un mecanismo conceptual para construir histórico desde el presente hacia el futuro.
Su valor es acumulativo y su inicio tardío implica pérdida irrecuperable de datos históricos.

### 1.13 Modos Operativos
El sistema puede operar bajo distintos modos, cada uno con garantías específicas:
- Modo histórico
- Modo de captura
- Modo operativo

La separación explícita de modos es necesaria para evitar contaminación entre investigación y operativa.

### 1.14 Edge
El edge es una ventaja estadística reproducible y explicable bajo condiciones reales de mercado.
El sistema no asume su existencia.

El edge debe:
- Ser formulado como hipótesis.
- Validarse fuera de muestra.
- Confirmarse en condiciones reales antes de su adopción sistemática.

### 1.15 Señal Explicable
Una señal es válida si:
- Puede describirse conceptualmente antes de codificarse.
- Registra los valores exactos de sus inputs.
- Puede reproducirse bajo el mismo dataset.

La explicabilidad es condición de auditabilidad.

---

## 2️⃣ Glosario del Sistema

Esta sección registra definiciones formales necesarias para evitar ambigüedad terminológica.

| Término | Definición |
|---|---|
| **Job** | Unidad lógica autónoma de trabajo. |
| **Contrato** | Interfaz pública entre capas. |
| **Snapshot** | Estado inmutable de datos consolidados en un instante. |
| **Dato consolidado** | Unidad mínima persistida y reproducible. |
| **Feature** | Variable cuantitativa pura derivada de datos. |
| **Señal** | Output de lógica estratégica con metadata de explicabilidad. |
| **Fuente de verdad** | Origen autorizado y persistido de un tipo de dato. |
| **Hueco** | Intervalo temporal sin datos persistidos. |
| **Stub** | Sustituto temporal que respeta contrato oficial. |
| **Edge** | Ventaja estadística reproducible bajo condiciones reales. |

---

## 📌 Cierre

Este documento define principios conceptuales.

- No define estructura técnica.
- No define organización física del sistema.
- No reemplaza al Blueprint.

Su modificación requiere revisión formal, ya que altera el marco interpretativo del sistema completo.
