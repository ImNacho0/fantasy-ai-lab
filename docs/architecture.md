# Arquitectura Conceptual — Fantasy AI Lab

## Visión General
`Fantasy AI Lab` está concebido como un entorno autónomo e independiente de experimentación, simulación y refinamiento de estrategias para Fantasy Football. Este sistema está desacoplado de cualquier infraestructura física de pago, garantizando un funcionamiento estable de coste 0 €.

## Estructura Modular
El sistema está dividido en varios módulos con responsabilidades claras:

```
                     FANTASY AI LAB (FastAPI / CLI)
                                   │
       ┌───────────────────────────┼───────────────────────────┐
       ▼                           ▼                           ▼
  Simulator                      Agents                    Knowledge
  - SimulationEngine             - BaseAgent               - Situation
  - MatchdayEngine               - Conservative, etc.      - Decision
  - ScoringEngine                                          - Outcome & Reward
  - MarketEngine
```

### 1. Motor de Simulación (Simulator)
- **SimulationEngine**: Coordina la instanciación de ligas y la progresión secuencial de jornadas de forma persistente y determinista.
- **MatchdayEngine**: Dirige el flujo de cada jornada individual: generación de eventos, selección de alineaciones de los agentes, procesamiento de decisiones de mercado, cálculo probabilístico de puntuaciones, liquidación de pujas y guardado de snapshots.
- **ScoringEngine**: Calcula los puntos de cada jugador en función de su xP, estado físico, rendimiento reciente y minutos estimados con una fluctuación estocástica.
- **MarketEngine**: Proporciona el espacio de puja, resolviendo ofertas de forma determinista para evitar conflictos y actualizando dinámicamente los precios según el rendimiento de los jugadores.
- **EventEngine**: Inyecta eventos rutinarios (lesiones leves, tarjetas) y situaciones extremas (lesiones graves de estrellas, desplomes del mercado) de forma determinista.

### 2. Agentes e Interfases Estratégicas (Agents)
- **BaseAgent**: Encapsula el comportamiento y la lógica de toma de decisiones del manager para seleccionar alineaciones y formular ofertas o ventas.
- Permite la futura integración fluida de perfiles (Conservative, Aggressive, Trader, etc.).

### 3. Almacenamiento de Conocimiento (Knowledge Store)
- Guarda sistemáticamente el contexto (`Situation`), la acción tomada (`Decision`), el resultado deportivo/económico (`Outcome`) y la recompensa ponderada (`Reward`), sirviendo como base de entrenamiento y búsqueda de similitud para modelos de machine learning.
