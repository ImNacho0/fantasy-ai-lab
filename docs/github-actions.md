# GitHub Actions Runner — Fantasy AI Lab

## Introducción
Para cumplir con la restricción de **Coste 0 €**, GitHub Actions se utiliza como el principal ejecutor gratuito de simulaciones pesadas de ligas.

## Configuración del Workflow
El workflow está definido en `.github/workflows/simulate.yml` y soporta dos modos de disparo:

### 1. Ejecución Manual (workflow_dispatch)
Permite lanzar simulaciones configurando parámetros interactivos desde la pestaña Actions de GitHub:
- `leagues`: Número de ligas (por defecto 5).
- `matchdays`: Jornadas a simular (por defecto 5).
- `seed`: Semilla aleatoria (por defecto 123).
- `extreme_matchday`: Jornada en la que inyectar un escenario extremo (opcional).
- `extreme_scenario`: Nombre del escenario (`STAR_PLAYER_INJURED`, `MARKET_CRASH`).

### 2. Ejecución Programada (schedule)
Lanza una simulación de control de forma diaria a medianoche UTC de manera automática.

## Checkpoints y Reanudación
Dado que los corredores de GitHub Actions tienen un límite máximo de tiempo por ejecución (6 horas) y pueden interrumpirse de forma inesperada, el motor está programado para ser **idempotente y tolerante a fallos**:
- Al final de la simulación de cada liga, el runner guarda un checkpoint (`leagues_completed`).
- Si el job se cancela o interrumpe, el estado del SimulationJob en la base de datos queda guardado.
- En la siguiente ejecución, el sistema detecta el trabajo incompleto y continúa exactamente desde la última liga no procesada, evitando la duplicación de datos o el desperdicio de tiempo de cómputo.
