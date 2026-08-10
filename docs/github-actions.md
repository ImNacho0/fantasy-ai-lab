# GitHub Actions + Neon — Fantasy AI Lab

GitHub Actions es el ejecutor de las simulaciones pesadas. Render/FastAPI solo crea jobs, solicita el workflow y consulta el estado persistido en Neon.

```text
Dashboard → POST /api/v1/simulations → Render/FastAPI
                                      └→ workflow_dispatch(job_id)
                                         → GitHub Actions + DATABASE_URL
                                            → Neon SimulationJob/results
                                      ← GET /api/v1/simulations/{job_id}
```

## Configuración

En Render configura como variables privadas:

- `DATABASE_URL`: la misma conexión Neon usada por Actions.
- `GITHUB_TOKEN`: token de mínimo alcance que pueda ejecutar workflows (`Actions: write`; para un repositorio público, un token con `public_repo` si se usa un PAT clásico).
- `GITHUB_REPOSITORY` (opcional): por defecto `ImNacho0/fantasy-ai-lab`.
- `GITHUB_WORKFLOW` (opcional): por defecto `simulate.yml`.
- `GITHUB_REF` (opcional): por defecto `main`.
- `ENV=production`: hace que una configuración incompleta falle explícitamente.

No se guardan tokens en la base de datos, respuestas HTTP, logs ni el repositorio.

En GitHub Actions, `DATABASE_URL` se inyecta exclusivamente como:

```yaml
DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

No hay ninguna URL de SQLite en el workflow. Neon es la base de datos del proceso de migración y de la simulación.

## Dispatch desde la API

`POST /api/v1/simulations` crea primero un `SimulationJob` en estado `pending` y, cuando `GITHUB_TOKEN` está configurado, solicita el workflow existente mediante `workflow_dispatch`. Los inputs enviados son:

- `job_id`
- `leagues`
- `matchdays`
- `seed`
- `extreme_matchday`
- `extreme_scenario`

La respuesta incluye `dispatch.accepted`. Una segunda solicitud no vuelve a lanzar el mismo job porque la reclamación se protege con bloqueo de fila en PostgreSQL y una marca persistente. `POST /api/v1/simulations/{id}/run` es una acción explícita de reintento.

Si GitHub rechaza el dispatch, el job se marca `failed` y se devuelve HTTP 502. En desarrollo sin `GITHUB_TOKEN`, el job permanece `pending` con `dispatch.status=not_configured` para que la CLI local siga funcionando; en Render se debe usar `ENV=production` para detectar ese error inmediatamente.

## Estados y progreso

- `pending`: creado y esperando el workflow.
- `running`: `JobService` lo establece al comenzar en Actions.
- `completed`: todas las ligas terminan y el checkpoint está persistido.
- `failed`: GitHub rechaza el dispatch o la ejecución registra una excepción.

`GET /api/v1/simulations/{job_id}` devuelve `leagues_completed`, `leagues_total`, `current_matchday_idx`, `checkpoint`, `error_message`, `started_at` y `completed_at`. El porcentaje del dashboard solo se calcula con las ligas realmente completadas; no se inventa progreso de jornadas.

## Workflow manual y programado

El mismo `.github/workflows/simulate.yml` soporta:

1. **Actions → Run workflow**: permite introducir `job_id` y conserva los inputs históricos.
2. **Schedule**: ejecuta la ruta standalone de la CLI, que crea su propio job en Neon cuando no existe `job_id`.

Las migraciones se ejecutan en un job separado con `concurrency`, para que dos ejecuciones simultáneas no compitan por el esquema. Las simulaciones posteriores pueden ejecutarse en paralelo y usan el mismo Neon.

## CLI y reanudación

La CLI mantiene su uso local:

```bash
PYTHONPATH=.:src DATABASE_URL=postgresql://... python -m fantasy_ai_lab.simulate --leagues 10 --matchdays 5 --seed 123
```

Actions usa el job creado por la API:

```bash
python -m fantasy_ai_lab.simulate --job-id 42
```

El segundo modo nunca crea un job duplicado: lee el job 42 desde Neon y continúa desde su checkpoint.
