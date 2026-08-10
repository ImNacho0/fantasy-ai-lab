from fantasy_ai_lab.database.models import Decision, Event, KnowledgeCase, Manager
from fantasy_ai_lab.knowledge.memory import KnowledgeService
from fantasy_ai_lab.simulator.counterfactuals import CounterfactualService
from fantasy_ai_lab.simulator.engine import SimulationEngine
from fantasy_ai_lab.simulator.events import EventEngine
from fantasy_ai_lab.simulator.jobs import JobService
from fantasy_ai_lab.training.evaluation import EvaluationService
from fantasy_ai_lab.training.tournaments import TournamentService
from fantasy_ai_lab.workers.runner import SimulationWorker


def test_memory_counterfactual_and_evaluation_pipeline(db_session):
    engine = SimulationEngine(seed=901)
    league = engine.create_league(db_session, "Advanced League", seed=901)
    engine.run_league_simulation(db_session, league.id, 1)

    assert db_session.query(KnowledgeCase).count() > 0
    decision = db_session.query(Decision).order_by(Decision.id).first()
    result = KnowledgeService.recommend(db_session, {"budget": 1.0, "roster_count": 15}, limit=5)
    assert result["sample_size"] > 0
    assert all("sample_size" in row for row in result["ranking"])

    CounterfactualService.evaluate(db_session, decision, [
        {"action": "HOLD", "expectedPoints": 12.0},
        {"action": "SELL", "expectedPoints": 2.0},
    ])
    comparison = CounterfactualService.compare(db_session, decision.id)
    assert comparison["chosen_action"] == decision.action_type
    assert len(comparison["alternatives"]) == 2

    manager = db_session.query(Manager).filter_by(league_id=league.id).first()
    evaluation = EvaluationService.evaluate_strategy(
        db_session, manager.strategy_type, manager.strategy_version, "training"
    )
    assert evaluation.sample_size > 0
    assert evaluation.metrics["profiles"]

    tournament = TournamentService.run(db_session, "Smoke tournament", [
        {"name": manager.strategy_type, "version": manager.strategy_version},
    ])
    assert tournament.status == "completed"
    assert tournament.rankings[0]["rank"] == 1


def test_advanced_scenario_and_bounded_worker(db_session):
    engine = SimulationEngine(seed=902)
    league = engine.create_league(db_session, "Scenario League", seed=902)
    events = EventEngine(seed=902).trigger_scheduled_scenario(
        db_session, league.id, 1, "MARKET_BOOM"
    )
    assert events[0].event_type == "MARKET_BOOM"
    assert events[0].is_extreme is True

    job = JobService.create_job(db_session, seed=903, leagues_total=2, matchdays=1)
    partial = SimulationWorker.run_batch(db_session, job.id, max_leagues=1)
    assert partial.status == "partial"
    assert partial.leagues_completed == 1
    assert partial.checkpoint["next_league_index"] == 1

    completed = SimulationWorker.run_batch(db_session, job.id, max_leagues=1)
    assert completed.status == "completed"
    assert completed.leagues_completed == 2
