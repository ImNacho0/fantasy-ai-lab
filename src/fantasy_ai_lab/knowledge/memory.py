"""Persistent historical memory and deterministic situation similarity search.

The Phase 4 store deliberately stays provider-free: features are flattened into
JSON, ranked in Python, and aggregated from persisted outcomes. This keeps the
same behavior on SQLite, PostgreSQL, and future vector-index implementations.
"""
from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from fantasy_ai_lab.database.models import Decision, KnowledgeCase, Manager, Outcome, Reward, Situation


def _flatten(value: Any, prefix: str = "") -> Dict[str, float]:
    """Flatten JSON-like state into deterministic numeric and categorical features."""
    result: Dict[str, float] = {}
    if isinstance(value, dict):
        for key in sorted(value, key=str):
            child = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(value[key], child))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        result[prefix] = float(value)
    elif isinstance(value, bool):
        result[prefix] = 1.0 if value else 0.0
    elif value is not None and prefix:
        # One-hot categorical values are deterministic and do not require an
        # external encoder. Matching categories contribute zero distance;
        # different categories contribute one distance.
        result[f"{prefix}={value}"] = 1.0
    return result


def feature_vector(features: Dict[str, Any]) -> Dict[str, float]:
    return _flatten(features or {})


def _feature_scales(vectors: List[Dict[str, float]], query: Dict[str, float]) -> Dict[str, float]:
    """Return per-feature ranges so currency does not dominate other fields."""
    keys = set(query)
    for vector in vectors:
        keys.update(vector)
    scales: Dict[str, float] = {}
    for key in keys:
        values = [vector.get(key, 0.0) for vector in vectors]
        values.append(query.get(key, 0.0))
        scales[key] = max(max(values) - min(values), 1.0)
    return scales


def _distance(left: Dict[str, float], right: Dict[str, float], scales: Optional[Dict[str, float]] = None) -> float:
    keys = set(left) | set(right)
    return sqrt(sum(
        ((left.get(key, 0.0) - right.get(key, 0.0)) / (scales or {}).get(key, 1.0)) ** 2
        for key in keys
    ))


def _reward_for_decision(db: Session, decision_id: int) -> Optional[Reward]:
    return db.query(Reward).filter_by(decision_id=decision_id, profile_name="balanced").order_by(Reward.id).first()


def _outcome_for_decision(db: Session, decision_id: int) -> Optional[Outcome]:
    return db.query(Outcome).filter_by(decision_id=decision_id).order_by(Outcome.id).first()


