from src.fantasy_ai_lab.simulator.engine import SimulationEngine
from src.fantasy_ai_lab.simulator.matchday import MatchdayEngine
from src.fantasy_ai_lab.database.models import Matchday, Event, Player, Decision

def test_simulate_matchday(db_session):
    engine = SimulationEngine(seed=100)
    league = engine.create_league(db_session, "Test Sim League", seed=100)

    # Run matchday 1
    engine.run_league_simulation(db_session, league.id, 1)
    assert league.matchday == 1

    # Assert Matchday record is completed
    md_record = db_session.query(Matchday).filter_by(league_id=league.id, matchday_number=1).first()
    assert md_record is not None
    assert md_record.status == "completed"

    # Assert Decisions were recorded
    decs = db_session.query(Decision).filter_by(league_id=league.id, matchday_number=1).all()
    assert len(decs) > 0

def test_extreme_scenario(db_session):
    engine = SimulationEngine(seed=200)
    league = engine.create_league(db_session, "Test Scenario League", seed=200)

    # Run matchday 1 with STAR_PLAYER_INJURED scenario
    engine.run_league_simulation(
        db_session,
        league.id,
        1,
        extreme_scenarios={1: "STAR_PLAYER_INJURED"}
    )

    # Verify extreme event was registered
    events = db_session.query(Event).filter_by(
        league_id=league.id,
        event_type="STAR_PLAYER_INJURED"
    ).all()
    assert len(events) == 1
    assert events[0].is_extreme is True
    assert events[0].severity == "extreme"

    # Verify that the target player's status was changed to injured_grave
    player = db_session.query(Player).filter_by(id=events[0].target_player_id).first()
    assert player.status == "injured_grave"
    assert player.play_probability == 0.0
