# Simulación y Reproducibilidad — Fantasy AI Lab

## Introducción
El motor de simulación de `Fantasy AI Lab` es determinista y almacena checkpoints granulares, permitiendo pausar, reanudar y recrear cualquier simulación si se proporciona la misma combinación de semilla (seed), configuración y conjunto de datos.

## Estructura de Semillas (Seeds)
Para asegurar que las simulaciones sean reproducibles y paralelizables sin interferencias de auto-incrementos de la base de datos o de ejecuciones asíncronas, las semillas se estructuran jerárquicamente:

- **Master Seed**: Semilla principal del `SimulationJob`.
- **League Seed**: Semilla única derivada con SHA-256 de `master_seed` y `league_index`; no depende del orden de ejecución ni de IDs de base de datos.
- **Agent/Matchday Seed**: Semilla de agente calculada de forma independiente usando `league_seed + manager_index + matchday_number`.

## Cómo Ejecutar una Simulación desde CLI
La simulación se puede lanzar fácilmente desde el terminal:

```bash
# Simular 10 ligas, con 5 jornadas cada una, semilla 123
PYTHONPATH=.:src python -m fantasy_ai_lab.simulate --leagues 10 --matchdays 5 --seed 123
```

### Inyección de Escenarios Extremos
Es posible probar la resiliencia de las estrategias inyectando escenarios críticos en jornadas concretas:

```bash
# Inyectar una lesión grave del jugador estrella en la jornada 3
PYTHONPATH=.:src python -m fantasy_ai_lab.simulate --leagues 5 --matchdays 5 --seed 456 --extreme-matchday 3 --extreme-scenario STAR_PLAYER_INJURED
```
