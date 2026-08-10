"""Bounded worker helpers for GitHub Actions and future queue consumers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from fantasy_ai_lab.database.models import SimulationJob
from fantasy_ai_lab.simulator.jobs import JobService


class SimulationWorker:
    """Run at most a bounded number of league units per invocation."""

    @staticmethod
    def run_batch(db: Session, job_id: int, max_leagues: Optional[int] = None) -> SimulationJob:
        job = db.query(SimulationJob).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"SimulationJob with ID {job_id} not found")
        if job.status in ("completed", "failed", "cancelled"):
            return job

        # JobService already resumes at leagues_completed. The worker limit is
        # enforced by temporarily bounding the job's requested total.
        original_total = job.leagues_total
        if max_leagues is not None:
            if max_leagues < 1:
                raise ValueError("max_leagues must be positive")
            job.leagues_total = min(original_total, job.leagues_completed + max_leagues)
            db.commit()
        try:
            result = JobService.run_job(db, job_id)
            result.checkpoint = {
                "completed_units": result.leagues_completed,
                "next_league_index": result.leagues_completed,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if result.leagues_completed < original_total:
                result.leagues_total = original_total
                result.status = "partial"
            db.commit()
            return result
        finally:
            if job.leagues_total != original_total and job.status != "partial":
                job.leagues_total = original_total
                db.commit()
