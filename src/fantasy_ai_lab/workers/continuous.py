"""Bounded continuous-training orchestration.

This is intentionally one cycle per invocation. Schedulers can call it again,
while each cycle remains resumable and safe for GitHub Actions/Render limits.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from fantasy_ai_lab.database.models import Evaluation, SimulationJob
from fantasy_ai_lab.simulator.jobs import JobService
from fantasy_ai_lab.training.evaluation import EvaluationService
from fantasy_ai_lab.workers.runner import SimulationWorker


class ContinuousTrainingWorker:
    @staticmethod
    def run_cycle(
        db: Session,
        seed: int,
        leagues_total: int = 1,
        matchdays: int = 1,
        batch_size: int = 1,
        strategy_name: Optional[str] = None,
        strategy_version: str = "v1.0",
        configuration: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        job = JobService.create_job(db, seed, leagues_total, matchdays, configuration)
        result = SimulationWorker.run_batch(db, job.id, max_leagues=batch_size)
        evaluation: Optional[Evaluation] = None
        if strategy_name:
            evaluation = EvaluationService.evaluate_strategy(
                db, strategy_name, strategy_version, "training"
            )
        return {
            "job_id": result.id,
            "job_status": result.status,
            "leagues_completed": result.leagues_completed,
            "leagues_total": result.leagues_total,
            "evaluation_id": evaluation.id if evaluation else None,
        }
