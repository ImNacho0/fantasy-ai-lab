"""Evaluation primitives for training, validation, and holdout comparison."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, Optional

from sqlalchemy.orm import Session

from fantasy_ai_lab.database.models import Decision, Evaluation, Manager, Reward


class EvaluationService:
    PROFILES = ("points-focused", "wealth-focused", "balanced", "risk-adjusted")

    @staticmethod
    def evaluate_strategy(
        db: Session,
        strategy_name: str,
        strategy_version: str = "v1.0",
        dataset_name: str = "all",
        league_id: Optional[int] = None,
    ) -> Evaluation:
        query = db.query(Reward, Decision, Manager).join(Decision, Reward.decision_id == Decision.id).join(
            Manager, Decision.manager_id == Manager.id
        ).filter(
            Manager.strategy_type == strategy_name,
            Decision.strategy_version == strategy_version,
        )
        if league_id is not None:
            query = query.filter(Decision.league_id == league_id)

        rewards = query.all()
        by_profile = defaultdict(list)
        for reward, _decision, _manager in rewards:
            by_profile[reward.profile_name].append(float(reward.total_reward or 0.0))

        sample_size = len({decision.id for _reward, decision, _manager in rewards})
        metrics = {
            "sample_size": sample_size,
            "reward_count": len(rewards),
            "profiles": {
                profile: {
                    "sample_size": len(values),
                    "mean": round(sum(values) / len(values), 6) if values else 0.0,
                    "min": round(min(values), 6) if values else 0.0,
                    "max": round(max(values), 6) if values else 0.0,
                }
                for profile, values in sorted(by_profile.items())
            },
        }
        evaluation = Evaluation(
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            dataset_name=dataset_name,
            sample_size=sample_size,
            metrics=metrics,
            status="candidate",
        )
        db.add(evaluation)
        db.commit()
        return evaluation

    @staticmethod
    def validate_candidate(
        db: Session,
        candidate: Evaluation,
        minimum_sample_size: int = 1,
        baseline_mean: Optional[float] = None,
    ) -> Evaluation:
        balanced = candidate.metrics.get("profiles", {}).get("balanced", {})
        mean = float(balanced.get("mean", 0.0))
        candidate.status = "validated" if (
            candidate.sample_size >= minimum_sample_size
            and (baseline_mean is None or mean > baseline_mean)
        ) else "rejected"
        db.commit()
        return candidate
