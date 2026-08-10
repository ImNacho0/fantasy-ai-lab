from fantasy_ai_lab.database.models import Counterfactual, Decision, KnowledgeCase, Manager, Situation
from fantasy_ai_lab.knowledge.memory import KnowledgeService, feature_vector
from fantasy_ai_lab.simulator.counterfactuals import CounterfactualService
from fantasy_ai_lab.simulator.engine import SimulationEngine


def test_phase4_memory_is_idempotent_and_aggregates_evidence(db_session):
    engine = SimulationEngine(seed=1400)
    league = engine.create_league(db_session, "Memory League", seed=1400)
    engine.run_league_simulation(db_session, league.id, 1)

    original_count = db_session.query(KnowledgeCase).count()
    decision = db_session.query(Decision).order_by(Decision.id).first()
    situation = db_session.query(Situation).filter_by(id=decision.situation_id).first()
    KnowledgeService.record_case(db_session, situation, decision)
    KnowledgeService.record_case(db_session, situation, decision)
    assert db_session.query(KnowledgeCase).count() == original_count

    vector = feature_vector({
        "budget": situation.state_features["budget"],
        "roster_count": situation.state_features["roster_count"],
        "matchday": situation.state_features["matchday"],
        "mode": "simulation",
    })
    assert "mode=simulation" in vector

    recommendation = KnowledgeService.recommend(
        db_session,
        {**situation.state_features, "mode": "simulation"},
        limit=3,
    )
    assert recommendation["sample_size"] >= 1
    assert recommendation["outcome_sample_size"] >= 1
    assert recommendation["ranking"]
    assert all("outcome_sample_size" in row for row in recommendation["ranking"])


def test_phase4_counterfactual_uses_observed_outcome_and_is_idempotent(db_session):
    engine = SimulationEngine(seed=1401)
    league = engine.create_league(db_session, "Counterfactual League", seed=1401)
    engine.run_league_simulation(db_session, league.id, 1)
    decision = db_session.query(Decision).order_by(Decision.id).first()

    CounterfactualService.evaluate(db_session, decision, [{
        "action": "HOLD",
        "expectedPoints": 99.0,
        "expectedWealth": 100.0,
    }])
    CounterfactualService.evaluate(db_session, decision, [{
        "action": "HOLD",
        "expectedPoints": 99.0,
        "expectedWealth": 100.0,
    }])
    db_session.commit()

    comparison = CounterfactualService.compare(db_session, decision.id)
    assert comparison["chosen_outcome"]["source"] == "observed_outcome"
    assert len(comparison["alternatives"]) == 1
    assert comparison["alternatives"][0]["source"] == "explicit_estimate"
    assert db_session.query(Counterfactual).filter_by(decision_id=decision.id).count() == 1


def test_phase4_memory_counterfactuals_report_missing_evidence(db_session):
    engine = SimulationEngine(seed=1402)
    league = engine.create_league(db_session, "Evidence League", seed=1402)
    engine.run_league_simulation(db_session, league.id, 1)
    decision = db_session.query(Decision).order_by(Decision.id).first()
    situation = db_session.query(Situation).filter_by(id=decision.situation_id).first()

    CounterfactualService.evaluate_from_memory(
        db_session,
        decision,
        situation.state_features,
        ["UNSEEN_ACTION"],
    )
    db_session.commit()
    comparison = CounterfactualService.compare(db_session, decision.id)
    alternative = comparison["alternatives"][0]
    assert alternative["source"] == "historical_memory"
    assert alternative["sample_size"] == 0
    assert alternative["confidence"] == 0.0
    assert alternative["result"]["reason"] == "no_similar_cases"
