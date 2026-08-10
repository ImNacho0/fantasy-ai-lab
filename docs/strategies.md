# Strategies — Fantasy AI Lab

## Separación de Agente y Estrategia
Para facilitar la evolución futura y permitir múltiples versiones de una misma estrategia (ej. `Aggressive v1`, `Aggressive v2`) sin duplicar código de agentes, la lógica de decisión se ha desacoplado del agente:

```
Manager ➔ BaseAgent ➔ StrategyConfig ➔ StrategyEngine (BaseStrategy)
```

## Configuración de Estrategias
Cada estrategia se rige por un perfil de pesos validable y serializable mediante **Pydantic**:

```json
{
  "risk_tolerance": 0.7,
  "points_weight": 0.8,
  "value_growth_weight": 0.4,
  "cash_weight": 0.3,
  "future_weight": 0.7,
  "market_weight": 0.8,
  "injury_risk_weight": 0.5
}
```

La lógica de validación garantiza que todos los pesos y tolerancias se mantengan acotados entre `0.0` y `1.0`.

## Creación de una Nueva Estrategia
Para crear una estrategia personalizada:
1. Hereda de `BaseStrategy` en `src/fantasy_ai_lab/strategy/base.py`.
2. Implementa `select_lineup(self, roster_players, rng)` para dictaminar la alineación ideal de 11 jugadores.
3. Implementa `make_market_decisions(self, market_players, roster_players, budget, rng)` para dictaminar las compras, ventas y ofertas del mercado.
