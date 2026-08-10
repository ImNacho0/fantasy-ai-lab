from src.fantasy_ai_lab.simulator.engine import SimulationEngine
from src.fantasy_ai_lab.database.models import League, Manager, Team, Player, Roster

def test_league_creation(db_session):
    engine = SimulationEngine(seed=42)
    league = engine.create_league(db_session, "Test League Core", seed=42, num_managers=4)

    assert league is not None
    assert league.name == "Test League Core"
    assert league.matchday == 0
    assert league.status == "active"

    # Check managers created
    managers = db_session.query(Manager).filter_by(league_id=league.id).all()
    assert len(managers) == 4

    # Check that each manager got 15 roster players initially
    for m in managers:
        rosters = db_session.query(Roster).filter_by(manager_id=m.id).all()
        assert len(rosters) == 15
        # Budget should have been deducted from initial 40M
        assert m.budget < 40000000.0

    # Check teams
    teams = db_session.query(Team).filter_by(league_id=league.id).all()
    assert len(teams) == 20

    # Check players
    players = db_session.query(Player).filter_by(league_id=league.id).all()
    assert len(players) == 420
