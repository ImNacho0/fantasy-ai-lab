"""Evaluation, backtesting, validation, and controlled strategy promotion."""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, stdev
from typing import Dict, Iterable, Optional

from sqlalchemy.orm import Session

from fantasy_ai_lab.database.models import Decision, Evaluation, Manager, Reward, StrategyVersion


class EvaluationService:
    PROFILES = ("points-focused", "wealth-focused", "balanced", "risk-adjusted")

    @staticmethod
    def _metrics(values_by_profile: Dict[str, list[float]], sample_size: int) -> dict:
        profiles: dict[str, dict[str, float | int]] = {}
        for profile, values in sorted(values_by_profile.items()):
            count = len(values)
            average = mean(values) if values else 0.0
            deviation = stdev(values) if count > 1 else 0.0
            standard_error = deviation / (count ** 0.5) if count > 1 else 0.0
            profiles[profile] = {
                "sample_size": count,
                "mean": round(average, 6),
                "min": round(min(values), 6) if values else 0.0,
                "max": round(max(values), 6) if values else 0.0,
                "stdev": round(deviation, 6),
                "standard_error": round(standard_error, 6),
                "confidence_95": [
                    round(average - 1.96 * standard_error, 6),
                    round(average + 1.96 * standard_error, 6),
                ],
            }
        return {
            "sample_size": sample_size,
            "reward_count": sum(len(values) for values in values_by_profile.values()),
            "profiles": profiles,
        }

    @staticmethod
    def evaluate_strategy(
        db: Session,
        strategy_name: str,
        strategy_version: str = "v1.0",
        dataset_name: str = "all",
        league_id: Optional[int] = None,
        status: str = "candidate",
    ) -> Evaluation:
        query = (
            db.query(Reward, Decision, Manager)
            .join(Decision, Reward.decision_id == Decision.id)
            .join(Manager, Decision.manager_id == Manager.id)
            .filter(
                Manager.strategy_type == strategy_name,
                Decision.strategy_version == strategy_version,
            )
        )
        if league_id is not None:
            query = query.filter(Decision.league_id == league_id)

        rewards = query.all()
        by_profile: dict[str, list[float]] = defaultdict(list)
        decision_ids: set[int] = set()
        for reward, decision, _manager in rewards:
            decision_ids.add(decision.id)
            by_profile[reward.profile_name].append(float(reward.total_reward or 0.0))

        sample_size = len(decision_ids)
        evaluation = Evaluation(
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            dataset_name=dataset_name,
            sample_size=sample_size,
            metrics=EvaluationService._metrics(by_profile, sample_size),
            status=status,
        )
        db.add(evaluation)
        db.commit()
        return evaluation

    @staticmethod
    def backtest_strategy(
        db: Session,
        strategy_name: str,
        strategy_version: str = "v1.0",
        dataset_name: str = "test",
        league_id: Optional[int] = None,
    ) -> Evaluation:
        """Evaluate a fixed strategy version against a named holdout slice.

        The simulator remains responsible for producing the slice. This method
        never mutates a strategy or promotes a candidate.
        """
        return EvaluationService.evaluate_strategy(
            db, strategy_name, strategy_version, dataset_name, league_id, status="backtested"
        )

    @staticmethod
    def validate_candidate(
        db: Session,
        candidate: Evaluation,
        minimum_sample_size: int = 1,
        baseline_mean: Optional[float] = None,
    ) -> Evaluation:
        balanced = candidate.metrics.get("profiles", {}).get("balanced", {})
        mean_reward = float(balanced.get("mean", 0.0))
        lower_bound = float((balanced.get("confidence_95") or [mean_reward])[0])
        candidate.status = "validated" if (
            candidate.sample_size >= minimum_sample_size
            and (baseline_mean is None or lower_bound > baseline_mean)
        ) else "rejected"
        db.commit()
        return candidate

    @staticmethod
    def register_candidate(
        db: Session,
        strategy_name: str,
        version: str,
        parameters: Optional[dict] = None,
        parent_version: Optional[str] = None,
    ) -> StrategyVersion:
        existing = db.query(StrategyVersion).filter_by(
            strategy_name=strategy_name, version=version
        ).first()
        if existing:
            return existing
        candidate = StrategyVersion(
            strategy_name=strategy_name,
            version=version,
            parameters=parameters or {},
            is_active=False,
            lifecycle_status="candidate",
            parent_version=parent_version,
        )
        db.add(candidate)
        db.commit()
        return candidate

    @staticmethod
    def promote_candidate(db: Session, evaluation_id: int) -> StrategyVersion:
        """Promote only a validated evaluation, atomically within this session."""
        evaluation = db.query(Evaluation).filter_by(id=evaluation_id).first()
        if not evaluation:
            raise ValueError("Evaluation not found")
        if evaluation.status != "validated":
            raise ValueError("Only validated evaluations can be promoted")

        version = db.query(StrategyVersion).filter_by(
            strategy_name=evaluation.strategy_name,
            version=evaluation.strategy_version,
        ).first()
        if not version:
            version = EvaluationService.register_candidate(
                db, evaluation.strategy_name, evaluation.strategy_version
            )
        db.query(StrategyVersion).filter(
            StrategyVersion.strategy_name == evaluation.strategy_name,
            StrategyVersion.id != version.id,
        ).update({"is_active": False, "lifecycle_status": "archived"}, synchronize_session=False)
        version.is_active = True
        version.lifecycle_status = "promoted"
        from fantasy_ai_lab.database.models import get_utc_now
        version.promoted_at = get_utc_now()
        evaluation.status = "promoted"
        db.commit()
        return version
