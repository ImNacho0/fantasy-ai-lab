# Esquema de Base de Datos y Persistencia — Fantasy AI Lab

## Motor y Soporte
El sistema de persistencia utiliza **SQLAlchemy** y soporta de forma nativa:
- **PostgreSQL**: Base de datos principal para producción/Docker/Render.
- **SQLite**: Fallback local inmediato y en memoria para ejecución rápida de tests (`sqlite:///:memory:`).

## Entidades Operativas Principales

```
                   [SimulationJob] (checkpoint y progreso)
                          │
                     [Simulation]
                          │
                       [League] ◄─── (Bifurcaciones por parent_league_id)
      ┌───────────┬───────┴──────────┬─────────────┐
      ▼           ▼                  ▼             ▼
  [Manager]    [Team]             [Player]      [Matchday]
      │                              │             │
      ├───────────┼──────────────────┤             │
      ▼           ▼                  ▼             ▼
  [Roster]    [Lineup]         [Transaction]    [Market] & [Bid]
```

## Entidades de Aprendizaje y Conocimiento

```
                    [Situation] (Features de contexto)
                         │
                    [Decision]  (Acciones, confianza, reasoning)
                         │
                    [Outcome]   (Resultados de puntos y riqueza)
                         │
                     [Reward]   (Métricas de recompensa optimizadas)
```

## Migraciones con Alembic
Las migraciones del esquema de base de datos están completamente configuradas. Para aplicar los esquemas más recientes a tu base de datos configurada en `DATABASE_URL`:

```bash
alembic upgrade head
```
