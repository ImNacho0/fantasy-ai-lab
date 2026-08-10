# Reward System — Fantasy AI Lab

## Separación de Outcome y Reward
Para permitir un aprendizaje flexible, el sistema diferencia claramente entre:
- **Outcome (Resultado)**: Qué ocurrió físicamente (ej. puntos conseguidos, variación del saldo de caja).
- **Reward (Recompensa)**: La valoración subjetiva que la estrategia hace de ese resultado.

## Perfiles de Recompensa (Reward Profiles)
Por cada decisión evaluada, el sistema calcula y persiste de forma independiente 4 perfiles de recompensa en la tabla `rewards`:

### 1. `points-focused`
Enfocado exclusivamente en la acumulación de puntos Fantasy deportivos:
$$\text{Reward} = \text{points\_gained}$$

### 2. `wealth-focused`
Enfocado exclusivamente en el incremento del valor presupuestario del club:
$$\text{Reward} = \frac{\text{wealth\_gained}}{1,000,000}$$

### 3. `balanced`
Equilibra de forma equitativa los objetivos de rendimiento deportivo y financiero:
$$\text{Reward} = (\text{points\_gained} \times 0.5) + \left(\frac{\text{wealth\_gained}}{1,000,000} \times 0.5\right)$$

### 4. `risk-adjusted`
Penaliza las decisiones de alta incertidumbre o de riesgo excesivo:
$$\text{Reward} = \text{points\_gained} + \frac{\text{wealth\_gained}}{1,000,000} - \text{risk\_penalty}$$
