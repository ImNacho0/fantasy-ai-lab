from fastapi.testclient import TestClient

from fantasy_ai_lab.api.main import app
from fantasy_ai_lab.simulator.jobs import JobService

client = TestClient(app)


def test_phase7_job_cancellation_persists_checkpoint(db_session):
    job = JobService.create_job(db_session, seed=1700, leagues_total=3, matchdays=1)
    job.leagues_completed = 1
    db_session.commit()
    cancelled = JobService.cancel_job(db_session, job.id)
    assert cancelled.status == "cancelled"
    assert cancelled.checkpoint["next_league_index"] == 1
    assert JobService.cancel_job(db_session, job.id).status == "cancelled"


def test_phase7_dashboard_overview_and_controls_are_available():
    overview = client.get("/api/v1/dashboard/overview")
    assert overview.status_code == 200
    assert "metrics" in overview.json()
    assert "jobs" in overview.json()

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Simulation queue" in dashboard.text
    assert "run-batch" in dashboard.text


def test_phase7_training_cycle_is_bounded():
    response = client.post("/api/v1/training/cycle", json={
        "seed": 1701,
        "leagues_total": 1,
        "matchdays": 1,
        "batch_size": 1,
    })
    assert response.status_code == 201
    data = response.json()
    assert data["leagues_completed"] == 1
    assert data["job_status"] == "completed"
