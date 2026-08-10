from fantasy_ai_lab.database.models import Event, Player
from fantasy_ai_lab.simulator.engine import SimulationEngine
from fantasy_ai_lab.simulator.events import EventEngine
from fantasy_ai_lab.simulator.snapshots import SnapshotService


def _event_signature(db_session, event):
    player = db_session.query(Player).filter_by(id=event.target_player_id).first()
    return (
        event.event_type,
        player.name if player else None,
        event.duration,
        event.probability,
        event.uncertainty,
        event.source,
        event.is_extreme,
    )


def test_phase3_catalog_and_deterministic_random_events(db_session):
    catalog = EventEngine.catalog()
    assert catalog["PLAYER_INJURED_GRAVE"]["duration"] == [2, 5]
    assert catalog["STAR_PLAYER_INJURED"]["is_extreme"] is True
    assert 0.0 <= catalog["TEAM_FORM_COLLAPSE"]["uncertainty"] <= 1.0

    first_engine = SimulationEngine(seed=1200)
    first_league = first_engine.create_league(db_session, "First", seed=1200)
    event_engine = EventEngine(seed=1200, probabilities={"PLAYER_INJURED_GRAVE": 1.0})
    first_events = event_engine.generate_random_events(db_session, first_league.id, 1)

    second_engine = SimulationEngine(seed=1200)
    second_league = second_engine.create_league(db_session, "Second", seed=1200)
    second_events = EventEngine(
        seed=1200,
        probabilities={"PLAYER_INJURED_GRAVE": 1.0},
    ).generate_random_events(db_session, second_league.id, 1)

    first_signatures = sorted(_event_signature(db_session, event) for event in first_events)
    second_signatures = sorted(_event_signature(db_session, event) for event in second_events)
    assert first_signatures == second_signatures


def test_phase3_star_injury_recovers_and_records_metadata(db_session):
    engine = SimulationEngine(seed=1201)
    league = engine.create_league(db_session, "Recovery League", seed=1201)
    event_engine = EventEngine(seed=1201)

    events = event_engine.trigger_scheduled_scenario(
        db_session, league.id, 1, "STAR_PLAYER_INJURED"
    )
    injury = events[0]
    star = db_session.query(Player).filter_by(id=injury.target_player_id).first()

    assert injury.probability == 1.0
    assert injury.uncertainty == EventEngine.CATALOG["STAR_PLAYER_INJURED"].uncertainty
    assert injury.recovery["status"] == "pending"
    assert star.status == "injured_grave"
    assert star.play_probability == 0.0

    for matchday in range(2, injury.duration + 2):
        event_engine.trigger_scheduled_scenario(
            db_session, league.id, matchday, "MANAGER_OVERBID"
        )

    assert star.status == "healthy"
    assert star.status_duration == 0
    recovery = db_session.query(Event).filter_by(
        league_id=league.id,
        target_player_id=star.id,
        event_type="PLAYER_RECOVERED",
    ).first()
    assert recovery is not None
    assert recovery.source == "recovery"
    assert injury.recovery["status"] == "completed"


def test_phase3_event_metadata_survives_snapshot_restore(db_session):
    engine = SimulationEngine(seed=1202)
    league = engine.create_league(db_session, "Snapshot Events", seed=1202)
    event_engine = EventEngine(seed=1202)
    event = event_engine.trigger_scheduled_scenario(
        db_session, league.id, 1, "MARKET_CRASH"
    )[0]
    original = {
        "type": event.event_type,
        "duration": event.duration,
        "impact": event.impact,
        "probability": event.probability,
        "uncertainty": event.uncertainty,
        "consequences": event.consequences,
        "source": event.source,
        "extreme": event.is_extreme,
    }

    snapshot = SnapshotService.create_snapshot(db_session, league.id, 0)
    SnapshotService.restore_snapshot(db_session, snapshot.id)
    restored = db_session.query(Event).filter_by(
        league_id=league.id, event_type="MARKET_CRASH"
    ).first()

    assert restored is not None
    assert {
        "type": restored.event_type,
        "duration": restored.duration,
        "impact": restored.impact,
        "probability": restored.probability,
        "uncertainty": restored.uncertainty,
        "consequences": restored.consequences,
        "source": restored.source,
        "extreme": restored.is_extreme,
    } == original
