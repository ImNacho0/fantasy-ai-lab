# Fases 2–7 — estado funcional

La rama `feature/phase-2-agents-strategies` mantiene el motor independiente de FastAPI y añade capacidades incrementales sin ejecutar acciones reales.

## Fase 2: agentes y estrategias

- `BaseAgent` delega en estrategias intercambiables.
- Hay nueve perfiles deterministas: Conservative, Aggressive, Trader, PointsMaximizer, LongTerm, Opportunistic, BudgetManager, Balanced y Random.
- `StrategyConfig` valida pesos entre 0 y 1 y admite nombres snake_case y camelCase para configuraciones externas.
- Las decisiones persisten estado, acciones disponibles, alternativas, confianza, expectativas, factores y versión.
- Cada decisión genera cuatro perfiles de recompensa independientes.

## Fase 3: eventos

`EventEngine` soporta lesiones leves/graves, sanciones, pérdida de titularidad, bajadas/subidas de forma, breakout y escenarios reproducibles como `STAR_PLAYER_INJURED`, `MARKET_CRASH`, `MARKET_BOOM`, `TEAM_FORM_COLLAPSE`, `KEY_PLAYER_LOSES_STARTING_ROLE` y `MANAGER_OVERBID`.

El catálogo declarativo expone para cada tipo la probabilidad, rango de duración, impacto, incertidumbre, severidad y si es extremo. Los eventos guardan además su origen (`random`, `scheduled` o `recovery`), consecuencias y estado de recuperación. El ciclo de vida restaura el estado previo al expirar la duración y crea un evento de recuperación auditable. Las semillas usan identidades estables de jugador y no dependen de IDs autoincrementales.

La API expone `GET /api/v1/events/catalog` y `GET /api/v1/leagues/{id}/events`, con filtros por jornada, tipo y eventos extremos. Los metadatos completos se conservan al restaurar o bifurcar snapshots.

## Fase 4: memoria, similitud y contrafactuales

`KnowledgeService` persiste casos de situación–decisión de forma idempotente. Convierte características numéricas y categóricas a vectores deterministas, normaliza cada dimensión durante la búsqueda para que el presupuesto no domine la distancia y permite filtrar por dataset, estrategia, versión y distancia máxima. Las recomendaciones agregan todos los casos candidatos por acción y devuelven tamaño de muestra, número de outcomes observados, recompensa media, dispersión, distancia más cercana y confianza media registrada; no presentan una estadística sin su evidencia.

`CounterfactualService` usa el `Outcome` observado como baseline cuando existe, mantiene explícitos los casos que solo tienen expectativas y puede estimar alternativas exclusivamente desde casos históricos similares. Los resultados son idempotentes por decisión/acción/jugador y guardan `source`, `sample_size`, `confidence` y evidencia. No se ejecutan operaciones reales.

Endpoints adicionales:

- `POST /api/v1/knowledge/similar`: busca con un payload completo de features y filtros.
- `POST /api/v1/decisions/{id}/counterfactuals/from-memory`: compara alternativas derivadas de memoria histórica.

## Fase 5: evaluación y torneos

`EvaluationService` calcula métricas por estrategia/versión/dataset y exige tamaño de muestra para validar candidatos. `TournamentService` ordena versiones por recompensa media con desempate por muestra. No existe promoción automática a producción.

## Fase 6: API

La API conserva los endpoints de simulación, snapshots y recomendación y añade:

- `POST/GET /api/v1/decisions/{id}/counterfactuals`
- `POST /api/v1/evaluate`
- `POST /api/v1/tournaments`

El modo de recomendación es solo lectura/simulación.

## Fase 7 — workers acotados y dashboard operativo

`SimulationWorker` mantiene checkpoints por liga, acepta lotes pequeños y permite cancelar un job sin perder la siguiente unidad reanudable. `ContinuousTrainingWorker` ejecuta un solo ciclo de simulación/evaluación por invocación; no crea un proceso infinito y queda preparado para ser llamado por GitHub Actions u otro scheduler.

El dashboard `/dashboard` de Render es una sala de control ligera: crea trabajos, lanza lotes de una liga, cancela trabajos, consulta métricas y actualiza el progreso por polling en `/api/v1/dashboard/overview`. Todas las acciones son de simulación; no hay ejecución contra fantasy-manager. El control de jobs sigue siendo persistente en PostgreSQL mediante `DATABASE_URL`.

: workers y CI

`SimulationWorker.run_batch` limita el número de ligas por invocación y deja un checkpoint persistido con la siguiente unidad de trabajo. Esto permite matrix jobs de GitHub Actions más adelante sin un proceso infinito.

Validación local equivalente a CI:

```bash
PYTHONPATH=.:src pytest -q
PYTHONPATH=.:src DATABASE_URL=sqlite:///fantasy_ai.db alembic upgrade head
PYTHONPATH=.:src python -m fantasy_ai_lab.simulate --leagues 2 --matchdays 2 --seed 123
```

El workflow usa runners estándar, ejecuta las migraciones y la simulación con `DATABASE_URL: ${{ secrets.DATABASE_URL }}`, y recibe `job_id` desde Render mediante `workflow_dispatch`. Las migraciones se serializan en un job separado para evitar carreras de esquema; no se utiliza SQLite en Actions. SQLite queda reservado para tests locales aislados. Nunca se almacenan secretos en el repositorio.
