# Architecture Decision Log

**Estado:** Activo
**Versión:** 0.1
**Naturaleza:** Registro informativo de decisiones arquitectónicas
**Autoridad:** Ninguna. Los contratos derivados viven en el Blueprint.
**Alineación:** Blueprint Técnico · System Concept Specification

---

## Propósito

Este documento registra las decisiones arquitectónicas significativas 
del sistema: qué se decidió, por qué, qué alternativas fueron 
descartadas y cuáles son las consecuencias operativas.

Los ADRs no son contratos. Son el razonamiento que produjo contratos.
Cuando una sección del Blueprint referencia un ADR, este documento 
provee el contexto completo de esa decisión.

---

## ADR-001 — Prohibición de Imputación de Datos y Frontera Feature/Signal

**Estado:** Aprobado
**Fecha:** 2026-03
**Documentos afectados:** Blueprint Técnico secciones 1.2, 1.4 · SCS secciones 1.16, 1.17

### Decisión

El sistema prohíbe en todas sus capas la imputación silenciosa de 
datos ausentes. Los NaN deben propagarse de forma transparente desde 
Data Layer hasta Strategy, que es la única capa autorizada a decidir 
el comportamiento ante datos incompletos.

Se establece formalmente la frontera epistemológica entre Feature 
(hecho matemático no falsable) y Signal (interpretación empírica 
falsable).

### Contexto

El sistema documental anterior (SAD) contenía principios de rigor 
probabilístico que no fueron trasladados a la nueva arquitectura 
durante la redefinición. Esta decisión recupera y formaliza esos 
principios dentro del nuevo marco.

### Problema

Sin esta frontera explícita, los implementadores tienden a:
- Usar `.fillna(0)` o `ffill()` en Processing para evitar errores 
  de cálculo, introduciendo precios ficticios en las features.
- Introducir heurísticas de mercado dentro del cálculo de variables, 
  colapsando la distinción entre observación e interpretación.
- Construir estrategias sobre datos que parecen limpios pero 
  contienen asunciones implícitas no auditables.

### Alternativas descartadas

**Alternativa A — Imputación permitida con flag:**
Permitir imputación pero marcar el dato como imputado mediante 
una columna auxiliar. Descartada porque introduce complejidad 
de estado en capas que deben ser puras, y porque el flag puede 
ignorarse silenciosamente en implementaciones futuras.

**Alternativa B — Responsabilidad en Data Layer:**
Que Data Layer entregue siempre DataFrames completos sin NaN. 
Descartada porque obliga a Data Layer a tomar decisiones 
estratégicas sobre qué hacer ante huecos, violando la separación 
de responsabilidades.

### Consecuencias

- Processing debe estar preparado para recibir y propagar NaN.
- La librería común de cálculo debe comportarse de forma predecible 
  ante NaN en todos sus inputs.
- Strategy debe implementar lógica explícita de manejo de 
  incertidumbre. No puede asumir inputs siempre completos.
- Los tests de la librería común deben incluir casos con NaN.

---

## ADR-002 — Agregación de RealTimeBars en DataDispatcher

**Estado:** Aprobado
**Fecha:** 2026-03
**Documentos afectados:** Blueprint Técnico (Data Layer responsibilities) · Phase 0 Implementation Spec (DataDispatcher) · ADR-001

### Decisión

La agregación de RealTimeBars (5s) hacia temporalidades superiores se implementará dentro del componente `DataDispatcher` del Data Layer.

`DataDispatcher` será responsable de:
1. Recibir las barras de 5 segundos provenientes de `ConnectionManager`.
2. Insertarlas en el `DataBuffer`.
3. Mantener el estado temporal necesario para construir barras agregadas.
4. Emitir barras consolidadas cuando se complete la ventana temporal correspondiente.

El resultado de esta agregación será tratado como dato consolidado y podrá ser servido mediante el contrato `get_snapshot`. Si el contrato `get_snapshot` solicita una temporalidad que requiere agregación, DataDispatcher provee el resultado generado.

### Contexto

La API de Interactive Brokers (IBKR) proporciona el stream de datos en tiempo real mediante el endpoint `reqRealTimeBars`, con una granularidad fija de 5 segundos. El sistema requerirá trabajar con temporalidades superiores (e.g., 1 minuto, 5 minutos), declaradas en los `JobConfig`. Se necesita un mecanismo de agregación determinista antes de exponer los datos a otras capas.

### Problema

La arquitectura exige una estricta separación de responsabilidades. El Processing Layer tiene responsabilidad exclusiva sobre transformaciones analíticas, pero no debe realizar transformaciones estructurales de los datos de mercado crudos (responsabilidad de ingestión). Si la agregación se hiciese en Processing o Strategy, violaría el Blueprint Técnico.

### Reglas de Agregación y Determinismo

Para garantizar que la agregación sea determinista y reproducible:
- **Open:** Primer open de la ventana.
- **High:** Máximo de todos los highs de la ventana.
- **Low:** Mínimo de todos los lows de la ventana.
- **Close:** Último close recibido en la ventana.
- **Volume:** Suma de volúmenes en la ventana.

Además:
- Las barras se agregan únicamente a partir de datos confirmados.
- Una barra agregada no puede modificarse una vez emitida.
- Las ventanas deben alinearse a límites temporales estándar (e.g., 10:01:00, 10:02:00).

### Alternativas descartadas

**Alternativa A — Agregación en Processing Layer:**
Rechazada porque violaría la frontera arquitectónica. Processing debe recibir datos ya consolidados y puros.

**Alternativa B — Agregación en Persistence Layer:**
Rechazada porque la persistencia es responsable de almacenar, no de transformar. Evitaría además servir datos desde memoria a través de `DataBuffer`.

**Alternativa C — Agregación en Strategy Layer:**
Rechazada porque Strategy está encargada de interpretar señales, no de formatear y estructurar datos de mercado.

### Consecuencias

- Mantiene las transformaciones estructurales confinadas al Data Layer.
- Asegura la pureza del Processing Layer (operaciones analíticas sobre datos listos).
- Strategy siempre operará sobre barras consistentes y consolidadas.
- Incrementará la complejidad del `DataDispatcher` al introducir estado temporal para las ventanas de agregación.

### Notas

Esta decisión aplica para la Fase 0. Ante futuras fuentes de datos en tiempo real, la política de agregación deberá alinearse con este ADR para garantizar la reproducibilidad del sistema completo.

---

## ADR-003

*(Reservado para próxima decisión arquitectónica significativa)*
