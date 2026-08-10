# Decisions — Fantasy AI Lab

## Contexto de Decisión
En la Fase 2, el sistema registra no solo la acción final tomada por el agente, sino también el estado en el que se encontraba y las alternativas que consideró, permitiendo un análisis contrafactual completo en fases posteriores.

## Información Registrada por Decisión
Cada registro de la tabla `decisions` guarda:

- **Chosen Action**: La acción definitiva (`action_type` como `BUY`, `SELL`, `LINEUP`, `HOLD`).
- **Confidence**: Un valor entre `0.0` y `1.0` que denota el nivel de certeza de la estrategia.
- **Expected Outcome**: Estimaciones previas sobre el impacto de la decisión:
  - `expectedPoints`: Puntos Fantasy estimados.
  - `expectedValueGrowth`: Crecimiento de valor esperado.
  - `expectedRisk`: Nivel de riesgo asumido.
- **Available Actions**: Conjunto completo de opciones que el agente tenía permitidas en el mercado y la plantilla en ese instante.
- **Alternative Actions**: Las opciones que fueron descartadas en favor de la seleccionada.

## Flujo del Proceso
```
1. Capturar Estado ➔ 2. Generar Acciones Candidatas ➔ 3. Evaluar Alternativas ➔ 4. Registrar Decisión
```
