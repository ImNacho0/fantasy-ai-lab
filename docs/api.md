# API Endpoints — Fantasy AI Lab

La API de FastAPI actúa como la interfaz de consulta y simulación interactiva. No bloquea peticiones de simulación largas; en su lugar, utiliza hilos de segundo plano de FastAPI para ejecutar trabajos asíncronos en Render Free.

## Endpoints Principales

### 1. Estado y Salud
- **`GET /health`**: Devuelve el estado de disponibilidad y hora UTC actual.

### 2. Gestión de Trabajos de Simulación (Simulation Jobs)
- **`POST /api/v1/simulations`**: Crea un nuevo trabajo de simulación persistente.
- **`GET /api/v1/simulations`**: Lista todos los trabajos de simulación creados.
- **`GET /api/v1/simulations/{id}`**: Obtiene el detalle, progreso (checkpoint) y ligas de un trabajo.
- **`POST /api/v1/simulations/{id}/run`**: Ejecuta de forma asíncrona en segundo plano un trabajo de simulación pendiente o pausado.

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
- **`GET /api/v1/knowledge/similar`**: Busca decisiones históricas basadas en un rango de precios y muestra su impacto en puntos y riqueza.
- **`GET /api/v1/strategy/current`**: Devuelve los parámetros de la estrategia activa.

### 6. Memoria, contrafactuales y evaluación
- **`GET /api/v1/knowledge/similar`**: Devuelve casos históricos con tamaño de muestra y resultados.
- **`POST /api/v1/decisions/{id}/counterfactuals`** y **`GET /api/v1/decisions/{id}/counterfactuals`**: registra y consulta alternativas estimadas sin ejecutar acciones reales.
- **`POST /api/v1/evaluate`**: calcula métricas de una estrategia y versión sobre un dataset.
- **`POST /api/v1/tournaments`**: compara versiones y devuelve ranking persistido.
