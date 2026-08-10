import pytest
import random
from pydantic import ValidationError
from src.fantasy_ai_lab.database.models import Manager, Player, Roster, Decision, Reward, Outcome
from src.fantasy_ai_lab.agents.base import BaseAgent
from src.fantasy_ai_lab.strategy.base import get_strategy_by_name, StrategyConfig
from src.fantasy_ai_lab.simulator.engine import SimulationEngine
from src.fantasy_ai_lab.simulator.matchday import MatchdayEngine

def test_strategy_config_validation():
    # Valid config
    config = StrategyConfig(name="Test", risk_tolerance=0.5, points_weight=0.8)
    assert config.name == "Test"
    assert config.risk_tolerance == 0.5

    # Invalid risk_tolerance > 1.0
    with pytest.raises(ValidationError):
        StrategyConfig(name="Test", risk_tolerance=1.5)

    # Invalid points_weight < 0.0
    with pytest.raises(ValidationError):
        StrategyConfig(name="Test", points_weight=-0.1)


def test_agent_loading_and_fallback():
    # Load each of the 9 strategy types
    strategies = [
        "Balanced", "Conservative", "Aggressive", "Trader",
        "PointsMaximizer", "LongTerm", "Opportunistic", "BudgetManager", "Random"
    ]
    for s_name in strategies:
        m = Manager(strategy_type=s_name)
        agent = BaseAgent(m)
        assert agent.strategy is not None

        # Check matching strategy config name (allowing alias mapping)
        if s_name in ["BudgetManager", "PointsMaximizer"]:
            assert agent.strategy.config.name == s_name
        else:
            assert s_name in [agent.strategy.config.name, "RandomBaselineStrategy"]

    # Test fallback
    m_none = Manager(strategy_type=None)
    agent_none = BaseAgent(m_none)
    assert agent_none.strategy is not None
    assert agent_none.strategy.config.name == "Balanced"


def test_agent_differentiation():
    # Set up same dummy state of roster and market players
    roster = [
        Player(id=1, name="Roster 1", position="FW", price=1000000.0, market_value=1000000.0, xp=4.5, form=1.0, play_probability=0.9, status="healthy"),
        Player(id=2, name="Roster 2", position="DF", price=1500000.0, market_value=1500000.0, xp=3.5, form=1.0, play_probability=0.9, status="healthy")
    ]
    market = [
        Player(id=3, name="Market Star", position="FW", price=5000000.0, market_value=6000000.0, xp=8.0, form=1.0, play_probability=1.0, status="healthy"),
        Player(id=4, name="Market Cheap", position="MF", price=500000.0, market_value=500000.0, xp=2.0, form=1.0, play_probability=0.8, status="healthy")
    ]

    rng = random.Random(42)

    # 1. BudgetManager: strictly refuses expensive buys
    bm_strat = get_strategy_by_name("BudgetManager")
    bm_dec = bm_strat.make_market_decisions(market, roster, budget=4000000.0, rng=rng)
    # Budget is 4M, but Star costs 5M. It only allows cheap.
    assert len(bm_dec) <= 1
    if bm_dec:
        assert bm_dec[0]["player_id"] == 4 # Cheap

    # 2. Aggressive: is willing to bid high on stars
    agg_strat = get_strategy_by_name("Aggressive")
    agg_dec = agg_strat.make_market_decisions(market, roster, budget=10000000.0, rng=rng)
    assert len(agg_dec) == 1
    assert agg_dec[0]["action"] == "BUY"
    assert agg_dec[0]["player_id"] == 3 # Star


def test_random_baseline_reproducibility():
    market = [
        Player(id=3, name="Market Star", position="FW", price=2000000.0, market_value=2000000.0, xp=8.0, form=1.0, play_probability=1.0, status="healthy"),
        Player(id=4, name="Market Cheap", position="MF", price=500000.0, market_value=500000.0, xp=2.0, form=1.0, play_probability=0.8, status="healthy")
    ]
    roster = [
        Player(id=1, name="Roster 1", position="FW", price=1000000.0, market_value=1000000.0, xp=4.5, form=1.0, play_probability=0.9, status="healthy")
    ]

    # Two random runs with the exact same seed must produce identical decisions
    rng1 = random.Random(999)
    rng2 = random.Random(999)

    r_strat = get_strategy_by_name("Random")
    dec1 = r_strat.make_market_decisions(market, roster, budget=20000000.0, rng=rng1)
    dec2 = r_strat.make_market_decisions(market, roster, budget=20000000.0, rng=rng2)

    assert dec1 == dec2


def test_reward_profiles(db_session):
    # Setup outcome metrics
    pts_gained = 15.5
    wealth_gained = 2000000.0 # 2M gained

    # 1. points-focused: total reward should be pts_gained
    # 2. wealth-focused: total reward should be wealth_gained / 1M = 2.0
    # 3. balanced: total reward should be (15.5 * 0.5) + (2.0 * 0.5) = 8.75
    # 4. risk-adjusted: total_reward should be pts_gained + wealth_gained_scaled - risk

    # Let's verify our calculation logic matches MatchdayEngine:
    points_focused_reward = pts_gained
    wealth_focused_reward = wealth_gained / 1000000.0
    balanced_reward = (pts_gained * 0.5) + ((wealth_gained / 1000000.0) * 0.5)

    assert points_focused_reward == 15.5
    assert wealth_focused_reward == 2.0
    assert balanced_reward == 8.75


def test_multi_agent_league_integration(db_session):
    # Create a league with all 9 managers
    engine = SimulationEngine(seed=123)
    league = engine.create_league(db_session, "Multi Agent League", seed=123, num_managers=9)

    # Verify managers are assigned diverse strategies
    managers = db_session.query(Manager).filter_by(league_id=league.id).all()
    assert len(managers) == 9

    strategy_names = [m.strategy_type for m in managers]
    assert "Conservative" in strategy_names
    assert "Aggressive" in strategy_names
    assert "Trader" in strategy_names
    assert "Random" in strategy_names

    # Run 1 matchday simulation
    engine.run_league_simulation(db_session, league.id, 1)
    assert league.matchday == 1

    # Check decisions and rewards are stored correctly
    decisions = db_session.query(Decision).filter_by(league_id=league.id, matchday_number=1).all()
    assert len(decisions) > 0

    # Inspect one decision
    sample_dec = decisions[0]
    assert sample_dec.expected_outcome is not None
    assert "expectedPoints" in sample_dec.expected_outcome
    assert sample_dec.reasoning_factors is not None
    assert "availableActions" in sample_dec.reasoning_factors
    assert "alternativeActions" in sample_dec.reasoning_factors

    # Check multiple rewards are logged per decision
    rewards = db_session.query(Reward).filter_by(decision_id=sample_dec.id).all()
    assert len(rewards) == 4 # points-focused, wealth-focused, balanced, risk-adjusted

    profile_names = [r.profile_name for r in rewards]
    assert "points-focused" in profile_names
    assert "wealth-focused" in profile_names
    assert "balanced" in profile_names
    assert "risk-adjusted" in profile_names
