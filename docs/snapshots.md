# Sistema de Snapshots, Restore, Fork & Replay — Fantasy AI Lab

## Introducción
Una de las funcionalidades core de la Fase 1 es la capacidad de congelar el estado de una liga y recrearlo o bifurcarlo para realizar contrafactuales: *"¿Qué habría ocurrido si el manager X hubiese comprado al jugador Y en la jornada 12?"*

## Snapshot (Congelar Estado)
Cuando se ejecuta `SnapshotService.create_snapshot`, el sistema recupera todos los registros de la liga en cascada (Managers, Rosters, Lineups, Players, Transactions, etc.) y genera un objeto JSON autónomo de persistencia que se guarda en la tabla `snapshots`.

## Restore (Revertir Estado)
Si una simulación de prueba toma un camino no deseado, `SnapshotService.restore_snapshot` realiza lo siguiente:
1. Elimina todos los registros dinámicos actuales asociados a esa liga para evitar duplicados o inconsistencias.
2. Reconstruye cada entidad en la base de datos a partir del JSON serializado, restaurando la liga exactamente a la jornada guardada.

## Fork (Bifurcar Simulación)
`SnapshotService.fork_snapshot` clona el snapshot en una **nueva liga independiente** (con una nueva ID de base de datos) y asocia `parent_league_id` a la liga de origen.
Para lograr esto sin violar las restricciones de clave primaria/foránea:
1. Genera un mapeo dinámico de IDs de Managers (`old_manager_id` -> `new_manager_id`).
2. Genera un mapeo dinámico de IDs de Jugadores (`old_player_id` -> `new_player_id`).
3. Inserta todos los registros clonados referenciando los nuevos IDs mapeados.
4. Incrementa levemente la semilla (`seed + 999`) de la nueva liga para inducir comportamientos e itinerarios de mercado alternativos y enriquecer los contrafactuales.

## Replay (Historial de la Liga)
`SnapshotService.replay_history` recopila y resume de forma cronológica jornada a jornada todos los eventos inyectados, decisiones de los agentes y transacciones realizadas en el mercado de fichajes para auditar el rendimiento.
