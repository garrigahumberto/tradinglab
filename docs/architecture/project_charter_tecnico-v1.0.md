# 📄 Project Charter Técnico — v1.0

**Estado:** Activo 🟢
**Naturaleza:** Documento rector de propósito y límites
**Autoridad:** Vinculante para arquitectura y desarrollo

---

## 1️⃣ Propósito del Proyecto

Diseñar y desarrollar un sistema cuantitativo profesional que:

- **Potencie y formalice** el *edge* operativo ya existente.
- Permita explorar, validar y descartar nuevas hipótesis cuantitativas.
- Funcione como herramienta activa de apoyo durante la operativa real.
- Mantenga el rigor científico, reproducibilidad y auditabilidad desde su base.
- Pueda evolucionar hacia automatización parcial o total si el *edge* validado lo justifica.

> **El sistema no es puramente académico ni puramente automático.**
> Es un sistema híbrido: operativo y científico, con capacidad de evolución estructural.

## 2️⃣ Objetivo Principal (Fase Actual)

Construir una infraestructura confiable que permita:

- Capturar y estructurar datos reales desde **IBKR**.
- Escanear múltiples activos bajo parámetros definidos.
- Detectar patrones previamente identificados manualmente.
- Generar alertas tempranas accionables.
- Predefinir órdenes de entrada/salida para ejecución en IBKR.
- Evaluar estadísticamente estrategias usando datos históricos disponibles.

**Métricas de Éxito de la Fase:**
- Estabilidad operativa.
- Calidad y consistencia de los datos almacenados.
- Reproducibilidad de resultados.
- Utilidad práctica durante la operativa real.

*(El éxito no se mide exclusivamente en PnL en esta etapa, pero sí en utilidad real).*

La arquitectura construida en esta fase deberá poder soportar múltiples clases de activo (acciones, opciones y futuros) sin rediseño estructural.

## 3️⃣ Alcance Inicial (Qué Sí Entra)

- ✔️ Ingestión robusta de datos desde IBKR.
- ✔️ Almacenamiento estructurado y escalable (ej. Data-Driven MarketDB).
- ✔️ Escaneo parametrizable de activos.
- ✔️ *Features* cuantitativas puras (vectores/dataframes).
- ✔️ Generación de señales explicables.
- ✔️ Evaluación estadística práctica.
- ✔️ Soporte para operativa asistida (semi-automatización).
- ✔️ Uso de *Paper Trading* como entorno técnico de prueba.
- ✔️ Validación progresiva del *edge* en cuenta real dedicada.

## 4️⃣ Fuera de Alcance (Por Ahora)

- ❌ Trading automático en real sin supervisión.
- ❌ Optimización de latencia de alta frecuencia (HFT).
- ❌ Arquitectura sobre-distribuida (ej. microservicios puros).
- ❌ UI compleja o dashboards web interactivos asíncronos.
- ❌ Modelos de caja negra (Deep Learning) sin explicabilidad.

*(La automatización total solo se considerará si el *edge* demuestra estabilidad y robustez en la validación real).*

## 5️⃣ Principios No Negociables

1. **Prioridad Data-Driven:** Primero data confiable, luego señales, luego ejecución.
2. **Reproducibilidad:** Por encima de la conveniencia técnica.
3. **Modularidad Consciente:** Las estrategias no dictan la arquitectura de datos.
4. **Cero Magia:** Nada "mágico" que no pueda explicarse lógicamente o matemáticamente.
5. **Arquitectura Protectora:** La arquitectura protege el sistema de la improvisación futura.
6. **Pragmatismo:** El sistema debe ser útil **hoy** sin sacrificar su evolución **mañana**.
7. **Testing Realista:** *Paper Trading* se utiliza como entorno técnico para probar integraciones de red y logs, no como validación definitiva del *edge financiero*.
8. **Automatización Evolutiva:** La automatización es una consecuencia de un proceso exitoso, no un objetivo de partida.

## 6️⃣ Naturaleza del Sistema (Arquitectura Dual)

El sistema opera en dos planos complementarios que comparten infraestructura, datos purificados y disciplina técnica:

### 🔬 Plano de Investigación
- Exploración acelerada de hipótesis.
- Validación estadística.
- Descarte agresivo de señales débiles.
- Análisis de retrospectiva (Backtesting).

### ⚙️ Plano Operativo
- Escáner en tiempo real del universo definido.
- Monitor de alertas tempranas.
- Soporte estructurado a decisiones.
- Preparación controlada de órdenes (gestión del spread/liquidez).

> **Máxima:** La operatividad no invalida el rigor científico. El rigor científico no debe bloquear la utilidad táctica práctica de esta semana.

## 7️⃣ Restricciones Reales Técnicas y de Entorno

- **Fuente Limitada:** Dependencia primaria de IBKR como fuente de datos.
- **Límites de Conexión:** Strictas políticas de *pacing/throttling* de IBKR que prohiben solicitudes históricas masivas y suscribirse a excesos de *tickers* en tiempo real.
- **Hardware Independiente:** Sin infraestructura dedicada externa (debe correr en una máquina local eficiente).
- **Equipo Solitario:** Recursos de desarrollo limitados (tú y asistentes AI).
- **Vacío Histórico:** Histórico de opciones muy pobre o nulo en API (nos obliga a grabarlo en *forward* desde ya para uso futuro).
- **Validación Final:** Requiere invariablemente una cuenta real y riesgo de capital para probar el impacto real de *slippage* e *impacto de mercado*.

## 8️⃣ Riesgos Identificados a Mitigar

- Recolección de datos asimétrica o incompleta (huecos en las bases de datos locales).
- Ilusiones estadísticas (sobre-ajustes o sesgos de supervivencia y "visión del futuro/Lookahead").
- Repetición del pecado original: *Sobre-ingeniería prematura*.
- Subestimar desconexiones, mantenimientos forzosos de TWS e incongruencias en los timestamps de IBKR.
- Diseñar lógicas (ej. carga masiva en RAM) desproporcionadas respecto al hardware u objeto real de análisis. 

## 9️⃣ Criterio Duro para Avanzar de Fase o Aprobar Señal

**🚫 NO SE AVANZARÁ SI LAS IDEAS/SEÑALES:**
- No pueden explicarse en lenguaje llano antes de codificarse.
- No pueden ser reproducibles en muestras fuera de contexto (Out Of Sample).
- No aportan una utilidad o atajo real a la operativa discrecional actual.
- Requieren suposiciones escondidas que luego no se loggearán ni se auditarán.
- Fracasan contundentemente en la validación progresiva controlada.