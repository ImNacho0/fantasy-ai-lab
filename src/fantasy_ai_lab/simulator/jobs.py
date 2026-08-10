import hashlib
import traceback
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from fantasy_ai_lab.database.models import SimulationJob, Simulation, League, get_utc_now
from fantasy_ai_lab.simulator.engine import SimulationEngine


class JobService:
    @staticmethod
    def create_job(
        db: Session,
        seed: int,
        leagues_total: int,
        matchdays: int,
        configuration: Optional[Dict[str, Any]] = None,
    ) -> SimulationJob:
        """Create a pending, durable simulation job."""
        job = SimulationJob(
            status="pending",
            seed=seed,
            leagues_total=leagues_total,
            leagues_completed=0,
            matchdays=matchdays,
            current_league_idx=0,
            current_matchday_idx=0,
            configuration=configuration or {},
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def claim_dispatch(db: Session, job_id: int, retry: bool = False) -> Optional[SimulationJob]:
        """Atomically claim one job for workflow dispatch.

        PostgreSQL row locking prevents two Render requests from dispatching the
        same job. The JSON marker is also useful on SQLite and survives process
        restarts. A retry is only possible through an explicit API call.
        """
        job = db.query(SimulationJob).filter_by(id=job_id).with_for_update().first()
        if not job:
            raise ValueError(f"SimulationJob with ID {job_id} not found")
        if job.status == "completed" or job.status == "running":
            return None
        config = dict(job.configuration or {})
        dispatch = dict(config.get("github_dispatch") or {})
        if not retry and dispatch.get("status") in {"requested", "accepted"}:
            return None
        if not retry and job.status == "failed":
            return None
        if retry:
            job.status = "pending"
            job.error_message = None
            job.completed_at = None
        config["github_dispatch"] = {
            "status": "requested",
            "requested_at": get_utc_now().isoformat(),
        }
        job.configuration = config
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def set_dispatch_state(
        db: Session,
        job_id: int,
        status: str,
        error_message: Optional[str] = None,
    ) -> SimulationJob:
        """Persist dispatch outcome without storing credentials or raw logs."""
        job = db.query(SimulationJob).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"SimulationJob with ID {job_id} not found")
        config = dict(job.configuration or {})
        config["github_dispatch"] = {
            "status": status,
            "updated_at": get_utc_now().isoformat(),
        }
        job.configuration = config
        if status == "failed":
            job.status = "failed"
            job.error_message = error_message or "GitHub workflow dispatch failed"
            job.completed_at = get_utc_now()
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def mark_failed(db: Session, job_id: int, error_message: str) -> SimulationJob:
        """Mark a worker failure with a bounded diagnostic message."""
        job = db.query(SimulationJob).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"SimulationJob with ID {job_id} not found")
        job.status = "failed"
        job.error_message = error_message[:4000]
        job.completed_at = get_utc_now()
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def run_job(db: Session, job_id: int) -> SimulationJob:
        """Run or resume a job, persisting a checkpoint after each league."""
        job = db.query(SimulationJob).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"SimulationJob with ID {job_id} not found.")
        if job.status in ["completed", "failed", "cancelled"]:
            return job

        job.status = "running"
        job.started_at = job.started_at or get_utc_now()
        db.commit()

        try:
            simulation = db.query(Simulation).filter_by(job_id=job.id).first()
            if not simulation:
                simulation = Simulation(job_id=job.id, name=f"Simulation from Job {job.id}")
                db.add(simulation)
                db.commit()

            engine = SimulationEngine(seed=job.seed)
            start_league_idx = job.leagues_completed
            extreme_scenarios_raw = (job.configuration or {}).get("extreme_scenarios", {})
            extreme_scenarios = {int(k): v for k, v in extreme_scenarios_raw.items()}

            for i in range(start_league_idx, job.leagues_total):
                db.refresh(job)
                if job.status == "cancelled":
                    break
                job.current_league_idx = i
                db.commit()

                digest = hashlib.sha256(f"{job.seed}:league:{i}".encode("utf-8")).digest()
                league_seed = int.from_bytes(digest[:8], "big") % 2_147_483_647
                league_name = f"League {i+1} - Job {job.id}"
                league = db.query(League).filter_by(
                    simulation_id=simulation.id, name=league_name
                ).first()
                if not league:
                    league = engine.create_league(
                        db=db,
                        name=league_name,
                        seed=league_seed,
                        num_managers=4,
                        simulation_id=simulation.id,
                    )
                    db.commit()

                engine.run_league_simulation(
                    db=db,
                    league_id=league.id,
                    matchdays_total=job.matchdays,
                    extreme_scenarios=extreme_scenarios,
                )

                job.leagues_completed = i + 1
                job.current_league_idx = i + 1
                job.current_matchday_idx = job.matchdays
                job.checkpoint = {
                    "completed_units": job.leagues_completed,
                    "completed_leagues": [
                        {
                            "index": n,
                            "seed": int.from_bytes(
                                hashlib.sha256(f"{job.seed}:league:{n}".encode("utf-8")).digest()[:8],
                                "big",
                            ) % 2_147_483_647,
                        }
                        for n in range(job.leagues_completed)
                    ],
                    "next_league_index": job.leagues_completed,
                }
                db.commit()

            if job.status != "cancelled":
                job.status = "completed"
                job.completed_at = get_utc_now()
            db.commit()
        except Exception as exc:
            job.status = "failed"
            job.error_message = f"{str(exc)}\n{traceback.format_exc()}"[:4000]
            job.completed_at = get_utc_now()
            db.commit()
            raise
        return job

    @staticmethod
    def cancel_job(db: Session, job_id: int) -> SimulationJob:
        job = db.query(SimulationJob).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"SimulationJob with ID {job_id} not found.")
        if job.status not in ("completed", "failed", "cancelled"):
            job.status = "cancelled"
            job.checkpoint = {
                **(job.checkpoint or {}),
                "cancelled_at_units": job.leagues_completed,
                "next_league_index": job.leagues_completed,
            }
            db.commit()
        return job