class KnowledgeService:
    """Persist cases and return evidence-backed historical recommendations."""

    @staticmethod
    def record_case(
        db: Session,
        situation: Situation,
        decision: Decision,
        features: Optional[Dict[str, Any]] = None,
        dataset_name: str = "simulation",
    ) -> KnowledgeCase:
        """Create or refresh one case; repeated retries never duplicate it."""
        vector = feature_vector(features or situation.state_features or {})
        manager = decision.manager or db.query(Manager).filter_by(id=decision.manager_id).first()
        case = db.query(KnowledgeCase).filter_by(
            situation_id=situation.id,
            decision_id=decision.id,
        ).first()
        if case is None:
            case = KnowledgeCase(
                situation_id=situation.id,
                decision_id=decision.id,
                feature_vector=vector,
                dataset_name=dataset_name,
                strategy_name=manager.strategy_type if manager else None,
                strategy_version=decision.strategy_version,
            )
            db.add(case)
        else:
            case.feature_vector = vector
            case.dataset_name = dataset_name
            case.strategy_name = manager.strategy_type if manager else case.strategy_name
            case.strategy_version = decision.strategy_version
        db.flush()
        return case

    @staticmethod
    def backfill_cases(db: Session, league_id: Optional[int] = None, dataset_name: str = "simulation") -> int:
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
                exists = db.query(KnowledgeCase).filter_by(
                    situation_id=situation.id,
                    decision_id=decision.id,
                ).first()
                if not exists:
                    KnowledgeService.record_case(db, situation, decision, dataset_name=dataset_name)
                    created += 1
        db.commit()
        return created

    @staticmethod
    def find_similar(
        db: Session,
        features: Dict[str, Any],
        limit: Optional[int] = 10,
        action_type: Optional[str] = None,
        strategy_name: Optional[str] = None,
        strategy_version: Optional[str] = None,
        dataset_name: Optional[str] = None,
        max_distance: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        query_vector = feature_vector(features)
        query = db.query(KnowledgeCase, Decision).join(Decision, KnowledgeCase.decision_id == Decision.id)
        if action_type:
            query = query.filter(Decision.action_type == action_type)
        if strategy_name:
            query = query.filter(KnowledgeCase.strategy_name == strategy_name)
        if strategy_version:
            query = query.filter(KnowledgeCase.strategy_version == strategy_version)
        if dataset_name:
            query = query.filter(KnowledgeCase.dataset_name == dataset_name)

        candidates = query.order_by(KnowledgeCase.id).all()
        scales = _feature_scales([case.feature_vector or {} for case, _ in candidates], query_vector)
        ranked: List[Dict[str, Any]] = []
        for case, decision in candidates:
            distance = _distance(query_vector, case.feature_vector or {}, scales)
            if max_distance is not None and distance > max_distance:
                continue
            outcome = _outcome_for_decision(db, decision.id)
            reward = _reward_for_decision(db, decision.id)
            ranked.append({
                "case_id": case.id,
                "decision_id": decision.id,
                "action": decision.action_type,
                "strategy_name": case.strategy_name,
                "strategy_version": case.strategy_version,
                "distance": round(distance, 6),
                "points_gained": float(outcome.points_gained or 0.0) if outcome else 0.0,
                "wealth_gained": float(outcome.wealth_gained or 0.0) if outcome else 0.0,
                "reward": float(reward.total_reward or 0.0) if reward else 0.0,
                "outcome_available": outcome is not None,
                "decision_confidence": float(decision.confidence or 0.0),
            })
        ranked.sort(key=lambda item: (item["distance"], item["case_id"]))
        return ranked if limit is None else ranked[: max(0, limit)]

    @staticmethod
    def recommend(
        db: Session,
        features: Dict[str, Any],
        limit: int = 10,
        action_type: Optional[str] = None,
        strategy_name: Optional[str] = None,
        strategy_version: Optional[str] = None,
        dataset_name: Optional[str] = None,
        max_distance: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Aggregate every matching case, while returning only the nearest cases."""
        all_cases = KnowledgeService.find_similar(
            db,
            features,
            limit=None,
            action_type=action_type,
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            dataset_name=dataset_name,
            max_distance=max_distance,
        )
        visible_cases = all_cases[: max(0, limit)]
        by_action: Dict[str, List[Dict[str, Any]]] = {}
        for case in all_cases:
            by_action.setdefault(case["action"] or "UNKNOWN", []).append(case)

        ranking = []
        for action, action_cases in by_action.items():
            rewards = [case["reward"] for case in action_cases]
            points = [case["points_gained"] for case in action_cases]
            wealth = [case["wealth_gained"] for case in action_cases]
            observed = [case for case in action_cases if case["outcome_available"]]
            ranking.append({
                "action": action,
                "sample_size": len(action_cases),
                "outcome_sample_size": len(observed),
                "average_reward": round(mean(rewards), 6),
                "average_points": round(mean(points), 6),
                "average_wealth": round(mean(wealth), 6),
                "reward_stddev": round(pstdev(rewards), 6) if len(rewards) > 1 else 0.0,
                "decision_confidence": round(mean(case["decision_confidence"] for case in action_cases), 6),
                "nearest_distance": round(min(case["distance"] for case in action_cases), 6),
            })
        ranking.sort(key=lambda item: (-item["average_reward"], -item["sample_size"], item["action"]))
        return {
            "sample_size": len(all_cases),
            "outcome_sample_size": sum(1 for case in all_cases if case["outcome_available"]),
            "cases": visible_cases,
            "ranking": ranking,
        }
