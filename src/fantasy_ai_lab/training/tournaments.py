"""Bounded strategy tournaments; no automatic production promotion."""
from __future__ import annotations

from typing import Dict, Iterable, List

from sqlalchemy.orm import Session

from fantasy_ai_lab.database.models import Evaluation, Tournament
from fantasy_ai_lab.training.evaluation import EvaluationService


class TournamentService:
    @staticmethod
    def run(
        db: Session,
        name: str,
        strategies: Iterable[Dict[str, str]],
        dataset_name: str = "all",
    ) -> Tournament:
        strategy_list = list(strategies)
        rankings: List[Dict[str, object]] = []
        for item in strategy_list:
            strategy_name = item["name"]
            version = item.get("version", "v1.0")
            evaluation = EvaluationService.evaluate_strategy(
                db, strategy_name, version, dataset_name
            )
            balanced = evaluation.metrics.get("profiles", {}).get("balanced", {})
            rankings.append({
                "strategy": strategy_name,
                "version": version,
                "sample_size": evaluation.sample_size,
                "mean_reward": balanced.get("mean", 0.0),
                "evaluation_id": evaluation.id,
            })
        rankings.sort(key=lambda row: (-float(row["mean_reward"]), -int(row["sample_size"]), str(row["strategy"])))
        for position, row in enumerate(rankings, 1):
            row["rank"] = position
        tournament = Tournament(
            name=name,
            configuration={"dataset": dataset_name, "strategies": strategy_list},
            rankings=rankings,
            status="completed",
        )
        db.add(tournament)
        db.commit()
        return tournament
