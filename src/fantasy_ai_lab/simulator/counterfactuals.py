"""Counterfactual analysis for decisions.

Counterfactuals are estimates only. They never invoke an external execution
adapter and never mutate a real Fantasy league.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from fantasy_ai_lab.database.models import Counterfactual, Decision, Outcome


class CounterfactualService:
    @staticmethod
    def _baseline(db: Session, decision: Decision) -> Dict[str, Any]:
        outcome = db.query(Outcome).filter_by(decision_id=decision.id).order_by(Outcome.id).first()
        if outcome is not None:
            return {
                "points": float(outcome.points_gained or 0.0),
                "wealth": float(outcome.wealth_gained or 0.0),
                "source": "observed_outcome",
                "sample_size": 1,
            }
        expected = decision.expected_outcome or {}
        return {
            "points": float(expected.get("expectedPoints", 0.0) or 0.0),
            "wealth": float(expected.get("expectedWealth", expected.get("expectedValueGrowth", 0.0)) or 0.0),
            "source": "decision_expected_outcome",
            "sample_size": 0,
        }

    @staticmethod
    def _upsert(
        db: Session,
        decision: Decision,
        action: str,
        player_id: Optional[int],
        points: float,
        wealth: float,
        baseline: Dict[str, Any],
        source: str,
        sample_size: int,
        confidence: float,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Counterfactual:
        result = db.query(Counterfactual).filter_by(
            decision_id=decision.id,
            action_type=action,
            player_id=player_id,
        ).first()
        if result is None:
            result = Counterfactual(
                decision_id=decision.id,
                action_type=action,
                player_id=player_id,
            )
            db.add(result)
        result.result_data = {
            "source": source,
            "baseline_action": decision.action_type,
            "baseline_source": baseline["source"],
            "expected_points": points,
            "expected_wealth": wealth,
            "sample_size": sample_size,
            "confidence": confidence,
            "evidence": evidence or {},
            "reason": (evidence or {}).get("reason"),
        }
        result.points_delta = round(points - baseline["points"], 6)
        result.wealth_delta = round(wealth - baseline["wealth"], 6)
        result.sample_size = sample_size
        result.confidence = round(confidence, 6)
        result.source = source
        db.flush()
        return result

    @staticmethod
    def evaluate(
        db: Session,
        decision: Decision,
        alternatives: Iterable[Dict[str, Any]],
    ) -> List[Counterfactual]:
        """Persist explicit alternative estimates without executing anything.

        Explicit values remain supported for simulation callers. Every result
        records its source and baseline so a client can distinguish an
        observed outcome, a decision expectation, or a supplied estimate.
        """
        baseline = CounterfactualService._baseline(db, decision)
        results: List[Counterfactual] = []
        expected = decision.expected_outcome or {}
        default_points = float(expected.get("expectedPoints", 0.0) or 0.0)
        default_wealth = float(expected.get("expectedWealth", expected.get("expectedValueGrowth", 0.0)) or 0.0)
        for alternative in alternatives:
            has_points = "expectedPoints" in alternative
            has_wealth = "expectedWealth" in alternative or "expectedValueGrowth" in alternative
            points = float(alternative.get("expectedPoints", default_points) or 0.0)
            wealth = float(alternative.get("expectedWealth", alternative.get("expectedValueGrowth", default_wealth)) or 0.0)
            source = "explicit_estimate" if has_points or has_wealth else "decision_expected_outcome"
            results.append(CounterfactualService._upsert(
                db,
                decision,
                str(alternative.get("action", "HOLD")),
                alternative.get("playerId"),
                points,
                wealth,
                baseline,
                source,
                int(alternative.get("sampleSize", 0) or 0),
                float(alternative.get("confidence", 0.0) or 0.0),
                {"input": alternative},
            ))
        return results

    @staticmethod
    def evaluate_from_memory(
        db: Session,
        decision: Decision,
        features: Dict[str, Any],
        actions: Iterable[str],
        limit: int = 100,
    ) -> List[Counterfactual]:
        """Estimate alternatives only from persisted similar historical cases."""
        from fantasy_ai_lab.knowledge.memory import KnowledgeService

        baseline = CounterfactualService._baseline(db, decision)
        results: List[Counterfactual] = []
        for action in actions:
            recommendation = KnowledgeService.recommend(
                db, features, limit=limit, action_type=action
            )
            row = recommendation["ranking"][0] if recommendation["ranking"] else None
            if row is None:
                points = 0.0
                wealth = 0.0
                sample_size = 0
                confidence = 0.0
                evidence = {"sample_size": 0, "reason": "no_similar_cases"}
            else:
                points = float(row["average_points"])
                wealth = float(row["average_wealth"])
                sample_size = int(row["outcome_sample_size"])
                confidence = float(row["decision_confidence"])
                evidence = {
                    "sample_size": row["sample_size"],
                    "outcome_sample_size": row["outcome_sample_size"],
                    "average_reward": row["average_reward"],
                    "nearest_distance": row["nearest_distance"],
                }
            results.append(CounterfactualService._upsert(
                db,
                decision,
                str(action),
                None,
                points,
                wealth,
                baseline,
                "historical_memory",
                sample_size,
                confidence,
                evidence,
            ))
        return results

    @staticmethod
    def compare(db: Session, decision_id: int) -> Dict[str, Any]:
        decision = db.query(Decision).filter_by(id=decision_id).first()
        if not decision:
            raise ValueError(f"Decision {decision_id} not found")
        alternatives = db.query(Counterfactual).filter_by(decision_id=decision_id).order_by(
            Counterfactual.points_delta.desc(), Counterfactual.id
        ).all()
        baseline = CounterfactualService._baseline(db, decision)
        return {
            "decision_id": decision_id,
            "chosen_action": decision.action_type,
            "chosen_outcome": baseline,
            "alternatives": [
                {
                    "id": item.id,
                    "action": item.action_type,
                    "player_id": item.player_id,
                    "points_delta": item.points_delta,
                    "wealth_delta": item.wealth_delta,
                    "sample_size": item.sample_size,
                    "confidence": item.confidence,
                    "source": item.source,
                    "result": item.result_data,
                }
                for item in alternatives
            ],
        }
