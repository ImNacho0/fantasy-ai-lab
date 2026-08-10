# API Endpoints — Fantasy AI Lab

La API de FastAPI actúa como la interfaz de consulta y simulación interactiva. Las simulaciones pesadas no se ejecutan en Render: la API crea el `SimulationJob` en Neon y dispara el workflow existente de GitHub Actions mediante `workflow_dispatch`.

## Endpoints Principales

### 1. Estado y Salud
- **`GET /health`**: Devuelve el estado de disponibilidad y hora UTC actual.

### 2. Gestión de Trabajos de Simulación (Simulation Jobs)
- **`POST /api/v1/simulations/{id}/run-batch`**: Mantiene el endpoint de control del dashboard y solicita explícitamente/reintenta el workflow de GitHub Actions; no consume CPU de Render para simular.
- **`POST /api/v1/simulations/{id}/cancel`**: Solicita cancelación segura y conserva la próxima unidad reanudable.
- **`GET /api/v1/dashboard/overview`**: Devuelve métricas y trabajos recientes para polling del dashboard.

- **`POST /api/v1/simulations`**: Crea un trabajo `pending` en Neon y, si `GITHUB_TOKEN` está configurado, solicita `simulate.yml` con `job_id`, `leagues`, `matchdays`, `seed`, `extreme_matchday` y `extreme_scenario`.
- **`GET /api/v1/simulations`**: Lista todos los trabajos de simulación creados.
- **`GET /api/v1/simulations/{id}`**: Obtiene el detalle, progreso (checkpoint) y ligas de un trabajo.
- **`POST /api/v1/simulations/{id}/run`**: Acción explícita para solicitar o reintentar el workflow de un job; los reintentos no son automáticos.

### 3. Eventos y operaciones de liga
- **`GET /api/v1/events/catalog`**: Devuelve el catálogo declarativo de eventos con probabilidades, duración, impacto, incertidumbre y severidad.
- **`GET /api/v1/leagues/{id}/events`**: Consulta eventos persistidos de una liga; admite filtros `matchday`, `event_type`, `extreme_only` y `limit`.

### 4. Operaciones de Liga y Snapshots
- **`GET /api/v1/leagues/{id}`**: Detalle de clasificación, managers y plantillas de una liga.
- **`GET /api/v1/leagues/{id}/snapshots`**: Lista todos los snapshots guardados para esa liga.
- **`POST /api/v1/leagues/{id}/snapshots`**: Crea manualmente un snapshot JSON del estado de la liga en una jornada concreta.
- **`POST /api/v1/snapshots/{id}/restore`**: Sobrescribe el estado activo de la liga con el guardado en el snapshot.
- **`POST /api/v1/snapshots/{id}/fork`**: Crea una nueva bifurcación (`League` independiente) a partir de un snapshot con un nuevo nombre.

### 5. Integración con `fantasy-manager` (Recomendación de Estrategia)
- **`POST /api/v1/decision`**: Recibe el estado real o simulado de una liga, busca situaciones similares en la base de datos de simulación y devuelve una recomendación explicada con nivel de confianza.
- **`GET /api/v1/knowledge/similar`**: Busca casos históricos cercanos a un precio y agrega evidencia por acción.
- **`POST /api/v1/knowledge/similar`**: Busca situaciones usando un objeto completo de features; admite filtros por acción, estrategia, versión, dataset y distancia máxima.
- **`GET /api/v1/strategy/current`**: Devuelve los parámetros de la estrategia activa.

### 6. Memoria, contrafactuales y evaluación
- **`GET /api/v1/knowledge/similar`**: Devuelve casos históricos con tamaño de muestra y resultados.
- **`POST /api/v1/decisions/{id}/counterfactuals`** y **`GET /api/v1/decisions/{id}/counterfactuals`**: registra y consulta alternativas estimadas sin ejecutar acciones reales; conserva baseline, fuente y tamaño de muestra.
- **`POST /api/v1/decisions/{id}/counterfactuals/from-memory`**: deriva alternativas únicamente de outcomes históricos similares.
- **`POST /api/v1/evaluate`**: calcula métricas de una estrategia y versión sobre un dataset.
- **`POST /api/v1/tournaments`**: compara versiones y devuelve ranking persistido.

### 7. Continuous training
- **`POST /api/v1/training/cycle`**: Ejecuta un único ciclo acotado de simulación/evaluación. No inicia procesos infinitos y puede volver a invocarse desde GitHub Actions.
