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

## ADR-002

*(Reservado para próxima decisión arquitectónica significativa)*
