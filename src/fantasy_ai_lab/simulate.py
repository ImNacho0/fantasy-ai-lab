import argparse
import sys
import traceback

from fantasy_ai_lab.database.connection import SessionLocal
from fantasy_ai_lab.database.models import SimulationJob
from fantasy_ai_lab.simulator.jobs import JobService


def main():
    parser = argparse.ArgumentParser(
        description="Fantasy AI Lab — Autonomous simulation and experiment engine"
    )
    parser.add_argument("--job-id", type=int, default=None, help="Existing SimulationJob to resume")
    parser.add_argument("--leagues", type=int, default=5)
    parser.add_argument("--matchdays", type=int, default=5)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--extreme-matchday", type=int, default=None)
    parser.add_argument("--extreme-scenario", type=str, default="STAR_PLAYER_INJURED")
    args = parser.parse_args()

    print("=" * 60)
    print("🧪 FANTASY AI LAB — SIMULATOR START")
    db = SessionLocal()
    job = None
    try:
        if args.job_id is not None:
            job = db.query(SimulationJob).filter_by(id=args.job_id).first()
            if job is None:
                raise ValueError(f"SimulationJob with ID {args.job_id} not found")
            print(f"Resuming Neon SimulationJob: {job.id} (status: {job.status})")
            print(f"Leagues: {job.leagues_total} | Matchdays: {job.matchdays} | Seed: {job.seed}")
        else:
            config = {}
            if args.extreme_matchday is not None:
                config["extreme_scenarios"] = {
                    str(args.extreme_matchday): args.extreme_scenario
                }
                print(
                    f"Extreme Scenario Config: {args.extreme_scenario} "
                    f"on matchday {args.extreme_matchday}"
                )
            job = JobService.create_job(
                db=db,
                seed=args.seed,
                leagues_total=args.leagues,
                matchdays=args.matchdays,
                configuration=config,
            )
            print(f"Created SimulationJob: {job.id} (status: {job.status})")

        print("Running simulation and persisting checkpoints...")
        job = JobService.run_job(db=db, job_id=job.id)
        print(f"Final status: {job.status}")
        print(f"Leagues completed: {job.leagues_completed}/{job.leagues_total}")
        print("=" * 60)
    except Exception as exc:
        if job is not None:
            try:
                JobService.mark_failed(db, job.id, str(exc))
            except Exception:
                db.rollback()
        print(f"\n❌ Error executing simulation: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
