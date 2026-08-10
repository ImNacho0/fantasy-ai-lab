"""Historical knowledge storage and deterministic similarity search.

This module intentionally uses plain numeric features instead of an LLM or an
external vector database. It is useful in tests, GitHub Actions, and local
SQLite, and can later be replaced by a vector index without changing callers.
"""
from __future__ import annotations

from math import sqrt
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from fantasy_ai_lab.database.models import Decision, KnowledgeCase, Outcome, Reward, Situation


def _flatten(value: Any, prefix: str = "") -> Dict[str, float]:
    """Flatten JSON-like state into deterministic numeric features."""
    result: Dict[str, float] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(value[key], child))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        result[prefix] = float(value)
    elif isinstance(value, bool):
        result[prefix] = 1.0 if value else 0.0
    return result


def feature_vector(features: Dict[str, Any]) -> Dict[str, float]:
    return _flatten(features)


def _distance(left: Dict[str, float], right: Dict[str, float]) -> float:
    keys = set(left) | set(right)
    return sqrt(sum((left.get(key, 0.0) - right.get(key, 0.0)) ** 2 for key in keys))


class KnowledgeService:
    """Persist cases and return similar historical decisions with sample sizes."""

    @staticmethod
    def record_case(
        db: Session,
        situation: Situation,
        decision: Decision,
        features: Optional[Dict[str, Any]] = None,
    ) -> KnowledgeCase:
        vector = feature_vector(features or situation.state_features or {})
        case = KnowledgeCase(
            situation_id=situation.id,
            decision_id=decision.id,
            feature_vector=vector,
        )
        db.add(case)
        db.flush()
        return case

    @staticmethod
    def backfill_cases(db: Session, league_id: Optional[int] = None) -> int:
        """Create missing cases for persisted situations and their decisions."""
        query = db.query(Situation)
        if league_id is not None:
            query = query.filter(Situation.league_id == league_id)
        created = 0
        for situation in query.order_by(Situation.id).all():
            decisions = db.query(Decision).filter(
                Decision.situation_id == situation.id
            ).order_by(Decision.id).all()
            for decision in decisions:
                exists = db.query(KnowledgeCase).filter_by(decision_id=decision.id).first()
                if not exists:
                    KnowledgeService.record_case(db, situation, decision)
                    created += 1
        db.commit()
        return created

    @staticmethod
    def find_similar(
        db: Session,
        features: Dict[str, Any],
        limit: int = 10,
        action_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query_vector = feature_vector(features)
        query = db.query(KnowledgeCase).join(Situation).join(Decision)
        if action_type:
            query = query.filter(Decision.action_type == action_type)

        ranked = []
        for case in query.all():
            distance = _distance(query_vector, case.feature_vector or {})
            decision = db.query(Decision).filter_by(id=case.decision_id).first()
            outcome = db.query(Outcome).filter_by(decision_id=case.decision_id).first()
            reward = db.query(Reward).filter_by(decision_id=case.decision_id).order_by(Reward.id).first()
            ranked.append({
                "case_id": case.id,
                "decision_id": case.decision_id,
                "action": decision.action_type if decision else None,
                "distance": round(distance, 6),
                "points_gained": outcome.points_gained if outcome else 0.0,
                "wealth_gained": outcome.wealth_gained if outcome else 0.0,
                "reward": reward.total_reward if reward else 0.0,
            })
        ranked.sort(key=lambda item: (item["distance"], item["case_id"]))
        return ranked[: max(0, limit)]

    @staticmethod
    def recommend(db: Session, features: Dict[str, Any], limit: int = 10) -> Dict[str, Any]:
        cases = KnowledgeService.find_similar(db, features, limit=limit)
        by_action: Dict[str, List[Dict[str, Any]]] = {}
        for case in cases:
            by_action.setdefault(case["action"] or "UNKNOWN", []).append(case)
        ranking = []
        for action, action_cases in by_action.items():
            rewards = [float(case["reward"]) for case in action_cases]
            ranking.append({
                "action": action,
                "sample_size": len(action_cases),
                "average_reward": round(sum(rewards) / len(rewards), 6),
                "average_points": round(sum(case["points_gained"] for case in action_cases) / len(action_cases), 6),
            })
        ranking.sort(key=lambda item: (-item["average_reward"], -item["sample_size"], item["action"]))
        return {"sample_size": len(cases), "cases": cases, "ranking": ranking}
