from fantasy_ai_lab.simulator.engine import SimulationEngine
from fantasy_ai_lab.database.models import Player, Manager

def test_deterministic_reproducibility(db_session):
    # Run simulation 1
    engine1 = SimulationEngine(seed=999)
    league1 = engine1.create_league(db_session, "League 1", seed=999)
    engine1.run_league_simulation(db_session, league1.id, 2)

    # Store points for managers
    points_run1 = {m.name: m.points for m in db_session.query(Manager).filter_by(league_id=league1.id).all()}

    # Run simulation 2 (completely new league but with the exact same seed)
    engine2 = SimulationEngine(seed=999)
    league2 = engine2.create_league(db_session, "League 2", seed=999)
    engine2.run_league_simulation(db_session, league2.id, 2)

    points_run2 = {m.name: m.points for m in db_session.query(Manager).filter_by(league_id=league2.id).all()}

    # Ensure points match exactly
    for name, pts1 in points_run1.items():
        # Match by corresponding name mapping (replacing League 1 with League 2 strings or strategy types)
        # Since name has Manager Strategy i, we can compare strategies directly
        m_strat = name.split()[1] # e.g. "Balanced"
        pts2 = next(m.points for m in db_session.query(Manager).filter_by(league_id=league2.id).all() if m.name.split()[1] == m_strat)
        assert pts1 == pts2, f"Discrepancy for manager strategy {m_strat}: {pts1} vs {pts2}"
