from fantasy_ai_lab.database.models import StrategyVersion
from fantasy_ai_lab.simulator.engine import SimulationEngine
from fantasy_ai_lab.training.evaluation import EvaluationService


def test_phase5_backtest_reports_uncertainty_and_requires_validation(db_session):
    engine = SimulationEngine(seed=1500)
    league = engine.create_league(db_session, "Training League", seed=1500)
    engine.run_league_simulation(db_session, league.id, 2)
    manager = league.managers[0]

    evaluation = EvaluationService.backtest_strategy(
        db_session, manager.strategy_type, manager.strategy_version, "test", league.id
    )
    balanced = evaluation.metrics["profiles"]["balanced"]
    assert evaluation.status == "backtested"
    assert balanced["sample_size"] > 0
    assert "confidence_95" in balanced

    EvaluationService.validate_candidate(db_session, evaluation, minimum_sample_size=1)
    assert evaluation.status == "validated"


def test_phase5_promotion_is_idempotent_and_archives_previous_version(db_session):
    current = EvaluationService.register_candidate(db_session, "Balanced", "v1.0", {"risk": 0.5})
    current.lifecycle_status = "promoted"
    current.is_active = True
    db_session.commit()
    candidate = EvaluationService.register_candidate(
        db_session, "Balanced", "v2.0", {"risk": 0.7}, parent_version="v1.0"
    )
    candidate_eval = EvaluationService.evaluate_strategy(
        db_session, "Balanced", "v2.0", "validation"
    )
    EvaluationService.validate_candidate(db_session, candidate_eval, minimum_sample_size=0)
    promoted = EvaluationService.promote_candidate(db_session, candidate_eval.id)
    assert promoted.version == "v2.0"
    assert promoted.is_active is True
    assert db_session.query(StrategyVersion).filter_by(
        strategy_name="Balanced", version="v1.0", is_active=True
    ).count() == 0


def test_phase5_unvalidated_candidate_cannot_promote(db_session):
    evaluation = EvaluationService.evaluate_strategy(db_session, "Missing", "v9", "validation")
    try:
        EvaluationService.promote_candidate(db_session, evaluation.id)
    except ValueError as exc:
        assert "validated" in str(exc)
    else:
        raise AssertionError("unvalidated evaluation was promoted")
