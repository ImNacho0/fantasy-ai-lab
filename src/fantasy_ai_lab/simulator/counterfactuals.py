"""Counterfactual analysis for decisions.

Counterfactuals are simulations/estimates only. They never invoke an external
execution adapter and never mutate a real Fantasy league.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from fantasy_ai_lab.database.models import Counterfactual, Decision, Player


class CounterfactualService:
    @staticmethod
    def evaluate(
        db: Session,
        decision: Decision,
        alternatives: Iterable[Dict[str, Any]],
    ) -> List[Counterfactual]:
        """Persist deterministic alternative estimates for a decision.

        An alternative may provide ``expectedPoints``/``expectedWealth``. If
        absent, the original decision's expectation is used as a neutral
        baseline, making the result explicit rather than inventing data.
        """
        expected = decision.expected_outcome or {}
        baseline_points = float(expected.get("expectedPoints", 0.0) or 0.0)
        baseline_wealth = float(expected.get("expectedWealth", expected.get("expectedValueGrowth", 0.0)) or 0.0)
        results: List[Counterfactual] = []
        for alternative in alternatives:
            points = float(alternative.get("expectedPoints", baseline_points) or 0.0)
            wealth = float(alternative.get("expectedWealth", baseline_wealth) or 0.0)
            result = Counterfactual(
                decision_id=decision.id,
                action_type=str(alternative.get("action", "HOLD")),
                player_id=alternative.get("playerId"),
                result_data={
                    "source": "expected_outcome",
                    "baseline_action": decision.action_type,
                    "expected_points": points,
                    "expected_wealth": wealth,
                },
                points_delta=round(points - baseline_points, 6),
                wealth_delta=round(wealth - baseline_wealth, 6),
            )
            db.add(result)
            results.append(result)
        db.flush()
        return results

    @staticmethod
    def compare(db: Session, decision_id: int) -> Dict[str, Any]:
        decision = db.query(Decision).filter_by(id=decision_id).first()
        if not decision:
            raise ValueError(f"Decision {decision_id} not found")
        alternatives = db.query(Counterfactual).filter_by(decision_id=decision_id).order_by(
            Counterfactual.points_delta.desc(), Counterfactual.id
        ).all()
        return {
            "decision_id": decision_id,
            "chosen_action": decision.action_type,
            "alternatives": [
                {
                    "id": item.id,
                    "action": item.action_type,
                    "player_id": item.player_id,
                    "points_delta": item.points_delta,
                    "wealth_delta": item.wealth_delta,
                    "result": item.result_data,
                }
                for item in alternatives
            ],
        }
