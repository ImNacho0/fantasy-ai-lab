from src.fantasy_ai_lab.simulator.jobs import JobService
from src.fantasy_ai_lab.database.models import SimulationJob, League, Roster

def test_job_execution_and_checkpoints(db_session):
    # Create a job for 2 leagues, 2 matchdays
    job = JobService.create_job(db_session, seed=777, leagues_total=2, matchdays=2)
    assert job.status == "pending"
    assert job.leagues_completed == 0

    # Run job
    job = JobService.run_job(db_session, job.id)
    assert job.status == "completed"
    assert job.leagues_completed == 2

    # Check that leagues were indeed simulated
    leagues = db_session.query(League).all()
    assert len(leagues) == 2
    for l in leagues:
        assert l.matchday == 2
        assert l.status == "completed"

def test_job_idempotency_on_rerun(db_session):
    job = JobService.create_job(db_session, seed=888, leagues_total=1, matchdays=2)

    # Run once
    job = JobService.run_job(db_session, job.id)
    assert job.status == "completed"

    roster_count_before = db_session.query(Roster).count()

    # Run again (re-run of completed job)
    job = JobService.run_job(db_session, job.id)
    assert job.status == "completed"

    # Roster count should not double/change!
    roster_count_after = db_session.query(Roster).count()
    assert roster_count_before == roster_count_after
