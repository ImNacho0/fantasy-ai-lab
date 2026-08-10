import traceback
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from src.fantasy_ai_lab.database.models import SimulationJob, Simulation, League
from src.fantasy_ai_lab.simulator.engine import SimulationEngine

class JobService:
    @staticmethod
    def create_job(db: Session, seed: int, leagues_total: int, matchdays: int, configuration: Optional[Dict[str, Any]] = None) -> SimulationJob:
        """
        Creates a new SimulationJob record.
        """
        job = SimulationJob(
            status="pending",
            seed=seed,
            leagues_total=leagues_total,
            leagues_completed=0,
            matchdays=matchdays,
            current_league_idx=0,
            current_matchday_idx=0,
            configuration=configuration or {}
        )
        db.add(job)
        db.commit()
        return job

    @staticmethod
    def run_job(db: Session, job_id: int) -> SimulationJob:
        """
        Runs or resumes a SimulationJob.
        Saves checkpoints at the end of each league simulation.
        Ensures fully deterministic, reproducible, and idempotent execution.
        """
        job = db.query(SimulationJob).filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"SimulationJob with ID {job_id} not found.")

        if job.status in ["completed", "failed"]:
            return job # Already finished, don't execute to ensure idempotency!

        job.status = "running"
        db.commit()

        try:
            # 1. Create or get the parent Simulation record
            simulation = db.query(Simulation).filter_by(job_id=job.id).first()
            if not simulation:
                simulation = Simulation(
                    job_id=job.id,
                    name=f"Simulation from Job {job.id}"
                )
                db.add(simulation)
                db.commit()

            # Initialize engine
            engine = SimulationEngine(seed=job.seed)

            # Determine start index based on completed leagues
            start_league_idx = job.leagues_completed

            # Extreme scenario configuration can be extracted from the config
            # e.g., config = {"extreme_scenarios": {3: "STAR_PLAYER_INJURED"}}
            extreme_scenarios_raw = job.configuration.get("extreme_scenarios", {})
            # Convert keys to integers for matchday mapping
            extreme_scenarios = {int(k): v for k, v in extreme_scenarios_raw.items()}

            for i in range(start_league_idx, job.leagues_total):
                job.current_league_idx = i
                db.commit()

                # Generate deterministic sub-seed for this league
                league_seed = job.seed + i

                # Check if this league has already been created (for idempotency on resume)
                league_name = f"League {i+1} - Job {job.id}"
                league = db.query(League).filter_by(simulation_id=simulation.id, name=league_name).first()

                if not league:
                    # Create new league
                    league = engine.create_league(
                        db=db,
                        name=league_name,
                        seed=league_seed,
                        num_managers=4,
                        simulation_id=simulation.id
                    )
                    db.commit()

                # Simulate remaining matchdays
                engine.run_league_simulation(
                    db=db,
                    league_id=league.id,
                    matchdays_total=job.matchdays,
                    extreme_scenarios=extreme_scenarios
                )

                # Persist checkpoint
                job.leagues_completed = i + 1
                db.commit()

            # Set status to completed
            job.status = "completed"
            db.commit()

        except Exception as e:
            # Save partial state on failure
            job.status = "partial"
            job.error_message = f"{str(e)}\n{traceback.format_exc()}"
            db.commit()
            raise e

        return job
