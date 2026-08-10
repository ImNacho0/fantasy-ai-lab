# Agents — Fantasy AI Lab

## Visión General
En la Fase 2, el simulador evoluciona de tener managers puramente pasivos a contar con agentes autónomos inteligentes. Un **Agent** actúa como la interfaz unificada del manager con el simulador de Fantasy Football, encapsulando la toma de decisiones.

## Abstracción Base
La clase `BaseAgent` en `src/fantasy_ai_lab/agents/base.py` define la firma para todos los agentes:

```python
class BaseAgent:
    def __init__(self, manager: Manager, seed: int = 123, strategy: Optional[BaseStrategy] = None):
        ...
```

Para asegurar total compatibilidad hacia atrás con la Fase 1, `BaseAgent` acepta la configuración de manager estándar y asocia dinámicamente la estrategia correspondiente de acuerdo al campo `manager.strategy_type`.

## Perfiles de Agentes Disponibles
El sistema implementa 9 perfiles con comportamientos característicos y toma de decisiones diferenciadas:

1. **ConservativeAgent**: Prioriza la reducción del riesgo de plantilla, evita comprar jugadores lesionados y mantiene altos niveles de liquidez.
2. **AggressiveAgent**: Apuesta fuertemente por estrellas de alto rendimiento (alta expectativa xP) pujando por encima del valor de mercado.
3. **TraderAgent**: Enfocado en la especulación económica. Compra activos infravalorados para venderlos durante periodos de máxima cotización (breakouts).
4. **PointsMaximizerAgent**: Maximiza el rendimiento deportivo inmediato en puntos esperados xP.
5. **LongTermAgent**: Evalúa la estabilidad deportiva de los jugadores considerando varias jornadas por delante.
6. **OpportunisticAgent**: Aprovecha rebajas extremas y gangas en el mercado de transferencias.
7. **BudgetManagerAgent**: Controla exhaustivamente la tesorería, restringiendo compras si el capital remanente es inferior a 15M.
8. **BalancedAgent**: Combina equilibradamente los factores de puntos, valor de mercado, liquidez y riesgo.
9. **RandomBaselineAgent**: Actúa como línea base pseudoaleatoria reproducible para contrastar el valor añadido de las estrategias inteligentes.
