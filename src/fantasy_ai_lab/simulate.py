import argparse
import sys
import traceback
from src.fantasy_ai_lab.database.connection import SessionLocal
from src.fantasy_ai_lab.simulator.jobs import JobService

def main():
    parser = argparse.ArgumentParser(
        description="Fantasy AI Lab — Autonomous simulation and experiment engine"
    )
    parser.add_argument(
        "--leagues",
        type=int,
        default=5,
        help="Total number of leagues to simulate (default: 5)"
    )
    parser.add_argument(
        "--matchdays",
        type=int,
        default=5,
        help="Number of matchdays per league (default: 5)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=123,
        help="Random seed for deterministic/reproducible generation (default: 123)"
    )
    parser.add_argument(
        "--extreme-matchday",
        type=int,
        default=None,
        help="Optionally inject an extreme scenario on a specific matchday (e.g. 3)"
    )
    parser.add_argument(
        "--extreme-scenario",
        type=str,
        default="STAR_PLAYER_INJURED",
        help="Scenario to inject: STAR_PLAYER_INJURED, MARKET_CRASH (default: STAR_PLAYER_INJURED)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("🧪 FANTASY AI LAB — SIMULATOR START")
    print(f"Leagues to simulate: {args.leagues}")
    print(f"Matchdays per league: {args.matchdays}")
    print(f"Master Seed: {args.seed}")

    config = {}
    if args.extreme_matchday is not None:
        config["extreme_scenarios"] = {
            str(args.extreme_matchday): args.extreme_scenario
        }
        print(f"Extreme Scenario Config: {args.extreme_scenario} on matchday {args.extreme_matchday}")
    print("=" * 60)

    db = SessionLocal()
    try:
        # 1. Create Job
        print("[1/3] Creating Simulation Job in Database...")
        job = JobService.create_job(
            db=db,
            seed=args.seed,
            leagues_total=args.leagues,
            matchdays=args.matchdays,
            configuration=config
        )
        print(f"      Success: Created Simulation Job ID = {job.id} (Status: {job.status})")

        # 2. Run Job
        print("\n[2/3] Running Simulation Job...")
        job = JobService.run_job(db=db, job_id=job.id)

        # 3. Finalize
        print("\n[3/3] Simulation completed successfully!")
        print(f"      Job ID: {job.id}")
        print(f"      Final Status: {job.status}")
        print(f"      Leagues completed: {job.leagues_completed}/{job.leagues_total}")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error executing simulation: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
