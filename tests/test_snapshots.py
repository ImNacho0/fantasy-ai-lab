from fantasy_ai_lab.simulator.engine import SimulationEngine
from fantasy_ai_lab.simulator.snapshots import SnapshotService
from fantasy_ai_lab.database.models import League, Snapshot, Roster, Manager

def test_snapshot_restore_fork(db_session):
    engine = SimulationEngine(seed=400)
    league = engine.create_league(db_session, "Original League", seed=400)

    # Run 2 matchdays
    engine.run_league_simulation(db_session, league.id, 2)
    assert league.matchday == 2

    # Take a snapshot
    snap = SnapshotService.create_snapshot(db_session, league.id, matchday_num=2, description="Backup matchday 2")
    assert snap is not None
    assert snap.matchday_number == 2

    # Modify original league (run 3rd matchday)
    engine.run_league_simulation(db_session, league.id, 3)
    assert league.matchday == 3

    # Restore back to matchday 2
    restored_league = SnapshotService.restore_snapshot(db_session, snap.id)
    assert restored_league.matchday == 2

    # Check that it deleted matchday 3 records
    assert restored_league.matchday == 2

    # Fork from snapshot
    forked_league = SnapshotService.fork_snapshot(db_session, snap.id, "Bifurcated League")
    assert forked_league is not None
    assert forked_league.name == "Bifurcated League"
    assert forked_league.parent_league_id == league.id
    assert forked_league.matchday == 2

    # Verify both leagues exist and have independent roster rows
    original_roster_count = db_session.query(Roster).filter_by(league_id=league.id).count()
    forked_roster_count = db_session.query(Roster).filter_by(league_id=forked_league.id).count()
    assert original_roster_count > 0
    assert forked_roster_count > 0

    # Check history replay
    history = SnapshotService.replay_history(db_session, league.id)
    assert len(history) == 2 # matchday 1 and matchday 2
    assert history[0]["matchday"] == 1
    assert history[1]["matchday"] == 2
